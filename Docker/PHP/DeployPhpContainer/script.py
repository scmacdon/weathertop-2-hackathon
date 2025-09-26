import boto3
import botocore
import subprocess
import sys
import json
import time

AWS_ACCOUNT_ID = '814548047983'
AWS_REGION = 'us-east-1'

ECR_REPO_NAME = 'weathertop-php-ecr-repo'
IMAGE_TAG = 'latest'
DOCKERFILE_DIR = 'C:/Users/scmacdon/Docker/PHP'

ECS_CLUSTER_NAME = 'MyPHPWeathertopCluster'
ECS_TASK_DEF_NAME = 'WeathertopPhp'
CONTAINER_NAME = 'app'
EXECUTION_ROLE_NAME = 'ecsTaskExecutionRole'
TASK_ROLE_NAME = 'ecsTaskRole'

SUBNETS = ['subnet-03c28397a3a7cd314', 'subnet-06dde61595900f899']
SECURITY_GROUPS = ['sg-0e357c99b6b13bf62']

LOG_GROUP = 'WeathertopPhpContainerLogs'
LOG_STREAM_PREFIX = 'weathertop-php-stream'

EVENTBRIDGE_RULE_NAME = 'ecs-php-schedule'
EVENTBRIDGE_SCHEDULE = 'cron(59 23 ? * FRI *)'

ecs = boto3.client('ecs', region_name=AWS_REGION)
logs = boto3.client('logs', region_name=AWS_REGION)
iam = boto3.client('iam')
ec2 = boto3.client('ec2', region_name=AWS_REGION)
ecr = boto3.client('ecr', region_name=AWS_REGION)
events = boto3.client('events', region_name=AWS_REGION)


def ensure_iam_role(role_name, assume_role_service, s3_bucket):
    try:
        iam.get_role(RoleName=role_name)
        print(f"[IAM] Role '{role_name}' already exists.")
    except iam.exceptions.NoSuchEntityException:
        print(f"[IAM] Creating role '{role_name}'...")
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": assume_role_service},
                "Action": "sts:AssumeRole"
            }]
        }
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description=f"Role for {role_name}"
        )
        print(f"[IAM] Role '{role_name}' created.")

        if role_name == EXECUTION_ROLE_NAME:
            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'
            )
            print(f"[IAM] Attached ECS Task Execution managed policy to '{role_name}'.")
        elif role_name == TASK_ROLE_NAME:
            iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn='arn:aws:iam::aws:policy/AdministratorAccess'
            )
            print(f"[IAM] Attached AdministratorAccess policy to '{role_name}'.")

    s3_access_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:PutObject"],
            "Resource": f"arn:aws:s3:::{s3_bucket}/*"
        }]
    }
    iam.put_role_policy(
        RoleName=role_name,
        PolicyName="AllowS3PutObject",
        PolicyDocument=json.dumps(s3_access_policy)
    )
    print(f"[IAM] Attached inline S3 PutObject policy to '{role_name}'.")


def ensure_outbound_rule():
    sg_id = SECURITY_GROUPS[0]
    try:
        sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
        egress_rules = sg.get('IpPermissionsEgress', [])
        has_all_traffic = any(
            rule['IpProtocol'] == '-1' and
            any(ipr.get('CidrIp') == '0.0.0.0/0' for ipr in rule.get('IpRanges', []))
            for rule in egress_rules
        )
        if not has_all_traffic:
            print(f"[EC2] Adding outbound rule to security group {sg_id}...")
            ec2.authorize_security_group_egress(
                GroupId=sg_id,
                IpPermissions=[{'IpProtocol': '-1', 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}]
            )
            print(f"[EC2] Outbound rule added.")
        else:
            print(f"[EC2] Outbound rule already exists on security group {sg_id}.")
    except botocore.exceptions.ClientError as e:
        if "InvalidPermission.Duplicate" in str(e):
            print(f"[EC2] Outbound rule already exists (duplicate).")
        else:
            raise


def recreate_ecr_repo(repo_name):
    try:
        ecr.describe_repositories(repositoryNames=[repo_name])
        print(f"[ECR] Repository '{repo_name}' exists. Deleting...")
        ecr.delete_repository(repositoryName=repo_name, force=True)
        print(f"[ECR] Repository '{repo_name}' deleted.")
        time.sleep(2)
    except ecr.exceptions.RepositoryNotFoundException:
        print(f"[ECR] Repository '{repo_name}' does not exist. Skipping deletion.")

    response = ecr.create_repository(repositoryName=repo_name)
    print(f"[ECR] Created repository '{repo_name}'.")
    return response['repository']['repositoryUri']


def create_log_group():
    existing_groups = logs.describe_log_groups(logGroupNamePrefix=LOG_GROUP).get('logGroups', [])
    if not any(g['logGroupName'] == LOG_GROUP for g in existing_groups):
        print(f"[CloudWatch Logs] Creating log group '{LOG_GROUP}'...")
        logs.create_log_group(logGroupName=LOG_GROUP)
        print(f"[CloudWatch Logs] Log group '{LOG_GROUP}' created.")
    else:
        print(f"[CloudWatch Logs] Log group '{LOG_GROUP}' already exists.")


def create_ecs_cluster():
    try:
        response = ecs.describe_clusters(clusters=[ECS_CLUSTER_NAME])
        if response['clusters'][0]['status'] == 'ACTIVE':
            print(f"[ECS] Cluster '{ECS_CLUSTER_NAME}' already exists and active.")
            return
    except Exception as e:
        print(f"[ECS] Exception checking cluster: {e}")

    print(f"[ECS] Creating cluster '{ECS_CLUSTER_NAME}'...")
    ecs.create_cluster(clusterName=ECS_CLUSTER_NAME)
    print(f"[ECS] Cluster '{ECS_CLUSTER_NAME}' created.")


def register_task_definition(image_uri):
    print(f"[ECS] Registering task definition '{ECS_TASK_DEF_NAME}' with image '{image_uri}'...")
    response = ecs.register_task_definition(
        family=ECS_TASK_DEF_NAME,
        networkMode='awsvpc',
        requiresCompatibilities=['FARGATE'],
        cpu='1024',
        memory='4096',
        executionRoleArn=f'arn:aws:iam::{AWS_ACCOUNT_ID}:role/{EXECUTION_ROLE_NAME}',
        taskRoleArn=f'arn:aws:iam::{AWS_ACCOUNT_ID}:role/{TASK_ROLE_NAME}',
        containerDefinitions=[{
            'name': CONTAINER_NAME,
            'image': image_uri,
            'essential': True,
            'cpu': 256,
            'memory': 512,
            'workingDirectory': '/app',
            'portMappings': [{'containerPort': 80}],
            'logConfiguration': {
                'logDriver': 'awslogs',
                'options': {
                    'awslogs-group': LOG_GROUP,
                    'awslogs-region': AWS_REGION,
                    'awslogs-stream-prefix': LOG_STREAM_PREFIX
                }
            }
        }]
    )
    task_def_arn = response['taskDefinition']['taskDefinitionArn']
    print(f"[ECS] Task definition ARN: {task_def_arn}")
    return task_def_arn


def deregister_old_task_definitions():
    print(f"[ECS] Deregistering old task definitions for '{ECS_TASK_DEF_NAME}'...")
    paginator = ecs.get_paginator('list_task_definitions')
    all_defs = []
    for page in paginator.paginate(familyPrefix=ECS_TASK_DEF_NAME, status='ACTIVE', sort='DESC'):
        all_defs.extend(page['taskDefinitionArns'])
    if not all_defs:
        print("[ECS] No active task definitions found.")
        return None
    latest = all_defs[0]
    for task_def_arn in all_defs[1:]:
        try:
            ecs.deregister_task_definition(taskDefinition=task_def_arn)
            print(f"[ECS] Deregistered old task definition: {task_def_arn}")
        except Exception as e:
            print(f"[ECS] Failed to deregister {task_def_arn}: {e}")
    return latest


def stop_old_running_tasks(latest_task_def_arn):
    print("[ECS] Stopping running tasks with old task definitions...")
    paginator = ecs.get_paginator('list_tasks')
    running_tasks = []
    for page in paginator.paginate(cluster=ECS_CLUSTER_NAME, desiredStatus='RUNNING'):
        running_tasks.extend(page['taskArns'])
    if not running_tasks:
        print("[ECS] No running tasks found.")
        return
    for i in range(0, len(running_tasks), 100):
        batch = running_tasks[i:i + 100]
        desc = ecs.describe_tasks(cluster=ECS_CLUSTER_NAME, tasks=batch)
        for task in desc['tasks']:
            if task['taskDefinitionArn'] != latest_task_def_arn:
                ecs.stop_task(cluster=ECS_CLUSTER_NAME, task=task['taskArn'], reason='Cleanup old task definition')


def ensure_eventbridge_permission(event_rule_name, target_arn):
    role_name = "EventBridgeInvokeECSRole"
    try:
        iam.get_role(RoleName=role_name)
    except iam.exceptions.NoSuchEntityException:
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "events.amazonaws.com"}, "Action": "sts:AssumeRole"}]
        }
        iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(assume_role_policy))
        iam.attach_role_policy(RoleName=role_name, PolicyArn='arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceEventsRole')

    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": "ecs:RunTask",
            "Resource": [
                f"arn:aws:ecs:{AWS_REGION}:{AWS_ACCOUNT_ID}:cluster/{ECS_CLUSTER_NAME}",
                target_arn
            ]
        }]
    }
    iam.put_role_policy(RoleName=role_name, PolicyName="AllowRunTaskOnCluster", PolicyDocument=json.dumps(inline_policy))
    return role_name


def ensure_eventbridge_rule(event_rule_name, schedule_expression):
    try:
        events.describe_rule(Name=event_rule_name)
    except events.exceptions.ResourceNotFoundException:
        events.put_rule(Name=event_rule_name, ScheduleExpression=schedule_expression, State='ENABLED')


def update_eventbridge_rule(event_rule_name, task_def_arn):
    target_id = '1'
    role_name = ensure_eventbridge_permission(event_rule_name, task_def_arn)
    target = {
        'Id': target_id,
        'Arn': f'arn:aws:ecs:{AWS_REGION}:{AWS_ACCOUNT_ID}:cluster/{ECS_CLUSTER_NAME}',
        'RoleArn': f'arn:aws:iam::{AWS_ACCOUNT_ID}:role/{role_name}',
        'EcsParameters': {
            'TaskDefinitionArn': task_def_arn,
            'TaskCount': 1,
            'LaunchType': 'FARGATE',
            'NetworkConfiguration': {
                'awsvpcConfiguration': {'Subnets': SUBNETS, 'SecurityGroups': SECURITY_GROUPS, 'AssignPublicIp': 'ENABLED'}
            }
        }
    }
    events.put_targets(Rule=event_rule_name, Targets=[target])


def main():
    print("=== Starting PHP Deployment ===")

    ensure_iam_role(EXECUTION_ROLE_NAME, 'ecs-tasks.amazonaws.com', 'weathertop2')
    ensure_iam_role(TASK_ROLE_NAME, 'ecs-tasks.amazonaws.com', 'weathertop2')
    ensure_outbound_rule()

    ecr_uri = recreate_ecr_repo(ECR_REPO_NAME)

    # Docker login, build, tag, push
    pw = subprocess.check_output(["aws", "ecr", "get-login-password", "--region", AWS_REGION])
    subprocess.run(["docker", "login", "--username", "AWS", "--password-stdin", ecr_uri], input=pw, check=True)
    subprocess.run(["docker", "build", "-t", f"{ECR_REPO_NAME}:{IMAGE_TAG}", DOCKERFILE_DIR], check=True)
    subprocess.run(["docker", "tag", f"{ECR_REPO_NAME}:{IMAGE_TAG}", f"{ecr_uri}:{IMAGE_TAG}"], check=True)
    subprocess.run(["docker", "push", f"{ecr_uri}:{IMAGE_TAG}"], check=True)

    create_log_group()
    create_ecs_cluster()

    task_def_arn = register_task_definition(f"{ecr_uri}:{IMAGE_TAG}")
    latest_task_def_arn = deregister_old_task_definitions()
    stop_old_running_tasks(latest_task_def_arn)

    ensure_eventbridge_rule(EVENTBRIDGE_RULE_NAME, EVENTBRIDGE_SCHEDULE)
    update_eventbridge_rule(EVENTBRIDGE_RULE_NAME, latest_task_def_arn)

    print("✅ PHP Deployment completed successfully.")


if __name__ == '__main__':
    main()



