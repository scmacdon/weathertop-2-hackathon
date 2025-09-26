import boto3
import datetime

# === CONFIG ===
AWS_ACCOUNT_ID = '814548047983'
AWS_REGION = 'us-east-1'

ECS_CLUSTER_NAME = 'MyKotlinWeathertopCluster'
ECS_TASK_DEF_NAME = 'WeathertopKotlin'
CONTAINER_NAME = 'app'

LOG_GROUP = 'WeathertopKotlinContainerLogs'
LOG_STREAM_PREFIX = 'weathertop-kotlin-stream'

# === CLIENTS ===
ecs_client = boto3.client("ecs", region_name=AWS_REGION)
logs_client = boto3.client("logs", region_name=AWS_REGION)


def get_running_task_arns(cluster_name):
    """Return ARNs of running tasks in the given cluster."""
    response = ecs_client.list_tasks(
        cluster=cluster_name,
        desiredStatus="RUNNING"
    )
    return response.get("taskArns", [])


def get_log_stream_name(task_id):
    """
    Construct the log stream name based on the prefix and ECS conventions.
    Usually format: {prefix}/{container_name}/{ecs_task_id}
    """
    return f"{LOG_STREAM_PREFIX}/{CONTAINER_NAME}/{task_id}"


def get_task_id_from_arn(task_arn):
    """Extract ECS task ID from ARN."""
    return task_arn.split("/")[-1]


def fetch_logs(log_group, log_stream):
    """Fetch and print ALL log events from CloudWatch (with pagination)."""
    try:
        next_token = None
        print(f"\n=== Logs for {log_stream} ===\n")

        while True:
            kwargs = {
                "logGroupName": log_group,
                "logStreamName": log_stream,
                "startFromHead": True,
            }
            if next_token:
                kwargs["nextToken"] = next_token

            response = logs_client.get_log_events(**kwargs)

            for event in response["events"]:
                ts = datetime.datetime.fromtimestamp(event["timestamp"]/1000.0)
                message = event["message"].rstrip()
                print(f"[{ts}] {message}")

            # Pagination check
            new_token = response.get("nextForwardToken")
            if not new_token or new_token == next_token:
                break
            next_token = new_token

    except logs_client.exceptions.ResourceNotFoundException:
        print(f"❌ Log stream {log_stream} not found.")

def main():
    print("🔍 Checking ECS tasks...")
    tasks = get_running_task_arns(ECS_CLUSTER_NAME)

    if not tasks:
        print("⚠️ No running tasks found in cluster.")
        return

    for task_arn in tasks:
        task_id = get_task_id_from_arn(task_arn)
        log_stream_name = get_log_stream_name(task_id)
        fetch_logs(LOG_GROUP, log_stream_name)


if __name__ == "__main__":
    main()
