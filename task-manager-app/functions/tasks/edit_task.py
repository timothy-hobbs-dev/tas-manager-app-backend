import datetime
import json
import boto3
import logging
import os
from datetime import datetime, timedelta
import pytz

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS services
try:
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('TasksTable')
    sns_client = boto3.client('sns')
    events_client = boto3.client('events')
except Exception as e:
    logger.error(f"Error initializing AWS services: {e}")
    raise

def delete_task_event_rules(task_id):
    """Delete all existing EventBridge rules for a task"""
    try:
        # Define rule names
        warning_rule_name = f"task-deadline-{task_id}"
        final_rule_name = f"task-final-deadline-{task_id}"
        
        for rule_name in [warning_rule_name, final_rule_name]:
            try:
                # Remove targets from the rule
                events_client.remove_targets(
                    Rule=rule_name,
                    Ids=[f"task-deadline-notification-{task_id}"]
                )
                
                # Delete the rule
                events_client.delete_rule(
                    Name=rule_name
                )
                
                logger.info(f"Successfully deleted event rule {rule_name} for task {task_id}")
            except events_client.exceptions.ResourceNotFoundException:
                # Rule doesn't exist, which is fine
                logger.info(f"Rule {rule_name} not found for task {task_id}")
            except Exception as e:
                logger.error(f"Error deleting rule {rule_name}: {e}")
                raise
                
    except Exception as e:
        logger.error(f"Error in delete_task_event_rules: {e}")
        raise

def schedule_deadline_notification(task, context):
    try:
        if 'deadline' not in task:
            logger.info("No deadline set for task, skipping notification scheduling")
            return

        try:
            # Parse the deadline and make it timezone-aware if it isn't already
            due_date = datetime.fromisoformat(task['deadline'].replace('Z', '+00:00'))
            if due_date.tzinfo is None:
                due_date = pytz.UTC.localize(due_date)
            
            # Get current time in UTC
            current_time = datetime.now(pytz.UTC)
            
            if due_date <= current_time:
                logger.error("Deadline must be in the future")
                return
            
            # Calculate notification time (1 hour before deadline)
            notification_time = due_date - timedelta(minutes=2)
            
            # Create a CloudWatch Events rule
            rule_name = f"task-deadline-{task['TaskId']}"
            
            # Format the cron expression using UTC time
            cron_expression = (
                f"cron({notification_time.minute} {notification_time.hour} "
                f"{notification_time.day} {notification_time.month} ? {notification_time.year})"
            )
            
            logger.info(f"Creating EventBridge rule with expression: {cron_expression}")
            
            # Create the rule
            events_client.put_rule(
                Name=rule_name,
                ScheduleExpression=cron_expression,
                State='ENABLED'
            )

            deadline_function_name = os.environ.get('TASKS_DEADLINE_FUNCTION_NAME')
            if not deadline_function_name:
                logger.error("TASKS_DEADLINE_FUNCTION_NAME environment variable not set")
                raise ValueError("Missing required environment variable: TASKS_DEADLINE_FUNCTION_NAME")

            # Create the Lambda target
            target_lambda_arn = os.environ.get('TASKS_DEADLINE_FUNCTION_ARN')
            if not target_lambda_arn:
                logger.error("TASKS_DEADLINE_FUNCTION_ARN environment variable not set")
                raise ValueError("Missing required environment variable: TASKS_DEADLINE_FUNCTION_ARN")
            
            logger.info(f"Setting target Lambda ARN: {target_lambda_arn}")

            # Add target to the rule
            events_client.put_targets(
                Rule=rule_name,
                Targets=[{
                    'Id': f"task-deadline-notification-{task['TaskId']}",
                    'Arn': target_lambda_arn,
                    'Input': json.dumps({
                        'taskId': task['TaskId'],
                        'assignee_email': task['responsibility']
                    })
                }]
            )

            # Add permission for EventBridge to invoke the Lambda
            lambda_client = boto3.client('lambda')
            try:
                lambda_client.add_permission(
                    FunctionName=deadline_function_name,
                    StatementId=f"EventBridge-{task['TaskId']}",
                    Action='lambda:InvokeFunction',
                    Principal='events.amazonaws.com',
                    SourceArn=f"arn:aws:events:{os.environ['AWS_REGION']}:{os.environ['AWS_ACCOUNT_ID']}:rule/{rule_name}"
                )
            except lambda_client.exceptions.ResourceConflictException:
                # Permission already exists, which is fine
                pass

            logger.info(f"Successfully scheduled deadline notification for task {task['TaskId']} at {notification_time} UTC")

        except ValueError as ve:
            logger.error(f"Invalid deadline format or missing environment variable: {ve}")
            return
            
    except Exception as e:
        logger.error(f"Error scheduling deadline notification: {e}")
        raise

def send_task_reassignment_notification(task, admin_email):
    """Send notification when task is reassigned"""
    topic_arn = os.environ.get('TASKS_ASSIGNMENT_TOPIC_ARN')
    if not topic_arn:
        logger.error("Cannot send notification: SNS Topic ARN is not configured")
        return

    try:
        assignee_email = task["responsibility"]
        message = {
            'taskId': task['TaskId'],
            'title': task.get('name', 'No title'),
            'description': task.get('description', 'No description'),
            'deadline': task.get('deadline', 'No deadline'),
            'assigned_by': admin_email,
            'responsibility': assignee_email
        }

        email_message = f"""
Task Reassigned

Task Details:
- Title: {message['title']}
- Description: {message['description']}
- Due Date: {message['deadline']}
- Task ID: {message['taskId']}
- Reassigned by: {message['assigned_by']}

Please log in to the system to view more details and start working on your task.
"""
        
        sns_client.publish(
            TopicArn=topic_arn,
            Message=email_message,
            Subject='Task Reassignment',
            MessageAttributes={
                'email': {
                    'DataType': 'String',
                    'StringValue': assignee_email
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error sending reassignment notification: {e}")
        raise

def send_task_reopened_notification(task, admin_email):
    """Send notification when task is reopened"""
    topic_arn = os.environ.get('REOPENED_TASKS_TOPIC_ARN')
    if not topic_arn:
        logger.error("Cannot send notification: SNS Topic ARN is not configured")
        return

    try:
        assignee_email = task["responsibility"]
        message = {
            'taskId': task['TaskId'],
            'title': task.get('name', 'No title'),
            'reopened_by': admin_email,
            'responsibility': assignee_email
        }

        email_message = f"""
Task Reopened

Task Details:
- Title: {message['title']}
- Task ID: {message['taskId']}
- Reopened by: {message['reopened_by']}

This task has been reopened and requires your attention.
"""
        
        sns_client.publish(
            TopicArn=topic_arn,
            Message=email_message,
            Subject='Task Reopened',
            MessageAttributes={
                'email': {
                    'DataType': 'String',
                    'StringValue': assignee_email
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error sending reopened notification: {e}")
        raise

def send_task_completed_notification(task, user_email):
    """Send notification when task is completed"""
    topic_arn = os.environ.get('TASKS_COMPLETE_TOPIC_ARN')
    if not topic_arn:
        logger.error("Cannot send notification: SNS Topic ARN is not configured")
        return

    try:
        message = {
            'taskId': task['TaskId'],
            'title': task.get('name', 'No title'),
            'completed_by': user_email,
            'completed_at': task.get('completed_at', str(datetime.now(pytz.UTC)))
        }

        email_message = f"""
Task Completed

Task Details:
- Title: {message['title']}
- Task ID: {message['taskId']}
- Completed by: {message['completed_by']}
- Completed at: {message['completed_at']}

This task has been marked as completed.
"""
        
        # Send to admin topic
        sns_client.publish(
            TopicArn=topic_arn,
            Message=email_message,
            Subject='Task Completed'
        )
        
    except Exception as e:
        logger.error(f"Error sending completion notification: {e}")
        raise

def lambda_handler(event, context):
    try:
        # Get user claims from authorizer
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        user_email = claims.get('email')
        user_groups = claims.get('cognito:groups', [])
        is_admin = 'admin' in user_groups
        
        if not user_email:
            logger.warning("Unauthorized access attempt: Missing email claim")
            return {
                'statusCode': 401,
                    'headers': {
                        'Content-Type': 'application/json'
                    },
                    'body': json.dumps({'error': 'Unauthorized'})
                }
        
        # Parse request body
        task_update = json.loads(event.get('body', '{}'))
        task_id = task_update.pop('TaskId', None)
        
        if not task_id:
            logger.warning("Invalid request: Missing TaskId")
            return {'statusCode': 400, 'body': json.dumps({'error': 'Invalid request: Missing TaskId'})}
        
        # Get existing task
        response = table.get_item(Key={'TaskId': task_id})
        task = response.get('Item')
        
        if not task:
            logger.warning(f"Task not found: {task_id}")
            return {'statusCode': 404, 'body': json.dumps({'error': 'Task not found'})}
        
        # Check permissions
        if not is_admin and task['responsibility'] != user_email:
            logger.warning(f"Unauthorized update attempt by {user_email} on task {task_id}")
            return {'statusCode': 403, 'body': json.dumps({'error': 'Unauthorized'})}
        
        # Handle deadline updates (admin only)
        if is_admin and 'deadline' in task_update:
            try:
                due_date = datetime.fromisoformat(task_update['deadline'].replace('Z', '+00:00'))

                # Ensure it's timezone-aware
                if due_date.tzinfo is None:
                    due_date = pytz.UTC.localize(due_date)

                if due_date <= datetime.now(pytz.UTC) + timedelta(minutes=2):
                    return {
                        'statusCode': 400,
                        'body': json.dumps({'error': 'Deadline must be in the future'})
                    }
            except ValueError:
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json'
                    },
                    'body': json.dumps({'error': 'Invalid deadline format. Use ISO format (e.g., 2025-01-11T18:00:00Z)'})
                }
            
            # Delete existing event rules
            delete_task_event_rules(task_id)
            task['deadline'] = task_update['deadline']
            # Reschedule deadline notification
            schedule_deadline_notification(task, context)
        
        # Handle task reassignment (admin only)
        if is_admin and 'responsibility' in task_update and task_update['responsibility'] != task['responsibility']:
            # Delete existing event rules
            delete_task_event_rules(task_id)
            
            # Update task assignment
            task['responsibility'] = task_update['responsibility']
            
            # Send reassignment notification
            send_task_reassignment_notification(task, user_email)

            schedule_deadline_notification(task, context)

            
        
        # Handle task reopening (admin only)
        if is_admin and task_update.get('status') == 'open' and task['status'] in ['completed', 'expired']:
            task['status'] = 'open'
            send_task_reopened_notification(task, user_email)
            
        
        # Handle task completion
        if task_update.get('status') == 'completed' and task['status'] != 'completed':
            task['status'] = 'completed'
            task['completed_at'] = str(datetime.now(pytz.UTC))
            send_task_completed_notification(task, user_email)
            
            # Delete both deadline event rules
            delete_task_event_rules(task_id)
        
        # Update allowed fields based on role
        allowed_fields = ['status', 'comment'] if not is_admin else task_update.keys()
        task.update({k: v for k, v in task_update.items() if k in allowed_fields})
        
        # Save updated task
        table.put_item(Item=task)
        logger.info(f"Task updated successfully: {task_id}")
        
        return {'statusCode': 200,
        'headers':{
            'Content-Type': 'application/json'
        } 'body': json.dumps({'message': 'Task updated successfully'})}
    
    except json.JSONDecodeError:
        logger.error("Error decoding JSON request body")
        return {
            'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json'
                },
            'body': json.dumps({'error': 'Invalid JSON format'})
            }
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json'
                }, 'body': json.dumps({'error': 'Internal Server Error'})
        }