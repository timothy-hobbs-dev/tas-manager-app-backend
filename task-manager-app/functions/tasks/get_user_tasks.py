import json
import boto3

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TasksTable')

def lambda_handler(event, context):
    claims = event['requestContext']['authorizer']['claims']
    user_email = claims['email']

    response = table.scan(FilterExpression=boto3.dynamodb.conditions.Attr('responsibility').eq(user_email))
    return {
        'statusCode': 200,
        "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True
            },
        'body': json.dumps(response['Items'])
    }
