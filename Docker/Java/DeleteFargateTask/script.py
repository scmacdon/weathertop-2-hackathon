import boto3
import time

"""
Script Name: ecs_cleanup.py

Description:
  This script performs a complete cleanup of an Amazon ECS (Fargate) environment in a specified AWS region.
  It stops and deletes all running ECS tasks, ECS services, deregisters all task definition revisions under
  a specific family name, and finally deletes the ECS cluster itself.

Prerequisites:
  - AWS credentials configured.
  - boto3 installed.
  - Sufficient IAM permissions.

Usage:
  python ecs_cleanup.py
"""

AWS_REGION = "us-east-1"
CLUSTER_NAME = "MyJavaWeathertopCluster"  # Fixed trailing space removed
TASK_DEFINITION_NAME = "WeathertopJava"

ecs = boto3.client("ecs", region_name=AWS_REGION)

def stop_and_delete_all_tasks():
    print("🔍 Listing all running tasks...")
    response = ecs.list_tasks(cluster=CLUSTER_NAME)
    task_arns = response.get("taskArns", [])

    if task_arns:
        print(f"🛑 Stopping {len(task_arns)} running task(s)...")
        for task_arn in task_arns:
            ecs.stop_task(cluster=CLUSTER_NAME, task=task_arn, reason="Cleanup before cluster deletion")
            print(f"🛑 Stopped task: {task_arn}")
        # Wait for tasks to stop
        print("⏳ Waiting 15 seconds for tasks to stop...")
        time.sleep(15)
    else:
        print("✅ No running tasks to stop.")

def stop_and_delete_services():
    print(f"🔍 Listing all services in cluster: {CLUSTER_NAME} ...")
    services = []
    paginator = ecs.get_paginator('list_services')
    for page in paginator.paginate(cluster=CLUSTER_NAME):
        services.extend(page['serviceArns'])

    if not services:
        print("✅ No services to stop or delete.")
        return

    print(f"🛑 Stopping and deleting {len(services)} service(s)...")

    # Scale down all services to 0 to stop running tasks
    for service_arn in services:
        print(f"🔄 Updating service {service_arn} desiredCount=0")
        ecs.update_service(cluster=CLUSTER_NAME, service=service_arn, desiredCount=0)

    # Wait until all running tasks are stopped for services
    print("⏳ Waiting for services to have 0 running tasks...")
    while True:
        all_stopped = True
        desc = ecs.describe_services(cluster=CLUSTER_NAME, services=services)
        for svc in desc['services']:
            running_count = svc.get('runningCount', 0)
            print(f"Service {svc['serviceName']} runningCount={running_count}")
            if running_count > 0:
                all_stopped = False
        if all_stopped:
            break
        time.sleep(5)

    # Delete all services now that tasks are stopped
    for service_arn in services:
        try:
            print(f"🗑️ Deleting service {service_arn}")
            ecs.delete_service(cluster=CLUSTER_NAME, service=service_arn, force=True)
        except ecs.exceptions.ClientError as e:
            print(f"⚠️ Failed to delete service {service_arn}: {e.response['Error']['Message']}")

    # Wait until services show status INACTIVE (deleted)
    print("⏳ Waiting for services to be INACTIVE...")
    while True:
        desc = ecs.describe_services(cluster=CLUSTER_NAME, services=services)
        active_services = [svc for svc in desc['services'] if svc['status'] != 'INACTIVE']
        if not active_services:
            break
        print(f"Services still active: {[svc['serviceName'] for svc in active_services]}")
        time.sleep(5)

    print("✅ All services stopped and deleted.")

def deregister_all_task_definitions():
    print(f"🧼 Deregistering all revisions of task definitions with family: {TASK_DEFINITION_NAME} ...")
    paginator = ecs.get_paginator('list_task_definitions')
    task_def_arns = []
    for page in paginator.paginate(familyPrefix=TASK_DEFINITION_NAME, sort='DESC'):
        task_def_arns.extend(page['taskDefinitionArns'])

    if not task_def_arns:
        print("⚠️ No task definitions found to deregister.")
        return

    for arn in task_def_arns:
        try:
            ecs.deregister_task_definition(taskDefinition=arn)
            print(f"✅ Deregistered: {arn}")
        except ecs.exceptions.ClientError as e:
            print(f"⚠️ Failed to deregister {arn}: {e.response['Error']['Message']}")

def delete_cluster():
    print(f"🧨 Deleting ECS cluster: {CLUSTER_NAME} ...")
    try:
        ecs.delete_cluster(cluster=CLUSTER_NAME)
        print("✅ ECS cluster deleted.")
    except ecs.exceptions.ClientError as e:
        print(f"⚠️ Failed to delete cluster: {e.response['Error']['Message']}")

if __name__ == "__main__":
    stop_and_delete_all_tasks()
    stop_and_delete_services()
    deregister_all_task_definitions()
    delete_cluster()

