import boto3
import time

AWS_REGION = "us-east-1"
CLUSTER_NAME = "MyJavaWeathertopCluster"
CONTAINER_NAME = "weathertop-java"
TASK_DEFINITION = "WeathertopJava"
SUBNETS = ['subnet-03c28397a3a7cd314', 'subnet-06dde61595900f899']
SECURITY_GROUPS = ["sg-0e357c99b6b13bf62"]
LOG_GROUP = "WeathertopContainerLogs"  # <-- Updated to match ECS task definition log group exactly
LOG_STREAM_PREFIX = "weathertop-stream"
S3_BUCKET_NAME = "weathertop2"
EXPECTED_JSON_FILE = "results/test-output.json"  # Adjust as needed

ecs = boto3.client("ecs", region_name=AWS_REGION)
logs = boto3.client("logs", region_name=AWS_REGION)
s3 = boto3.client("s3", region_name=AWS_REGION)

# --------------------------
# ✅ Original: Launch ECS Task
# --------------------------
def run_fargate_task():
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
    print(f"🚀 Started task with ARN: {task_arn}")

    if wait_for_task_running(task_arn):
        return wait_for_task_stopped(task_arn)
    return False

# --------------------------
# ✅ Original: Wait for RUNNING
# --------------------------
def wait_for_task_running(task_arn, max_attempts=50, delay=6):
    print("⏳ Waiting for task to enter RUNNING state...")
    for attempt in range(max_attempts):
        response = ecs.describe_tasks(cluster=CLUSTER_NAME, tasks=[task_arn])
        tasks = response.get("tasks", [])
        if tasks:
            status = tasks[0].get("lastStatus")
            print(f"Attempt {attempt+1}: Task status: {status}")
            if status == "RUNNING":
                print("✅ Task is now RUNNING.")
                return True
            elif status == "STOPPED":
                print("⚠️ Task stopped before RUNNING.")
                return False
        time.sleep(delay)
    print("❌ Timed out waiting for task to RUN.")
    return False

# --------------------------
# ✅ New: Wait for STOPPED and Validate
# --------------------------
def wait_for_task_stopped(task_arn, max_attempts=60, delay=10):
    print("⏳ Waiting for task to STOP...")
    task_id = task_arn.split("/")[-1]
    log_stream_name = f"{LOG_STREAM_PREFIX}/{CONTAINER_NAME}/{task_id}"
    for attempt in range(max_attempts):
        response = ecs.describe_tasks(cluster=CLUSTER_NAME, tasks=[task_arn])
        tasks = response.get("tasks", [])
        if tasks:
            task = tasks[0]
            status = task.get("lastStatus")
            print(f"Attempt {attempt+1}: Task status: {status}")
            if status == "STOPPED":
                container = task["containers"][0]
                exit_code = container.get("exitCode")
                reason = container.get("reason", "")
                print(f"🛑 Task stopped with exit code {exit_code}. Reason: {reason}")
                print("📜 Fetching CloudWatch logs...")
                fetch_cloudwatch_logs(log_stream_name)
                print("📦 Checking S3 output...")
                check_s3_upload(EXPECTED_JSON_FILE)
                return exit_code == 0
        time.sleep(delay)
    print("❌ Timed out waiting for task to STOP.")
    return False

# --------------------------
# ✅ New: Fetch CloudWatch Logs
# --------------------------
def fetch_cloudwatch_logs(log_stream_name):
    try:
        response = logs.get_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=log_stream_name,
            startFromHead=True
        )
        events = response.get("events", [])
        if not events:
            print("⚠️ No log events found.")
        for event in events:
            print(f"[LOG] {event['message'].strip()}")
    except logs.exceptions.ResourceNotFoundException:
        print("❌ Log stream not found.")
    except Exception as e:
        print(f"⚠️ Error fetching logs: {str(e)}")

# --------------------------
# ✅ New: Check S3 Upload
# --------------------------
def check_s3_upload(expected_key):
    try:
        s3.head_object(Bucket=S3_BUCKET_NAME, Key=expected_key)
        print(f"✅ File '{expected_key}' found in S3 bucket '{S3_BUCKET_NAME}'.")
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            print(f"❌ File '{expected_key}' not found in S3 bucket '{S3_BUCKET_NAME}'.")
        else:
            print(f"⚠️ Error checking S3: {str(e)}")

# --------------------------
# ✅ Main Entry Point
# --------------------------
if __name__ == "__main__":
    success = run_fargate_task()
    if success:
        print("🎉 ECS Task ran and completed successfully!")
    else:
        print("🚨 ECS Task failed or did not finish cleanly.")



