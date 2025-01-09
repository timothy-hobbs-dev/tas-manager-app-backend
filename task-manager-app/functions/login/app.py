import os
import boto3
import json
import logging

# Initialize logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Cognito client
client = boto3.client("cognito-idp")

USER_POOL_ID = os.getenv("USER_POOL_ID")
CLIENT_ID = os.getenv("CLIENT_ID")

def lambda_handler(event, context):
    try:
        # Handle both string and dict body formats
        if isinstance(event["body"], str):
            body = json.loads(event["body"])
        else:
            body = event["body"]
            
        username = body["username"]
        password = body["password"]

        logger.info(f"Attempting login for user: {username}")

        # Authenticate the user
        response = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password
            },
            ClientId=CLIENT_ID
        )

        logger.info(f"User {username} logged in successfully.")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"  # Adjust this for production
            },
            "body": json.dumps({
                "message": "Login successful",
                "id_token": response["AuthenticationResult"]["IdToken"],
                "access_token": response["AuthenticationResult"]["AccessToken"],
                "refresh_token": response["AuthenticationResult"]["RefreshToken"]
            })
        }
    
    except client.exceptions.NotAuthorizedException:
        logger.error(f"Invalid credentials for user: {username}")
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid credentials"})
        }
    
    except client.exceptions.UserNotFoundException:
        logger.error(f"User not found: {username}")
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "User not found"})
        }
    
    except (KeyError, json.JSONDecodeError) as e:
        logger.error(f"Invalid request format: {str(e)}")
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid request format"})
        }
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error"})
        }