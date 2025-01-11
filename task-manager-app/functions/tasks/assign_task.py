import json
import boto3
import uuid
import logging
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB and SNS
try:
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('TasksTable')
    sns_client = boto3.client('sns')
except Exception as e:
    logger.error(f"Error initializing AWS services: {e}")
    raise

# Get SNS topic ARN from environment variable
TASKS_ASSIGNMENT_TOPIC_ARN = os.getenv('TASKS_ASSIGNMENT_TOPIC_ARN')

def send_task_notification(task, assignee_email):
    try:
        # Create a formatted message
        message = {
            'taskId': task['TaskId'],
            'title': task.get('title', 'No title'),
            'description': task.get('description', 'No description'),
            'dueDate': task.get('dueDate', 'No due date'),
            'priority': task.get('priority', 'No priority'),
            'assignee': assignee_email
        }

        # Convert message to string and format it for email
        email_message = f"""
New Task Assigned

Task Details:
- Title: {message['title']}
- Description: {message['description']}
- Due Date: {message['dueDate']}
- Priority: {message['priority']}
- Task ID: {message['taskId']}

Please log in to the system to view more details and start working on your task.
"""

        # Publish to SNS topic
        response = sns_client.publish(
            TopicArn=TASKS_ASSIGNMENT_TOPIC_ARN,
            Message=email_message,
            Subject='New Task Assignment',
            MessageAttributes={
                'email': {
                    'DataType': 'String',
                    'StringValue': assignee_email
                }
            }
        )
        logger.info(f"Notification sent successfully: {response['MessageId']}")
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        # Don't raise the exception - we don't want to fail the task creation if notification fails
        pass

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
        
        # Validate required fields
        required_fields = ['name', 'responsibility']
        missing_fields = [field for field in required_fields if field not in task]
        if missing_fields:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Missing required fields: {", ".join(missing_fields)}'})
            }

        # Generate TaskId and set status
        task['TaskId'] = str(uuid.uuid4())
        task['status'] = 'open'
        
        # Save task to DynamoDB
        table.put_item(Item=task)
        
        # Send notification to assignee
        send_task_notification(task, task['responsibility'])
        
        logger.info(f"Task assigned successfully: {task['TaskId']}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Task assigned successfully!',
                'TaskId': task['TaskId']
            })
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