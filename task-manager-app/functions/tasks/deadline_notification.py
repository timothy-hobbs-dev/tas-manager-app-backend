import json
import boto3
import logging
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')
events_client = boto3.client('events')

TABLE_NAME = os.environ.get('TABLE_NAME')
TASKS_DEADLINE_TOPIC_ARN = os.environ.get('TASKS_DEADLINE_TOPIC_ARN')

def lambda_handler(event, context):
    try:
        task_id = event['taskId']
        assignee_email = event['assignee_email']

        # Get task details from DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        response = table.get_item(Key={'TaskId': task_id})
        
        if 'Item' not in response:
            logger.warning(f"Task {task_id} not found")
            return
            
        task = response['Item']
        
        # Only send notification if task is still open
        if task['status'] != 'open':
            logger.info(f"Task {task_id} is not open, skipping notification")
            return

        # Create notification message
        message = f"""
⚠️ Upcoming Task Deadline Alert ⚠️

Your task is due in 1 hour!

Task Details:
- Title: {task.get('name', 'No title')}
- Description: {task.get('description', 'No description')}
- Due Date: {task.get('deadline', 'No deadline')}
- Task ID: {task_id}

Please ensure you complete this task before the deadline.
"""

        # Send SNS notification
        sns_client.publish(
            TopicArn=TASKS_DEADLINE_TOPIC_ARN,
            Message=message,
            Subject='⚠️ Task Due in 1 Hour!',
            MessageAttributes={
                'email': {
                    'DataType': 'String',
                    'StringValue': assignee_email
                }
            }
        )

        # Clean up the CloudWatch Events rule
        rule_name = f"task-deadline-{task_id}"
        events_client.remove_targets(
            Rule=rule_name,
            Ids=[f"task-deadline-notification-{task_id}"]
        )
        events_client.delete_rule(
            Name=rule_name
        )

        logger.info(f"Deadline notification sent for task {task_id}")

    except Exception as e:
        logger.error(f"Error sending deadline notification: {e}")
        raise