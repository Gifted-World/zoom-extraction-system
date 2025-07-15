#!/usr/bin/env python3
"""
Generate and update a Google Sheets report of all Zoom sessions with file URLs.
Maintains a single persistent sheet that gets updated with new sessions.
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Add the parent directory to the path so we can import from the app
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

import config
from app.services.drive_manager import get_drive_service

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Sheet configuration
SHEET_NAME = "Zoom Sessions Report"
SHEET_ID_FILE = os.path.join(parent_dir, "zoom_sessions_sheet_id.txt")

class SessionReportGenerator:
    def __init__(self):
        self.drive_service = get_drive_service()
        self.sheets_service = build('sheets', 'v4', credentials=service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        ))
        
    def get_all_sessions(self) -> List[Dict]:
        """Get all session folders and their metadata from Google Drive."""
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
            logger.info(f"Found {len(course_folders)} course folders")
            
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
                logger.info(f"Found {len(session_folders)} session folders in {course_name}")
                
                for session_folder in session_folders:
                    session_name = session_folder['name']
                    session_id = session_folder['id']
                    
                    # Get session metadata and files
                    session_data = self.extract_session_data(course_name, session_name, session_id)
                    if session_data:
                        sessions.append(session_data)
                        
        except Exception as e:
            logger.error(f"Error getting sessions: {e}")
            
        return sessions
    
    def extract_session_data(self, course_name: str, session_name: str, session_id: str) -> Optional[Dict]:
        """Extract session metadata and file URLs from a session folder."""
        try:
            # Get all files in the session folder
            if config.USE_SHARED_DRIVE:
                query = f"parents in '{session_id}' and trashed = false"
                results = self.drive_service.files().list(
                    q=query,
                    corpora="drive",
                    driveId=config.GOOGLE_SHARED_DRIVE_ID,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True
                ).execute()
            else:
                query = f"parents in '{session_id}' and trashed = false"
                results = self.drive_service.files().list(q=query).execute()
            
            files = results.get('files', [])
            
            # Initialize session data
            session_data = {
                'course_name': course_name,
                'session_name': session_name,
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
            
            # Extract date from session name (assuming format: SessionName_YYYY-MM-DD)
            if '_' in session_name:
                parts = session_name.split('_')
                if len(parts) >= 2:
                    date_part = parts[-1]
                    if len(date_part) == 10 and date_part.count('-') == 2:
                        session_data['date'] = date_part
            
            # Process each file
            for file in files:
                file_name = file['name']
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
    
    def get_or_create_sheet(self) -> str:
        """Get existing sheet ID or create a new one."""
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
            spreadsheet_body = {
                'properties': {
                    'title': SHEET_NAME
                }
            }
            
            spreadsheet = self.sheets_service.spreadsheets().create(
                body=spreadsheet_body
            ).execute()
            
            spreadsheet_id = spreadsheet['spreadsheetId']
            
            # Move the spreadsheet to the specified folder
            if config.USE_SHARED_DRIVE:
                self.drive_service.files().update(
                    fileId=spreadsheet_id,
                    addParents=config.GOOGLE_DRIVE_ROOT_FOLDER,
                    supportsAllDrives=True
                ).execute()
            else:
                self.drive_service.files().update(
                    fileId=spreadsheet_id,
                    addParents=config.GOOGLE_DRIVE_ROOT_FOLDER
                ).execute()
            
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
            
            body = {
                'values': [headers]
            }
            
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
                                    'backgroundColor': {
                                        'red': 0.2,
                                        'green': 0.2,
                                        'blue': 0.2
                                    },
                                    'textFormat': {
                                        'foregroundColor': {
                                            'red': 1.0,
                                            'green': 1.0,
                                            'blue': 1.0
                                        },
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
    
    def get_existing_sessions(self, sheet_id: str) -> set:
        """Get the set of existing session UUIDs from the sheet."""
        try:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range='G:G'  # Meeting UUID column
            ).execute()
            
            values = result.get('values', [])
            # Skip header row and get UUIDs
            existing_uuids = {row[0] for row in values[1:] if row and row[0]}
            
            logger.info(f"Found {len(existing_uuids)} existing sessions in sheet")
            return existing_uuids
            
        except Exception as e:
            logger.error(f"Error getting existing sessions: {e}")
            return set()
    
    def append_new_sessions(self, sheet_id: str, new_sessions: List[Dict]) -> int:
        """Append new sessions to the existing sheet."""
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
            body = {
                'values': rows
            }
            
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=sheet_id,
                range='A1',
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f"Appended {len(new_sessions)} new sessions to sheet")
            return len(new_sessions)
            
        except Exception as e:
            logger.error(f"Error appending sessions: {e}")
            return 0
    
    def update_sheet(self, sessions: List[Dict], append_only: bool = False) -> tuple:
        """Update the sheet with sessions. Returns (sheet_url, sessions_added)."""
        sheet_id = self.get_or_create_sheet()
        if not sheet_id:
            return "", 0
        
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        
        if append_only:
            # Get existing sessions and only append new ones
            existing_uuids = self.get_existing_sessions(sheet_id)
            new_sessions = [s for s in sessions if s.get('meeting_uuid') not in existing_uuids]
            
            sessions_added = self.append_new_sessions(sheet_id, new_sessions)
            
            if sessions_added > 0:
                logger.info(f"Added {sessions_added} new sessions to existing sheet")
            else:
                logger.info("No new sessions to add")
                
            return sheet_url, sessions_added
        else:
            # Clear and rebuild the entire sheet (for initial population)
            try:
                # Clear existing data (except header)
                self.sheets_service.spreadsheets().values().clear(
                    spreadsheetId=sheet_id,
                    range='A2:Z'
                ).execute()
                
                # Add all sessions
                sessions_added = self.append_new_sessions(sheet_id, sessions)
                logger.info(f"Rebuilt sheet with {sessions_added} sessions")
                
                return sheet_url, sessions_added
                
            except Exception as e:
                logger.error(f"Error rebuilding sheet: {e}")
                return sheet_url, 0

def main(append_only: bool = False):
    """Main function to generate/update the session report."""
    generator = SessionReportGenerator()
    
    logger.info("Starting session report generation...")
    
    # Get all sessions
    sessions = generator.get_all_sessions()
    
    if not sessions:
        logger.warning("No sessions found!")
        return
    
    logger.info(f"Found {len(sessions)} sessions")
    
    # Update the sheet
    sheet_url, sessions_added = generator.update_sheet(sessions, append_only=append_only)
    
    if sheet_url:
        print(f"Sheet URL: {sheet_url}")
        print(f"Sessions added: {sessions_added}")
    else:
        print("Failed to update sheet")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate/update Zoom sessions report")
    parser.add_argument('--append-only', action='store_true', 
                       help='Only append new sessions (default: rebuild entire sheet)')
    
    args = parser.parse_args()
    main(append_only=args.append_only)