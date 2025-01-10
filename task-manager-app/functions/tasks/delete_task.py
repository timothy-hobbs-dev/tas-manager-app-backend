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
        user_groups = claims.get('cognito:groups', [])
        is_admin = 'admin' in user_groups
        
        if not is_admin:
            logger.warning("Unauthorized delete attempt")
            return {'statusCode': 403, 'body': json.dumps({'error': 'Unauthorized'})}

        # Parse the request body safely
        body = json.loads(event['body'])  # Fix: Parse the JSON string into a dictionary

        task_id = body.get('TaskId')  # Use .get() to avoid KeyError

        if not task_id:
            logger.warning("Invalid request: Missing TaskId")
            return {'statusCode': 400, 'body': json.dumps({'error': 'Invalid request: Missing TaskId'})}

        response = table.get_item(Key={'TaskId': task_id})

        if 'Item' not in response:
            logger.warning(f"Task not found: {task_id}")
            return {'statusCode': 404, 'body': json.dumps({'error': 'Task not found'})}

        table.delete_item(Key={'TaskId': task_id})
        logger.info(f"Task deleted successfully: {task_id}")

        return {'statusCode': 200, 'body': json.dumps({'message': 'Task deleted successfully'})}

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return {'statusCode': 400, 'body': json.dumps({'error': 'Invalid JSON format'})}

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Internal Server Error'})}
