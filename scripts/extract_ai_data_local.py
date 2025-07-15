#!/usr/bin/env python3
"""
Script to extract AI summary and smart recording data for existing recordings and save them locally.
This script will:
1. Read the Zoom Recordings Report to get meeting UUIDs
2. Call the Zoom API with the include_fields=ai_summary parameter
3. Save the AI summary and smart recording data to a local folder
4. Print out the paths to the saved files
"""

import os
import sys
import json
import logging
import argparse
import asyncio
import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Add the parent directory to the path so we can import from the app
parent_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(parent_dir))

import config
from scripts.test_zoom_auth import force_new_oauth_token

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global variables
oauth_tokens = {}

def get_oauth_token(account_type: str = "primary") -> str:
    """
    Get OAuth token for the specified account type.
    
    Args:
        account_type: Type of Zoom account to use ("primary" or "personal")
        
    Returns:
        OAuth token
    """
    global oauth_tokens
    
    # If token is not cached or expired, get a new one
    if account_type not in oauth_tokens:
        oauth_tokens[account_type] = force_new_oauth_token(account_type)
        
    return oauth_tokens[account_type]

async def get_zoom_report_data() -> pd.DataFrame:
    """
    Get data from the Zoom Recordings Report.
    
    Returns:
        DataFrame containing the report data
    """
    # Get the report ID
    report_id = os.environ.get("ZOOM_REPORT_ID")
    if not report_id:
        logger.error("ZOOM_REPORT_ID not found in environment variables")
        return pd.DataFrame()
    
    logger.info(f"Using Zoom Report ID: {report_id}")
    
    # Set up Google Sheets API client
    credentials = service_account.Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE, 
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    sheets_service = build("sheets", "v4", credentials=credentials)
    
    # Get sheet names first
    sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=report_id).execute()
    sheets = sheet_metadata.get('sheets', '')
    if not sheets:
        logger.error("No sheets found in the spreadsheet")
        return pd.DataFrame()
    
    # Use the first sheet
    sheet_title = sheets[0]['properties']['title']
    logger.info(f"Using sheet: {sheet_title}")
    
    # Get the data
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=report_id,
        range=f"{sheet_title}"
    ).execute()
    values = result.get('values', [])
    
    if not values:
        logger.error("No data found in the spreadsheet")
        return pd.DataFrame()
    
    # Convert to DataFrame
    headers = values[0]
    data = values[1:]
    df = pd.DataFrame(data, columns=headers)
    
    logger.info(f"Found {len(df)} recordings in the report")
    
    return df

async def get_recording_info(meeting_uuid: str, account_type: str = "primary") -> Dict:
    """
    Get recording information from the Zoom API.
    
    Args:
        meeting_uuid: UUID of the meeting
        account_type: Type of Zoom account to use ("primary" or "personal")
        
    Returns:
        Dictionary with recording information
    """
    # Get OAuth token
    token = get_oauth_token(account_type)
    
    # Set up request
    url = f"{config.ZOOM_BASE_URL}/meetings/{meeting_uuid}/recordings"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    params = {
        "include_fields": "ai_summary"
    }
    
    # Make request
    try:
        logger.info(f"Getting recording info for meeting {meeting_uuid} with account {account_type}")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            logger.info(f"Successfully got recording info for meeting {meeting_uuid}")
            return response.json()
        else:
            logger.error(f"Failed to get recording info for meeting {meeting_uuid}: {response.status_code} {response.text}")
            return {}
    except Exception as e:
        logger.error(f"Error getting recording info for meeting {meeting_uuid}: {str(e)}")
        return {}

async def download_ai_summary_files(meeting_uuid: str, recording_data: Dict, output_dir: str, account_type: str = "primary") -> Dict[str, str]:
    """
    Download AI summary files for a meeting.
    
    Args:
        meeting_uuid: UUID of the meeting
        recording_data: Recording data from the Zoom API
        output_dir: Directory to save the files to
        account_type: Type of Zoom account to use ("primary" or "personal")
        
    Returns:
        Dictionary with paths to the saved files
    """
    result = {}
    
    # Save the raw response for debugging
    raw_response_path = os.path.join(output_dir, "raw_response.json")
    with open(raw_response_path, "w") as f:
        json.dump(recording_data, f, indent=2)
    result["raw_response"] = raw_response_path
    
    # Check if the recording is password protected
    password = recording_data.get("password", "")
    logger.info(f"Recording password: {password}")
    
    # Look for AI summary files in the recording_files array
    recording_files = recording_data.get("recording_files", [])
    for file in recording_files:
        if file.get("file_type") == "SUMMARY":
            file_type = file.get("recording_type", "unknown")
            download_url = file.get("download_url")
            
            if download_url:
                # Create the output file path
                output_file = os.path.join(output_dir, f"{file_type}.json")
                
                # Download the file
                logger.info(f"Downloading {file_type} file for meeting {meeting_uuid}")
                
                try:
                    # First try with Authorization header
                    headers = {"Authorization": f"Bearer {get_oauth_token(account_type)}"}
                    
                    # If password is available, add it to the URL
                    if password:
                        download_url = f"{download_url}?pwd={password}"
                        logger.info(f"Adding password to download URL: {download_url}")
                    
                    response = requests.get(download_url, headers=headers)
                    
                    if response.status_code == 200:
                        # Check if the response is HTML (password page) or JSON
                        content_type = response.headers.get("Content-Type", "")
                        if "text/html" in content_type:
                            logger.warning(f"Got HTML response for {file_type} file. This might be a password page.")
                            
                            # Try with password as a parameter
                            if password:
                                params = {"pwd": password}
                                response = requests.get(download_url, headers=headers, params=params)
                                
                                if response.status_code == 200 and "application/json" in response.headers.get("Content-Type", ""):
                                    logger.info(f"Successfully downloaded {file_type} file with password as parameter")
                                else:
                                    logger.error(f"Failed to download {file_type} file with password as parameter: {response.status_code}")
                                    continue
                            else:
                                logger.error(f"No password available for password-protected recording {meeting_uuid}")
                                continue
                        
                        # Save the file
                        with open(output_file, "wb") as f:
                            f.write(response.content)
                        result[file_type] = output_file
                        logger.info(f"Saved {file_type} file to {output_file}")
                    else:
                        logger.error(f"Failed to download {file_type} file: {response.status_code} {response.text}")
                except Exception as e:
                    logger.error(f"Error downloading {file_type} file: {str(e)}")
    
    # Look for smart recording chapters and highlights
    smart_chapters = recording_data.get("smart_recording_chapters", [])
    if smart_chapters:
        chapters_path = os.path.join(output_dir, "smart_chapters.json")
        with open(chapters_path, "w") as f:
            json.dump(smart_chapters, f, indent=2)
        result["smart_chapters"] = chapters_path
        logger.info(f"Saved smart chapters to {chapters_path}")
    
    smart_highlights = recording_data.get("smart_recording_highlights", [])
    if smart_highlights:
        highlights_path = os.path.join(output_dir, "smart_highlights.json")
        with open(highlights_path, "w") as f:
            json.dump(smart_highlights, f, indent=2)
        result["smart_highlights"] = highlights_path
        logger.info(f"Saved smart highlights to {highlights_path}")
    
    return result

async def process_recording(recording: Dict, account_type: str = "primary") -> None:
    """
    Process a recording from the Zoom Recordings Report.
    
    Args:
        recording: Dictionary with recording information from the report
        account_type: Type of Zoom account to use ("primary" or "personal")
    """
    # Get meeting UUID
    meeting_uuid = recording.get("Meeting UUID")
    if not meeting_uuid:
        logger.warning(f"No meeting UUID found for recording {recording.get('Meeting Topic', 'Unknown')}")
        return
    
    # Get session folder name
    session_folder = recording.get("Session Folder")
    if not session_folder:
        logger.warning(f"No session folder found for recording {recording.get('Meeting Topic', 'Unknown')}")
        session_folder = recording.get("Meeting Topic", "Unknown")
    
    # Create output directory
    output_dir = os.path.join("ai_summaries", session_folder)
    os.makedirs(output_dir, exist_ok=True)
    
    # Get recording info
    recording_data = await get_recording_info(meeting_uuid, account_type)
    if not recording_data:
        logger.warning(f"No recording data found for meeting {meeting_uuid}")
        return
    
    # Download AI summary files
    ai_summary_files = await download_ai_summary_files(meeting_uuid, recording_data, output_dir, account_type)
    
    # Check if we found any AI summary files
    if "summary" in ai_summary_files or "summary_next_steps" in ai_summary_files:
        logger.info(f"Found AI summary files for meeting {meeting_uuid}")
    else:
        logger.warning(f"No AI summary files found for meeting {meeting_uuid}")

async def main() -> None:
    """Main function to extract AI summaries."""
    parser = argparse.ArgumentParser(description="Extract AI summaries from Zoom recordings")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO", help="Set the logging level")
    parser.add_argument("--account", choices=["primary", "personal", "both"], default="primary", help="Which Zoom account to use")
    args = parser.parse_args()
    
    # Set log level
    logger.setLevel(getattr(logging, args.log_level))
    
    # Get report data
    report_data = await get_zoom_report_data()
    if report_data.empty:
        logger.error("No report data found")
        return
    
    # Process each recording
    for _, recording in report_data.iterrows():
        if args.account == "both":
            # Try primary first, then personal
            await process_recording(recording, "primary")
            await process_recording(recording, "personal")
        else:
            await process_recording(recording, args.account)
    
    logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(main()) 