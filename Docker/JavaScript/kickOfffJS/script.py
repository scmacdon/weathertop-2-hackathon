import boto3
import time
from datetime import datetime, timezone, timedelta
import re

AWS_REGION = "us-east-1"

CLUSTER_NAME = "MyJSWeathertopCluster"
TASK_DEFINITION = "WeathertopJS"
SUBNETS = ['subnet-03c28397a3a7cd314', 'subnet-06dde61595900f899']
SECURITY_GROUPS = ["sg-0e357c99b6b13bf62"]

LOG_GROUP = "WeathertopJSContainerLogs"
LOG_STREAM_PREFIX = "weathertop-js-stream"

S3_BUCKET = "weathertop2"
S3_PREFIX = "javascriptv3-"

ecs = boto3.client("ecs", region_name=AWS_REGION)
logs = boto3.client("logs", region_name=AWS_REGION)
s3 = boto3.client("s3")


def run_fargate_task():
    print(f"🚀 Launching Java task '{TASK_DEFINITION}' in cluster '{CLUSTER_NAME}'...")
    try:
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
        print(f"✅ Started Java task with ARN: {task_arn}")
        return task_arn
    except Exception as e:
        print(f"❌ Exception while starting task: {e}")
        return None


def wait_for_task_running(cluster, task_arn, timeout_seconds=120):
    print(f"⏳ Waiting for task to enter RUNNING state (timeout {timeout_seconds}s)...")
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
        tasks = response.get("tasks", [])
        if not tasks:
            print("❌ Task not found in ECS describe_tasks response.")
            return False
        last_status = tasks[0].get("lastStatus")
        print(f" - Current status: {last_status}")
        if last_status == "RUNNING":
            print("✅ Task is RUNNING.")
            return True
        if last_status == "STOPPED":
            print("❌ Task stopped unexpectedly.")
            return False
        time.sleep(5)
    print("❌ Timeout waiting for task RUNNING state.")
    return False


def wait_for_task_completion(cluster, task_arn, timeout_seconds=3600):
    print(f"⏳ Waiting for task to STOP (timeout {timeout_seconds}s)...")
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
        tasks = response.get("tasks", [])
        if not tasks:
            print("❌ Task not found.")
            return False
        last_status = tasks[0].get("lastStatus")
        print(f" - Current status: {last_status}")
        if last_status == "STOPPED":
            print("✅ Task has stopped.")
            exit_code = tasks[0]["containers"][0].get("exitCode")
            print(f" - Container exit code: {exit_code}")
            return exit_code == 0
        time.sleep(10)
    print("❌ Timeout waiting for task to stop.")
    return False


def get_log_stream_name(task_arn):
    task_id = task_arn.split("/")[-1]
    container_name = "app"  # must match ECS task container name
    return f"{LOG_STREAM_PREFIX}/{container_name}/{task_id}"


def fetch_task_logs(log_group, log_stream, retries=5, delay=5):
    print(f"📥 Fetching logs from CloudWatch Logs group '{log_group}', stream '{log_stream}' ...")
    for attempt in range(retries):
        try:
            resp = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                startFromHead=True,
                limit=10000
            )
            events = resp.get("events", [])
            if events:
                print(f"ℹ️ Retrieved {len(events)} log events.")
                return events
            else:
                print(f"⚠️ No logs yet, retrying ({attempt+1}/{retries})...")
                time.sleep(delay)
        except logs.exceptions.ResourceNotFoundException:
            print(f"⚠️ Log stream not found, retrying ({attempt+1}/{retries})...")
            time.sleep(delay)
    print("❌ Failed to retrieve logs after retries.")
    return []


def print_logs(log_events):
    print("\n===== Task logs start =====")
    for event in log_events:
        ts = datetime.fromtimestamp(event["timestamp"] / 1000).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{ts} | {event['message'].rstrip()}")
    print("===== Task logs end =====\n")


def check_recent_java_file(bucket):
    now = datetime.now(timezone.utc)
    fifteen_minutes_ago = now - timedelta(minutes=15)
    response = s3.list_objects_v2(Bucket=bucket, Prefix='java-')
    found_recent = False
    for obj in response.get('Contents', []):
        key = obj['Key']
        last_modified = obj['LastModified']
        if re.match(r'^java-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}\.json$', key):
            if last_modified >= fifteen_minutes_ago:
                print(f"✅ Found recent Java JSON: {key}, uploaded at {last_modified}")
                found_recent = True
    if not found_recent:
        print("❌ No Java JSON uploaded in the last 15 minutes.")
    return found_recent


if __name__ == "__main__":
    task_arn = run_fargate_task()
    if task_arn:
        if wait_for_task_running(CLUSTER_NAME, task_arn):
            task_success = wait_for_task_completion(CLUSTER_NAME, task_arn)
            log_stream_name = get_log_stream_name(task_arn)
            logs_events = fetch_task_logs(LOG_GROUP, log_stream_name)
            if logs_events:
                print_logs(logs_events)
            else:
                print("⚠️ No logs found for the task.")
            if task_success:
                print("🎯 Task completed successfully. Checking S3 upload...")
                check_recent_java_file(S3_BUCKET)
            else:
                print("❌ Task failed.")
        else:
            print("❌ Task did not reach RUNNING state.")
