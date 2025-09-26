import boto3
from botocore.exceptions import ClientError

ecs_client = boto3.client("ecs", region_name="us-east-1")
events_client = boto3.client("events", region_name="us-east-1")
iam_client = boto3.client("iam", region_name="us-east-1")
logs = boto3.client("logs", region_name="us-east-1")

# ===== JS ECS CONFIG =====
TASK_FAMILY = "WeathertopPhp"
CLUSTER_ARN = "arn:aws:ecs:us-east-1:814548047983:cluster/MyPHPWeathertopCluster"

LOG_GROUP = 'WeathertopPhpContainerLogs'
LOG_STREAM_PREFIX = 'weathertop-php-stream'


def get_latest_task_definition(task_name):
    try:
        response = ecs_client.list_task_definitions(
            familyPrefix=task_name,
            sort="DESC",
            status="ACTIVE"
        )
        return response["taskDefinitionArns"][0] if response["taskDefinitionArns"] else None
    except ClientError as e:
        print(f"❌ Error getting task definition: {e}")
        exit(1)


def describe_task_definition(task_def_arn):
    try:
        response = ecs_client.describe_task_definition(taskDefinition=task_def_arn)
        td = response["taskDefinition"]
        return {
            "taskRoleArn": td.get("taskRoleArn"),
            "executionRoleArn": td.get("executionRoleArn"),
            "networkMode": td.get("networkMode"),
            "cpu": td.get("cpu"),
            "memory": td.get("memory"),
            "containerDefinitions": td.get("containerDefinitions", [])
        }
    except ClientError as e:
        print(f"❌ Error describing task definition: {e}")
        exit(1)


def get_running_tasks(cluster_arn, task_name):
    try:
        tasks = ecs_client.list_tasks(cluster=cluster_arn, desiredStatus="RUNNING")["taskArns"]
        running = []
        if tasks:
            described = ecs_client.describe_tasks(cluster=cluster_arn, tasks=tasks)
            for t in described["tasks"]:
                if task_name in t["taskDefinitionArn"]:
                    running.append(t["taskArn"])
        return running
    except ClientError as e:
        print(f"❌ Error getting running tasks: {e}")
        return []


def find_eventbridge_rules(task_def_name):
    try:
        rules = events_client.list_rules()["Rules"]
        matches = []
        for rule in rules:
            targets = events_client.list_targets_by_rule(Rule=rule["Name"])["Targets"]
            for target in targets:
                if "EcsParameters" in target:
                    if task_def_name in target["EcsParameters"]["TaskDefinitionArn"]:
                        matches.append({
                            "ruleName": rule["Name"],
                            "scheduleExpression": rule.get("ScheduleExpression"),
                            "state": rule["State"],
                            "description": rule.get("Description", ""),
                            "target": target
                        })
        return matches
    except ClientError as e:
        print(f"❌ Error getting EventBridge rules: {e}")
        return []


def human_readable_schedule(expr):
    if expr and expr.startswith("cron("):
        parts = expr.replace("cron(", "").replace(")", "").split()
        return f"Every {parts[4]} at {parts[1]}:{parts[0]} UTC"
    return "N/A"


# ---- New IAM Role permission checker ----
def role_has_ecs_run_task_permission(role_arn):
    """
    Check if the IAM Role has ecs:RunTask permission
    """
    try:
        role_name = role_arn.split("/")[-1]
        # List attached managed policies
        attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']

        # Check managed policies
        for pol in attached_policies:
            pol_arn = pol['PolicyArn']
            pol_version = iam_client.get_policy(PolicyArn=pol_arn)['Policy']['DefaultVersionId']
            pol_doc = iam_client.get_policy_version(PolicyArn=pol_arn, VersionId=pol_version)['PolicyVersion']['Document']

            if policy_allows_ecs_run_task(pol_doc):
                return True

        # Check inline policies
        inline_policies = iam_client.list_role_policies(RoleName=role_name)['PolicyNames']
        for pol_name in inline_policies:
            pol_doc = iam_client.get_role_policy(RoleName=role_name, PolicyName=pol_name)['PolicyDocument']
            if policy_allows_ecs_run_task(pol_doc):
                return True

        return False

    except ClientError as e:
        print(f"❌ IAM check error for role {role_arn}: {e}")
        return False


def policy_allows_ecs_run_task(policy_doc):
    """
    Very basic check if policy document allows ecs:RunTask
    """
    statements = policy_doc.get('Statement', [])
    if not isinstance(statements, list):
        statements = [statements]

    for stmt in statements:
        if stmt.get('Effect', '') != 'Allow':
            continue
        actions = stmt.get('Action', [])
        if isinstance(actions, str):
            actions = [actions]
        for action in actions:
            if action == '*' or action.lower() == 'ecs:runtask':
                return True
    return False


# --- New: Check for S3 PutObject permission on bucket (basic placeholder) ---
def role_has_s3_putobject_permission(role_arn, bucket_name):
    try:
        role_name = role_arn.split("/")[-1]
        attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']

        for pol in attached_policies:
            pol_arn = pol['PolicyArn']
            pol_version = iam_client.get_policy(PolicyArn=pol_arn)['Policy']['DefaultVersionId']
            pol_doc = iam_client.get_policy_version(PolicyArn=pol_arn, VersionId=pol_version)['PolicyVersion']['Document']

            if policy_allows_s3_putobject(pol_doc, bucket_name):
                return True

        inline_policies = iam_client.list_role_policies(RoleName=role_name)['PolicyNames']
        for pol_name in inline_policies:
            pol_doc = iam_client.get_role_policy(RoleName=role_name, PolicyName=pol_name)['PolicyDocument']
            if policy_allows_s3_putobject(pol_doc, bucket_name):
                return True

        return False
    except ClientError as e:
        print(f"❌ IAM check error for S3 PutObject on role {role_arn}: {e}")
        return False


def policy_allows_s3_putobject(policy_doc, bucket_name):
    statements = policy_doc.get('Statement', [])
    if not isinstance(statements, list):
        statements = [statements]

    bucket_arn = f"arn:aws:s3:::{bucket_name}/*"
    for stmt in statements:
        if stmt.get('Effect', '') != 'Allow':
            continue
        actions = stmt.get('Action', [])
        resources = stmt.get('Resource', [])
        if isinstance(actions, str):
            actions = [actions]
        if isinstance(resources, str):
            resources = [resources]
        if 's3:PutObject' in [a.lower() for a in actions] or '*' in actions:
            if bucket_arn in resources or '*' in resources:
                return True
    return False


# --- New: Inspect environment variables of running containers ---
def print_task_container_env_vars(cluster_arn, task_arns):
    try:
        described = ecs_client.describe_tasks(cluster=cluster_arn, tasks=task_arns)
        for task in described["tasks"]:
            print(f"\n🔍 Inspecting task {task['taskArn']} containers environment variables:")
            for container in task.get("containers", []):
                env_vars = container.get("environment", [])
                if env_vars:
                    print(f"Container {container['name']} environment vars:")
                    for env in env_vars:
                        print(f"  {env['name']} = {env['value']}")
                else:
                    # Note: environment variables in describe_tasks may be empty if not explicitly set in task definition.
                    # Instead, print container definitions env vars as fallback.
                    print(f"Container {container['name']} has no environment variables set in running task.")
    except ClientError as e:
        print(f"❌ Error describing task containers env vars: {e}")


# --- New: Print environment variables from Task Definition container definitions ---
def print_task_definition_container_env_vars(task_def_info):
    print("\n🔍 Inspecting Task Definition container environment variables:")
    for container in task_def_info.get("containerDefinitions", []):
        env_vars = container.get("environment", [])
        if env_vars:
            print(f"Container {container['name']} environment vars:")
            for env in env_vars:
                print(f"  {env['name']} = {env['value']}")
        else:
            print(f"Container {container['name']} has no environment variables defined.")


# --- New: Fetch recent CloudWatch Logs for container ---
def print_recent_container_logs(log_group, log_stream_prefix):
    print(f"\n📄 Fetching recent CloudWatch logs for log group '{log_group}', stream prefix '{log_stream_prefix}'...\n")
    try:
        streams = logs.describe_log_streams(
            logGroupName=log_group,
            logStreamNamePrefix=log_stream_prefix,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        if not streams['logStreams']:
            print("No log streams found.")
            return

        stream_name = streams['logStreams'][0]['logStreamName']
        events = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            startFromHead=False,
            limit=50
        )
        print(f"--- Last 50 log events from {stream_name} ---")
        for event in events['events']:
            print(event['message'])
        print(f"--- End of logs ---")
    except ClientError as e:
        print(f"❌ Error fetching logs: {e}")


if __name__ == "__main__":
    print(f"\n🔍 Inspecting ECS Task for family: {TASK_FAMILY}\n")

    latest_task_arn = get_latest_task_definition(TASK_FAMILY)
    if not latest_task_arn:
        print(f"❌ No active task definition found for {TASK_FAMILY}")
        exit(1)

    print(f"✅ Latest Task Definition ARN: {latest_task_arn}")
    td_info = describe_task_definition(latest_task_arn)
    print(f"📦 Task Definition Metadata\n")
    print(f"Task Role ARN: {td_info['taskRoleArn']}")
    print(f"Execution Role ARN: {td_info['executionRoleArn']}")
    print(f"Network Mode: {td_info['networkMode']}")
    print(f"CPU: {td_info['cpu']}")
    print(f"Memory: {td_info['memory']}")

    # Print container env vars from task definition for comparison
    print_task_definition_container_env_vars(td_info)

    print(f"\n🔗 ECS Cluster ARN: {CLUSTER_ARN}")

    running_tasks = get_running_tasks(CLUSTER_ARN, TASK_FAMILY)
    if running_tasks:
        print(f"🛠 ECS Tasks:\nRunning Tasks: {len(running_tasks)}")
        for t in running_tasks:
            print(f" - {t}")
        # Inspect env vars of running tasks containers
        print_task_container_env_vars(CLUSTER_ARN, running_tasks)
    else:
        print("🛠 ECS Tasks:\nNo RUNNING ECS tasks found.")

    rules = find_eventbridge_rules(TASK_FAMILY)
    print("\n🔔 EventBridge Rules\n")
    if not rules:
        print("No EventBridge rules found for this task.")
    else:
        for r in rules:
            print(f"Name: {r['ruleName']}")
            print(f"Schedule Expression: {r['scheduleExpression']}")
            print(f"Human-readable Schedule: {human_readable_schedule(r['scheduleExpression'])}")
            print(f"State: {r['state']}")
            print(f"Description: {r['description']}")
            print(f"Targets:")
            t = r["target"]
            print(f"    ID: {t['Id']}")
            print(f"    ARN: {t['Arn']}")
            ecs_params = t["EcsParameters"]
            print(f"    Task Definition ARN: {ecs_params['TaskDefinitionArn']}")
            print(f"    Launch Type: {ecs_params['LaunchType']}")
            net_cfg = t.get("NetworkConfiguration", {}).get("awsvpcConfiguration", {})
            print(f"    Subnets: {', '.join(net_cfg.get('subnets', []))}")
            print(f"    Security Groups: {', '.join(net_cfg.get('securityGroups', []))}")
            print(f"    Assign Public IP: {net_cfg.get('assignPublicIp', 'DISABLED')}")
            print("")

    # Fetch recent logs from CloudWatch to find credential or network errors
    print_recent_container_logs(LOG_GROUP, LOG_STREAM_PREFIX)

    # === FINAL CHECK ===
    print("=== 📢 FINAL CHECK ===")
    can_invoke = False
    for role_arn in [td_info.get('taskRoleArn'), td_info.get('executionRoleArn')]:
        if role_arn and role_has_ecs_run_task_permission(role_arn):
            can_invoke = True
            break

    if can_invoke:
        print("✅ EventBridge CAN invoke this ECS task based on IAM permissions.")
    else:
        print("❌ EventBridge CANNOT invoke this ECS task based on IAM permissions.")

    # Additional check: verify S3 PutObject permission for task role (adjust bucket name accordingly)
    bucket_name = 'weathertop2'  # Change as needed to your S3 bucket
    if td_info.get('taskRoleArn'):
        has_s3 = role_has_s3_putobject_permission(td_info['taskRoleArn'], bucket_name)
        if has_s3:
            print(f"✅ Task role {td_info['taskRoleArn']} has S3 PutObject permission on bucket '{bucket_name}'.")
        else:
            print(f"❌ Task role {td_info['taskRoleArn']} DOES NOT have S3 PutObject permission on bucket '{bucket_name}'.")

    print("\n✅ ECS Inspection script completed.\n")




