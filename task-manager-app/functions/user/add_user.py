import json
import boto3
import os

cognito_client = boto3.client('cognito-idp')

USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')

def lambda_handler(event, context):
    try:
        body = json.loads(event['body'])
        username = body['username']
        email = body['email']
        role = body.get('role', 'user')  # Default role if not provided
        temporary_password = body.get('password', "DefaultTemp123!")  

        response = cognito_client.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=username,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'custom:role', 'Value': role}
            ],
            TemporaryPassword=temporary_password,
            MessageAction='SUPPRESS'  # Prevents Cognito from sending an email
        )

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'User created successfully', 'username': username})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
