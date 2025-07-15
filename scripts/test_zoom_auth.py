#!/usr/bin/env python3
"""
Script to test the OAuth authentication with Zoom API.
This script will:
1. Get an OAuth token from Zoom API
2. Test the token by making simple API calls
3. Check if the token has the necessary permissions to access recordings
"""

import os
import sys
import json
import logging
import argparse
import requests
from datetime import datetime, timedelta

# Add the parent directory to the path so we can import from the app
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

import config

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def force_new_oauth_token(account_type="primary"):
    """
    Force getting a new OAuth token directly from Zoom API.
    
    Args:
        account_type: Type of account to use ("primary" or "personal")
        
    Returns:
        OAuth token as string
    """
    try:
        if account_type == "personal" and config.PERSONAL_ZOOM_CLIENT_ID and config.PERSONAL_ZOOM_CLIENT_SECRET and config.PERSONAL_ZOOM_ACCOUNT_ID:
            client_id = config.PERSONAL_ZOOM_CLIENT_ID
            client_secret = config.PERSONAL_ZOOM_CLIENT_SECRET
            account_id = config.PERSONAL_ZOOM_ACCOUNT_ID
        else:
            client_id = config.ZOOM_CLIENT_ID
            client_secret = config.ZOOM_CLIENT_SECRET
            account_id = config.ZOOM_ACCOUNT_ID
        
        url = "https://zoom.us/oauth/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "account_credentials",
            "account_id": account_id,
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        logger.info(f"Requesting new access token from {url}")
        logger.debug(f"Request data: {json.dumps(data)}")
        
        response = requests.post(url, headers=headers, data=data)
        logger.info(f"Response status code: {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Failed to get access token: {response.text}")
            return None
            
        result = response.json()
        token = result["access_token"]
        
        logger.info("New access token received")
        logger.info(f"Token type: {result['token_type']}")
        logger.info(f"Expires in: {result['expires_in']} seconds")
        
        # Log scopes
        scopes = result.get("scope", "").split(" ")
        logger.info(f"OAuth scopes: {', '.join(scopes)}")
        
        # Check if the required scope is present
        required_scope = "cloud_recording:read:list_account_recordings:master"
        if required_scope in scopes:
            logger.info(f"Required scope '{required_scope}' is present!")
        else:
            logger.warning(f"Required scope '{required_scope}' is NOT present in the token!")
            
        return token
    except Exception as e:
        logger.error(f"Error getting OAuth token: {e}")
        return None

def test_oauth_token(account_type="primary"):
    """
    Test the OAuth token by making a simple API call.
    
    Args:
        account_type: Type of account to use ("primary" or "personal")
    """
    # Force getting a new token
    token = force_new_oauth_token(account_type)
    if not token:
        logger.error("Failed to get OAuth token")
        return False
        
    logger.info(f"Successfully got OAuth token: {token[:20]}...")
    
    # Test token with a simple API call
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Try to get user list
    url = f"{config.ZOOM_BASE_URL}/users"
    logger.info(f"Testing token with API call to {url}")
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        users = response.json().get("users", [])
        logger.info(f"API call successful! Found {len(users)} users")
    else:
        logger.error(f"API call failed: {response.status_code} - {response.text}")
        return False
    
    # Test if we can access recordings
    if account_type == "personal" and config.PERSONAL_ZOOM_ACCOUNT_ID:
        account_id = config.PERSONAL_ZOOM_ACCOUNT_ID
    else:
        account_id = config.ZOOM_ACCOUNT_ID
        
    # Get yesterday's date
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Try to get recordings from account-level endpoint
    url = f"{config.ZOOM_BASE_URL}/accounts/{account_id}/recordings"
    params = {
        "from": yesterday,
        "to": yesterday,
        "page_size": 10,
        "include_fields": "ai_summary"
    }
    
    logger.info(f"Testing if we can access recordings: {url}")
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        meetings = response.json().get("meetings", [])
        logger.info(f"Successfully accessed recordings! Found {len(meetings)} meetings from yesterday")
        
        # Check if any meeting has AI summary
        ai_summaries = 0
        for meeting in meetings:
            if meeting.get("ai_summary"):
                ai_summaries += 1
        
        if ai_summaries > 0:
            logger.info(f"Found {ai_summaries} meetings with AI summaries")
        else:
            logger.info("No AI summaries found in the meetings")
            
        # Try to get a specific meeting's recordings if any meetings were found
        if meetings:
            meeting_uuid = meetings[0].get("uuid")
            if meeting_uuid:
                url = f"{config.ZOOM_BASE_URL}/meetings/{meeting_uuid}/recordings"
                params = {"include_fields": "ai_summary"}
                
                logger.info(f"Testing if we can access a specific meeting's recordings: {url}")
                response = requests.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    logger.info("Successfully accessed specific meeting recordings!")
                    
                    # Check if meeting has AI summary
                    meeting_data = response.json()
                    if meeting_data.get("ai_summary"):
                        logger.info("Meeting has AI summary!")
                    else:
                        logger.info("Meeting does not have AI summary")
                else:
                    logger.warning(f"Failed to access specific meeting recordings: {response.status_code} - {response.text}")
        
        return True
    else:
        logger.error(f"Failed to access recordings: {response.status_code} - {response.text}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test OAuth authentication with Zoom API")
    parser.add_argument("--account", type=str, choices=["primary", "personal", "both"], default="both", help="Which Zoom account to test")
    
    args = parser.parse_args()
    
    if args.account == "both" or args.account == "primary":
        logger.info("Testing primary account")
        primary_result = test_oauth_token("primary")
        logger.info(f"Primary account test result: {'SUCCESS' if primary_result else 'FAILURE'}")
        
    if args.account == "both" or args.account == "personal":
        if config.PERSONAL_ZOOM_CLIENT_ID and config.PERSONAL_ZOOM_CLIENT_SECRET and config.PERSONAL_ZOOM_ACCOUNT_ID:
            logger.info("Testing personal account")
            personal_result = test_oauth_token("personal")
            logger.info(f"Personal account test result: {'SUCCESS' if personal_result else 'FAILURE'}")
        else:
            logger.warning("Personal account credentials not configured, skipping test") 