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
    table_name = os.environ.get('TABLE_NAME', 'TasksTable')
    table = dynamodb.Table(table_name)
    sns_client = boto3.client('sns')
except Exception as e:
    logger.error(f"Error initializing AWS services: {e}")
    raise

# Get SNS topic ARN from environment variable
TASKS_ASSIGNMENT_TOPIC_ARN = os.environ.get('TASKS_ASSIGNMENT_TOPIC_ARN')
if not TASKS_ASSIGNMENT_TOPIC_ARN:
    logger.error("TASKS_ASSIGNMENT_TOPIC_ARN environment variable is not set")

def send_task_notification(task, admin_email):
    if not TASKS_ASSIGNMENT_TOPIC_ARN:
        logger.error("Cannot send notification: SNS Topic ARN is not configured")
        return

    try:
        assignee_email =task["responsibility"]
        # Create a formatted message
        message = {
            'taskId': task['TaskId'],
            'title': task.get('name', 'No title'),
            'description': task.get('description', 'No description'),
            'comment': task.get('comment', 'No description'),
            'deadline': task.get('deadline', 'No deadline'),
            'assigned_by': admin_email,
            'responsibility': assignee_email
        }

        # Convert message to string and format it for email
        email_message = f"""
New Task Assigned

Task Details:
- Title: {message['title']}
- Description: {message['description']}
- Due Date: {message['deadline']}
- Task ID: {message['taskId']}
- Assigned by {message['assigned_by']}

Please log in to the system to view more details and start working on your task.
"""
        logger.info(f"Attempting to send notification to topic: {TASKS_ASSIGNMENT_TOPIC_ARN}")
        
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
        logger.error(f"Topic ARN: {TASKS_ASSIGNMENT_TOPIC_ARN}")
        logger.error(f"Task: {json.dumps(task)}")
        # Don't raise the exception - we don't want to fail the task creation if notification fails
        pass

# Rest of the lambda_handler remains the same...

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
        send_task_notification(task, user_email)
        
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