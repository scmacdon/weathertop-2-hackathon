import boto3
import json
import time
import os

# ==== CONFIG SECTION ====

LAMBDA_FUNCTION_NAME = "WeathertopGetNoTests"
JAR_FILE_PATH = "C:/Users/scmacdon/TestGit/Weathertop/target/Weathertop-1.0-SNAPSHOT.jar"
S3_BUCKET_NAME = "weathertop2"  # Replace with your bucket
S3_KEY = f"lambda/{os.path.basename(JAR_FILE_PATH)}"
IAM_ROLE_NAME = "LambdaS3ExecutionRole"
LAMBDA_HANDLER = "com.weathertop.lambda.SDKStatNoTests::handleRequest"  # Java-style handler
RUNTIME = "java21"
REGION = "us-east-1"

# ========================

iam = boto3.client("iam")
s3 = boto3.client("s3")
lambda_client = boto3.client("lambda", region_name=REGION)

def create_iam_role():
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    try:
        response = iam.create_role(
            RoleName=IAM_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy),
            Description="IAM Role for Lambda to access S3, ECS, and EventBridge"
        )
        role_arn = response['Role']['Arn']
        print("✅ Created IAM role:", role_arn)

        # Wait for role to propagate
        time.sleep(5)

    except iam.exceptions.EntityAlreadyExistsException:
        print(f"ℹ️ Role '{IAM_ROLE_NAME}' already exists. Fetching ARN...")
        role_arn = iam.get_role(RoleName=IAM_ROLE_NAME)['Role']['Arn']

    # Attach AWS managed policies (idempotent)
    managed_policies = [
        "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
        "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
    ]

    attached_policies = iam.list_attached_role_policies(RoleName=IAM_ROLE_NAME).get('AttachedPolicies', [])
    attached_arns = [p['PolicyArn'] for p in attached_policies]

    for policy_arn in managed_policies:
        if policy_arn not in attached_arns:
            print(f"Attaching managed policy {policy_arn} to role {IAM_ROLE_NAME}...")
            iam.attach_role_policy(RoleName=IAM_ROLE_NAME, PolicyArn=policy_arn)
        else:
            print(f"Managed policy {policy_arn} already attached.")

    # Define inline ECS + EventBridge read-only policy JSON
    inline_policy_name = "CustomECSAndEventBridgePolicy"
    inline_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ecs:Describe*",
                    "ecs:List*",
                    "ecs:ListClusters",
                    "ecs:ListContainerInstances",
                    "ecs:ListServices",
                    "ecs:ListTaskDefinitions",
                    "ecs:ListTasks"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "events:ListRules",
                    "events:DescribeRule",
                    "events:PutRule",
                    "events:PutTargets",
                    "events:RemoveTargets",
                    "events:DeleteRule"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:GetLogEvents",
                    "logs:FilterLogEvents"
                ],
                "Resource": "*"
            }
        ]
    }

    # Put or update the inline policy on the role
    print(f"Putting inline ECS+EventBridge policy '{inline_policy_name}' on role {IAM_ROLE_NAME}...")
    iam.put_role_policy(
        RoleName=IAM_ROLE_NAME,
        PolicyName=inline_policy_name,
        PolicyDocument=json.dumps(inline_policy_document)
    )

    print("✅ IAM role setup complete.")
    return role_arn

def upload_jar_to_s3():
    print(f"📤 Uploading {JAR_FILE_PATH} to s3://{S3_BUCKET_NAME}/{S3_KEY}")
    s3.upload_file(JAR_FILE_PATH, S3_BUCKET_NAME, S3_KEY)

def create_or_update_lambda(role_arn):
    try:
        print("🚀 Creating Lambda function...")
        lambda_client.create_function(
            FunctionName=LAMBDA_FUNCTION_NAME,
            Runtime=RUNTIME,
            Role=role_arn,
            Handler=LAMBDA_HANDLER,
            Code={"S3Bucket": S3_BUCKET_NAME, "S3Key": S3_KEY},
            Timeout=30,
            MemorySize=512,
            Publish=True
        )
    except lambda_client.exceptions.ResourceConflictException:
        print("ℹ️ Lambda already exists. Updating code and configuration...")
        lambda_client.update_function_code(
            FunctionName=LAMBDA_FUNCTION_NAME,
            S3Bucket=S3_BUCKET_NAME,
            S3Key=S3_KEY,
            Publish=True
        )
        lambda_client.update_function_configuration(
            FunctionName=LAMBDA_FUNCTION_NAME,
            Handler=LAMBDA_HANDLER,
            Role=role_arn,
            Runtime=RUNTIME,
            Timeout=30,
            MemorySize=512
        )

if __name__ == "__main__":
    role_arn = create_iam_role()
    upload_jar_to_s3()
    create_or_update_lambda(role_arn)
    print("✅ Lambda deployment complete.")

