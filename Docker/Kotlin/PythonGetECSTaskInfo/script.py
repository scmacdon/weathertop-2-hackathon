
import boto3
from datetime import datetime, timezone
import pytz
import time

AWS_REGION = 'us-east-1'
CLUSTER_NAME = 'MyKotlinWeathertopCluster'
TASK_DEFINITION_FAMILY = 'WeathertopKotlin'
LOG_GROUP = 'WeathertopContainerLogs'

ecs = boto3.client('ecs', region_name=AWS_REGION)
logs = boto3.client('logs', region_name=AWS_REGION)

def to_est(dt):
    if not dt:
        return "N/A"
    est = pytz.timezone("US/Eastern")
    return dt.astimezone(est).strftime('%Y-%m-%d %I:%M:%S %p %Z')

def poll_for_task_stop(cluster, task_arn, timeout_secs=120, poll_interval=5):
    print(f"⏳ Polling ECS task until it stops (timeout {timeout_secs}s)...")
    elapsed = 0
    while elapsed < timeout_secs:
        response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
        task = response['tasks'][0]
        if task['lastStatus'] == 'STOPPED':
            print(f"✅ Task has stopped after {elapsed}s.")
            return task
        time.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError("❌ Task did not stop within the timeout window.")

def fetch_tasks_by_status(status_type='STOPPED'):
    return ecs.list_tasks(
        cluster=CLUSTER_NAME,
        family=TASK_DEFINITION_FAMILY,
        desiredStatus=status_type,
        maxResults=10
    )['taskArns']

def describe_task_definition_only(task_def_arn):
    """Show container info from the task definition when no tasks have been run."""
    print("\n📦 Inspecting task definition (no tasks found in cluster)...")
    td = ecs.describe_task_definition(taskDefinition=task_def_arn)['taskDefinition']

    print(f"Task Definition ARN: {td['taskDefinitionArn']}")
    print(f"Family: {td['family']}")
    print(f"Revision: {td['revision']}")
    print(f"Network Mode: {td['networkMode']}")
    print(f"Requires Compatibilities: {td.get('requiresCompatibilities', [])}")
    print(f"CPU: {td.get('cpu', 'N/A')}")
    print(f"Memory: {td.get('memory', 'N/A')}")

    for c in td['containerDefinitions']:
        print(f"\n--- Container: {c['name']} ---")
        print(f"Image: {c['image']}")
        print(f"CPU: {c.get('cpu', 'N/A')}")
        print(f"Memory: {c.get('memory', 'N/A')}")
        print(f"Environment Variables: {[f'{e['name']}={e['value']}' for e in c.get('environment', [])]}")
        if 'logConfiguration' in c:
            log_cfg = c['logConfiguration']
            print(f"Log Driver: {log_cfg.get('logDriver')}")
            print(f"Log Options: {log_cfg.get('options', {})}")

def get_latest_task_info():
    print(f"🔍 Searching ECS tasks for family: {TASK_DEFINITION_FAMILY}")

    # Step 1: Get the latest task definition ARN
    task_defs = ecs.list_task_definitions(familyPrefix=TASK_DEFINITION_FAMILY, sort='DESC')
    if not task_defs['taskDefinitionArns']:
        print("❌ No task definitions found.")
        return

    latest_task_def_arn = task_defs['taskDefinitionArns'][0]
    print(f"✅ Found latest task definition: {latest_task_def_arn}")

    # Step 2: Try STOPPED first, then RUNNING
    task_arns = fetch_tasks_by_status('STOPPED')
    task_status_checked = 'STOPPED'

    if not task_arns:
        print("ℹ️ No STOPPED tasks found. Trying RUNNING tasks instead...")
        task_arns = fetch_tasks_by_status('RUNNING')
        task_status_checked = 'RUNNING'

    if not task_arns:
        print("❌ No ECS tasks found for either STOPPED or RUNNING.")
        describe_task_definition_only(latest_task_def_arn)
        return

    # Step 3: Get task details and sort
    described = ecs.describe_tasks(cluster=CLUSTER_NAME, tasks=task_arns)
    sorted_tasks = sorted(
        described['tasks'],
        key=lambda x: x.get('startedAt', datetime(1970, 1, 1, tzinfo=timezone.utc)),
        reverse=True
    )

    latest_task = sorted_tasks[0]
    container = latest_task['containers'][0] if latest_task['containers'] else {}

    print(f"\n--- 📝 ECS Task Summary ({task_status_checked}) ---")
    print(f"Task ARN        : {latest_task['taskArn']}")
    print(f"Last Status     : {latest_task['lastStatus']}")
    print(f"Desired Status  : {latest_task['desiredStatus']}")
    print(f"Started At      : {to_est(latest_task.get('startedAt'))}")
    print(f"Stopped At      : {to_est(latest_task.get('stoppedAt'))}")
    print(f"Stopped Reason  : {latest_task.get('stoppedReason', 'N/A')}")
    print(f"Container Name  : {container.get('name', 'N/A')}")
    print(f"Container Status: {container.get('lastStatus', 'N/A')}")
    print(f"Exit Code       : {container.get('exitCode', 'N/A')}")
    print(f"Reason (if failed): {container.get('reason', 'N/A')}")

    exit_code = container.get('exitCode')
    if exit_code == 0:
        print("✅ Task exited cleanly.")
    elif exit_code is not None:
        print("❌ Task did not exit cleanly.")
    else:
        print("ℹ️ Task may still be running or container did not report exit code.")

    # Step 4: Print logs
    log_stream_name = container.get('logStreamName')
    if not log_stream_name:
        task_id = latest_task['taskArn'].split("/")[-1]
        container_name = container.get('name', 'unknown')
        log_stream_name = f"{container_name}/{task_id}"

    print(f"\n📚 Attempting to fetch log stream: {log_stream_name}")

    try:
        events = logs.get_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=log_stream_name,
            limit=10,
            startFromHead=False
        )
        if events['events']:
            print("📜 Last log lines:")
            for e in events['events']:
                timestamp = datetime.fromtimestamp(e['timestamp'] / 1000, tz=timezone.utc)
                print(f"[{to_est(timestamp)}] {e['message']}")
        else:
            print("ℹ️ No log events found.")
    except logs.exceptions.ResourceNotFoundException:
        print("⚠️ Log stream not found in CloudWatch.")

if __name__ == '__main__':
    get_latest_task_info()
