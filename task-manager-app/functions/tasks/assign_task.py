import json
import boto3
import uuid
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
        
        if not user_email:
            logger.warning("Unauthorized access attempt: Missing email claim")
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Unauthorized'})
            }
        
        task = json.loads(event.get('body', '{}'))
        if not task:
            logger.warning("Invalid request: Missing task data")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid request: Missing task data'})
            }
        
        task['TaskId'] = str(uuid.uuid4())
        task['status'] = 'open'
        table.put_item(Item=task)
        
        logger.info(f"Task assigned successfully: {task['TaskId']}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Task assigned successfully!', 'TaskId': task['TaskId']})
        }
    
    except json.JSONDecodeError:
        logger.error("Error decoding JSON request body")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON format'})
        }
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal Server Error'})
        }
