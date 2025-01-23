import boto3
import json

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TasksTable')

def lambda_handler(event, context):
    user_role = event['requestContext']['authorizer']['claims']['cognito:groups']
    if user_role != 'admin':
        return {'statusCode': 403, 'body': 'Unauthorized'}

    response = table.scan()
    return {'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps(response['Items'])}
