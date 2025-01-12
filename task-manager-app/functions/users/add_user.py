import json
import boto3
import os
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
cognito_client = boto3.client('cognito-idp')
sns_client = boto3.client('sns')

# Environment variables
USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
TASKS_ASSIGNMENT_TOPIC_ARN = os.getenv('TASKS_ASSIGNMENT_TOPIC_ARN')
TASKS_DEADLINE_TOPIC_ARN = os.getenv('TASKS_DEADLINE_TOPIC_ARN')
CLOSED_TASKS_TOPIC_ARN = os.getenv('CLOSED_TASKS_TOPIC_ARN')
REOPENED_TASKS_TOPIC_ARN = os.getenv('REOPENED_TASKS_TOPIC_ARN')

def subscribe_to_topic_with_filter(email, topic_arn, topic_name):
    """
    Subscribe a user to an SNS topic with email-specific filtering
    """
    try:
        # Create subscription with filter policy
        response = sns_client.subscribe(
            TopicArn=topic_arn,
            Protocol='email',
            Endpoint=email,
            Attributes={
                'FilterPolicy': json.dumps({
                    'email': [email]
                })
            }
        )
        logger.info(f"Successfully subscribed {email} to {topic_name} with filter policy")
        return response['SubscriptionArn']
    except Exception as e:
        logger.error(f"Error subscribing {email} to {topic_name}: {str(e)}")
        raise

def subscribe_to_all_topics(email):
    """
    Subscribe user to all notification topics with appropriate filters
    """
    topic_configs = [
        (TASKS_ASSIGNMENT_TOPIC_ARN, "Task Assignments"),
        (TASKS_DEADLINE_TOPIC_ARN, "Task Deadlines"),
        (CLOSED_TASKS_TOPIC_ARN, "Closed Tasks"),
        (REOPENED_TASKS_TOPIC_ARN, "Reopened Tasks")
    ]
    
    subscription_results = []
    for topic_arn, topic_name in topic_configs:
        if topic_arn:  # Only attempt subscription if topic ARN is configured
            try:
                subscription_arn = subscribe_to_topic_with_filter(email, topic_arn, topic_name)
                subscription_results.append({
                    'topic': topic_name,
                    'status': 'success',
                    'arn': subscription_arn
                })
            except Exception as e:
                subscription_results.append({
                    'topic': topic_name,
                    'status': 'failed',
                    'error': str(e)
                })
                logger.error(f"Failed to subscribe to {topic_name}: {str(e)}")
                # Continue with other subscriptions even if one fails
                continue
    
    return subscription_results

def create_cognito_user(username, email, role, temporary_password):
    """
    Create a user in Cognito and assign them to appropriate group
    """
    try:
        # Create the user in Cognito
        response = cognito_client.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=username,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'}
            ],
            TemporaryPassword=temporary_password,
        )
        
        # Add user to appropriate group
        group_name = 'admin' if role == 'admin' else 'regular'
        cognito_client.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=group_name
        )
        
        return response
    except Exception as e:
        logger.error(f"Error creating Cognito user: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        # Parse and validate input
        body = json.loads(event['body'])
        username = body.get('username')
        email = body.get('email')
        role = body.get('role', 'user')
        temporary_password = body.get('password', "DefaultTemp123!")
        
        # Input validation
        if not username or not email:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing required fields: username and email are required'
                })
            }
        
        # Create user in Cognito
        cognito_response = create_cognito_user(username, email, role, temporary_password)
        
        # Subscribe to notification topics
        subscription_results = subscribe_to_all_topics(email)
        
        # Prepare success response
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'User created successfully',
                'username': username,
                'cognito_status': cognito_response['User']['UserStatus'],
                'subscriptions': subscription_results
            })
        }

    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'details': str(e)
            })
        }