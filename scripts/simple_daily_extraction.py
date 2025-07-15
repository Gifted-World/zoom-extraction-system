#!/usr/bin/env python3
"""
Simple daily extraction script for new Zoom recordings (last 24 hours).
Extracts: transcript, AI summary, AI next steps, smart chapters, smart highlights, 
zoom video URL, and metadata for all accounts.
"""

import os
import sys
import json
import logging
import asyncio
import tempfile
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from app.services.zoom_client import get_oauth_token, list_recordings, download_transcript
from app.services.drive_manager import create_folder_structure, upload_file, upload_content, get_drive_service

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"logs/daily_extraction_{datetime.now().strftime('%Y%m%d')}.log")
    ]
)
logger = logging.getLogger(__name__)

# Sheet configuration
SHEET_NAME = "Zoom Sessions Report"
SHEET_ID_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "zoom_sessions_sheet_id.txt")

class SimpleZoomExtractor:
    def __init__(self):
        self.accounts = self._setup_accounts()
        self.temp_dir = tempfile.mkdtemp()
        self.drive_service = None
        self.sheets_service = None
        
    def _setup_accounts(self) -> List[Dict[str, str]]:
        """Setup all Zoom accounts for processing."""
        accounts = []
        
        # Primary account (3 users)
        if config.ZOOM_CLIENT_ID and config.ZOOM_CLIENT_SECRET and config.ZOOM_ACCOUNT_ID:
            accounts.append({
                "name": "primary",
                "type": "primary",
                "client_id": config.ZOOM_CLIENT_ID,
                "client_secret": config.ZOOM_CLIENT_SECRET,
                "account_id": config.ZOOM_ACCOUNT_ID
            })
        
        # Personal account
        if config.PERSONAL_ZOOM_CLIENT_ID and config.PERSONAL_ZOOM_CLIENT_SECRET and config.PERSONAL_ZOOM_ACCOUNT_ID:
            accounts.append({
                "name": "personal",
                "type": "personal", 
                "client_id": config.PERSONAL_ZOOM_CLIENT_ID,
                "client_secret": config.PERSONAL_ZOOM_CLIENT_SECRET,
                "account_id": config.PERSONAL_ZOOM_ACCOUNT_ID
            })
            
        logger.info(f"Configured {len(accounts)} accounts for processing")
        return accounts
    
    def _init_sheets_service(self):
        """Initialize Google Sheets service."""
        if not self.sheets_service:
            self.sheets_service = build('sheets', 'v4', credentials=service_account.Credentials.from_service_account_file(
                config.GOOGLE_CREDENTIALS_FILE,
                scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            ))
        if not self.drive_service:
            self.drive_service = get_drive_service()
    
    async def get_recordings_since_date(self, account: Dict[str, str], from_date: str = None) -> List[Dict[str, Any]]:
        """Get recordings since a specific date for a specific account using user-level API."""
        try:
            if from_date is None:
                # Default to July 12, 2025 for initial extraction
                from_date = "2025-07-12"
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            logger.info(f"Fetching recordings from {from_date} to {today} for {account['name']} account")
            
            # Use user-level recordings endpoint instead of account-level
            recordings_data = await self.list_user_recordings(
                from_date=from_date,
                to_date=today,
                account_type=account["type"]
            )
            
            meetings = recordings_data.get("meetings", [])
            logger.info(f"Found {len(meetings)} meetings for {account['name']} account")
            
            return meetings
            
        except Exception as e:
            logger.error(f"Error fetching recordings for {account['name']}: {e}")
            return []
    
    async def list_user_recordings(self, from_date: str, to_date: str, account_type: str) -> Dict[str, Any]:
        """List recordings for users in the account using user-level API."""
        try:
            # Get OAuth token
            token = get_oauth_token(account_type)
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # First get list of users in the account
            users_response = requests.get(
                f"{config.ZOOM_BASE_URL}/users",
                headers=headers,
                params={"page_size": 100}
            )
            users_response.raise_for_status()
            users_data = users_response.json()
            
            all_meetings = []
            
            # Get recordings for each user
            for user in users_data.get("users", []):
                user_id = user.get("id")
                user_email = user.get("email")
                
                logger.info(f"Fetching recordings for user: {user_email}")
                
                try:
                    # Use user-level recordings endpoint
                    recordings_response = requests.get(
                        f"{config.ZOOM_BASE_URL}/users/{user_id}/recordings",
                        headers=headers,
                        params={
                            "from": from_date,
                            "to": to_date,
                            "page_size": 100
                        }
                    )
                    recordings_response.raise_for_status()
                    recordings_data = recordings_response.json()
                    
                    user_meetings = recordings_data.get("meetings", [])
                    logger.info(f"Found {len(user_meetings)} meetings for {user_email}")
                    
                    # Add user info to each meeting
                    for meeting in user_meetings:
                        meeting["host_email"] = user_email
                        meeting["host_name"] = user.get("display_name", user_email)
                    
                    all_meetings.extend(user_meetings)
                    
                except Exception as e:
                    logger.warning(f"Error fetching recordings for user {user_email}: {e}")
                    continue
            
            return {"meetings": all_meetings}
            
        except Exception as e:
            logger.error(f"Error in list_user_recordings: {e}")
            return {"meetings": []}
    
    async def get_smart_recording_details(self, meeting_id: str, session_data: Dict[str, Any], account: Dict[str, str]) -> None:
        """Get Smart Recording details (chapters and highlights) for a specific meeting."""
        try:
            # Get OAuth token
            token = get_oauth_token(account["type"])
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # Call the specific meeting recording endpoint
            response = requests.get(
                f"{config.ZOOM_BASE_URL}/meetings/{meeting_id}/recordings",
                headers=headers
            )
            response.raise_for_status()
            meeting_data = response.json()
            
            # Extract Smart Recording data if available
            if "smart_recording_chapters" in meeting_data:
                session_data["smart_chapters"] = meeting_data["smart_recording_chapters"]
                logger.info(f"Found {len(meeting_data['smart_recording_chapters'])} Smart Recording chapters")
            else:
                logger.info(f"No Smart Recording chapters found for meeting {meeting_id}")
            
            if "smart_recording_highlights" in meeting_data:
                session_data["smart_highlights"] = meeting_data["smart_recording_highlights"]
                logger.info(f"Found {len(meeting_data['smart_recording_highlights'])} Smart Recording highlights")
            else:
                logger.info(f"No Smart Recording highlights found for meeting {meeting_id}")
                
        except Exception as e:
            logger.warning(f"Error getting Smart Recording details for meeting {meeting_id}: {e}")
    
    async def extract_session_data(self, meeting: Dict[str, Any], account: Dict[str, str]) -> Dict[str, Any]:
        """Extract all required data for a session."""
        try:
            meeting_uuid = meeting.get("uuid", "")
            meeting_id = meeting.get("id", "")
            meeting_topic = meeting.get("topic", "Unknown")
            meeting_date = meeting.get("start_time", "")[:10]  # Extract date part
            host_name = meeting.get("host_name", "Unknown")
            host_email = meeting.get("host_email", "Unknown")
            
            logger.info(f"Processing: {meeting_topic} ({meeting_date})")
            
            session_data = {
                "meeting_uuid": meeting_uuid,
                "meeting_id": meeting_id,
                "meeting_topic": meeting_topic,
                "meeting_date": meeting_date,
                "host_name": host_name,
                "host_email": host_email,
                "account_type": account["type"],
                "start_time": meeting.get("start_time", ""),
                "duration": meeting.get("duration", 0),
                "files": {}
            }
            
            # Get Smart Recording details from specific meeting endpoint
            await self.get_smart_recording_details(meeting_id, session_data, account)
            
            # Extract recording files
            recording_files = meeting.get("recording_files", [])
            
            for file in recording_files:
                file_type = file.get("file_type", "")
                recording_type = file.get("recording_type", "")
                download_url = file.get("download_url", "")
                
                # Look for MP4 video files (prefer shared_screen_with_speaker_view variants)
                if file_type == "MP4":
                    if "shared_screen_with_speaker_view" in recording_type:
                        session_data["zoom_video_url"] = download_url
                    elif recording_type == "shared_screen" and "zoom_video_url" not in session_data:
                        session_data["zoom_video_url"] = download_url
                    elif recording_type == "active_speaker" and "zoom_video_url" not in session_data:
                        session_data["zoom_video_url"] = download_url
                        
                # Look for TRANSCRIPT files with VTT extension
                elif file_type == "TRANSCRIPT" and file.get("file_extension") == "VTT":
                    session_data["transcript_url"] = download_url
                    
                # Look for AI summary files
                elif file_type == "SUMMARY":
                    if recording_type == "summary":
                        session_data["ai_summary_url"] = download_url
                    elif recording_type == "summary_next_steps":
                        session_data["ai_next_steps_url"] = download_url
            
            return session_data
            
        except Exception as e:
            logger.error(f"Error extracting session data: {e}")
            return {}
    
    async def download_and_save_files(self, session_data: Dict[str, Any], session_folder_id: str) -> Dict[str, str]:
        """Download and save all files to Google Drive."""
        try:
            file_urls = {}
            
            # Save metadata
            metadata = {
                "meeting_uuid": session_data.get("meeting_uuid"),
                "meeting_topic": session_data.get("meeting_topic"),
                "meeting_date": session_data.get("meeting_date"),
                "host_name": session_data.get("host_name"),
                "host_email": session_data.get("host_email"),
                "account_type": session_data.get("account_type"),
                "start_time": session_data.get("start_time"),
                "duration": session_data.get("duration"),
                "processed_at": datetime.now().isoformat()
            }
            
            file_id = await upload_content(
                content=json.dumps(metadata, indent=2),
                folder_id=session_folder_id,
                file_name=config.FOLDER_STRUCTURE["files"]["metadata"],
                mime_type="application/json"
            )
            file_urls["metadata"] = file_id.get("webViewLink", "")
            
            # Save Zoom video URL
            if session_data.get("zoom_video_url"):
                file_id = await upload_content(
                    content=session_data["zoom_video_url"],
                    folder_id=session_folder_id,
                    file_name=config.FOLDER_STRUCTURE["files"]["zoom_video_url"],
                    mime_type="text/plain"
                )
                file_urls["zoom_video_url"] = file_id.get("webViewLink", "")
            
            # Download and save transcript (VTT file)
            if session_data.get("transcript_url"):
                # Download VTT file using the download URL with access token
                token = get_oauth_token(session_data.get("account_type", "primary"))
                
                # Add access token to the download URL
                download_url = session_data["transcript_url"]
                separator = "&" if "?" in download_url else "?"
                download_url_with_token = f"{download_url}{separator}access_token={token}"
                
                response = requests.get(download_url_with_token)
                
                if response.status_code == 200:
                    # Save VTT content to temp file
                    transcript_path = os.path.join(self.temp_dir, "transcript.vtt")
                    with open(transcript_path, 'wb') as f:
                        f.write(response.content)
                    
                    # Upload to Google Drive
                    file_id = await upload_file(
                        file_path=transcript_path,
                        folder_id=session_folder_id,
                        file_name=config.FOLDER_STRUCTURE["files"]["transcript"],
                        mime_type="text/vtt"
                    )
                    file_urls["transcript"] = file_id.get("webViewLink", "")
                    logger.info(f"VTT transcript downloaded and uploaded successfully")
                else:
                    logger.warning(f"Failed to download VTT transcript: {response.status_code}")
            
            # Save AI summary files
            for file_type in ["ai_summary", "ai_next_steps"]:
                url_key = f"{file_type}_url"
                if session_data.get(url_key):
                    # Download AI summary file
                    token = get_oauth_token(session_data.get("account_type", "primary"))
                    response = requests.get(session_data[url_key], headers={"Authorization": f"Bearer {token}"})
                    
                    if response.status_code == 200:
                        file_id = await upload_content(
                            content=response.text,
                            folder_id=session_folder_id,
                            file_name=config.FOLDER_STRUCTURE["files"][file_type],
                            mime_type="application/json"
                        )
                        file_urls[file_type] = file_id.get("webViewLink", "")
            
            # Save smart recording data
            if session_data.get("smart_chapters"):
                file_id = await upload_content(
                    content=json.dumps(session_data["smart_chapters"], indent=2),
                    folder_id=session_folder_id,
                    file_name=config.FOLDER_STRUCTURE["files"]["smart_chapters"],
                    mime_type="application/json"
                )
                file_urls["smart_chapters"] = file_id.get("webViewLink", "")
            
            if session_data.get("smart_highlights"):
                file_id = await upload_content(
                    content=json.dumps(session_data["smart_highlights"], indent=2),
                    folder_id=session_folder_id,
                    file_name=config.FOLDER_STRUCTURE["files"]["smart_highlights"],
                    mime_type="application/json"
                )
                file_urls["smart_highlights"] = file_id.get("webViewLink", "")
            
            return file_urls
            
        except Exception as e:
            logger.error(f"Error downloading and saving files: {e}")
            return {}
    
    async def process_session(self, meeting: Dict[str, Any], account: Dict[str, str]) -> bool:
        """Process a single session."""
        try:
            # Extract session data
            session_data = await self.extract_session_data(meeting, account)
            if not session_data:
                return False
            
            # Create folder structure
            course_name = session_data["meeting_topic"].split(" - ")[0] if " - " in session_data["meeting_topic"] else session_data["meeting_topic"]
            
            folder_structure = await create_folder_structure(
                course_name=course_name,
                session_number=0,  # No session numbers for now
                session_name=session_data["meeting_topic"],
                session_date=session_data["meeting_date"]
            )
            
            session_folder_id = folder_structure["session_folder_id"]
            
            # Download and save files
            file_urls = await self.download_and_save_files(session_data, session_folder_id)
            
            logger.info(f"Successfully processed session: {session_data['meeting_topic']}")
            logger.info(f"Files saved: {list(file_urls.keys())}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error processing session: {e}")
            return False
    
    def get_or_create_sheet(self) -> str:
        """Get existing sheet ID or create a new one."""
        self._init_sheets_service()
        
        # Check if we have a stored sheet ID
        if os.path.exists(SHEET_ID_FILE):
            with open(SHEET_ID_FILE, 'r') as f:
                sheet_id = f.read().strip()
            
            # Verify the sheet still exists
            try:
                self.sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
                logger.info(f"Using existing sheet: {sheet_id}")
                return sheet_id
            except Exception as e:
                logger.warning(f"Existing sheet not found: {e}")
        
        # Create a new sheet
        return self.create_new_sheet()
    
    def create_new_sheet(self) -> str:
        """Create a new Google Sheet."""
        try:
            # Create sheet directly in target folder using Drive API
            file_metadata = {
                'name': SHEET_NAME,
                'mimeType': 'application/vnd.google-apps.spreadsheet',
                'parents': [config.GOOGLE_DRIVE_ROOT_FOLDER]
            }
            
            if config.USE_SHARED_DRIVE:
                file = self.drive_service.files().create(
                    body=file_metadata,
                    supportsAllDrives=True
                ).execute()
            else:
                file = self.drive_service.files().create(
                    body=file_metadata
                ).execute()
            
            spreadsheet_id = file['id']
            
            # Create header row
            headers = [
                'Meeting Topic',
                'Host Name', 
                'Host Email',
                'Date',
                'Duration (minutes)',
                'Transcript URL',
                'Meeting UUID',
                'Zoom Video URL',
                'AI Summary URL',
                'AI Next Steps URL',
                'Chapters URL',
                'Highlights URL'
            ]
            
            body = {'values': [headers]}
            
            self.sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range='A1',
                valueInputOption='RAW',
                body=body
            ).execute()
            
            # Format the header row
            format_body = {
                'requests': [
                    {
                        'repeatCell': {
                            'range': {
                                'sheetId': 0,
                                'startRowIndex': 0,
                                'endRowIndex': 1
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': {'red': 0.2, 'green': 0.2, 'blue': 0.2},
                                    'textFormat': {
                                        'foregroundColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0},
                                        'bold': True
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat(backgroundColor,textFormat)'
                        }
                    }
                ]
            }
            
            self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=format_body
            ).execute()
            
            # Make the sheet publicly viewable
            self.drive_service.permissions().create(
                fileId=spreadsheet_id,
                body={'role': 'reader', 'type': 'anyone'},
                supportsAllDrives=True
            ).execute()
            
            # Store the sheet ID
            with open(SHEET_ID_FILE, 'w') as f:
                f.write(spreadsheet_id)
            
            logger.info(f"Created new sheet: {spreadsheet_id}")
            return spreadsheet_id
            
        except Exception as e:
            logger.error(f"Error creating new sheet: {e}")
            return ""
    
    def get_all_sessions_from_drive(self) -> List[Dict]:
        """Get all session data from Google Drive folders."""
        sessions = []
        
        try:
            # Get all course folders
            if config.USE_SHARED_DRIVE:
                query = f"parents in '{config.GOOGLE_DRIVE_ROOT_FOLDER}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                results = self.drive_service.files().list(
                    q=query,
                    corpora="drive",
                    driveId=config.GOOGLE_SHARED_DRIVE_ID,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True
                ).execute()
            else:
                query = f"parents in '{config.GOOGLE_DRIVE_ROOT_FOLDER}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                results = self.drive_service.files().list(q=query).execute()
            
            course_folders = results.get('files', [])
            
            for course_folder in course_folders:
                course_name = course_folder['name']
                course_id = course_folder['id']
                
                # Get session folders within each course
                if config.USE_SHARED_DRIVE:
                    query = f"parents in '{course_id}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                    session_results = self.drive_service.files().list(
                        q=query,
                        corpora="drive",
                        driveId=config.GOOGLE_SHARED_DRIVE_ID,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True
                    ).execute()
                else:
                    query = f"parents in '{course_id}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                    session_results = self.drive_service.files().list(q=query).execute()
                
                session_folders = session_results.get('files', [])
                
                for session_folder in session_folders:
                    session_name = session_folder['name']
                    session_id = session_folder['id']
                    
                    # Get session data
                    session_data = self.extract_session_data_from_drive(course_name, session_name, session_id)
                    if session_data:
                        sessions.append(session_data)
                        
        except Exception as e:
            logger.error(f"Error getting sessions from drive: {e}")
            
        return sessions
    
    def extract_session_data_from_drive(self, course_name: str, session_name: str, session_id: str) -> Optional[Dict]:
        """Extract session data from a Google Drive folder."""
        try:
            # Get all files in the session folder (with creation time to handle duplicates)
            if config.USE_SHARED_DRIVE:
                query = f"parents in '{session_id}' and trashed = false"
                results = self.drive_service.files().list(
                    q=query,
                    corpora="drive",
                    driveId=config.GOOGLE_SHARED_DRIVE_ID,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    fields="files(id,name,webViewLink,createdTime)",
                    orderBy="createdTime desc"
                ).execute()
            else:
                query = f"parents in '{session_id}' and trashed = false"
                results = self.drive_service.files().list(
                    q=query,
                    fields="files(id,name,webViewLink,createdTime)",
                    orderBy="createdTime desc"
                ).execute()
            
            files = results.get('files', [])
            
            # Initialize session data
            session_data = {
                'meeting_topic': '',
                'host_name': '',
                'host_email': '',
                'date': '',
                'duration_minutes': '',
                'transcript_url': '',
                'meeting_uuid': '',
                'zoom_video_url': '',
                'ai_summary_url': '',
                'ai_next_steps_url': '',
                'chapters_url': '',
                'highlights_url': ''
            }
            
            # Extract date from session name
            if '_' in session_name:
                parts = session_name.split('_')
                if len(parts) >= 2:
                    date_part = parts[-1]
                    if len(date_part) == 10 and date_part.count('-') == 2:
                        session_data['date'] = date_part
            
            # Handle duplicates: keep the most recent, delete older ones
            file_groups = {}
            for file in files:
                file_name = file['name']
                if file_name not in file_groups:
                    file_groups[file_name] = []
                file_groups[file_name].append(file)
            
            # Clean up duplicates and get the most recent of each file type
            unique_files = {}
            for file_name, file_list in file_groups.items():
                if len(file_list) > 1:
                    # Sort by creation time (most recent first due to orderBy above)
                    most_recent = file_list[0]
                    older_files = file_list[1:]
                    
                    # Delete older duplicates
                    for old_file in older_files:
                        try:
                            if config.USE_SHARED_DRIVE:
                                self.drive_service.files().delete(
                                    fileId=old_file['id'],
                                    supportsAllDrives=True
                                ).execute()
                            else:
                                self.drive_service.files().delete(fileId=old_file['id']).execute()
                            logger.info(f"Deleted duplicate file: {file_name} (ID: {old_file['id']})")
                        except Exception as e:
                            logger.warning(f"Failed to delete duplicate file {old_file['id']}: {e}")
                    
                    unique_files[file_name] = most_recent
                else:
                    unique_files[file_name] = file_list[0]
            
            # Process each unique file
            for file_name, file in unique_files.items():
                file_id = file['id']
                web_view_link = file.get('webViewLink', '')
                
                if file_name == 'session_metadata.json':
                    # Get metadata from the JSON file
                    metadata = self.get_file_content(file_id)
                    if metadata:
                        try:
                            metadata_json = json.loads(metadata)
                            session_data['meeting_topic'] = metadata_json.get('meeting_topic', '')
                            session_data['host_name'] = metadata_json.get('host_name', '')
                            session_data['host_email'] = metadata_json.get('host_email', '')
                            session_data['meeting_uuid'] = metadata_json.get('meeting_uuid', '')
                            session_data['duration_minutes'] = str(metadata_json.get('duration', ''))
                            
                            # Extract date from metadata if not found in session name
                            if not session_data['date']:
                                start_time = metadata_json.get('start_time', '')
                                if start_time:
                                    session_data['date'] = start_time[:10]
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in metadata file for {session_name}")
                            
                elif file_name == 'transcript.vtt':
                    session_data['transcript_url'] = web_view_link
                elif file_name == 'zoom_video_url.txt':
                    # Get the actual Zoom URL from the file content
                    zoom_url = self.get_file_content(file_id)
                    if zoom_url:
                        session_data['zoom_video_url'] = zoom_url.strip()
                elif file_name == 'ai_summary.json':
                    session_data['ai_summary_url'] = web_view_link
                elif file_name == 'ai_next_steps.json':
                    session_data['ai_next_steps_url'] = web_view_link
                elif file_name == 'smart_chapters.json':
                    session_data['chapters_url'] = web_view_link
                elif file_name == 'smart_highlights.json':
                    session_data['highlights_url'] = web_view_link
                    
            return session_data
            
        except Exception as e:
            logger.error(f"Error extracting session data for {session_name}: {e}")
            return None
    
    def get_file_content(self, file_id: str) -> Optional[str]:
        """Get the content of a file from Google Drive."""
        try:
            if config.USE_SHARED_DRIVE:
                content = self.drive_service.files().get_media(
                    fileId=file_id,
                    supportsAllDrives=True
                ).execute()
            else:
                content = self.drive_service.files().get_media(fileId=file_id).execute()
            
            return content.decode('utf-8')
        except Exception as e:
            logger.error(f"Error getting file content for {file_id}: {e}")
            return None
    
    def get_existing_sessions_from_sheet(self, sheet_id: str) -> set:
        """Get existing session UUIDs from the sheet."""
        try:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range='G:G'  # Meeting UUID column
            ).execute()
            
            values = result.get('values', [])
            # Skip header row and get UUIDs
            existing_uuids = {row[0] for row in values[1:] if row and row[0]}
            
            return existing_uuids
            
        except Exception as e:
            logger.error(f"Error getting existing sessions from sheet: {e}")
            return set()
    
    def append_new_sessions_to_sheet(self, sheet_id: str, new_sessions: List[Dict]) -> int:
        """Append new sessions to the sheet."""
        if not new_sessions:
            return 0
            
        try:
            # Prepare rows for new sessions
            rows = []
            for session in new_sessions:
                row = [
                    session.get('meeting_topic', ''),
                    session.get('host_name', ''),
                    session.get('host_email', ''),
                    session.get('date', ''),
                    session.get('duration_minutes', ''),
                    session.get('transcript_url', ''),
                    session.get('meeting_uuid', ''),
                    session.get('zoom_video_url', ''),
                    session.get('ai_summary_url', ''),
                    session.get('ai_next_steps_url', ''),
                    session.get('chapters_url', ''),
                    session.get('highlights_url', '')
                ]
                rows.append(row)
            
            # Append to the sheet
            body = {'values': rows}
            
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range='A1',
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f"Appended {len(new_sessions)} new sessions to sheet")
            return len(new_sessions)
            
        except Exception as e:
            logger.error(f"Error appending sessions to sheet: {e}")
            return 0
    
    def update_session_report(self) -> str:
        """Update the session report with all sessions from Google Drive."""
        try:
            logger.info("Updating session report...")
            
            # Get or create the sheet
            sheet_id = self.get_or_create_sheet()
            if not sheet_id:
                logger.error("Failed to get or create sheet")
                return ""
            
            # Get all sessions from Google Drive
            all_sessions = self.get_all_sessions_from_drive()
            logger.info(f"Found {len(all_sessions)} sessions in Google Drive")
            
            # Get existing sessions from sheet
            existing_uuids = self.get_existing_sessions_from_sheet(sheet_id)
            logger.info(f"Found {len(existing_uuids)} existing sessions in sheet")
            
            # Filter out sessions that already exist
            new_sessions = [s for s in all_sessions if s.get('meeting_uuid') not in existing_uuids]
            
            # Append new sessions
            sessions_added = self.append_new_sessions_to_sheet(sheet_id, new_sessions)
            
            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
            
            if sessions_added > 0:
                logger.info(f"Added {sessions_added} new sessions to report: {sheet_url}")
            else:
                logger.info(f"No new sessions to add. Report: {sheet_url}")
            
            return sheet_url
            
        except Exception as e:
            logger.error(f"Error updating session report: {e}")
            return ""
    
    async def run_daily_extraction(self):
        """Run the daily extraction for all accounts."""
        try:
            logger.info("Starting daily extraction for all accounts")
            
            total_processed = 0
            total_errors = 0
            
            for account in self.accounts:
                logger.info(f"Processing {account['name']} account")
                
                # Get recordings since July 12, 2025 (or since last run)
                meetings = await self.get_recordings_since_date(account)
                
                if not meetings:
                    logger.info(f"No recordings found for {account['name']} account")
                    continue
                
                # Process each meeting
                for meeting in meetings:
                    try:
                        success = await self.process_session(meeting, account)
                        if success:
                            total_processed += 1
                        else:
                            total_errors += 1
                    except Exception as e:
                        logger.error(f"Error processing meeting: {e}")
                        total_errors += 1
            
            logger.info(f"Daily extraction completed: {total_processed} processed, {total_errors} errors")
            
            # Update session report if any sessions were processed
            if total_processed > 0:
                try:
                    sheet_url = self.update_session_report()
                    if sheet_url:
                        logger.info(f"Updated session report: {sheet_url}")
                    else:
                        logger.warning("Failed to update session report")
                except Exception as e:
                    logger.error(f"Error updating session report: {e}")
            
        except Exception as e:
            logger.error(f"Error in daily extraction: {e}")
        finally:
            # Clean up temp directory
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)

async def main():
    """Main function."""
    extractor = SimpleZoomExtractor()
    await extractor.run_daily_extraction()

if __name__ == "__main__":
    asyncio.run(main())