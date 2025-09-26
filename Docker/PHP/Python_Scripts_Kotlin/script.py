
import boto3
import botocore
import json
import time

# Configuration - your values
AWS_ACCOUNT_ID = '814548047983'
AWS_REGION = 'us-east-1'
CLUSTER_NAME = 'MyJavaWeathertopCluster'
TASK_DEFINITION_NAME = 'WeathertopJava'
CONTAINER_NAME = 'weathertop-java'
IMAGE = f'{AWS_ACCOUNT_ID}.dkr.ecr.{AWS_REGION}.amazonaws.com/weathertop-java:latest'
LOG_GROUP = 'WeathertopContainerLogs'
LOG_STREAM_PREFIX = 'weathertop-stream'
CPU = '256'
MEMORY = '512'
SERVICE_NAME = 'JavaWeathertop'
SUBNETS = ['subnet-03c28397a3a7cd314', 'subnet-06dde61595900f899']
SECURITY_GROUPS = ['sg-0e357c99b6b13bf62']
IAM_ROLE_NAME = 'ecsTaskExecutionRole'
TASK_ROLE_NAME = 'ecsTaskRole'
S3_BUCKET_NAME = 'weathertop2'

# AWS clients
ecs_client = boto3.client('ecs', region_name=AWS_REGION)
logs_client = boto3.client('logs', region_name=AWS_REGION)
iam_client = boto3.client('iam')
ec2_client = boto3.client('ec2', region_name=AWS_REGION)
ecr_client = boto3.client('ecr', region_name=AWS_REGION)

def ensure_iam_role():
    try:
        iam_client.get_role(RoleName=IAM_ROLE_NAME)
        print(f"IAM role '{IAM_ROLE_NAME}' already exists.")
    except iam_client.exceptions.NoSuchEntityException:
        print(f"Creating IAM role '{IAM_ROLE_NAME}'...")
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {
                    "Service": "ecs-tasks.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }]
        }
        iam_client.create_role(
            RoleName=IAM_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="ECS Task Execution Role for Fargate"
        )
        print("Attaching AmazonECSTaskExecutionRolePolicy...")
        iam_client.attach_role_policy(
            RoleName=IAM_ROLE_NAME,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'
        )
    # Always attach inline S3 PutObject policy
    print("Attaching inline S3 PutObject policy...")
    s3_access_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:PutObject"],
            "Resource": f"arn:aws:s3:::{S3_BUCKET_NAME}/*"
        }]
    }
    iam_client.put_role_policy(
        RoleName=IAM_ROLE_NAME,
        PolicyName="AllowS3PutObject",
        PolicyDocument=json.dumps(s3_access_policy)
    )

def ensure_task_role():
    import time

    try:
        iam_client.get_role(RoleName=TASK_ROLE_NAME)
        print(f"IAM task role '{TASK_ROLE_NAME}' already exists.")
    except iam_client.exceptions.NoSuchEntityException:
        print(f"Creating IAM task role '{TASK_ROLE_NAME}' for ECS task runtime permissions...")
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {
                    "Service": "ecs-tasks.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }]
        }
        iam_client.create_role(
            RoleName=TASK_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="ECS Task Role for container runtime with broad AWS permissions"
        )
        time.sleep(5)  # Wait for propagation

    attached_policies = iam_client.list_attached_role_policies(RoleName=TASK_ROLE_NAME).get('AttachedPolicies', [])
    admin_policy_arn = 'arn:aws:iam::aws:policy/AdministratorAccess'
    if not any(p['PolicyArn'] == admin_policy_arn for p in attached_policies):
        print(f"Attaching AdministratorAccess managed policy to '{TASK_ROLE_NAME}'...")
        iam_client.attach_role_policy(RoleName=TASK_ROLE_NAME, PolicyArn=admin_policy_arn)
    else:
        print(f"AdministratorAccess policy already attached to '{TASK_ROLE_NAME}'.")

    print(f"Attaching inline S3 PutObject policy to '{TASK_ROLE_NAME}'...")
    s3_access_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:PutObject"],
            "Resource": f"arn:aws:s3:::{S3_BUCKET_NAME}/*"
        }]
    }
    iam_client.put_role_policy(
        RoleName=TASK_ROLE_NAME,
        PolicyName="AllowS3PutObject",
        PolicyDocument=json.dumps(s3_access_policy)
    )

def ensure_outbound_rule():
    sg_id = SECURITY_GROUPS[0]
    try:
        sg = ec2_client.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]
        egress_rules = sg.get('IpPermissionsEgress', [])
        has_all_traffic = any(
            rule['IpProtocol'] == '-1' and
            any(ipr.get('CidrIp') == '0.0.0.0/0' for ipr in rule.get('IpRanges', []))
            for rule in egress_rules
        )
        if not has_all_traffic:
            print(f"Adding outbound rule to security group {sg_id}...")
            ec2_client.authorize_security_group_egress(
                GroupId=sg_id,
                IpPermissions=[{
                    'IpProtocol': '-1',
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }]
            )
        else:
            print(f"Outbound rule already exists on security group {sg_id}.")
    except botocore.exceptions.ClientError as e:
        if "InvalidPermission.Duplicate" in str(e):
            print(f"Outbound rule already exists (duplicate).")
        else:
            raise

def create_ecs_cluster():
    try:
        response = ecs_client.describe_clusters(clusters=[CLUSTER_NAME])
        clusters = response.get('clusters', [])
        if clusters and clusters[0]['status'] == 'ACTIVE':
            print(f"ECS cluster '{CLUSTER_NAME}' already exists and is ACTIVE.")
            return clusters[0]['clusterArn']
    except Exception as e:
        print(f"Cluster '{CLUSTER_NAME}' does not exist or error: {e}")

    print(f"Creating ECS cluster '{CLUSTER_NAME}'...")
    response = ecs_client.create_cluster(clusterName=CLUSTER_NAME)
    cluster_arn = response['cluster']['clusterArn']
    print(f"Cluster ARN: {cluster_arn}")
    wait_for_cluster_active(CLUSTER_NAME)
    return cluster_arn

def wait_for_cluster_active(cluster_name, timeout=60, interval=5):
    print(f"Waiting for ECS cluster '{cluster_name}' to become ACTIVE...")
    waited = 0
    while waited < timeout:
        response = ecs_client.describe_clusters(clusters=[cluster_name])
        clusters = response.get('clusters', [])
        if clusters and clusters[0]['status'] == 'ACTIVE':
            print(f"ECS cluster '{cluster_name}' is ACTIVE.")
            return
        time.sleep(interval)
        waited += interval
    raise TimeoutError(f"Timed out waiting for cluster '{cluster_name}' to become ACTIVE.")

def create_log_group():
    existing_groups = logs_client.describe_log_groups(logGroupNamePrefix=LOG_GROUP).get('logGroups', [])
    if not any(g['logGroupName'] == LOG_GROUP for g in existing_groups):
        print(f"Creating CloudWatch Logs log group '{LOG_GROUP}'...")
        logs_client.create_log_group(logGroupName=LOG_GROUP)
    else:
        print(f"Log group '{LOG_GROUP}' already exists.")

def validate_ecr_image_exists():
    try:
        print(f"Checking if ECR image '{IMAGE}' exists...")
        ecr_client.describe_images(repositoryName='weathertop-java', imageIds=[{'imageTag': 'latest'}])
        print("ECR image found.")
    except ecr_client.exceptions.RepositoryNotFoundException:
        raise SystemExit("ECR repository 'weathertop-java' not found.")
    except ecr_client.exceptions.ImageNotFoundException:
        raise SystemExit("ECR image 'weathertop-java:latest' not found. Push it before deploying.")

def register_task_definition():
    print(f"Registering task definition '{TASK_DEFINITION_NAME}'...")
    response = ecs_client.register_task_definition(
        family=TASK_DEFINITION_NAME,
        networkMode='awsvpc',
        requiresCompatibilities=['FARGATE'],
        cpu=CPU,
        memory=MEMORY,
        executionRoleArn=f'arn:aws:iam::{AWS_ACCOUNT_ID}:role/{IAM_ROLE_NAME}',
        taskRoleArn=f'arn:aws:iam::{AWS_ACCOUNT_ID}:role/{TASK_ROLE_NAME}',
        containerDefinitions=[{
            'name': CONTAINER_NAME,
            'image': IMAGE,
            'essential': True,
            'memory': int(MEMORY),
            'cpu': int(CPU),
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
    print(f"Task definition ARN: {task_def_arn}")
    return task_def_arn

# Removed create_service function (kept code but not called)

def run_task(task_def_arn):
    print(f"Running task from task definition '{task_def_arn}'...")
    response = ecs_client.run_task(
        cluster=CLUSTER_NAME,
        launchType='FARGATE',
        taskDefinition=task_def_arn,
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': SUBNETS,
                'securityGroups': SECURITY_GROUPS,
                'assignPublicIp': 'ENABLED'
            }
        }
    )
    tasks = response.get('tasks', [])
    if tasks:
        print(f"Task started: {tasks[0]['taskArn']}")
    else:
        print("Failed to start task.")

def main():
    ensure_iam_role()
    ensure_task_role()
    ensure_outbound_rule()
    validate_ecr_image_exists()
    cluster_arn = create_ecs_cluster()
    create_log_group()
    task_def_arn = register_task_definition()
    # Run task directly instead of creating a service
    run_task(task_def_arn)
    print("✅ ECS Fargate task started (not a long-running service).")

if __name__ == "__main__":
    main()
