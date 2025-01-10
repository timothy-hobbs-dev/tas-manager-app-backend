import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TasksTable')

def lambda_handler(event, context):

    return {
        'statusCode': 200,
        'body': json.dumps(event),
        'context': json.dumps(context)
    }
