import json
import boto3
import os

cognito_client = boto3.client('cognito-idp')
sns_client = boto3.client('sns')

USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
TASKS_ASSIGNMENT_TOPIC_ARN = os.getenv('TASKS_ASSIGNMENT_TOPIC_ARN')
TASKS_DEADLINE_TOPIC_ARN = os.getenv('TASKS_DEADLINE_TOPIC_ARN')
CLOSED_TASKS_TOPIC_ARN = os.getenv('CLOSED_TASKS_TOPIC_ARN')
REOPENED_TASKS_TOPIC_ARN = os.getenv('REOPENED_TASKS_TOPIC_ARN')

def subscribe_to_topics(email):
    topics = [
        TASKS_ASSIGNMENT_TOPIC_ARN,
        TASKS_DEADLINE_TOPIC_ARN,
        CLOSED_TASKS_TOPIC_ARN,
        REOPENED_TASKS_TOPIC_ARN
    ]
    
    for topic_arn in topics:
        try:
            sns_client.subscribe(
                TopicArn=topic_arn,
                Protocol='email',
                Endpoint=email
            )
        except Exception as e:
            print(f"Error subscribing to topic {topic_arn}: {str(e)}")

def lambda_handler(event, context):
    try:
        body = json.loads(event['body'])
        username = body['username']
        email = body['email']
        role = body.get('role', 'user')  # Default role if not provided
        temporary_password = body.get('password', "DefaultTemp123!")  

        # Create Cognito user
        response = cognito_client.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=username,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'}
            ],
            TemporaryPassword=temporary_password,
        )

        # Add user to the appropriate group
        group_name = 'admin' if role == 'admin' else 'regular'
        cognito_client.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=group_name
        )

        # Subscribe user to SNS topics
        subscribe_to_topics(email)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'User created successfully and subscribed to notification topics',
                'username': username
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }