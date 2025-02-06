import boto3
import json
import os

def lambda_handler(event, context):
    # Check if user is admin
    user_role = event['requestContext']['authorizer']['claims']['cognito:groups']
    if user_role != 'admin':
        return {
            'statusCode': 403,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True
            },
            'body': json.dumps({'message': 'Unauthorized - Admin access required'})
        }
    
    # Initialize Cognito Identity Provider client
    cognito_client = boto3.client('cognito-idp')
    
    try:
        users = []
        pagination_token = None
        
        # Keep fetching users until there are no more
        while True:
            if pagination_token:
                response = cognito_client.list_users(
                    UserPoolId=os.environ['COGNITO_USER_POOL_ID'],
                    PaginationToken=pagination_token
                )
            else:
                response = cognito_client.list_users(
                    UserPoolId=os.environ['COGNITO_USER_POOL_ID']
                )
            
            # Process each user
            for user in response['Users']:
                user_data = {
                    'username': user['Username'],
                    'status': user['UserStatus'],
                    'enabled': user['Enabled'],
                    'created': user['UserCreateDate'].isoformat(),
                    'attributes': {
                        attr['Name']: attr['Value'] 
                        for attr in user['Attributes']
                    }
                }
                users.append(user_data)
            
            # Check if there are more users to fetch
            if 'PaginationToken' in response:
                pagination_token = response['PaginationToken']
            else:
                break
                
        return {
            'statusCode': 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True
            },
            'body': json.dumps(users)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True
            },
            'body': json.dumps({'error': str(e)})
        }