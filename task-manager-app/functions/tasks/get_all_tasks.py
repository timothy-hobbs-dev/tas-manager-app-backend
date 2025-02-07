import boto3
import json
from boto3.dynamodb.conditions import Attr, Key
from typing import Dict, Optional

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('TasksTable')

def parse_filter_params(query_params: Dict) -> Optional[str]:
    """Parse filter parameters from query string."""
    filter_expr = None
    valid_fields = {'status', 'responsibility', 'name', 'description'}
    
    for field in valid_fields:
        if field in query_params:
            value = query_params[field]
            condition = Attr(field).contains(value) if field == 'name' else Attr(field).eq(value)
            filter_expr = condition if filter_expr is None else filter_expr & condition
    
    return filter_expr


def get_sort_key(sort_param: str) -> str:
    """Validate and return sort key."""
    valid_sort_fields = {
        'completed_at', 'deadline', 'name', 'status',
        'responsibility', 'description'
    }
    
    # Default sort by deadline if invalid field provided
    field = sort_param.split(':')[0] if ':' in sort_param else sort_param
    return field if field in valid_sort_fields else 'deadline'

def lambda_handler(event, context):
    try:
        # Get user claims from authorizer
        claims = event['requestContext']['authorizer']['claims']
        user_groups = claims.get('cognito:groups', [])
        user_email = claims.get('email')
        is_admin = 'admin' in user_groups

        if not user_email:
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Credentials': True
                },
                'body': json.dumps({'message': 'Missing user email'})
            }

    except KeyError:
        return {
            'statusCode': 401,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Credentials': True
            },
            'body': json.dumps({'message': 'Missing authorization'})
        }

    # Parse query parameters
    query_params = event.get('queryStringParameters', {}) or {}
    
    # If not admin, force filter by user's email
    if not is_admin:
        query_params['responsibility'] = user_email
    
    # Pagination parameters
    limit = int(query_params.get('limit', 10))
    last_evaluated_key = json.loads(query_params.get('next_token', 'null'))
    
    # Sorting parameters
    sort_param = query_params.get('sort', 'deadline')
    sort_key = get_sort_key(sort_param)
    sort_desc = sort_param.endswith(':desc')
    
    # Build scan parameters
    scan_params = {
        'Limit': limit
    }
    
    # Add filters if present
    filter_expr = parse_filter_params(query_params)
    if filter_expr:
        scan_params['FilterExpression'] = filter_expr
    
    # Add pagination token if present
    if last_evaluated_key:
        scan_params['ExclusiveStartKey'] = last_evaluated_key

    # Perform scan
    response = table.scan(**scan_params)
    
    # Sort results
    items = response.get('Items', [])
    items.sort(
        key=lambda x: x.get(sort_key, ''),
        reverse=sort_desc
    )
    
    # Prepare response
    result = {
        'items': items,
        'count': len(items),
        'next_token': json.dumps(response.get('LastEvaluatedKey'))
            if 'LastEvaluatedKey' in response else None
    }
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Credentials': True
        },
        'body': json.dumps(result)
    }