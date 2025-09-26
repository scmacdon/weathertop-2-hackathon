import boto3
from botocore.exceptions import ClientError

ecs_client = boto3.client("ecs", region_name="us-east-1")
events_client = boto3.client("events", region_name="us-east-1")
iam_client = boto3.client("iam", region_name="us-east-1")

# ===== JS ECS CONFIG =====
TASK_FAMILY = "WeathertopJS"
CLUSTER_ARN = "arn:aws:ecs:us-east-1:814548047983:cluster/MyJSWeathertopCluster"

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
            "memory": td.get("memory")
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

    print(f"\n🔗 ECS Cluster ARN: {CLUSTER_ARN}")

    running_tasks = get_running_tasks(CLUSTER_ARN, TASK_FAMILY)
    if running_tasks:
        print(f"🛠 ECS Tasks:\nRunning Tasks: {len(running_tasks)}")
        for t in running_tasks:
            print(f" - {t}")
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



