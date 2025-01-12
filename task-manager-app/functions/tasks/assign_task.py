import json
import boto3
import uuid
import logging
import os
from datetime import datetime, timedelta
import pytz  # Add this import for timezone handling


# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS services
try:
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ.get('TABLE_NAME', 'TasksTable')
    table = dynamodb.Table(table_name)
    sns_client = boto3.client('sns')
    events_client = boto3.client('events')
except Exception as e:
    logger.error(f"Error initializing AWS services: {e}")
    raise

# Get SNS topic ARNs from environment variables
TASKS_ASSIGNMENT_TOPIC_ARN = os.environ.get('TASKS_ASSIGNMENT_TOPIC_ARN')
TASKS_DEADLINE_TOPIC_ARN = os.environ.get('TASKS_DEADLINE_TOPIC_ARN')

def schedule_deadline_notification(task, context):
    try:
        if 'deadline' in task:
            try:
                # Parse the deadline and make it timezone-aware if it isn't already
                due_date = datetime.fromisoformat(task['deadline'].replace('Z', '+00:00'))
                if due_date.tzinfo is None:
                    due_date = pytz.UTC.localize(due_date)
                
                # Get current time in UTC
                current_time = datetime.now(pytz.UTC)
                
                if due_date <= current_time:
                    return {
                        'statusCode': 400,
                        'body': json.dumps({'error': 'Deadline must be in the future'})
                    }
            except ValueError:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Invalid deadline format. Use ISO format (e.g., 2025-01-11T18:00:00Z)'})
                }

        # Create a CloudWatch Events rule
        rule_name = f"task-deadline-{task['TaskId']}"
        
        # Format the cron expression using UTC time
        cron_expression = (
            f"cron({notification_time.minute} {notification_time.hour} "
            f"{notification_time.day} {notification_time.month} ? {notification_time.year})"
        )
        
        events_client.put_rule(
            Name=rule_name,
            ScheduleExpression=cron_expression,
            State='ENABLED'
        )

        # Add target to the rule
        events_client.put_targets(
            Rule=rule_name,
            Targets=[{
                'Id': f"task-deadline-notification-{task['TaskId']}",
                'Arn': context.invoked_function_arn.replace(
                    context.function_name,
                    'TaskDeadlineNotificationFunction'
                ),
                'Input': json.dumps({
                    'taskId': task['TaskId'],
                    'assignee_email': task['responsibility']
                })
            }]
        )

        logger.info(f"Scheduled deadline notification for task {task['TaskId']} at {notification_time} UTC")

    except Exception as e:
        logger.error(f"Error scheduling deadline notification: {e}")
        
def send_task_notification(task, admin_email):
    if not TASKS_ASSIGNMENT_TOPIC_ARN:
        logger.error("Cannot send notification: SNS Topic ARN is not configured")
        return

    try:
        assignee_email = task["responsibility"]
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
- Assigned by: {message['assigned_by']}

Please log in to the system to view more details and start working on your task.
"""
        logger.info(f"Attempting to send notification to topic: {TASKS_ASSIGNMENT_TOPIC_ARN}")
        
        # Publish to SNS topic with message attributes for filtering
        response = sns_client.publish(
            TopicArn=TASKS_ASSIGNMENT_TOPIC_ARN,
            Message=email_message,
            Subject='New Task Assignment',
            MessageAttributes={
                'email': {
                    'DataType': 'String',
                    'StringValue': assignee_email
                }
            },
            MessageStructure='string'  # Explicitly set message structure
        )
        logger.info(f"Notification sent successfully: {response['MessageId']}")
        
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        logger.error(f"Topic ARN: {TASKS_ASSIGNMENT_TOPIC_ARN}")
        logger.error(f"Task: {json.dumps(task)}")
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
        
        # Validate required fields
        required_fields = ['name', 'responsibility']
        missing_fields = [field for field in required_fields if field not in task]
        if missing_fields:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Missing required fields: {", ".join(missing_fields)}'})
            }

        # Validate deadline format if provided
        if 'deadline' in task:
            try:
                due_date = datetime.fromisoformat(task['deadline'].replace('Z', '+00:00'))

                # Ensure it's timezone-aware
                if due_date.tzinfo is None:
                    due_date = pytz.UTC.localize(due_date)

                if due_date <= datetime.now(pytz.UTC):  # Compare with an aware datetime

                    return {
                        'statusCode': 400,
                        'body': json.dumps({'error': 'Deadline must be in the future'})
                    }
            except ValueError:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Invalid deadline format. Use ISO format (e.g., 2025-01-11T18:00:00Z)'})
                }

        # Generate TaskId and set status
        task['TaskId'] = str(uuid.uuid4())
        task['status'] = 'open'
        
        # Save task to DynamoDB
        table.put_item(Item=task)
        
        # Send notification to assignee
        send_task_notification(task, user_email)
        
        # Schedule deadline notification if deadline is set
        if 'deadline' in task:
            schedule_deadline_notification(task, context)
        
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