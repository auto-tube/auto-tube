# test_polly.py
import boto3
import botocore # Import botocore to catch specific exceptions
import os
import sys
import traceback

print("--- Starting Polly Connection Test ---")

# Optional: Print environment variables to help debug credentials
# print(f"AWS_ACCESS_KEY_ID: {os.environ.get('AWS_ACCESS_KEY_ID')}")
# print(f"AWS_SECRET_ACCESS_KEY: {'*' * 5 if os.environ.get('AWS_SECRET_ACCESS_KEY') else 'Not Set'}") # Mask secret key
# print(f"AWS_DEFAULT_REGION: {os.environ.get('AWS_DEFAULT_REGION')}")
# print(f"AWS_PROFILE: {os.environ.get('AWS_PROFILE')}")
# print("-" * 20)

polly_client = None
success = False

try:
    # Initialize client - specify region explicitly if needed, otherwise uses default
    # region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1') # Example getting region
    # print(f"Attempting to create Polly client in region: {region}")
    # polly_client = boto3.client('polly', region_name=region)
    polly_client = boto3.client('polly') # Uses default region from config/env

    print("Attempting to call describe voices...")
    # Make a simple, low-cost API call to verify connection and permissions
    response = polly_client.describe_voices() # Limit results

    print("\nSUCCESS: Successfully connected to AWS Polly!")
    print("Able to describe voices. Credentials and permissions seem okay.")
    # print("Sample Voice Response Snippet:")
    print(response.get('Voices', 'No voices found in response')[0] if response.get('Voices') else "N/A")
    success = True

except botocore.exceptions.NoCredentialsError:
    print("\nERROR: AWS credentials not found.")
    print("Please configure credentials using 'aws configure', environment variables, or IAM roles.")
    traceback.print_exc(limit=1) # Print limited traceback
except botocore.exceptions.ClientError as e:
    # Handles errors like invalid region, access denied (might indicate permission issue)
    print(f"\nERROR: AWS Client Error connecting to Polly: {e}")
    if "invalid region" in str(e).lower():
         print("Hint: Check your configured AWS region name.")
    elif "access denied" in str(e).lower():
         print("Hint: Check the IAM permissions for your configured credentials.")
    traceback.print_exc(limit=1)
except ImportError:
    print("\nERROR: Failed to import boto3 or botocore.")
    print("Please ensure boto3 is installed in your virtual environment (`python -m pip install boto3`).")
except Exception as e:
    print(f"\nERROR: An unexpected error occurred: {e}")
    traceback.print_exc()

print("\n--- Polly Connection Test Finished ---")

# Optional: Exit with a specific code based on success/failure
# sys.exit(0 if success else 1)