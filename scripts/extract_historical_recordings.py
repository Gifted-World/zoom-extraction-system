#!/usr/bin/env python
"""
Script to extract historical recordings from Zoom and save them to Google Drive.
This script will:
1. Authenticate with Zoom API
2. Fetch list of past recordings within a date range
3. Download VTT transcripts for each recording
4. Create appropriate folder structure in Google Drive
5. Upload transcripts to Google Drive

Logging:
- All operations are logged to both console and a timestamped log file in the 'logs' directory
- Log level can be controlled with the --log-level parameter (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Use DEBUG level to see full OAuth scopes and detailed API interactions
"""

import os
import sys
import argparse
import requests
import json
import time
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Any, Literal
import re
import pandas as pd
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Add the parent directory to the path so we can import from the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.drive_manager import create_folder_structure, upload_file, get_drive_service
import config

# Set up logging with timestamped log file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_filename = os.path.join(log_dir, f"zoom_extraction_{timestamp}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_filename)
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {log_filename}")

class ZoomClient:
    """Client for interacting with Zoom API."""
    
    def __init__(self, account_type: Literal["primary", "personal"] = "primary"):
        """
        Initialize the Zoom client.
        
        Args:
            account_type: Type of account to use ("primary" or "personal")
        """
        self.account_type = account_type
        
        if account_type == "personal" and config.PERSONAL_ZOOM_CLIENT_ID:
            self.client_id = config.PERSONAL_ZOOM_CLIENT_ID
            self.client_secret = config.PERSONAL_ZOOM_CLIENT_SECRET
            self.account_id = config.PERSONAL_ZOOM_ACCOUNT_ID
        else:
            self.client_id = config.ZOOM_CLIENT_ID
            self.client_secret = config.ZOOM_CLIENT_SECRET
            self.account_id = config.ZOOM_ACCOUNT_ID
            
        self.base_url = config.ZOOM_BASE_URL
        self.access_token = None
        self.token_expiry = 0
        
        logger.info(f"Zoom Configuration ({account_type} account):")
        logger.info(f"Client ID: *****************{self.client_id[-4:]}")
        logger.info(f"Client Secret: ********")
        logger.info(f"Account ID: ******************{self.account_id[-4:]}")
        logger.info(f"Base URL: {self.base_url}")
        
    def get_access_token(self) -> str:
        """Get an access token from Zoom API."""
        if self.access_token and time.time() < self.token_expiry:
            return self.access_token
            
        url = "https://zoom.us/oauth/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "account_credentials",
            "account_id": self.account_id,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        logger.info(f"Requesting access token from {url}")
        logger.info(f"Request data: {json.dumps(data)}")
        
        try:
            response = requests.post(url, headers=headers, data=data)
            logger.info(f"Response status code: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Failed to get access token: {response.text}")
                return None
                
            result = response.json()
            self.access_token = result["access_token"]
            self.token_expiry = time.time() + result["expires_in"] - 60  # Subtract 60 seconds for safety
            
            logger.info("Access token received")
            logger.info(f"Token type: {result['token_type']}")
            logger.info(f"Expires in: {result['expires_in']} seconds")
            
            # Log scopes based on log level
            scopes = result.get("scope", "").split(" ")
            if logger.level <= logging.DEBUG:
                logger.debug(f"OAuth scopes: {', '.join(scopes)}")
            else:
                logger.info(f"OAuth scopes received (use --log-level=DEBUG to see full scopes)")
                
            return self.access_token
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            return None
            
    def download_file(self, url: str, output_path: str) -> bool:
        """
        Download a file from a URL using the access token.
        
        Args:
            url: URL to download from
            output_path: Path to save the file
            
        Returns:
            True if successful, False otherwise
        """
        if not url:
            logger.warning("No URL provided for download")
            return False
            
        access_token = self.get_access_token()
        if not access_token:
            logger.error("No access token available for download")
            return False
            
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        try:
            logger.debug(f"Downloading file from URL: {url}")
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to download file: {response.status_code} - {response.text}")
                return False
                
            with open(output_path, "wb") as f:
                f.write(response.content)
                
            logger.debug(f"File downloaded to: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return False
    
    def list_users(self) -> List[Dict]:
        """
        List users in the Zoom account.
        
        Returns:
            List of user objects
        """
        url = f"{self.base_url}/users"
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json"
        }
        params = {
            "status": "active",
            "page_size": 100
        }
        
        logger.info(f"Listing users from {url}")
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to list users: {response.text}")
                raise Exception(f"Failed to list users: {response.text}")
                
            data = response.json()
            users = data.get("users", [])
            logger.info(f"Found {len(users)} users")
            return users
        except Exception as e:
            logger.error(f"Error listing users: {str(e)}")
            raise
        
    def get_recordings(self, start_date: str, end_date: str, user_email: Optional[str] = None, page_size: int = 100) -> List[Dict]:
        """
        Get recordings from Zoom API.
        
        Args:
            start_date: Start date in format YYYY-MM-DD
            end_date: End date in format YYYY-MM-DD
            user_email: Optional email of specific user to get recordings for
            page_size: Number of recordings per page
            
        Returns:
            List of recording objects
        """
        recordings = []
        
        # If specific user is provided, get recordings only for that user
        if user_email:
            logger.info(f"Getting recordings for specific user: {user_email}")
            user_id = self._get_user_id_by_email(user_email)
            if user_id:
                user_recordings = self._get_user_recordings(user_id, start_date, end_date, page_size)
                recordings.extend(user_recordings)
            return recordings
        
        # First, try to use the account-level endpoint
        try:
            logger.info(f"Attempting to get recordings from account-level endpoint")
            account_recordings = self._get_account_recordings(start_date, end_date, page_size)
            if account_recordings:
                logger.info(f"Successfully retrieved recordings from account-level endpoint")
                return account_recordings
        except Exception as e:
            logger.warning(f"Failed to get recordings from account-level endpoint: {str(e)}")
            logger.info("Falling back to user-level endpoint")
        
        # If account-level endpoint fails, try user-level endpoint
        try:
            # Get list of users
            users = self.list_users()
            
            # Get recordings for each user
            for user in users:
                user_id = user.get("id")
                if not user_id:
                    continue
                
                logger.info(f"Getting recordings for user {user.get('email', user_id)}")
                user_recordings = self._get_user_recordings(user_id, start_date, end_date, page_size)
                recordings.extend(user_recordings)
                
            return recordings
        except Exception as e:
            logger.error(f"Error getting recordings: {str(e)}")
            raise
    
    def _get_user_id_by_email(self, email: str) -> Optional[str]:
        """
        Get user ID by email.
        
        Args:
            email: User email
            
        Returns:
            User ID if found, None otherwise
        """
        url = f"{self.base_url}/users"
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json"
        }
        params = {
            "email": email,
            "status": "active"
        }
        
        logger.info(f"Looking up user ID for email: {email}")
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to get user by email: {response.text}")
                return None
                
            data = response.json()
            users = data.get("users", [])
            
            if not users:
                logger.warning(f"No user found with email: {email}")
                return None
                
            user_id = users[0].get("id")
            logger.info(f"Found user ID: {user_id} for email: {email}")
            return user_id
        except Exception as e:
            logger.error(f"Error getting user by email: {str(e)}")
            return None
    
    def _get_account_recordings(self, start_date: str, end_date: str, page_size: int = 100) -> List[Dict]:
        """
        Get recordings from account-level endpoint.
        
        Args:
            start_date: Start date in format YYYY-MM-DD
            end_date: End date in format YYYY-MM-DD
            page_size: Number of recordings per page
            
        Returns:
            List of recording objects
        """
        recordings = []
        next_page_token = ""
        
        logger.info(f"Getting account recordings from {start_date} to {end_date}")
        
        while True:
            url = f"{self.base_url}/accounts/{self.account_id}/recordings"
            params = {
                "from": start_date,
                "to": end_date,
                "page_size": page_size,
                "next_page_token": next_page_token,
                "include_fields": "ai_summary"  # Include AI summary in the response
            }
            headers = {
                "Authorization": f"Bearer {self.get_access_token()}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"Making request to {url}")
            logger.info(f"Request parameters: {json.dumps(params)}")
            
            response = requests.get(url, params=params, headers=headers)
            logger.info(f"Response status code: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Failed to get account recordings: {response.text}")
                raise Exception(f"Failed to get account recordings: {response.text}")
                
            data = response.json()
            meetings = data.get("meetings", [])
            logger.info(f"Retrieved {len(meetings)} recordings")
            
            recordings.extend(meetings)
            
            next_page_token = data.get("next_page_token", "")
            if not next_page_token:
                break
                
        return recordings
    
    def get_user(self, user_id: str) -> Dict:
        """
        Get user details from Zoom API.
        
        Args:
            user_id: User ID
            
        Returns:
            User details as dictionary
        """
        url = f"{self.base_url}/users/{user_id}"
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Getting user details for {user_id}")
        
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to get user details: {response.text}")
                return {}
        except Exception as e:
            logger.warning(f"Error getting user details: {e}")
            return {}
    
    def _get_user_recordings(self, user_id: str, start_date: str, end_date: str, page_size: int = 100) -> List[Dict]:
        """
        Get recordings for a specific user.
        
        Args:
            user_id: User ID
            start_date: Start date in format YYYY-MM-DD
            end_date: End date in format YYYY-MM-DD
            page_size: Number of recordings per page
            
        Returns:
            List of recording objects
        """
        recordings = []
        next_page_token = ""
        
        logger.info(f"Getting user recordings from {start_date} to {end_date} for user {user_id}")
        
        while True:
            url = f"{self.base_url}/users/{user_id}/recordings"
            params = {
                "from": start_date,
                "to": end_date,
                "page_size": page_size,
                "next_page_token": next_page_token,
                "include_fields": "ai_summary"  # Include AI summary in the response
            }
            headers = {
                "Authorization": f"Bearer {self.get_access_token()}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"Making request to {url}")
            logger.info(f"Request parameters: {json.dumps(params)}")
            
            response = requests.get(url, params=params, headers=headers)
            logger.info(f"Response status code: {response.status_code}")
            
            if response.status_code != 200:
                logger.warning(f"Failed to get user recordings: {response.text}")
                return []
                
            data = response.json()
            meetings = data.get("meetings", [])
            logger.info(f"Retrieved {len(meetings)} recordings for user {user_id}")
            
            recordings.extend(meetings)
            
            next_page_token = data.get("next_page_token", "")
            if not next_page_token:
                break
                
        return recordings
        
    def download_transcript(self, download_url: str, output_path: str) -> bool:
        """
        Download a transcript file from Zoom.
        
        Args:
            download_url: URL to download the transcript
            output_path: Path to save the transcript
            
        Returns:
            True if successful, False otherwise
        """
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}"
        }
        
        response = requests.get(download_url, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to download transcript: {response.text}")
            return False
            
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(response.content)
            
        return True

def parse_meeting_topic(topic: str) -> Dict[str, str]:
    """
    Parse the meeting topic to extract course name and session information.
    Accepts any format of meeting topic.
    
    Args:
        topic: Meeting topic
        
    Returns:
        Dictionary with course_name, session_number, and session_name
    """
    # Try to parse with expected format: "Course Name - Session X: Session Name"
    try:
        parts = topic.split(" - ")
        if len(parts) >= 2 and "Session" in parts[1]:
            course_name = parts[0].strip()
            session_part = parts[1].strip()
            
            # Try to extract session number
            session_number_match = re.search(r"Session\s*(\d+)", session_part)
            if session_number_match:
                session_number = int(session_number_match.group(1))
            else:
                session_number = 0
                
            # Try to extract session name
            if ":" in session_part:
                session_name = session_part.split(":", 1)[1].strip()
            else:
                session_name = session_part.replace(f"Session {session_number}", "").strip()
                
            return {
                "course_name": course_name,
                "session_number": session_number,
                "session_name": session_name
            }
    except (IndexError, ValueError, AttributeError):
        pass
        
    # If we can't parse with the expected format, use the topic as is
    logger.info(f"Using generic format for meeting topic: {topic}")
    return {
        "course_name": topic,
        "session_number": 0,
        "session_name": topic
    }

async def process_recording(recording: Dict, temp_dir: str) -> bool:
    """
    Process a recording by downloading transcript and uploading to Drive.
    
    Args:
        recording: Recording object from Zoom API
        temp_dir: Directory for temporary files
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Extract meeting information
        topic = recording.get("topic", "Unknown Meeting")
        start_time = recording.get("start_time", "")
        account_type = recording.get("account_type", "primary")
        
        # Parse start time to get date
        try:
            start_date = datetime.fromisoformat(start_time.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse start time: {start_time}")
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        # Parse meeting topic to get course and session information
        parsed_topic = parse_meeting_topic(topic)
        course_name = parsed_topic["course_name"]
        session_number = parsed_topic["session_number"]
        session_name = parsed_topic["session_name"]
        
        logger.info(f"Course: {course_name}, Session: {session_name}, Date: {start_date}")
        
        # Check for transcript
        transcript_file = None
        video_files = []
        chat_file = None
        
        for file in recording.get("recording_files", []):
            file_type = file.get("file_type", "")
            
            if file_type == "TRANSCRIPT":
                transcript_file = file
            elif file_type in ["MP4", "M4A"]:
                video_files.append(file)
            elif file_type == "CHAT":
                chat_file = file
        
        if not transcript_file:
            logger.warning(f"No transcript found for {topic}")
        
        # Create folder structure in Drive
        folder_ids = await create_folder_structure(course_name, session_name, start_date)
        if not folder_ids:
            logger.error(f"Failed to create folder structure for {topic}")
            return False
        
        course_folder_id = folder_ids["course_folder_id"]
        session_folder_id = folder_ids["session_folder_id"]
        
        logger.info(f"Created folder structure: Course ID: {course_folder_id}, Session ID: {session_folder_id}")
        
        # Download and upload transcript if available
        if transcript_file:
            download_url = transcript_file.get("download_url", "")
            if download_url:
                # Create local path for transcript
                transcript_path = os.path.join(temp_dir, f"{topic.replace(' ', '_')}_transcript.vtt")
                
                # Initialize Zoom client with the appropriate account type
                zoom_client = ZoomClient(account_type)
                
                # Download transcript
                logger.info(f"Downloading transcript for {topic}")
                if zoom_client.download_transcript(download_url, transcript_path):
                    # Upload to Drive
                    logger.info(f"Uploading transcript for {topic}")
                    await upload_file(
                        file_path=transcript_path,
                        folder_id=session_folder_id,
                        file_name="transcript.vtt",
                        mime_type="text/vtt"
                    )
                    
                    # Clean up
                    os.unlink(transcript_path)
                    logger.info(f"Transcript processed for {topic}")
                else:
                    logger.error(f"Failed to download transcript for {topic}")
        
        # Download and upload chat log if available
        if chat_file:
            download_url = chat_file.get("download_url", "")
            if download_url:
                # Create local path for chat log
                chat_path = os.path.join(temp_dir, f"{topic.replace(' ', '_')}_chat.txt")
                
                # Initialize Zoom client with the appropriate account type
                zoom_client = ZoomClient(account_type)
                
                # Download chat log
                logger.info(f"Downloading chat log for {topic}")
                if zoom_client.download_file(download_url, chat_path):
                    # Upload to Drive
                    logger.info(f"Uploading chat log for {topic}")
                    await upload_file(
                        file_path=chat_path,
                        folder_id=session_folder_id,
                        file_name="chat_log.txt",
                        mime_type="text/plain"
                    )
                    
                    # Clean up
                    os.unlink(chat_path)
                    logger.info(f"Chat log processed for {topic}")
                else:
                    logger.error(f"Failed to download chat log for {topic}")
        
        # Update meeting metadata
        await update_meeting_metadata(session_folder_id, recording, video_files, chat_file)
        
        # Process AI summary and smart recording data if available
        await process_ai_data(session_folder_id, recording, account_type)
        
        return True
    except Exception as e:
        logger.error(f"Error processing recording: {e}")
        return False

async def update_meeting_metadata(session_folder_id: str, recording: Dict, video_files: List[Dict], chat_file: Dict = None) -> None:
    """
    Create or update metadata file with meeting information.
    
    Args:
        session_folder_id: ID of the session folder
        recording: Recording object from Zoom API
        video_files: List of video file objects
        chat_file: Chat file object (optional)
    """
    try:
        # Create metadata object
        metadata = {
            "meeting_id": recording.get("id", ""),
            "meeting_uuid": recording.get("uuid", ""),
            "topic": recording.get("topic", ""),
            "host_id": recording.get("host_id", ""),
            "host_email": recording.get("host_email", ""),
            "host_name": recording.get("host_name", "Unknown"),
            "start_time": recording.get("start_time", ""),
            "end_time": recording.get("end_time", ""),
            "duration": recording.get("duration", 0),
            "total_size": recording.get("total_size", 0),
            "recording_count": recording.get("recording_count", 0),
            "share_url": recording.get("share_url", ""),
            "password": recording.get("password", ""),
            "timezone": recording.get("timezone", ""),
            "videos": [],
            "chat_url": None,
            "extracted_at": datetime.now().isoformat(),
        }
        
        # Add video information
        for video in video_files:
            metadata["videos"].append({
                "id": video.get("id", ""),
                "file_type": video.get("file_type", ""),
                "file_size": video.get("file_size", 0),
                "play_url": video.get("play_url", ""),
                "download_url": video.get("download_url", ""),
                "recording_type": video.get("recording_type", ""),
                "recording_start": video.get("recording_start", ""),
                "recording_end": video.get("recording_end", ""),
            })
            
        # Add chat information if available
        if chat_file:
            metadata["chat_url"] = chat_file.get("download_url", "")
            
        # Save metadata to temporary file
        metadata_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp", "metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
            
        # Upload metadata to Drive
        await upload_file(
            file_path=metadata_path,
            folder_id=session_folder_id,
            file_name="meeting_metadata.json",
            mime_type="application/json"
        )
        
        # Clean up
        os.unlink(metadata_path)
        
        logger.info(f"Updated meeting metadata")
    except Exception as e:
        logger.error(f"Error updating meeting metadata: {e}")

async def process_ai_data(session_folder_id: str, recording: Dict, account_type: str = "primary") -> None:
    """
    Process AI-generated data from Zoom (AI summary, smart chapters, smart highlights).
    
    Args:
        session_folder_id: ID of the session folder in Drive
        recording: Recording object from Zoom API
        account_type: Type of Zoom account to use ("primary" or "personal")
    """
    try:
        # Import here to avoid circular imports
        from app.services.zoom_client import get_recording_info
        
        meeting_uuid = recording.get("uuid")
        if not meeting_uuid:
            logger.warning("No meeting UUID found in recording data")
            return
            
        logger.info(f"Processing AI data for meeting {meeting_uuid}")
        
        # Get recording info with AI summary
        recording_info = await get_recording_info(meeting_uuid, account_type)
        
        # Create temp directory if it doesn't exist
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Process AI summary
        if hasattr(recording_info, "ai_summary") and recording_info.ai_summary:
            logger.info(f"AI summary found for meeting {meeting_uuid}")
            
            # Save to temp file
            ai_summary_path = os.path.join(temp_dir, "ai_summary.json")
            with open(ai_summary_path, "w") as f:
                json.dump(recording_info.ai_summary.dict(), f, indent=2)
            
            # Upload to Drive
            file_metadata = await upload_file(
                file_path=ai_summary_path,
                folder_id=session_folder_id,
                file_name="ai_summary.json",
                mime_type="application/json"
            )
            
            if file_metadata:
                logger.info(f"AI summary uploaded for meeting {meeting_uuid}")
            
            # Clean up
            os.unlink(ai_summary_path)
        else:
            logger.info(f"No AI summary found for meeting {meeting_uuid}")
        
        # Process smart chapters
        if hasattr(recording_info, "smart_recording_chapters") and recording_info.smart_recording_chapters:
            logger.info(f"Smart chapters found for meeting {meeting_uuid}")
            
            # Save to temp file
            chapters_path = os.path.join(temp_dir, "smart_chapters.json")
            chapters_data = [chapter.dict() for chapter in recording_info.smart_recording_chapters]
            with open(chapters_path, "w") as f:
                json.dump(chapters_data, f, indent=2)
            
            # Upload to Drive
            file_metadata = await upload_file(
                file_path=chapters_path,
                folder_id=session_folder_id,
                file_name="smart_chapters.json",
                mime_type="application/json"
            )
            
            if file_metadata:
                logger.info(f"Smart chapters uploaded for meeting {meeting_uuid}")
            
            # Clean up
            os.unlink(chapters_path)
        else:
            logger.info(f"No smart chapters found for meeting {meeting_uuid}")
        
        # Process smart highlights
        if hasattr(recording_info, "smart_recording_highlights") and recording_info.smart_recording_highlights:
            logger.info(f"Smart highlights found for meeting {meeting_uuid}")
            
            # Save to temp file
            highlights_path = os.path.join(temp_dir, "smart_highlights.json")
            highlights_data = [highlight.dict() for highlight in recording_info.smart_recording_highlights]
            with open(highlights_path, "w") as f:
                json.dump(highlights_data, f, indent=2)
            
            # Upload to Drive
            file_metadata = await upload_file(
                file_path=highlights_path,
                folder_id=session_folder_id,
                file_name="smart_highlights.json",
                mime_type="application/json"
            )
            
            if file_metadata:
                logger.info(f"Smart highlights uploaded for meeting {meeting_uuid}")
            
            # Clean up
            os.unlink(highlights_path)
        else:
            logger.info(f"No smart highlights found for meeting {meeting_uuid}")
            
    except Exception as e:
        logger.error(f"Error processing AI data: {e}")
        return

async def create_summary_report(recordings: List[Dict], temp_dir: str) -> None:
    """
    Create a summary report of all recordings in Google Sheets.
    Merges new recordings with existing report data to ensure all sessions are preserved.
    
    Args:
        recordings: List of recording objects from Zoom API
        temp_dir: Directory for temporary files
    """
    logger.info("Creating summary report of extracted recordings")
    
    # Prepare data for the new recordings
    new_report_data = []
    for recording in recordings:
        # Extract basic information
        topic = recording.get("topic", "Unknown")
        start_time = recording.get("start_time", "")
        duration = recording.get("duration", 0)
        
        # Extract user information
        user_name = recording.get("host_name", recording.get("host_id", "Unknown"))
        user_email = recording.get("host_email", "Unknown")
        
        # Try to get more detailed host information if available
        if user_name == "Unknown" or user_email == "Unknown":
            try:
                # If we have host_id but not name/email, try to get user details
                host_id = recording.get("host_id")
                if host_id:
                    # Create a local ZoomClient instance
                    from scripts.extract_historical_recordings import ZoomClient
                    local_zoom_client = ZoomClient()
                    user_details = local_zoom_client.get_user(host_id)
                    if user_details:
                        user_name = user_details.get("first_name", "") + " " + user_details.get("last_name", "")
                        user_email = user_details.get("email", user_email)
            except Exception as e:
                logger.warning(f"Could not get host details: {e}")
        
        # Check if transcript exists
        has_transcript = False
        transcript_url = None
        
        # Find video URL
        zoom_video_url = ""
        video_files = []
        
        for file in recording.get("recording_files", []):
            if file.get("file_type") == "TRANSCRIPT":
                has_transcript = True
                transcript_url = file.get("download_url", "")
            elif file.get("file_type") in ["MP4", "M4A"]:
                video_files.append(file)
                if not zoom_video_url and file.get("file_type") == "MP4":
                    zoom_video_url = file.get("play_url", "")
        
        # Calculate total size in MB and round to integer
        total_size_mb = int(sum(file.get("file_size", 0) for file in recording.get("recording_files", [])) / (1024 * 1024))
        
        # Parse meeting topic to get folder information
        parsed_topic = parse_meeting_topic(topic)
        course_name = parsed_topic["course_name"]
        session_number = parsed_topic["session_number"]
        session_name = parsed_topic["session_name"]
        
        # Parse start time to get date
        try:
            start_date = datetime.fromisoformat(start_time.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except (ValueError, AttributeError):
            start_date = datetime.now().strftime("%Y-%m-%d")
        
        # Find the session folder in Drive to get analysis file links
        session_folder_id = None
        analysis_links = {
            "executive_summary_url": "",
            "pedagogical_analysis_url": "",
            "aha_moments_url": "",
            "engagement_metrics_url": "",
            "concise_summary_url": "",
            "ai_summary_url": "",
            "smart_chapters_url": "",
            "smart_highlights_url": ""
        }
        
        try:
            # Get Drive service
            drive_service = get_drive_service()
            
            # Find course folder
            course_folder_name = f"{course_name}"
            query = f"name = '{course_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{config.GOOGLE_DRIVE_ROOT_FOLDER}' in parents and trashed = false"
            results = drive_service.files().list(q=query).execute()
            
            if results.get('files'):
                course_folder_id = results['files'][0]['id']
                
                # Find session folder
                session_folder_name = f"{course_name}_{start_date}"
                query = f"name = '{session_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{course_folder_id}' in parents and trashed = false"
                results = drive_service.files().list(q=query).execute()
                
                if not results.get('files'):
                    # Try with session number in the name
                    session_folder_name = f"Session_{session_number}_{session_name}_{start_date}"
                    query = f"name = '{session_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{course_folder_id}' in parents and trashed = false"
                    results = drive_service.files().list(q=query).execute()
                
                if results.get('files'):
                    session_folder_id = results['files'][0]['id']
                    
                    # Find analysis files
                    analysis_file_names = [
                        "executive_summary.md",
                        "pedagogical_analysis.md",
                        "aha_moments.md",
                        "engagement_metrics.json",
                        "concise_summary.md",
                        "ai_summary.json",
                        "smart_chapters.json",
                        "smart_highlights.json"
                    ]
                    
                    for file_name in analysis_file_names:
                        query = f"name = '{file_name}' and '{session_folder_id}' in parents and trashed = false"
                        results = drive_service.files().list(q=query, fields="files(id, name, webViewLink)").execute()
                        
                        if results.get('files'):
                            file_key = file_name.split(".")[0] + "_url"
                            analysis_links[file_key] = results['files'][0].get('webViewLink', '')
        except Exception as e:
            logger.error(f"Error finding analysis files for {topic}: {e}")
        
        # Add to report data - exclude Password and Drive Video URL
        new_report_data.append({
            "Meeting Topic": topic,
            "Host Name": user_name,
            "Host Email": user_email,
            "Date": datetime.fromisoformat(start_time.replace("Z", "+00:00")).strftime("%d %b %Y") if "T" in start_time else start_date,
            "Start Time": start_time,
            "Duration (minutes)": duration,
            "Has Transcript": has_transcript,
            "Transcript URL": transcript_url if has_transcript else "N/A",
            "Meeting UUID": recording.get("uuid", ""),
            "Meeting ID": recording.get("id", ""),
            "Size (MB)": total_size_mb,
            "Zoom Video URL": zoom_video_url,
            "Executive Summary URL": analysis_links["executive_summary_url"],
            "Pedagogical Analysis URL": analysis_links["pedagogical_analysis_url"],
            "Aha Moments URL": analysis_links["aha_moments_url"],
            "Engagement Metrics URL": analysis_links["engagement_metrics_url"],
            "Concise Summary URL": analysis_links["concise_summary_url"],
            "AI Summary URL": analysis_links["ai_summary_url"],
            "Smart Chapters URL": analysis_links["smart_chapters_url"],
            "Smart Highlights URL": analysis_links["smart_highlights_url"],
            "Account Type": recording.get("account_type", "primary")
        })
    
    # If no new recordings, just log and return
    if not new_report_data:
        logger.warning("No new recordings found for the report")
        return
    
    # First check if we have a specific report ID in environment variables
    report_id = os.environ.get("ZOOM_REPORT_ID", "")
    if not report_id:
        logger.warning("No ZOOM_REPORT_ID found in environment variables")
    
    # Try to download existing report data
    existing_report_data = []
    existing_report_downloaded = False
    
    try:
        if report_id:
            drive_service = get_drive_service()
            
            # First check if the file exists and is accessible
            try:
                logger.info(f"Downloading existing report with ID: {report_id}")
                
                # Export the Google Sheet as CSV
                request = drive_service.files().export_media(
                    fileId=report_id,
                    mimeType='text/csv'
                )
                
                existing_report_path = os.path.join(temp_dir, "existing_zoom_report.csv")
                
                with open(existing_report_path, 'wb') as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done = False
                    while done is False:
                        status, done = downloader.next_chunk()
                
                # Read the existing report
                if os.path.exists(existing_report_path) and os.path.getsize(existing_report_path) > 0:
                    existing_df = pd.read_csv(existing_report_path)
                    existing_report_data = existing_df.to_dict('records')
                    logger.info(f"Successfully downloaded existing report with {len(existing_report_data)} entries")
                    existing_report_downloaded = True
            except Exception as e:
                logger.warning(f"Could not download existing report: {e}")
    except Exception as e:
        logger.warning(f"Error accessing existing report: {e}")
    
    # Merge existing and new report data
    merged_report_data = []
    
    if existing_report_downloaded and existing_report_data:
        # Create a set of UUIDs from new recordings to avoid duplicates
        new_uuids = {record.get("Meeting UUID") for record in new_report_data if record.get("Meeting UUID")}
        
        # Add all existing records that don't have UUIDs in the new data
        for record in existing_report_data:
            if record.get("Meeting UUID") not in new_uuids:
                merged_report_data.append(record)
            else:
                logger.info(f"Skipping existing record with UUID {record.get('Meeting UUID')} as it's in new data")
        
        # Add all new records
        merged_report_data.extend(new_report_data)
        logger.info(f"Merged report has {len(merged_report_data)} entries ({len(existing_report_data)} existing + {len(new_report_data)} new)")
    else:
        # If no existing data, just use new data
        merged_report_data = new_report_data
        logger.info(f"Using only new data with {len(new_report_data)} entries")
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(merged_report_data)
    
    # Ensure URLs don't spill over by setting display.max_colwidth
    with pd.option_context('display.max_colwidth', None):
        report_path = os.path.join(temp_dir, "zoom_recordings_report.csv")
        df.to_csv(report_path, index=False)
    logger.info(f"Saved merged report to {report_path}")
    
    # Upload to Google Drive
    try:
        drive_service = get_drive_service()
        
        if report_id:
            # Use the specific report ID
            try:
                # Create media
                media = MediaFileUpload(
                    report_path,
                    mimetype='text/csv',
                    resumable=True
                )
                
                # Update file content
                logger.info(f"Updating report with ID: {report_id}")
                
                # Update the file
                file = drive_service.files().update(
                    fileId=report_id,
                    media_body=media,
                    supportsAllDrives=True
                ).execute()
                
                # Get the webViewLink
                file = drive_service.files().get(
                    fileId=report_id,
                    fields='webViewLink',
                    supportsAllDrives=True
                ).execute()
                
                logger.info(f"Report updated successfully")
                logger.info(f"Report can be viewed at: {file.get('webViewLink')}")
                return
            except Exception as e:
                logger.warning(f"Error updating report with ID {report_id}: {e}")
                # Continue with the regular flow to create/update by name
        
        # If no specific ID or failed to update, check if report exists by name
        report_name = "Zoom Recordings Report"
        
        # Check in shared drive if configured
        if config.USE_SHARED_DRIVE:
            query = f"name = '{report_name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
            results = drive_service.files().list(
                q=query,
                corpora="drive",
                driveId=config.GOOGLE_SHARED_DRIVE_ID,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()
        else:
            # Check in regular drive
            query = f"name = '{report_name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and '{config.GOOGLE_DRIVE_ROOT_FOLDER}' in parents and trashed = false"
            results = drive_service.files().list(q=query).execute()
        
        if results.get('files'):
            # Update existing report
            file_id = results['files'][0]['id']
            
            # Create media
            media = MediaFileUpload(
                report_path,
                mimetype='text/csv',
                resumable=True
            )
            
            # Update file content
            logger.info(f"Updating existing report with ID: {file_id}")
            
            if config.USE_SHARED_DRIVE:
                file = drive_service.files().update(
                    fileId=file_id,
                    media_body=media,
                    supportsAllDrives=True
                ).execute()
                
                # Get the webViewLink
                file = drive_service.files().get(
                    fileId=file_id,
                    fields='webViewLink',
                    supportsAllDrives=True
                ).execute()
            else:
                file = drive_service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
                
                # Get the webViewLink
                file = drive_service.files().get(
                    fileId=file_id,
                    fields='webViewLink'
                ).execute()
            
            logger.info(f"Report updated successfully")
            logger.info(f"Report can be viewed at: {file.get('webViewLink')}")
        else:
            # Create new report
            if config.USE_SHARED_DRIVE:
                file_metadata = {
                    'name': report_name,
                    'driveId': config.GOOGLE_SHARED_DRIVE_ID,
                    'parents': [config.GOOGLE_DRIVE_ROOT_FOLDER],
                    'mimeType': 'application/vnd.google-apps.spreadsheet'
                }
                
                # Create media
                media = MediaFileUpload(
                    report_path,
                    mimetype='text/csv',
                    resumable=True
                )
                
                # Upload file
                logger.info("Creating new report in shared drive")
                file = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,webViewLink',
                    supportsAllDrives=True
                ).execute()
            else:
                file_metadata = {
                    'name': report_name,
                    'parents': [config.GOOGLE_DRIVE_ROOT_FOLDER],
                    'mimeType': 'application/vnd.google-apps.spreadsheet'
                }
                
                # Create media
                media = MediaFileUpload(
                    report_path,
                    mimetype='text/csv',
                    resumable=True
                )
                
                # Upload file
                logger.info("Creating new report in Google Drive")
                file = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,webViewLink'
                ).execute()
            
            logger.info(f"Report created with ID: {file.get('id')}")
            logger.info(f"Report can be viewed at: {file.get('webViewLink')}")
            logger.info(f"Add this ID to your .env file as ZOOM_REPORT_ID=\"{file.get('id')}\"")
        
    except Exception as e:
        logger.error(f"Error uploading report to Google Drive: {e}")
        logger.info(f"Report is still available locally at: {report_path}")
        
    return

async def main():
    """Main function to extract recordings and save to Drive."""
    parser = argparse.ArgumentParser(description="Extract historical recordings from Zoom")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--temp-dir", type=str, default="./temp", help="Temporary directory for downloads")
    parser.add_argument("--user-email", type=str, help="Specific user email to get recordings for")
    parser.add_argument("--log-level", type=str, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        default="INFO", help="Set the logging level")
    parser.add_argument("--account", type=str, choices=["primary", "personal", "both"], 
                        default="both", help="Which Zoom account to process")
    
    args = parser.parse_args()
    
    # Set logging level based on command-line argument
    logger.setLevel(getattr(logging, args.log_level))
    
    # Set default dates if not provided
    if not args.start_date:
        args.start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not args.end_date:
        args.end_date = datetime.now().strftime("%Y-%m-%d")
        
    # Create temp directory
    os.makedirs(args.temp_dir, exist_ok=True)
    
    # Determine which accounts to process
    accounts_to_process = []
    if args.account == "primary" or args.account == "both":
        accounts_to_process.append("primary")
    if args.account == "personal" or args.account == "both":
        # Only add personal account if credentials are configured
        if config.PERSONAL_ZOOM_CLIENT_ID and config.PERSONAL_ZOOM_ACCOUNT_ID:
            accounts_to_process.append("personal")
        else:
            logger.warning("Personal Zoom account credentials not configured, skipping")
    
    all_recordings = []
    
    try:
        logger.info(f"Extracting recordings from {args.start_date} to {args.end_date}")
        if args.user_email:
            logger.info(f"Getting recordings only for user: {args.user_email}")
        
        # Process each account
        for account_type in accounts_to_process:
            logger.info(f"Processing {account_type} Zoom account")
            
            # Get recordings for this account
            zoom_client = ZoomClient(account_type)
            recordings = zoom_client.get_recordings(args.start_date, args.end_date, args.user_email)
            
            logger.info(f"Found {len(recordings)} recordings in {account_type} account")
            
            # Process each recording
            for recording in recordings:
                topic = recording.get("topic", "Unknown Meeting")
                logger.info(f"Processing recording from {account_type} account: {topic}")
                
                # Add account type to the recording for reference
                recording["account_type"] = account_type
                
                success = await process_recording(recording, args.temp_dir)
                if success:
                    logger.info(f"Successfully processed recording: {topic}")
                else:
                    logger.warning(f"Failed to process recording: {topic}")
            
            # Add to the combined list
            all_recordings.extend(recordings)
                
        logger.info(f"Extraction completed for all accounts. Total recordings: {len(all_recordings)}")
        
        # Create summary report with all recordings
        await create_summary_report(all_recordings, args.temp_dir)
        
    except Exception as e:
        logger.error(f"Error extracting recordings: {e}")
        sys.exit(1)
        
if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 