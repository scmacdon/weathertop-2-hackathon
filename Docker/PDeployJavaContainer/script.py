import boto3
import subprocess
import sys
import os
import time
import re
from datetime import datetime

AWS_REGION = 'us-east-1'
ECR_REPO_NAME = 'weathertop-ecr-repo'
IMAGE_TAG = 'latest'
DOCKERFILE_DIR = 'C:/Users/scmacdon/Docker/Java'  # Path to Dockerfile and app

# ECS Values from your inspection
ECS_CLUSTER_NAME = 'MyJavaWeathertopCluster'
ECS_TASK_DEF_NAME = 'WeathertopJava'  # Matches your registered task family
EXECUTION_ROLE_ARN = 'arn:aws:iam::814548047983:role/ecsTaskExecutionRole'
TASK_ROLE_ARN = 'arn:aws:iam::814548047983:role/ecsTaskRole'
SUBNETS = ['subnet-03c28397a3a7cd314', 'subnet-06dde61595900f899']
SECURITY_GROUPS = ['sg-0e357c99b6b13bf62']
EVENTBRIDGE_RULE_NAME = 'ecs-java-schedule'
CONTAINER_NAME = 'app'  # Matches container name in definition
LANGUAGE_PREFIX = 'java'  # Used for file pattern matching if needed

sts = boto3.client('sts')
account_id = sts.get_caller_identity()["Account"]
ecr_client = boto3.client('ecr', region_name=AWS_REGION)
ecs_client = boto3.client('ecs', region_name=AWS_REGION)
events_client = boto3.client('events', region_name=AWS_REGION)

def get_or_create_ecr_repo(repo_name):
    try:
        response = ecr_client.describe_repositories(repositoryNames=[repo_name])
        print(f"✅ ECR repository '{repo_name}' already exists.")
        return response["repositories"][0]["repositoryUri"]
    except ecr_client.exceptions.RepositoryNotFoundException:
        response = ecr_client.create_repository(repositoryName=repo_name)
        print(f"✅ Created ECR repository '{repo_name}'.")
        return response["repository"]["repositoryUri"]

def get_ecr_login():
    print("🔑 Logging in to ECR...")
    result = subprocess.run(
        ["aws", "ecr", "get-login-password", "--region", AWS_REGION],
        stdout=subprocess.PIPE,
        check=True
    )
    password = result.stdout.decode().strip()
    subprocess.run([
        "docker", "login",
        "--username", "AWS",
        "--password", password,
        f"{account_id}.dkr.ecr.{AWS_REGION}.amazonaws.com"
    ], check=True)
    print("✅ Docker login successful.")

def build_and_push_docker_image(ecr_uri):
    print("🐳 Building Docker image...")
    subprocess.run([
        "docker", "build", "-t", f"{ECR_REPO_NAME}:{IMAGE_TAG}", DOCKERFILE_DIR
    ], check=True)

    full_image_uri = f"{ecr_uri}:{IMAGE_TAG}"

    print(f"🔁 Tagging image as {full_image_uri}")
    subprocess.run([
        "docker", "tag", f"{ECR_REPO_NAME}:{IMAGE_TAG}", full_image_uri
    ], check=True)

    print("🚀 Pushing image to ECR...")
    subprocess.run([
        "docker", "push", full_image_uri
    ], check=True)

    print("✅ Image pushed to ECR.")
    return full_image_uri

def register_task_definition(image_uri):
    print("📦 Registering ECS task definition...")
    response = ecs_client.register_task_definition(
        family=ECS_TASK_DEF_NAME,
        taskRoleArn=TASK_ROLE_ARN,
        executionRoleArn=EXECUTION_ROLE_ARN,
        requiresCompatibilities=["FARGATE"],
        networkMode="awsvpc",
        cpu="256",
        memory="512",
        containerDefinitions=[
            {
                "name": "app",
                "image": image_uri,
                "essential": True,
                "portMappings": [{"containerPort": 80}]
            }
        ]
    )
    print("✅ Task definition registered.")
    return response["taskDefinition"]["taskDefinitionArn"]

def stop_running_tasks(cluster_name, task_family):
    print("⏳ Stopping existing running tasks...")
    tasks = ecs_client.list_tasks(cluster=cluster_name, family=task_family, desiredStatus='RUNNING')['taskArns']
    if not tasks:
        print("No running tasks found.")
        return
    for task_arn in tasks:
        print(f"Stopping task: {task_arn}")
        ecs_client.stop_task(cluster=cluster_name, task=task_arn, reason="Deploying new task definition")
    print("✅ All running tasks stopped.")

def run_new_task(cluster_name, task_def_arn, subnets, security_groups):
    print("🚀 Running new Fargate task...")
    response = ecs_client.run_task(
        cluster=cluster_name,
        launchType='FARGATE',
        taskDefinition=task_def_arn,
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': subnets,
                'securityGroups': security_groups,
                'assignPublicIp': 'ENABLED'
            }
        }
    )
    failures = response.get('failures')
    if failures:
        print(f"❌ Failed to run task: {failures}")
        sys.exit(1)
    print("✅ New task started.")
    return response

# === NEW ENHANCEMENTS START HERE ===

def update_eventbridge_target(rule_name, new_task_def_arn):
    """
    Update EventBridge scheduled task rule with new task definition ARN.
    """
    print("🔄 Updating EventBridge rule to use latest task definition...")
    targets = events_client.list_targets_by_rule(Rule=rule_name)["Targets"]
    updated_targets = []

    for target in targets:
        if "EcsParameters" in target:
            target["EcsParameters"]["TaskDefinitionArn"] = new_task_def_arn
            updated_targets.append(target)

    if updated_targets:
        events_client.put_targets(Rule=rule_name, Targets=updated_targets)
        print("✅ EventBridge rule updated with new task definition.")
    else:
        print("⚠️ No ECS-compatible targets found for this rule.")

def get_file_timestamp_pattern(prefix):
    """
    Returns a compiled regex pattern that matches timestamped JSON files.
    Example match: java-2025-07-29T16-45.json
    """
    pattern = re.compile(prefix + r"-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2})\.json")
    return pattern

# === MAIN EXECUTION ===

if __name__ == "__main__":
    try:
        ecr_uri = get_or_create_ecr_repo(ECR_REPO_NAME)
        get_ecr_login()
        full_image_uri = build_and_push_docker_image(ecr_uri)
        task_def_arn = register_task_definition(full_image_uri)
        print(f"🆕 Registered new Task Definition ARN: {task_def_arn}")

        stop_running_tasks(ECS_CLUSTER_NAME, ECS_TASK_DEF_NAME)
        run_new_task(ECS_CLUSTER_NAME, task_def_arn, SUBNETS, SECURITY_GROUPS)

        # Optional: Uncomment to update EventBridge rule
        # update_eventbridge_target(EVENTBRIDGE_RULE_NAME, task_def_arn)

        print("🎉 Deployment and task replacement completed successfully.")

    except subprocess.CalledProcessError as e:
        print(f"❌ Subprocess error: {e}")
        sys.exit(1)
    except Exception as ex:
        print(f"❌ General error: {ex}")
        sys.exit(1)

