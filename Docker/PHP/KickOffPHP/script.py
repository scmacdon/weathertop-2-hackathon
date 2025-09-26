import boto3
import time
import datetime

AWS_REGION = "us-east-1"
CLUSTER_NAME = "MyPHPWeathertopCluster"
TASK_DEFINITION = "WeathertopPhp"
SUBNETS = ['subnet-03c28397a3a7cd314', 'subnet-06dde61595900f899']
SECURITY_GROUPS = ["sg-0e357c99b6b13bf62"]

LOG_GROUP = "WeathertopPhpContainerLogs"
LOG_STREAM_PREFIX = "weathertop-php-stream"
CONTAINER_NAME = "app"

ecs = boto3.client("ecs", region_name=AWS_REGION)
logs = boto3.client("logs", region_name=AWS_REGION)


def run_fargate_task():
    print(f"🚀 Launching task '{TASK_DEFINITION}' in cluster '{CLUSTER_NAME}'...")
    response = ecs.run_task(
        cluster=CLUSTER_NAME,
        launchType="FARGATE",
        taskDefinition=TASK_DEFINITION,
        count=1,
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': SUBNETS,
                'securityGroups': SECURITY_GROUPS,
                'assignPublicIp': 'ENABLED'
            }
        }
    )
    tasks = response.get("tasks", [])
    if not tasks:
        print("❌ Failed to start task:", response.get("failures", []))
        return None
    task_arn = tasks[0]["taskArn"]
    print(f"✅ Started task with ARN: {task_arn}")
    return task_arn


def wait_for_task_stop(cluster, task_arn, timeout_seconds=600):
    """Wait until the task reaches STOPPED state and return exit code."""
    print("⏳ Waiting for task to stop...")
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
        tasks = response.get("tasks", [])
        if not tasks:
            print("❌ Task not found.")
            return None

        status = tasks[0].get("lastStatus")
        print(f" - Status: {status}")

        if status == "STOPPED":
            containers = tasks[0].get("containers", [])
            exit_code = containers[0].get("exitCode") if containers else None
            print(f"✅ Task stopped with exit code: {exit_code}")
            return exit_code

        time.sleep(5)

    print("❌ Timeout waiting for task to stop.")
    return None


def get_latest_log_stream(log_group, log_stream_prefix, timeout_seconds=60):
    """Wait for the actual CloudWatch log stream to appear and return its name."""
    print(f"⏳ Waiting for log stream with prefix '{log_stream_prefix}'...")
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            streams = logs.describe_log_streams(
                logGroupName=log_group,
                logStreamNamePrefix=log_stream_prefix,
                limit=50
            ).get("logStreams", [])

            if streams:
                latest_stream = max(
                    streams,
                    key=lambda s: s.get("lastEventTimestamp", 0)
                )["logStreamName"]
                print(f"✅ Found log stream: {latest_stream}")
                return latest_stream

        except logs.exceptions.ResourceNotFoundException:
            pass
        except Exception as e:
            print(f"❌ Exception while listing log streams: {e}")

        time.sleep(2)

    print(f"⚠️ No log stream found with prefix '{log_stream_prefix}' after {timeout_seconds}s.")
    return None


def fetch_task_logs(log_group, log_stream, start_time=None):
    """Fetch all available log events from CloudWatch Logs."""
    print(f"📥 Fetching logs from '{log_group}/{log_stream}'...")
    next_token = None
    all_events = []
    start_time_ms = int(start_time.timestamp() * 1000) if start_time else None

    while True:
        kwargs = {
            "logGroupName": log_group,
            "logStreamName": log_stream,
            "startFromHead": True
        }
        if start_time_ms:
            kwargs["startTime"] = start_time_ms
        if next_token:
            kwargs["nextToken"] = next_token

        try:
            resp = logs.get_log_events(**kwargs)
            events = resp.get("events", [])
            all_events.extend(events)

            new_token = resp.get("nextForwardToken")
            if new_token == next_token:
                break
            next_token = new_token

            if not events:
                time.sleep(2)
                continue

        except logs.exceptions.ResourceNotFoundException:
            print("⚠️ Log stream not found yet. Retrying...")
            time.sleep(2)
        except Exception as e:
            print(f"❌ Exception fetching logs: {e}")
            break

    print(f"ℹ️ Retrieved {len(all_events)} log events.")
    return all_events


def print_logs(events):
    print("\n===== Task logs =====")
    for e in events:
        ts = datetime.datetime.fromtimestamp(e["timestamp"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{ts} | {e['message'].rstrip()}")
    print("===== End logs =====\n")


if __name__ == "__main__":
    task_arn = run_fargate_task()
    if not task_arn:
        exit(1)

    # Wait until the task has stopped
    exit_code = wait_for_task_stop(CLUSTER_NAME, task_arn)

    # Fetch logs
    log_stream_prefix = f"{LOG_STREAM_PREFIX}/{CONTAINER_NAME}/"
    log_stream_name = get_latest_log_stream(LOG_GROUP, log_stream_prefix)
    if log_stream_name:
        events = fetch_task_logs(LOG_GROUP, log_stream_name)
        if events:
            print_logs(events)
        else:
            print("⚠️ No logs found. Task may not have emitted logs.")
    else:
        print("⚠️ Could not find log stream.")

    if exit_code != 0:
        print(f"❌ Task exited with code {exit_code}")




