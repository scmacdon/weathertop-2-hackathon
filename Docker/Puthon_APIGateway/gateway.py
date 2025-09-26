import boto3
import json
import time
import requests

def delete_api_gateway(apigateway, lambda_arn):
    print("🧹 Checking for existing APIs to delete...")
    apis = apigateway.get_rest_apis(limit=500)['items']
    for api in apis:
        api_id = api['id']
        api_name = api.get('name')
        try:
            resources = apigateway.get_resources(restApiId=api_id)['items']
            for resource in resources:
                resource_id = resource['id']
                methods = resource.get('resourceMethods', {})
                for method in methods:
                    integration = apigateway.get_integration(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=method
                    )
                    if lambda_arn in integration.get('uri', ''):
                        print(f"🗑️ Deleting existing API: {api_name} (ID: {api_id})")
                        apigateway.delete_rest_api(restApiId=api_id)
                        return
        except apigateway.exceptions.NotFoundException:
            continue
        except Exception as e:
            print(f"⚠️ Error while checking API {api_name}: {e}")

def call_api_endpoint(url):
    print(f"\n🔍 Testing API endpoint: {url}")
    try:
        response = requests.get(url, params={
            "taskDefinitionArnVal": "arn:aws:ecs:us-east-1:814548047983:task-definition/WeathertopJava:18",
            "clusterName": "MyJavaWeathertopCluster",
            "cron": "cron(59 23 ? * FRI *)"
        })
        print("🔁 Response status code:", response.status_code)
        print("📄 Response body:\n", response.text)
    except Exception as e:
        print("❌ Error invoking endpoint:", e)

def get_latest_lambda_logs(lambda_function_name):
    print(f"\n📂 Fetching recent logs for Lambda: {lambda_function_name}")
    logs = boto3.client('logs', region_name='us-east-1')
    log_group = f'/aws/lambda/{lambda_function_name}'
    try:
        response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        if not response['logStreams']:
            print("❌ No log streams found.")
            return
        stream_name = response['logStreams'][0]['logStreamName']
        events = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=stream_name,
            limit=20,
            startFromHead=False
        )
        print("📄 Latest Lambda logs:")
        for e in events['events']:
            print(e['message'])
    except Exception as e:
        print("❌ Failed to fetch Lambda logs:", e)

def create_api_gateway(apigateway, lambda_client, api_name, resource_path, lambda_function_name, lambda_arn, stage_name):
    # 1. Create REST API
    api_response = apigateway.create_rest_api(
        name=api_name,
        description='API for Weathertop2 WeathertopLangStats Lambda function'
    )
    api_id = api_response['id']
    print(f"✅ Created REST API with ID: {api_id}")

    # 2. Get Root Resource ID
    resources = apigateway.get_resources(restApiId=api_id)
    root_id = next(item['id'] for item in resources['items'] if item['path'] == '/')

    # 3. Create /stats Resource
    resource_response = apigateway.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart=resource_path
    )
    resource_id = resource_response['id']
    print(f"✅ Created resource '/{resource_path}' with ID: {resource_id}")

    # 4. Create GET Method
    apigateway.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='GET',
        authorizationType='NONE'
    )

    # 5. Integrate GET Method with Lambda
    apigateway.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='GET',
        type='AWS_PROXY',
        integrationHttpMethod='POST',
        uri=f'arn:aws:apigateway:us-east-1:lambda:path/2015-03-31/functions/{lambda_arn}/invocations'
    )

    # 6. Enable CORS
    apigateway.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='OPTIONS',
        authorizationType='NONE'
    )

    apigateway.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='OPTIONS',
        type='MOCK',
        requestTemplates={'application/json': '{"statusCode": 200}'}
    )

    apigateway.put_method_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='OPTIONS',
        statusCode='200',
        responseParameters={
            'method.response.header.Access-Control-Allow-Headers': False,
            'method.response.header.Access-Control-Allow-Methods': False,
            'method.response.header.Access-Control-Allow-Origin': False
        },
        responseModels={'application/json': 'Empty'}
    )

    apigateway.put_integration_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod='OPTIONS',
        statusCode='200',
        responseParameters={
            'method.response.header.Access-Control-Allow-Headers': "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'",
            'method.response.header.Access-Control-Allow-Methods': "'GET,OPTIONS'",
            'method.response.header.Access-Control-Allow-Origin': "'*'"
        },
        responseTemplates={'application/json': ''}
    )

    # 7. Deploy the API
    apigateway.create_deployment(
        restApiId=api_id,
        stageName=stage_name
    )
    print(f"✅ Deployed API to stage: {stage_name}")

    # Enable logging on the stage
    try:
        apigateway.update_stage(
            restApiId=api_id,
            stageName=stage_name,
            patchOperations=[
                {'op': 'replace', 'path': '/*/*/logging/loglevel', 'value': 'INFO'},
                {'op': 'replace', 'path': '/*/*/metrics/enabled', 'value': 'true'}
            ]
        )
        print("✅ Enabled API Gateway stage logging.")
    except Exception as e:
        print(f"⚠️ Failed to enable stage logging: {e}")

    # Grant permission to API Gateway
    lambda_client.add_permission(
        FunctionName=lambda_function_name,
        StatementId='APIGatewayInvokePermission',
        Action='lambda:InvokeFunction',
        Principal='apigateway.amazonaws.com',
        SourceArn=f'arn:aws:execute-api:us-east-1:814548047983:{api_id}/*/GET/{resource_path}'
    )
    print("✅ Granted API Gateway invoke permission to Lambda.")

    invoke_url = f'https://{api_id}.execute-api.us-east-1.amazonaws.com/{stage_name}/{resource_path}'
    print(f"\n🚀 API Endpoint: {invoke_url}")

    return invoke_url

def main():
    apigateway = boto3.client('apigateway', region_name='us-east-1')
    lambda_client = boto3.client('lambda', region_name='us-east-1')

    api_name = 'Stats'
    resource_path = 'stats'
    lambda_function_name = 'WeathertopGetNoTests'
    lambda_arn = f'arn:aws:lambda:us-east-1:814548047983:function:{lambda_function_name}'
    stage_name = 'prod'

    # Always delete existing API using the Lambda
    delete_api_gateway(apigateway, lambda_arn)

    # Always create a new one
    print("🚀 Creating a new API Gateway...")
    invoke_url = create_api_gateway(
        apigateway, lambda_client, api_name, resource_path, lambda_function_name, lambda_arn, stage_name
    )

    call_api_endpoint(invoke_url)
    get_latest_lambda_logs(lambda_function_name)

if __name__ == "__main__":
    main()
