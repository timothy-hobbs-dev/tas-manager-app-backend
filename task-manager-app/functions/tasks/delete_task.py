import boto3
import json

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TasksTable')

def lambda_handler(event, context):
    claims = event['requestContext']['authorizer']['claims']
    user_groups = claims.get('cognito:groups', [])
    is_admin = 'admin' in user_groups

    if not is_admin:
        return {'statusCode': 403, 'body': json.dumps({'error': 'Unauthorized'})}

    task_id = event['queryStringParameters']['TaskId']
    table.delete_item(Key={'TaskId': task_id})
    return {'statusCode': 200, 'body': json.dumps({'message': 'Task deleted successfully'})}
