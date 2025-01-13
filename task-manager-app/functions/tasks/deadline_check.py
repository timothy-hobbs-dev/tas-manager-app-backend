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
sqs = boto3.client('sqs')
events_client = boto3.client('events')

TABLE_NAME = os.environ.get('TABLE_NAME')
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
        
        # Only process if task is still open
        if task['status'] != 'open':
            logger.info(f"Task {task_id} is not open, skipping deadline check")
            return

        # Send task to SQS for processing
        sqs.send_message(
            QueueUrl=EXPIRED_TASKS_QUEUE_URL,
            MessageBody=json.dumps({
                'taskId': task_id,
                'assignee_email': assignee_email
            })
        )

        # Clean up the deadline rule
        rule_name = f"task-final-deadline-{task_id}"
        events_client.remove_targets(
            Rule=rule_name,
            Ids=[f"task-final-deadline-{task_id}"]
        )
        events_client.delete_rule(
            Name=rule_name
        )

        logger.info(f"Task {task_id} deadline reached, sent to processing queue")

    except Exception as e:
        logger.error(f"Error in deadline check handler: {e}")
        raise
