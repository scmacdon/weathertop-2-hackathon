import boto3
from datetime import datetime, timezone
import pytz
import botocore
import json

AWS_REGION = 'us-east-1'
CLUSTER_NAME = 'MyJavaWeathertopCluster'
TASK_DEFINITION_FAMILY = 'WeathertopJava'
LOG_GROUP = 'WeathertopContainerLogs'
EVENTBRIDGE_RULE_PREFIX = 'ecs-java-schedule'

ecs = boto3.client('ecs', region_name=AWS_REGION)
logs = boto3.client('logs', region_name=AWS_REGION)
ec2 = boto3.client('ec2', region_name=AWS_REGION)
events = boto3.client('events', region_name=AWS_REGION)
iam = boto3.client('iam', region_name=AWS_REGION)

# Convert UTC to EST/EDT
def to_est(dt):
    if not dt:
        return "N/A"
    est = pytz.timezone("US/Eastern")
    return dt.astimezone(est).strftime('%Y-%m-%d %I:%M:%S %p %Z')

# Enhanced human-readable cron logic
def human_readable_schedule(expr):
    if expr.startswith("cron(") and expr.endswith(")"):
        cron_expr = expr[5:-1].strip()
        parts = cron_expr.split()
        if len(parts) == 6:
            minute, hour, dom, month, dow, year = parts
            day_map = {
                '1': 'Sunday', '2': 'Monday', '3': 'Tuesday',
                '4': 'Wednesday', '5': 'Thursday', '6': 'Friday',
                '7': 'Saturday', '?': 'any day'
            }
            dow_human = day_map.get(dow.upper(), dow)
            hour_int = int(hour)
            hour_fmt = f"{hour_int % 12 or 12}:00 {'AM' if hour_int < 12 else 'PM'}"
            return f"Every {dow_human} at {hour_fmt} UTC"
        else:
            return f"Cron schedule: {cron_expr}"
    elif expr.startswith("rate(") and expr.endswith(")"):
        return f"Rate schedule: {expr[5:-1]}"
    return f"Schedule expression: {expr}"

def check_eventbridge_role_permissions(role_arn):
    """Check if IAM role has ecs:RunTask permission."""
    try:
        role_name = role_arn.split("/")[-1]
        has_permission = False

        # Inline policies
        inline_policies = iam.list_role_policies(RoleName=role_name)["PolicyNames"]
        for pol_name in inline_policies:
            pol_doc = iam.get_role_policy(RoleName=role_name, PolicyName=pol_name)["PolicyDocument"]
            if json.dumps(pol_doc).find("ecs:RunTask") != -1:
                has_permission = True

        # Attached policies
        attached_policies = iam.list_attached_role_policies(RoleName=role_name)["AttachedPolicies"]
        for pol in attached_policies:
            pol_doc = iam.get_policy_version(
                PolicyArn=pol["PolicyArn"],
                VersionId=iam.get_policy(PolicyArn=pol["PolicyArn"])["Policy"]["DefaultVersionId"]
            )["PolicyVersion"]["Document"]
            if json.dumps(pol_doc).find("ecs:RunTask") != -1:
                has_permission = True

        return has_permission
    except botocore.exceptions.ClientError as e:
        print(f"   ❌ Error checking IAM role {role_arn}: {e}")
        return False

def get_latest_task_info():
    print(f"🔍 Finding tasks for task definition family: {TASK_DEFINITION_FAMILY}")

    # Get latest task definition ARN
    task_defs = ecs.list_task_definitions(familyPrefix=TASK_DEFINITION_FAMILY, sort='DESC')
    if not task_defs['taskDefinitionArns']:
        print("❌ No task definitions found.")
        return

    latest_task_def_arn = task_defs['taskDefinitionArns'][0]
    print(f"✅ Latest task definition: {latest_task_def_arn}")

    # Get task definition details
    task_def = ecs.describe_task_definition(taskDefinition=latest_task_def_arn)['taskDefinition']
    task_role_arn = task_def.get('taskRoleArn', 'N/A')
    exec_role_arn = task_def.get('executionRoleArn', 'N/A')

    print("\n--- 📦 Task Definition Metadata ---")
    print(f"Task Role ARN         : {task_role_arn}")
    print(f"Execution Role ARN    : {exec_role_arn}")
    print(f"Network Mode          : {task_def['networkMode']}")
    print(f"CPU                   : {task_def.get('cpu', 'N/A')}")
    print(f"Memory                : {task_def.get('memory', 'N/A')}")

    # Get ECS cluster ARN
    cluster_arn = None
    clusters = ecs.describe_clusters(clusters=[CLUSTER_NAME])
    if clusters['clusters']:
        cluster_arn = clusters['clusters'][0]['clusterArn']
        print(f"\n🔗 ECS Cluster ARN      : {cluster_arn}")
    else:
        print("❌ Cluster not found.")

    # Networking details
    subnet_id = None
    sg_ids = []

    try:
        task_arns = ecs.list_tasks(
            cluster=CLUSTER_NAME,
            family=TASK_DEFINITION_FAMILY,
            desiredStatus='RUNNING',
            maxResults=5
        )['taskArns']
    except botocore.exceptions.ClientError as e:
        print(f"Error listing tasks: {e}")
        task_arns = []

    if not task_arns:
        print("\n❌ No RUNNING ECS tasks found. Checking for STOPPED tasks...")
        try:
            task_arns = ecs.list_tasks(
                cluster=CLUSTER_NAME,
                family=TASK_DEFINITION_FAMILY,
                desiredStatus='STOPPED',
                maxResults=5
            )['taskArns']
        except botocore.exceptions.ClientError as e:
            print(f"Error listing stopped tasks: {e}")
            task_arns = []

    if not task_arns:
        print("\n❌ No ECS tasks found at all.")
    else:
        task = ecs.describe_tasks(cluster=CLUSTER_NAME, tasks=[task_arns[0]])['tasks'][0]
        last_status = task.get('lastStatus', 'N/A')
        desired_status = task.get('desiredStatus', 'N/A')
        started_at = task.get('startedAt')
        started_at_str = to_est(started_at) if started_at else "N/A"

        print(f"\n--- 🟢 Current Task Status ---")
        print(f"Task ARN           : {task['taskArn']}")
        print(f"Last Status        : {last_status}")
        print(f"Desired Status     : {desired_status}")
        print(f"Started At (EST)   : {started_at_str}")

        eni_id = None
        for attachment in task.get('attachments', []):
            if attachment['type'] == 'ElasticNetworkInterface':
                for detail in attachment['details']:
                    if detail['name'] == 'networkInterfaceId':
                        eni_id = detail['value']

        if eni_id:
            try:
                eni = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])['NetworkInterfaces'][0]
                subnet_id = eni['SubnetId']
                sg_ids = [sg['GroupId'] for sg in eni['Groups']]
                print("\n--- 🌐 Networking Details ---")
                print(f"ENI ID               : {eni_id}")
                print(f"Subnet ID            : {subnet_id}")
                print(f"Security Groups      : {', '.join(sg_ids)}")
                print(f"VPC ID               : {eni['VpcId']}")
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'InvalidNetworkInterfaceID.NotFound':
                    print(f"⚠️ ENI {eni_id} not found (probably deleted after task stopped).")
                else:
                    raise
        else:
            print("⚠️ No ENI found for the task.")

    print("\n--- ✅ Values for Java Target ---")
    print(f'Task Definition ARN : {latest_task_def_arn}')
    print(f'Cluster ARN         : {cluster_arn}')
    print(f'Task Role ARN       : {task_role_arn}')
    print(f'Execution Role ARN  : {exec_role_arn}')
    if task_arns and subnet_id is not None:
        print(f'Subnet ID           : {subnet_id}')
        print(f'Security Groups     : {", ".join(sg_ids)}')

    print("\n--- 🔔 EventBridge Schedule Rules matching prefix ---")
    rules = []
    next_token = None
    while True:
        if next_token:
            response = events.list_rules(NamePrefix=EVENTBRIDGE_RULE_PREFIX, NextToken=next_token)
        else:
            response = events.list_rules(NamePrefix=EVENTBRIDGE_RULE_PREFIX)
        rules.extend(response.get('Rules', []))
        next_token = response.get('NextToken')
        if not next_token:
            break

    if not rules:
        print("❌ No EventBridge schedule rules found with that prefix.")
        return

    # New flag to track final verdict
    can_invoke = False

    for rule in rules:
        print(f"\nRule Name     : {rule['Name']}")
        print(f"Schedule Expr : {rule.get('ScheduleExpression', 'N/A')}")
        print(f"State         : {rule.get('State', 'N/A')}")
        print(f"Description   : {rule.get('Description', 'N/A')}")
        print(f"Human Readable Schedule: {human_readable_schedule(rule.get('ScheduleExpression', ''))}")

        targets_resp = events.list_targets_by_rule(Rule=rule['Name'])
        targets = targets_resp.get('Targets', [])
        if not targets:
            print("⚠️ No targets found for this rule.")
            continue

        for target in targets:
            print("\n  Target ID   :", target.get('Id'))
            print("  Target ARN  :", target.get('Arn'))
            ecs_params = target.get('EcsParameters')
            if ecs_params:
                print("  ECS Task Definition ARN:", ecs_params.get('TaskDefinitionArn'))
                print("  Launch Type            :", ecs_params.get('LaunchType'))
                net_cfg = ecs_params.get('NetworkConfiguration')
                if net_cfg and 'awsvpcConfiguration' in net_cfg:
                    awsvpc = net_cfg['awsvpcConfiguration']
                    print("  Subnets                :", ', '.join(awsvpc.get('Subnets', [])))
                    print("  Security Groups        :", ', '.join(awsvpc.get('SecurityGroups', [])))
                    print("  Assign Public IP       :", awsvpc.get('AssignPublicIp'))
            else:
                print("  No ECS Parameters found in target.")

            role_arn = target.get('RoleArn')
            if role_arn:
                print(f"  EventBridge Target Role ARN: {role_arn}")
                if check_eventbridge_role_permissions(role_arn):
                    print("  ✅ This role HAS permission to run ECS tasks.")
                    can_invoke = True
                else:
                    print("  ❌ This role does NOT have ecs:RunTask permission.")
            else:
                print("  ⚠️ No RoleArn found for this target.")

    # Final verdict
    print("\n=== 📢 FINAL CHECK ===")
    if can_invoke:
        print("✅ EventBridge CAN invoke this ECS task based on IAM permissions.")
    else:
        print("❌ EventBridge CANNOT invoke this ECS task — missing IAM permission.")

if __name__ == '__main__':
    get_latest_task_info()


