#deadline_warning.py
import json
import boto3
import logging
import os
from datetime import datetime
import pytz

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
sns_client = boto3.client('sns')
events_client = boto3.client('events')
sqs = boto3.client('sqs')

TABLE_NAME = os.environ.get('TABLE_NAME')
TASKS_DEADLINE_TOPIC_ARN = os.environ.get('TASKS_DEADLINE_TOPIC_ARN')
EXPIRED_TASKS_QUEUE_URL = os.environ.get('EXPIRED_TASKS_QUEUE_URL')

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

        # Schedule the actual deadline check
        deadline = datetime.fromisoformat(task['deadline'].replace('Z', '+00:00'))
        
        # Create a new rule for the actual deadline
        deadline_rule_name = f"task-final-deadline-{task_id}"
        
        cron_expression = (
            f"cron({deadline.minute} {deadline.hour} "
            f"{deadline.day} {deadline.month} ? {deadline.year})"
        )
        
        # Create the deadline rule
        events_client.put_rule(
            Name=deadline_rule_name,
            ScheduleExpression=cron_expression,
            State='ENABLED'
        )

        # Add target to the deadline rule
        events_client.put_targets(
            Rule=deadline_rule_name,
            Targets=[{
                'Id': f"task-final-deadline-{task_id}",
                'Arn': os.environ['DEADLINE_CHECK_FUNCTION_ARN'],
                'Input': json.dumps({
                    'taskId': task_id,
                    'assignee_email': assignee_email
                })
            }]
        )

    # Add permission for EventBridge to invoke the Lambda
        lambda_client = boto3.client('lambda')
        try:
            lambda_client.add_permission(
                FunctionName=os.environ['DEADLINE_CHECK_FUNCTION_NAME'],
                StatementId=f"EventBridge-{task['TaskId']}",
                Action='lambda:InvokeFunction',
                Principal='events.amazonaws.com',
                SourceArn=f"arn:aws:events:{os.environ['AWS_REGION']}:{os.environ['AWS_ACCOUNT_ID']}:rule/{deadline_rule_name}"
            )
        except lambda_client.exceptions.ResourceConflictException:
            # Permission already exists, which is fine
            pass

        # Clean up the warning notification rule
        warning_rule_name = f"task-deadline-{task_id}"
        events_client.remove_targets(
            Rule=warning_rule_name,
            Ids=[f"task-deadline-notification-{task_id}"]
        )
        events_client.delete_rule(
            Name=warning_rule_name
        )

        logger.info(f"Deadline warning sent and final deadline scheduled for task {task_id}")

    except Exception as e:
        logger.error(f"Error in deadline warning handler: {e}")
        raise
