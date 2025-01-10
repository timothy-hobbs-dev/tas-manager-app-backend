import json
import boto3
import uuid

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TasksTable')

def lambda_handler(event, context):
    claims = event['requestContext']['authorizer']['claims']
    user_email = claims['email']

    task = json.loads(event['body'])
    task['TaskId'] = str(uuid.uuid4())
    task['status'] = 'open'

    table.put_item(Item=task)
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Task assigned successfully!', 'TaskId': task['TaskId']})
    }
