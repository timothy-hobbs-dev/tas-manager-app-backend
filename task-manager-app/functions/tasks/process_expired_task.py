import json
import boto3
import logging
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
stepfunctions = boto3.client('stepfunctions')
sqs = boto3.client('sqs')

STEP_FUNCTION_ARN = os.environ['STEP_FUNCTION_ARN']

def lambda_handler(event, context):
    try:
        # Process SQS messages
        for record in event['Records']:
            # Parse the message
            message = json.loads(record['body'])
            task_id = message['taskId']
            
            # Start Step Function execution
            execution_input = {
                'taskId': task_id
            }
            
            response = stepfunctions.start_execution(
                stateMachineArn=STEP_FUNCTION_ARN,
                input=json.dumps(execution_input)
            )
            
            logger.info(f"Started Step Function execution for task {task_id}: {response['executionArn']}")
            
    except Exception as e:
        logger.error(f"Error processing expired task: {e}")
        raise