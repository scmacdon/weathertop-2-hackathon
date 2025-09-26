"""
Script to run an AWS Fargate task using the Boto3 library.
This script performs the following actions:
1. Imports the Boto3 library for interacting with AWS services.
2. Defines constants for the AWS region, ECS cluster name, task definition, subnets, and security groups.
3. Creates an ECS client using Boto3, specifying the AWS region.
4. Defines a function `run_fargate_task` to:
- Run a Fargate task in the specified ECS cluster.
- Use the specified task definition.
- Launch the task in FARGATE mode.
- Specify the subnets and security groups for network configuration.
- Enable the assignment of a public IP address to the task.
- Check the response for task details or failures.
- Print the task ARN if the task starts successfully, or print failure details if the task fails to start.
5. Calls the `run_fargate_task` function when the script is executed directly.
Prerequisites:
- AWS credentials configured for Boto3 (e.g., via AWS CLI or environment variables).
- An ECS cluster with the specified name.
- A task definition with the specified name.
- The specified subnets and security groups must exist and be correctly configured.
Note:
- This script is designed to be run directly and will execute the `run_fargate_task` function.
- The task will be launched with a public IP address, allowing it to communicate with the internet.
"""

import boto3

AWS_REGION = "us-east-1"
CLUSTER_NAME = "MyKotlinWeathertopCluster"
TASK_DEFINITION = "WeathertopKotlin"
SUBNETS = ['subnet-03c28397a3a7cd314', 'subnet-06dde61595900f899']  # your public subnets
SECURITY_GROUPS = ["sg-0e357c99b6b13bf62"]

ecs = boto3.client("ecs", region_name=AWS_REGION)

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
        print("Failed to start task:", response.get("failures", []))
        return None
    task_arn = tasks[0]["taskArn"]
    print(f"Started task with ARN: {task_arn}")
    return task_arn

if __name__ == "__main__":
    run_fargate_task()
