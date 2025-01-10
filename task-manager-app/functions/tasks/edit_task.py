import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TasksTable')

def lambda_handler(event, context):
    claims = event['requestContext']['authorizer']['claims']
    user_email = claims.get('email')
    user_groups = claims.get('cognito:groups', [])
    is_admin = 'admin' in user_groups

    task_update = json.loads(event['body'])
    task_id = task_update.pop('TaskId')

    response = table.get_item(Key={'TaskId': task_id})
    task = response.get('Item')

    if not task:
        return {'statusCode': 404, 'body': json.dumps({'error': 'Task not found'})}

    # Regular users can only edit 'status' and 'user_comment'
    if not is_admin and task['responsibility'] != user_email:
        return {'statusCode': 403, 'body': json.dumps({'error': 'Unauthorized'})}

    allowed_fields = ['status', 'user_comment'] if not is_admin else task_update.keys()
    task.update({k: v for k, v in task_update.items() if k in allowed_fields})

    table.put_item(Item=task)
    return {'statusCode': 200, 'body': json.dumps({'message': 'Task updated successfully'})}
