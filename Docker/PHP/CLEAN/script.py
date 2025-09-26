import boto3
import time

AWS_REGION = 'us-east-1'
AWS_ACCOUNT_ID = '814548047983'
ECR_REPO_NAME = 'weathertop-php-ecr-repo'
ECS_CLUSTER_NAME = 'MyPHPWeathertopCluster'

ecs = boto3.client('ecs', region_name=AWS_REGION)
ecr = boto3.client('ecr', region_name=AWS_REGION)

def delete_ecr_repo(repo_name):
    try:
        print(f"[ECR] Deleting repo '{repo_name}' and all images...")
        ecr.delete_repository(repositoryName=repo_name, force=True)
        print("[ECR] Deleted successfully.")
    except ecr.exceptions.RepositoryNotFoundException:
        print("[ECR] Repo does not exist, nothing to delete.")
    time.sleep(2)

def stop_all_tasks(cluster_name):
    paginator = ecs.get_paginator('list_tasks')
    tasks = []
    for page in paginator.paginate(cluster=cluster_name):
        tasks.extend(page['taskArns'])
    for task in tasks:
        print(f"[ECS] Stopping task: {task}")
        ecs.stop_task(cluster=cluster_name, task=task, reason="Cleanup before redeploy")
    time.sleep(2)

def deregister_all_task_definitions(family_name):
    paginator = ecs.get_paginator('list_task_definitions')
    for page in paginator.paginate(familyPrefix=family_name):
        for td in page['taskDefinitionArns']:
            print(f"[ECS] Deregistering task definition: {td}")
            ecs.deregister_task_definition(taskDefinition=td)

if __name__ == "__main__":
    delete_ecr_repo(ECR_REPO_NAME)
    stop_all_tasks(ECS_CLUSTER_NAME)
    deregister_all_task_definitions('WeathertopPhp')
    print("✅ Cleanup completed.")
