#!/usr/bin/env python3
"""
Script to extract AI summary and smart recording data for existing recordings.
This script will:
1. Read the Zoom Recordings Report to get meeting UUIDs
2. Call the Zoom API with the include_fields=ai_summary parameter
3. Save the AI summary and smart recording data to the appropriate folders in Google Drive
4. Update the report with links to these files
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
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

import config
from app.services.drive_manager import get_drive_service, upload_file
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
        
    # Use the first sheet's title
    sheet_title = sheets[0]['properties']['title']
    logger.info(f"Using sheet: {sheet_title}")
    
    # Get the spreadsheet values
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=report_id,
        range=f"{sheet_title}"
    ).execute()
        
    values = result.get('values', [])
    if not values:
        logger.error("No data found in report")
        return pd.DataFrame()
    
    # Convert to DataFrame
    headers = values[0]
    data = values[1:]
    df = pd.DataFrame(data, columns=headers)
    
    logger.info(f"Found {len(df)} total sessions in report")
    
    return df

async def extract_and_save_ai_data(meeting_uuid: str, session_folder_id: str, account_type: str = "primary") -> Dict[str, str]:
    """
    Extract AI summary and smart recording data for a meeting and save to Drive.
    
    Args:
        meeting_uuid: UUID of the meeting
        session_folder_id: ID of the session folder in Drive
        account_type: Type of Zoom account to use ("primary" or "personal")
        
    Returns:
        Dictionary with URLs of the saved files
    """
    result = {}
    
    try:
        # Get a fresh OAuth token
        token = force_new_oauth_token(account_type)
        if not token:
            logger.error(f"Failed to get OAuth token for {account_type} account")
            return {}
        
        # Create temp directory if it doesn't exist
        temp_dir = os.path.join(parent_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Get recording info with AI summary
        logger.info(f"Getting recording info for meeting {meeting_uuid} from {account_type} account")
        logger.info(f"Request URL: {config.ZOOM_BASE_URL}/meetings/{meeting_uuid}/recordings")
        
        response = requests.get(
            f"{config.ZOOM_BASE_URL}/meetings/{meeting_uuid}/recordings",
            headers={"Authorization": f"Bearer {token}"},
            params={"include_fields": "ai_summary"}
        )
        
        if response.status_code == 200:
            logger.info("Successfully retrieved recording info directly by UUID")
            recording_info = response.json()
            
            # Save the raw response for debugging
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = os.path.join(temp_dir, f"zoom_response_{timestamp}.json")
            with open(debug_file, "w") as f:
                json.dump(recording_info, f, indent=2)
            
            # Log the keys in the response
            logger.info(f"Response keys: {', '.join(recording_info.keys())}")
            
            # Extract AI summary files
            ai_summary_files = []
            for file in recording_info.get("recording_files", []):
                if file.get("file_type") == "SUMMARY":
                    ai_summary_files.append(file)
            
            logger.info(f"Found {len(ai_summary_files)} AI summary files")
            
            if not ai_summary_files:
                logger.warning("No AI summary files found")
                return {}
            
            # Download and save each AI summary file
            for file in ai_summary_files:
                recording_type = file.get("recording_type", "")
                download_url = file.get("download_url", "")
                
                if not download_url:
                    logger.warning(f"No download URL for {recording_type}")
                    continue
                
                # Download the file
                logger.info(f"Downloading {recording_type} from {download_url}")
                file_response = requests.get(download_url)
                
                if file_response.status_code != 200:
                    logger.warning(f"Failed to download {recording_type}: {file_response.status_code}")
                    continue
                
                # Save to temp file
                file_name = f"{recording_type}.json"
                temp_file = os.path.join(temp_dir, file_name)
                with open(temp_file, "wb") as f:
                    f.write(file_response.content)
                
                # Upload to Google Drive
                try:
                    file_url = await upload_file(
                        temp_file,
                        session_folder_id,
                        file_name,
                        "application/json"
                    )
                    
                    if file_url:
                        logger.info(f"AI {recording_type} uploaded for meeting {meeting_uuid}")
                        
                        # Map recording types to report columns
                        if recording_type == "summary":
                            result["AI Summary URL"] = file_url.get("webViewLink", "")
                        elif recording_type == "summary_next_steps":
                            result["AI Next Steps URL"] = file_url.get("webViewLink", "")
                    else:
                        logger.warning(f"Failed to upload {recording_type}")
                except Exception as e:
                    logger.warning(f"Error uploading file: {e}")
            
            # Extract smart recording data (chapters and highlights)
            smart_chapters = recording_info.get("smart_recording_chapters", [])
            smart_highlights = recording_info.get("smart_recording_highlights", [])
            
            if smart_chapters:
                # Save to temp file
                temp_file = os.path.join(temp_dir, "smart_chapters.json")
                with open(temp_file, "w") as f:
                    json.dump(smart_chapters, f, indent=2)
                
                # Upload to Google Drive
                try:
                    file_url = await upload_file(
                        temp_file,
                        session_folder_id,
                        "smart_chapters.json",
                        "application/json"
                    )
                    
                    if file_url:
                        logger.info(f"Smart chapters uploaded for meeting {meeting_uuid}")
                        result["Smart Chapters URL"] = file_url.get("webViewLink", "")
                    else:
                        logger.warning("Failed to upload smart chapters")
                except Exception as e:
                    logger.warning(f"Error uploading smart chapters: {e}")
            
            if smart_highlights:
                # Save to temp file
                temp_file = os.path.join(temp_dir, "smart_highlights.json")
                with open(temp_file, "w") as f:
                    json.dump(smart_highlights, f, indent=2)
                
                # Upload to Google Drive
                try:
                    file_url = await upload_file(
                        temp_file,
                        session_folder_id,
                        "smart_highlights.json",
                        "application/json"
                    )
                    
                    if file_url:
                        logger.info(f"Smart highlights uploaded for meeting {meeting_uuid}")
                        result["Smart Highlights URL"] = file_url.get("webViewLink", "")
                    else:
                        logger.warning("Failed to upload smart highlights")
                except Exception as e:
                    logger.warning(f"Error uploading smart highlights: {e}")
            
            return result
        
        elif response.status_code == 404:
            logger.warning(f"Recording not found for meeting {meeting_uuid}")
            # We can't access account-level recordings, so we'll just return empty results
            logger.warning("Cannot access account-level recordings, skipping fallback search")
            return {}
        else:
            logger.warning(f"Failed to get recording info: {response.status_code}")
            return {}
    
    except Exception as e:
        logger.error(f"Error extracting AI data: {e}")
        return {}

async def find_session_folder(meeting_topic: str, meeting_date: str) -> Optional[str]:
    """
    Find the session folder ID in Google Drive.
    
    Args:
        meeting_topic: Topic of the meeting
        meeting_date: Date of the meeting (YYYY-MM-DD)
        
    Returns:
        Folder ID or None if not found
    """
    try:
        drive_service = get_drive_service()
        
        # Try different folder name formats
        folder_names = [
            f"{meeting_topic}_{meeting_date}",
            f"{meeting_topic.split(' - ')[0]}_{meeting_date}",
            meeting_topic
        ]
        
        for folder_name in folder_names:
            query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            
            if config.USE_SHARED_DRIVE:
                results = drive_service.files().list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
            else:
                results = drive_service.files().list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name)"
                ).execute()
            
            folders = results.get("files", [])
            
            if folders:
                logger.info(f"Found session folder: {folders[0]['name']}")
                return folders[0]["id"]
        
        # If not found, try to find parent course folder and then look inside it
        course_name = meeting_topic.split(" - ")[0] if " - " in meeting_topic else meeting_topic
        query = f"name = '{course_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        
        if config.USE_SHARED_DRIVE:
            results = drive_service.files().list(
                q=query,
                spaces="drive",
                fields="files(id, name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
        else:
            results = drive_service.files().list(
                q=query,
                spaces="drive",
                fields="files(id, name)"
            ).execute()
        
        course_folders = results.get("files", [])
        
        if course_folders:
            course_folder_id = course_folders[0]["id"]
            
            # Look for session folder inside course folder
            query = f"'{course_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            
            if config.USE_SHARED_DRIVE:
                results = drive_service.files().list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
            else:
                results = drive_service.files().list(
                    q=query,
                    spaces="drive",
                    fields="files(id, name)"
                ).execute()
            
            session_folders = results.get("files", [])
            
            # Look for folder with the date in the name
            for folder in session_folders:
                if meeting_date in folder["name"]:
                    logger.info(f"Found session folder: {folder['name']}")
                    return folder["id"]
        
        logger.warning(f"Session folder not found for {meeting_topic} - {meeting_date}")
        return None
    
    except Exception as e:
        logger.error(f"Error finding session folder: {e}")
        return None

async def update_zoom_report(df: pd.DataFrame, meeting_uuid: str, ai_data_urls: Dict[str, str]) -> bool:
    """
    Update the Zoom Recordings Report with AI data URLs.
    
    Args:
        df: DataFrame containing the report data
        meeting_uuid: UUID of the meeting
        ai_data_urls: Dictionary with URLs to update
        
    Returns:
        True if successful, False otherwise
    """
    if not ai_data_urls:
        logger.warning(f"No AI data URLs to update for meeting {meeting_uuid}")
        return False
    
    try:
        # Get the report ID
        report_id = os.environ.get("ZOOM_REPORT_ID")
        if not report_id:
            logger.error("ZOOM_REPORT_ID not found in environment variables")
            return False
        
        # Set up Google Sheets API client
        credentials = service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE, 
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        sheets_service = build("sheets", "v4", credentials=credentials)
        
        # Get sheet names first
        sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=report_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        
        if not sheets:
            logger.error("No sheets found in the spreadsheet")
            return False
            
        # Use the first sheet's title
        sheet_title = sheets[0]['properties']['title']
        
        # Find the row with the matching UUID
        uuid_col = df.columns[df.columns.str.contains("UUID", case=False)].tolist()
        if not uuid_col:
            logger.error("UUID column not found in report")
            return False
        
        uuid_col = uuid_col[0]
        row_idx = df[df[uuid_col] == meeting_uuid].index.tolist()
        
        if not row_idx:
            logger.warning(f"Row with UUID {meeting_uuid} not found in report")
            return False
        
        row_idx = row_idx[0] + 1  # Add 1 for header row
        
        # Get all column headers
        headers = df.columns.tolist()
        
        # Prepare updates
        updates = []
        
        # Map AI data URLs to column names
        url_mapping = {
            "AI Summary URL": "AI Summary URL",
            "AI Next Steps URL": "AI Next Steps URL",
            "Smart Chapters URL": "Smart Chapters URL",
            "Smart Highlights URL": "Smart Highlights URL"
        }
        
        for ai_data_type, url in ai_data_urls.items():
            col_name = url_mapping.get(ai_data_type)
            if not col_name or col_name not in headers:
                # If column doesn't exist, try to add it
                if col_name:
                    logger.info(f"Column {col_name} not found in report, adding it")
                    
                    # Add new column
                    col_idx = len(headers)
                    col_letter = chr(ord('A') + col_idx)
                    
                    # Update headers in the spreadsheet
                    headers_range = f"{sheet_title}!{col_letter}1"
                    sheets_service.spreadsheets().values().update(
                        spreadsheetId=report_id,
                        range=headers_range,
                        valueInputOption="RAW",
                        body={"values": [[col_name]]}
                    ).execute()
                    
                    # Add column to headers list
                    headers.append(col_name)
                else:
                    continue
            
            # Find column index
            col_idx = headers.index(col_name)
            col_letter = chr(ord('A') + col_idx)
            
            # Add update
            cell_range = f"{sheet_title}!{col_letter}{row_idx + 1}"
            updates.append({
                "range": cell_range,
                "values": [[url]]
            })
        
        if not updates:
            logger.warning(f"No updates to make for meeting {meeting_uuid}")
            return False
        
        # Apply updates
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": updates
        }
        
        result = sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=report_id,
            body=body
        ).execute()
        
        logger.info(f"Updated {len(updates)} cells for meeting {meeting_uuid}")
        return True
    
    except Exception as e:
        logger.error(f"Error updating report: {e}")
        return False

async def process_meetings(account_type: str = "primary"):
    """
    Process meetings from the Zoom Recordings Report.
    
    Args:
        account_type: Type of Zoom account to use ("primary" or "personal")
    """
    # Get data from the Zoom Recordings Report
    df = await get_zoom_report_data()
    
    if df.empty:
        logger.error("No data found in Zoom Recordings Report")
        return
    
    # Find UUID column
    uuid_col = df.columns[df.columns.str.contains("UUID", case=False)].tolist()
    if not uuid_col:
        logger.error("UUID column not found in report")
        return
    
    uuid_col = uuid_col[0]
    
    # Find topic column
    topic_col = df.columns[df.columns.str.contains("Topic", case=False)].tolist()
    if not topic_col:
        logger.error("Topic column not found in report")
        return
    
    topic_col = topic_col[0]
    
    # Find date column
    date_col = df.columns[df.columns.str.contains("Date", case=False)].tolist()
    if not date_col:
        logger.error("Date column not found in report")
        return
    
    date_col = date_col[0]
    
    # Process each meeting
    for _, row in df.iterrows():
        meeting_uuid = row.get(uuid_col)
        meeting_topic = row.get(topic_col)
        meeting_date = row.get(date_col)
        
        if not meeting_uuid or not meeting_topic:
            logger.warning(f"No meeting UUID or topic found for row {_}, skipping")
            continue
        
        logger.info(f"Processing meeting: {meeting_topic} ({meeting_date}) - UUID: {meeting_uuid}")
        
        # Find session folder
        session_folder_id = await find_session_folder(meeting_topic, meeting_date)
        
        if not session_folder_id:
            logger.warning(f"Session folder not found for {meeting_topic}, skipping")
            continue
        
        # Process with specified account
        logger.info(f"Processing with {account_type} account")
        ai_data_urls = await extract_and_save_ai_data(meeting_uuid, session_folder_id, account_type)
        
        if not ai_data_urls:
            logger.warning(f"No AI data found for meeting {meeting_topic}")
            continue
        
        # Update Zoom Report
        await update_zoom_report(df, meeting_uuid, ai_data_urls)

async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Extract AI summary and smart recording data from Zoom recordings")
    parser.add_argument("--account", choices=["primary", "personal", "both"], default="primary", help="Which Zoom account to use")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO", help="Set the logging level")
    
    args = parser.parse_args()
    
    # Set log level
    logger.setLevel(getattr(logging, args.log_level))
    
    # Process meetings
    if args.account == "both":
        await process_meetings("primary")
        await process_meetings("personal")
    else:
        await process_meetings(args.account)

if __name__ == "__main__":
    asyncio.run(main()) 