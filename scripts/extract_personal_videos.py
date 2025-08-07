#!/usr/bin/env python3
"""
Script to download all Zoom recordings including videos to Google Drive.
Specifically for personal account with limited Zoom storage.
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timedelta
import requests
import tempfile

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from app.services.drive_manager import create_folder_structure, upload_file, get_drive_service
from app.services.zoom_client import get_oauth_token

# Set up logging
# Create both detailed log file and simpler console output
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = f"{log_dir}/personal_extraction_{datetime.now().strftime('%Y%m%d')}.log"

# File handler - detailed logs
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

# Console handler - minimal logs
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)  # Only WARNING and above for console
console_handler.setFormatter(logging.Formatter("%(message)s"))

# Custom logger for specific meeting updates
meeting_logger = logging.getLogger("meeting_updates")
meeting_logger.setLevel(logging.INFO)
meeting_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Override Google Drive root folder with user-specified folder
# Use specific personal folder ID if available, otherwise fallback to default
TARGET_DRIVE_FOLDER = os.getenv('PERSONAL_DRIVE_FOLDER_ID', config.GOOGLE_DRIVE_ROOT_FOLDER)

class PersonalZoomExtractor:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.account_type = "personal"  # Force using personal account
        self.processed_file = "processed_meetings.json"
        self.processed_meetings = self._load_processed_meetings()
        
    def _load_processed_meetings(self):
        """Load list of already processed meetings"""
        if os.path.exists(self.processed_file):
            try:
                with open(self.processed_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
        
    def _save_processed_meetings(self):
        """Save list of processed meetings"""
        try:
            with open(self.processed_file, 'w') as f:
                json.dump(self.processed_meetings, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving processed meetings: {e}")
        
    async def get_recordings(self, from_date, to_date):
        """Get recordings from personal Zoom account"""
        try:
            # Get OAuth token for personal account
            logger.info(f"Getting OAuth token for account type: {self.account_type}")
            logger.info(f"Using client ID: {config.PERSONAL_ZOOM_CLIENT_ID[:5]}...{config.PERSONAL_ZOOM_CLIENT_ID[-4:]}")
            logger.info(f"Using account ID: {config.PERSONAL_ZOOM_ACCOUNT_ID[:5]}...{config.PERSONAL_ZOOM_ACCOUNT_ID[-4:]}")
            
            # Direct implementation of OAuth token request to debug
            url = "https://zoom.us/oauth/token"
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {
                "grant_type": "account_credentials",
                "account_id": config.PERSONAL_ZOOM_ACCOUNT_ID,
                "client_id": config.PERSONAL_ZOOM_CLIENT_ID,
                "client_secret": config.PERSONAL_ZOOM_CLIENT_SECRET
            }
            
            logger.info(f"Making OAuth request to {url}")
            response = requests.post(url, headers=headers, data=data)
            
            if response.status_code != 200:
                logger.error(f"OAuth error ({response.status_code}): {response.text}")
                return []
            
            token_data = response.json()
            token = token_data["access_token"]
            logger.info(f"Successfully obtained OAuth token")
            
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
                    # Use user-level recordings endpoint with proper pagination
                    next_page_token = ""
                    page_count = 0
                    total_meetings_for_user = 0
                    
                    while True:
                        page_count += 1
                        logger.info(f"Fetching page {page_count} for user {user_email}")
                        
                        params = {
                            "from": from_date,
                            "to": to_date,
                            "page_size": 300,
                            "trash_type": "meeting_recordings" # Include recordings that might be in trash
                        }
                        
                        # Add next_page_token for pagination
                        if next_page_token:
                            params["next_page_token"] = next_page_token
                        
                        recordings_response = requests.get(
                            f"{config.ZOOM_BASE_URL}/users/{user_id}/recordings",
                            headers=headers,
                            params=params
                        )
                        recordings_response.raise_for_status()
                        recordings_data = recordings_response.json()
                        
                        user_meetings = recordings_data.get("meetings", [])
                        total_meetings_for_user += len(user_meetings)
                        
                        # Add user info to each meeting
                        for meeting in user_meetings:
                            meeting["host_email"] = user_email
                            meeting["host_name"] = user.get("display_name", user_email)
                        
                        all_meetings.extend(user_meetings)
                        
                        # Check if there are more pages
                        next_page_token = recordings_data.get("next_page_token", "")
                        if not next_page_token:
                            break
                    
                    logger.info(f"Found {total_meetings_for_user} meetings for {user_email} across {page_count} pages")
                    
                except Exception as e:
                    logger.warning(f"Error fetching recordings for user {user_email}: {e}")
                    continue
            
            return all_meetings
        except Exception as e:
            logger.error(f"Error getting recordings: {e}")
            return []
    
    async def download_and_upload_file(self, download_url, destination_folder_id, file_name, mime_type="application/octet-stream"):
        """Download file from Zoom and upload to Drive"""
        try:
            # Get OAuth token
            token = get_oauth_token(self.account_type)
            
            # Download file with auth token
            logger.info(f"Downloading {file_name}...")
            
            # Add access token to the download URL
            separator = "&" if "?" in download_url else "?"
            download_url_with_token = f"{download_url}{separator}access_token={token}"
            
            temp_file_path = os.path.join(self.temp_dir, file_name)
            response = requests.get(download_url_with_token, stream=True)
            
            if response.status_code == 200:
                with open(temp_file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logger.info(f"Download complete. Uploading {file_name} to Drive...")
                
                # Upload to Google Drive
                file_metadata = await upload_file(
                    file_path=temp_file_path,
                    folder_id=destination_folder_id,
                    file_name=file_name,
                    mime_type=mime_type
                )
                
                # Delete local file
                os.remove(temp_file_path)
                
                logger.info(f"Successfully uploaded {file_name}")
                return file_metadata
            else:
                logger.error(f"Failed to download {file_name}: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error downloading/uploading {file_name}: {e}")
            return None
    
    async def process_meeting(self, meeting, meeting_num=0, total_meetings=0):
        """Process a single meeting's recordings"""
        try:
            topic = meeting.get("topic", "Unknown Meeting")
            start_time = meeting.get("start_time", "")
            
            # Parse meeting topic and date for folder structure
            if " - " in topic:
                course_name = topic.split(" - ")[0]
            else:
                course_name = topic
                
            # Parse date
            try:
                start_date = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                session_date = start_date.strftime("%Y-%m-%d")
                formatted_date = start_date.strftime("%b %d, %Y")
            except:
                session_date = datetime.now().strftime("%Y-%m-%d")
                formatted_date = "Unknown Date"
            
            # Create folder name with date and meeting name
            session_name = f"{topic} ({formatted_date})"
            
            logger.info(f"Processing: {session_name}")
            if meeting_num > 1:  # Don't print progress indicator for first item as we already showed "Processing X recordings"
                print(f"Processing {meeting_num}/{total_meetings}: {topic}")
            
            # Fix folder names that might cause issues with Google Drive API
            safe_course_name = course_name.replace("'", "")
            safe_session_name = session_name.replace("'", "")
            
            # Create folder structure (override root folder with target folder)
            # Hack: Save original root folder, replace temporarily, then restore
            original_root_folder = config.GOOGLE_DRIVE_ROOT_FOLDER
            config.GOOGLE_DRIVE_ROOT_FOLDER = TARGET_DRIVE_FOLDER
            
            folder_structure = await create_folder_structure(
                course_name=safe_course_name,
                session_number=0,
                session_name=safe_session_name,
                session_date=session_date
            )
            
            # Restore original root folder
            config.GOOGLE_DRIVE_ROOT_FOLDER = original_root_folder
            
            session_folder_id = folder_structure["session_folder_id"]
            
            # Process all files
            files_uploaded = []
            for file in meeting.get("recording_files", []):
                file_type = file.get("file_type", "")
                recording_type = file.get("recording_type", "")
                download_url = file.get("download_url", "")
                
                if not download_url:
                    continue
                
                # Determine file name and type
                if file_type == "MP4":
                    if "shared_screen_with_speaker_view" in recording_type:
                        file_name = "recording_with_speaker.mp4"
                    elif "shared_screen" in recording_type:
                        file_name = "recording_shared_screen.mp4"
                    else:
                        file_name = f"recording_{recording_type}.mp4"
                    mime_type = "video/mp4"
                    
                elif file_type == "M4A":
                    file_name = "audio_recording.m4a"
                    mime_type = "audio/mp4"
                    
                elif file_type == "TRANSCRIPT" or file_type == "CC":
                    file_name = "transcript.vtt"
                    mime_type = "text/vtt"
                    
                elif file_type == "CHAT" or recording_type == "chat_file":
                    file_name = "chat_log.txt"
                    mime_type = "text/plain"
                    
                elif recording_type == "summary":
                    file_name = "ai_summary.json"
                    mime_type = "application/json"
                    
                elif recording_type == "summary_next_steps":
                    file_name = "ai_next_steps.json"
                    mime_type = "application/json"
                    
                else:
                    file_name = f"{file_type}_{recording_type}.txt"
                    mime_type = "text/plain"
                
                # Download and upload file
                result = await self.download_and_upload_file(
                    download_url=download_url,
                    destination_folder_id=session_folder_id,
                    file_name=file_name,
                    mime_type=mime_type
                )
                
                if result:
                    files_uploaded.append(file_name)
            
            # Save meeting metadata
            metadata = {
                "meeting_uuid": meeting.get("uuid", ""),
                "meeting_id": meeting.get("id", ""),
                "meeting_topic": topic,
                "host_name": meeting.get("host_name", ""),
                "host_email": meeting.get("host_email", ""),
                "start_time": start_time,
                "end_time": meeting.get("end_time", ""),
                "duration": meeting.get("duration", 0),
                "timezone": meeting.get("timezone", ""),
                "total_size": meeting.get("total_size", 0),
                "share_url": meeting.get("share_url", ""),
                "processed_at": datetime.now().isoformat()
            }
            
            metadata_path = os.path.join(self.temp_dir, "metadata.json")
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)
                
            await upload_file(
                file_path=metadata_path,
                folder_id=session_folder_id,
                file_name="meeting_metadata.json",
                mime_type="application/json"
            )
            
            os.remove(metadata_path)
            
            logger.info(f"Successfully processed {topic}. Files: {', '.join(files_uploaded)}")
            # Print concise summary to console
            print(f"✓ Downloaded: {topic} ({len(files_uploaded)} files)")
            return True
            
        except Exception as e:
            logger.error(f"Error processing meeting {meeting.get('topic', 'Unknown')}: {e}")
            return False
    
    async def get_recordings_by_month(self, start_date, end_date):
        """Get recordings month-by-month to work around API limitations"""
        all_meetings = []
        
        # Parse start and end dates
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Create a list of month ranges
        current_dt = end_dt
        month_ranges = []
        
        # Work backwards month by month
        while current_dt >= start_dt:
            # Last day of the current month
            month_end = current_dt.strftime("%Y-%m-%d")
            
            # First day of the current month
            month_start = current_dt.replace(day=1).strftime("%Y-%m-%d")
            
            # Ensure we don't go before the requested start date
            if datetime.strptime(month_start, "%Y-%m-%d") < start_dt:
                month_start = start_date
                
            month_ranges.append((month_start, month_end))
            
            # Move to the first day of the previous month
            if current_dt.month == 1:
                # If January, go to December of previous year
                current_dt = current_dt.replace(year=current_dt.year-1, month=12, day=1)
            else:
                # Otherwise, go to previous month same year
                current_dt = current_dt.replace(month=current_dt.month-1, day=1)
                
            # Go to the end of the month
            # Determine the last day of the month
            if current_dt.month in [1, 3, 5, 7, 8, 10, 12]:
                current_dt = current_dt.replace(day=31)
            elif current_dt.month in [4, 6, 9, 11]:
                current_dt = current_dt.replace(day=30)
            else:  # February
                if (current_dt.year % 4 == 0 and current_dt.year % 100 != 0) or (current_dt.year % 400 == 0):
                    current_dt = current_dt.replace(day=29)  # Leap year
                else:
                    current_dt = current_dt.replace(day=28)
        
        # Process each month range
        for month_idx, (month_start, month_end) in enumerate(month_ranges):
            print(f"Fetching recordings for month {month_idx+1}/{len(month_ranges)}: {month_start} to {month_end}")
            month_meetings = await self.get_recordings(month_start, month_end)
            all_meetings.extend(month_meetings)
            
            # Don't overwhelm the API
            if month_idx < len(month_ranges) - 1:
                await asyncio.sleep(1)
                
        return all_meetings
    
    async def get_oldest_recording_date(self):
        """Get the date of the oldest recording available"""
        try:
            # Get OAuth token for personal account
            token = await self._get_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            oldest_date = datetime.now()
            print("Checking for oldest recording date...")
            
            # Try to fetch recordings from the last 6 months first
            check_end_date = datetime.now()
            check_start_date = (check_end_date - timedelta(days=180))
            
            try:
                params = {
                    "from": check_start_date.strftime("%Y-%m-%d"),
                    "to": check_end_date.strftime("%Y-%m-%d"),
                    "page_size": 300,
                    "trash_type": "meeting_recordings" # Include recordings that might be in trash
                }
                
                recordings_response = requests.get(
                    f"{config.ZOOM_BASE_URL}/users/me/recordings",
                    headers=headers,
                    params=params
                )
                recordings_response.raise_for_status()
                recordings_data = recordings_response.json()
                
                meetings = recordings_data.get("meetings", [])
                
                # If we found meetings, find the oldest one
                if meetings:
                    # Sort by start time
                    meetings.sort(key=lambda m: m.get("start_time", ""))
                    oldest_meeting_date = datetime.fromisoformat(meetings[0].get("start_time", "").replace("Z", "+00:00"))
                    
                    # Update oldest date
                    if oldest_meeting_date < oldest_date:
                        oldest_date = oldest_meeting_date
                        print(f"  Found oldest recording from {oldest_date.strftime('%Y-%m-%d')}")
                        
                # Check if we need to look back further (if we got 300 results which is the max)
                if len(meetings) == 300:
                    # Try an earlier period
                    second_check_end_date = check_start_date - timedelta(days=1)
                    second_check_start_date = second_check_end_date - timedelta(days=180)
                    
                    params = {
                        "from": second_check_start_date.strftime("%Y-%m-%d"),
                        "to": second_check_end_date.strftime("%Y-%m-%d"),
                        "page_size": 300,
                        "trash_type": "meeting_recordings"
                    }
                    
                    second_response = requests.get(
                        f"{config.ZOOM_BASE_URL}/users/me/recordings",
                        headers=headers,
                        params=params
                    )
                    second_response.raise_for_status()
                    second_data = second_response.json()
                    
                    second_meetings = second_data.get("meetings", [])
                    
                    if second_meetings:
                        second_meetings.sort(key=lambda m: m.get("start_time", ""))
                        second_oldest_date = datetime.fromisoformat(second_meetings[0].get("start_time", "").replace("Z", "+00:00"))
                        
                        if second_oldest_date < oldest_date:
                            oldest_date = second_oldest_date
                            print(f"  Found even older recording from {oldest_date.strftime('%Y-%m-%d')}")
            except Exception as e:
                logger.warning(f"Error checking for oldest recording: {e}")
            
            # Add a buffer of 30 days before the oldest recording
            oldest_date = oldest_date - timedelta(days=30)
            oldest_date_str = oldest_date.strftime("%Y-%m-%d")
            print(f"Oldest recording found from around {oldest_date_str}")
            
            return oldest_date_str
        except Exception as e:
            logger.error(f"Error determining oldest recording date: {e}")
            # Fallback to 1 year ago
            return (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    
    async def run_extraction(self, start_date=None, end_date=None, limit=None):
        """Run the extraction process"""
        try:
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d")
                
            if not start_date:
                # Find the oldest recording instead of going back a fixed period
                start_date = await self.get_oldest_recording_date()
            
            logger.info(f"Starting extraction from {start_date} to {end_date}")
            logger.info(f"Using Google Drive folder ID: {TARGET_DRIVE_FOLDER}")
            
            # Get recordings month-by-month to work around API limitations
            print(f"Fetching recordings from {start_date} to {end_date}")
            meetings = await self.get_recordings_by_month(start_date, end_date)
            logger.info(f"Found {len(meetings)} meetings to process")
            
            # Filter out already processed meetings
            new_meetings = []
            skipped_count = 0
            
            for meeting in meetings:
                meeting_uuid = meeting.get("uuid", "")
                if meeting_uuid in self.processed_meetings:
                    logger.info(f"Skipping already processed meeting: {meeting.get('topic', 'Unknown')}")
                    skipped_count += 1
                else:
                    new_meetings.append(meeting)
            
            meetings = new_meetings
            logger.info(f"Found {len(meetings)} new meetings to process (skipped {skipped_count} already processed)")
            
            # Print summary to console
            if meetings:
                print(f"Processing {len(meetings)} new Zoom recordings (skipped {skipped_count} already processed)")
            
            # Limit the number of meetings to process if specified
            if limit and limit > 0:
                meetings = meetings[:limit]
                logger.info(f"Limited to processing {limit} meetings")
            
            success_count = 0
            error_count = 0
            total_meetings = len(meetings)
            
            for i, meeting in enumerate(meetings, 1):
                try:
                    success = await self.process_meeting(meeting, i, total_meetings)
                    if success:
                        # Save UUID of successfully processed meeting
                        meeting_uuid = meeting.get("uuid", "")
                        if meeting_uuid:
                            self.processed_meetings[meeting_uuid] = {
                                "topic": meeting.get("topic", ""),
                                "date": meeting.get("start_time", "")[:10],
                                "processed_at": datetime.now().isoformat()
                            }
                            # Save after each successful meeting
                            self._save_processed_meetings()
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Error processing meeting: {e}")
                    error_count += 1
            
            logger.info(f"Extraction completed. Processed: {success_count}, Errors: {error_count}")
            
            # Print final summary to console
            print(f"Finished! Successfully downloaded {success_count} recordings" + 
                  (f" with {error_count} errors" if error_count > 0 else ""))
            
        except Exception as e:
            logger.error(f"Error in extraction: {e}")
        finally:
            # Clean up temp directory
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)

async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract Zoom recordings to Google Drive")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, help="Limit number of meetings to process")
    
    args = parser.parse_args()
    
    extractor = PersonalZoomExtractor()
    await extractor.run_extraction(args.start_date, args.end_date, args.limit)

if __name__ == "__main__":
    asyncio.run(main())