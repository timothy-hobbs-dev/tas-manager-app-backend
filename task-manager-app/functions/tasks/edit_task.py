#edit_task.py
import datetime
import json
import boto3
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB
try:
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('TasksTable')
except Exception as e:
    logger.error(f"Error initializing DynamoDB: {e}")
    raise

def lambda_handler(event, context):
    try:
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        user_email = claims.get('email')
        user_groups = claims.get('cognito:groups', [])
        is_admin = 'admin' in user_groups
        
        if not user_email:
            logger.warning("Unauthorized access attempt: Missing email claim")
            return {'statusCode': 401, 'body': json.dumps({'error': 'Unauthorized'})}
        
        task_update = json.loads(event.get('body', '{}'))
        task_id = task_update.pop('TaskId', None)
        
        if not task_id:
            logger.warning("Invalid request: Missing TaskId")
            return {'statusCode': 400, 'body': json.dumps({'error': 'Invalid request: Missing TaskId'})}
        
        response = table.get_item(Key={'TaskId': task_id})
        task = response.get('Item')
        
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return {'statusCode': 404, 'body': json.dumps({'error': 'Task not found'})}
        
        if not is_admin and task['responsibility'] != user_email:
            logger.warning(f"Unauthorized update attempt by {user_email} on task {task_id}")
            return {'statusCode': 403, 'body': json.dumps({'error': 'Unauthorized'})}
        
        allowed_fields = ['status', 'comment'] if not is_admin else task_update.keys()
        task.update({k: v for k, v in task_update.items() if k in allowed_fields})

        if task_update['status'] == 'completed':
            task['completed_at'] =str(datetime.now())

        
        table.put_item(Item=task)
        logger.info(f"Task updated successfully: {task_id}")
        
        return {'statusCode': 200, 'body': json.dumps({'message': 'Task updated successfully'})}
    
    except json.JSONDecodeError:
        logger.error("Error decoding JSON request body")
        return {'statusCode': 400, 'body': json.dumps({'error': 'Invalid JSON format'})}
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Internal Server Error'})}
