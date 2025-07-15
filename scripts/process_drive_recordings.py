#!/usr/bin/env python
"""
Script to process recordings stored in Google Drive and generate insights.
This script will:
1. Connect to Google Drive
2. Find all course folders
3. Find all session folders with unprocessed transcripts
4. For each transcript, generate insights
5. Save insights in the same folder

Logging:
- All operations are logged to both console and a timestamped log file in the 'logs' directory
- Log level can be controlled with the --log-level parameter (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Use DEBUG level to see detailed API interactions
"""

import os
import sys
import argparse
import tempfile
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import time
import asyncio
import anthropic

# Add the parent directory to the path so we can import from the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import AnalysisRequest, AnalysisResult
from app.services.analysis import generate_analysis
import config

# Set up logging with timestamped log file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_filename = os.path.join(log_dir, f"drive_processing_{timestamp}.log")

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

class DriveManager:
    """Class for interacting with Google Drive."""
    
    def __init__(self):
        """Initialize the Drive manager."""
        credentials_file = config.GOOGLE_CREDENTIALS_FILE
        scopes = ["https://www.googleapis.com/auth/drive"]
        
        logger.info(f"Initializing Drive Manager")
        logger.debug(f"Using credentials file: {credentials_file}")
        logger.debug(f"Using scopes: {scopes}")
        
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=scopes
        )
        
        self.service = build("drive", "v3", credentials=credentials)
        # Also create a sheets service for accessing spreadsheets
        self.sheets_service = build("sheets", "v4", credentials=credentials)
        self.root_folder_id = config.GOOGLE_DRIVE_ROOT_FOLDER
        self.use_shared_drive = config.USE_SHARED_DRIVE
        self.shared_drive_id = config.GOOGLE_SHARED_DRIVE_ID if config.USE_SHARED_DRIVE else None
        
        if self.use_shared_drive:
            logger.info(f"Drive Manager initialized with shared drive ID: {self.shared_drive_id}")
        else:
            logger.info(f"Drive Manager initialized with root folder ID: {self.root_folder_id}")
        
    def list_folders(self, parent_id: str) -> List[Dict]:
        """
        List all folders in a parent folder.
        
        Args:
            parent_id: ID of the parent folder
            
        Returns:
            List of folder objects
        """
        query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        logger.debug(f"Listing folders with query: {query}")
        
        results = []
        page_token = None
        
        while True:
            if self.use_shared_drive:
                response = self.service.files().list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name)",
                    pageToken=page_token,
                    corpora="drive",
                    driveId=self.shared_drive_id,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True
                ).execute()
            else:
                response = self.service.files().list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name)",
                    pageToken=page_token
                ).execute()
            
            page_results = response.get("files", [])
            results.extend(page_results)
            logger.debug(f"Retrieved {len(page_results)} folders in this page")
            
            page_token = response.get("nextPageToken")
            
            if not page_token:
                break
                
        logger.debug(f"Found total of {len(results)} folders")
        return results
        
    def list_files(self, parent_id: str) -> List[Dict]:
        """
        List all files in a folder.
        
        Args:
            parent_id: ID of the parent folder
            
        Returns:
            List of file objects
        """
        query = f"'{parent_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
        logger.debug(f"Listing files with query: {query}")
        
        results = []
        page_token = None
        
        while True:
            if self.use_shared_drive:
                response = self.service.files().list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, webViewLink)",
                    pageToken=page_token,
                    corpora="drive",
                    driveId=self.shared_drive_id,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True
                ).execute()
            else:
                response = self.service.files().list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, webViewLink)",
                    pageToken=page_token
                ).execute()
            
            page_results = response.get("files", [])
            results.extend(page_results)
            logger.debug(f"Retrieved {len(page_results)} files in this page")
            
            page_token = response.get("nextPageToken")
            
            if not page_token:
                break
                
        logger.debug(f"Found total of {len(results)} files")
        return results
        
    def download_file(self, file_id: str, output_path: str) -> bool:
        """
        Download a file from Drive.
        
        Args:
            file_id: ID of the file to download
            output_path: Path to save the file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.debug(f"Downloading file with ID: {file_id} to {output_path}")
            
            if self.use_shared_drive:
                request = self.service.files().get_media(
                    fileId=file_id,
                    supportsAllDrives=True
                )
            else:
                request = self.service.files().get_media(fileId=file_id)
            
            with open(output_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")
                    
            logger.debug(f"File downloaded successfully")
            return True
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return False
            
    def create_marker_file(self, folder_id: str, marker_name: str = ".processed") -> bool:
        """
        Create a marker file to indicate processing is complete.
        
        Args:
            folder_id: ID of the folder
            marker_name: Name of the marker file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.debug(f"Creating marker file in folder: {folder_id}")
            file_metadata = {
                "name": marker_name,
                "parents": [folder_id],
                "mimeType": "text/plain"
            }
            
            if self.use_shared_drive:
                result = self.service.files().create(
                    body=file_metadata,
                    fields="id",
                    supportsAllDrives=True
                ).execute()
            else:
                result = self.service.files().create(
                    body=file_metadata,
                    fields="id"
                ).execute()
            
            logger.debug(f"Marker file created with ID: {result.get('id')}")
            return True
        except Exception as e:
            logger.error(f"Error creating marker file: {e}")
            return False

    def upload_file(self, file_path: str, parent_id: str, file_name: str, mime_type: str = 'application/octet-stream') -> str:
        """
        Upload a file to Google Drive.
        
        Args:
            file_path: Path to the file
            parent_id: ID of the parent folder
            file_name: Name to give the file in Google Drive
            mime_type: MIME type of the file
            
        Returns:
            ID of the uploaded file
        """
        try:
            logger.debug(f"Uploading file: {file_path} to folder: {parent_id}")
            
            file_metadata = {
                'name': file_name,
                'parents': [parent_id]
            }
            
            media = MediaFileUpload(
                file_path,
                mimetype=mime_type,
                resumable=True
            )
            
            if self.use_shared_drive:
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id',
                    supportsAllDrives=True
                ).execute()
            else:
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
            
            logger.debug(f"File uploaded successfully with ID: {file.get('id')}")
            return file.get('id')
        
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            raise

    def check_report_for_insights(self, folder_name: str) -> Dict[str, str]:
        """
        Check if insights already exist in the Zoom report for this session.
        
        Args:
            folder_name: Name of the session folder
            
        Returns:
            Dictionary with insight URLs
        """
        try:
            # Get the report ID from environment
            report_id = os.environ.get("ZOOM_REPORT_ID", "")
            if not report_id:
                logger.info("No report ID found in environment variables, skipping report check")
                return {}
                
            logger.info(f"Checking report for existing insights for: {folder_name}")
            
            # First get the sheet metadata to find the actual sheet name
            sheet_metadata = self.sheets_service.spreadsheets().get(spreadsheetId=report_id).execute()
            sheets = sheet_metadata.get('sheets', '')
            
            if not sheets:
                logger.info("No sheets found in the spreadsheet")
                return {}
                
            # Use the first sheet's title
            sheet_title = sheets[0]['properties']['title']
            logger.info(f"Using sheet: {sheet_title}")
            
            # Get the spreadsheet values using the Sheets API with the correct sheet name
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=report_id,
                range=f"{sheet_title}!A1:Q1000"  # Using explicit range with sheet name
            ).execute()
                
            values = result.get('values', [])
            if not values:
                logger.info("No data found in report")
                return {}
                
            # Find the session in the report
            session_row = None
            for i, row in enumerate(values):
                if len(row) > 0 and folder_name in row[0]:
                    session_row = row
                    break
                    
            if not session_row:
                logger.info(f"Session {folder_name} not found in report")
                return {}
                
            # Extract insight URLs if they exist
            insight_urls = {}
            headers = values[0]
            
            url_columns = {
                "Executive Summary URL": "executive_summary_url",
                "Pedagogical Analysis URL": "pedagogical_analysis_url",
                "Aha Moments URL": "aha_moments_url",
                "Engagement Metrics URL": "engagement_metrics_url",
                "Concise Summary URL": "concise_summary_url"
            }
            
            for header, key in url_columns.items():
                try:
                    idx = headers.index(header)
                    if idx < len(session_row) and session_row[idx]:
                        insight_urls[key] = session_row[idx]
                except (ValueError, IndexError):
                    pass
                    
            logger.info(f"Found {len(insight_urls)} existing insight URLs for {folder_name}")
            return insight_urls
            
        except Exception as e:
            logger.error(f"Error checking report for insights: {e}")
            return {}

async def generate_concise_summary_from_text(executive_summary: str) -> str:
    """
    Generate a concise summary from an executive summary using Claude API.
    
    Args:
        executive_summary: The executive summary text
        
    Returns:
        A concise summary of the executive summary
    """
    try:
        logger.info("Generating concise summary from executive summary")
        
        # Import the API queue
        from app.services.api_queue import api_queue
        
        # Create the prompt
        prompt = f"""You are an expert educational content summarizer. Your task is to create a concise summary (150-200 words) of the following executive summary of an educational session. 
        
The summary should:
1. Capture the key topics and main insights
2. Highlight the most important learning outcomes
3. Be written in a clear, professional style
4. Be easily scannable for busy educators

Here is the executive summary to condense:

{executive_summary}

Provide only the concise summary without any additional commentary or explanations. Do not include any headings or labels like "Concise Summary:" in your response.
"""
        
        # Use the API queue to manage rate limits
        logger.info(f"Queuing concise summary generation request")
        concise_summary = await api_queue.add_request(
            prompt=prompt,
            max_tokens=1024,
            temperature=0.2
        )
        
        logger.info(f"Successfully generated concise summary ({len(concise_summary)} chars)")
        return concise_summary
                
    except Exception as e:
        logger.error(f"Error generating concise summary: {e}")
        # Return a placeholder if generation fails
        return "**Concise Summary Generation Failed**\n\nThe system encountered an error while trying to generate a concise summary. Please refer to the executive summary for details."

async def process_session_folder(drive_manager: DriveManager, folder_id: str, folder_name: str, temp_dir: str, retry_failed: bool = False, backoff_time: int = 120) -> bool:
    """
    Process a session folder by generating insights for the transcript.
    
    Args:
        drive_manager: Drive manager instance
        folder_id: ID of the session folder
        folder_name: Name of the session folder
        temp_dir: Directory for temporary files
        retry_failed: Whether to retry previously failed folders
        backoff_time: Time to wait before retrying after rate limit (seconds)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if already processed
        files = drive_manager.list_files(folder_id)
        file_names = [file["name"] for file in files]
        
        # Check for marker file indicating successful processing
        if ".processed" in file_names and not retry_failed:
            logger.info(f"Folder already processed: {folder_name}")
            return True
            
        # Check for marker file indicating failed processing
        if ".processing_failed" in file_names and not retry_failed:
            logger.info(f"Folder previously failed processing and retry_failed is False: {folder_name}")
            return False
        
        # Check if insights already exist in the report
        existing_insight_urls = drive_manager.check_report_for_insights(folder_name)
            
        # Find transcript file
        logger.debug(f"Looking for transcript file in folder")
        transcript_file = None
        chat_file = None
        metadata_file = None
        
        for file in files:
            if file["name"].lower().endswith(".vtt") or file["name"] == "transcript.vtt":
                transcript_file = file
            elif file["name"] == "chat_log.txt":
                chat_file = file
            elif file["name"] == "meeting_metadata.json":
                metadata_file = file
        
        if not transcript_file:
            logger.warning(f"No transcript file found in folder: {folder_name}")
            return False
        
        # Download transcript file
        transcript_path = os.path.join(temp_dir, "transcript.vtt")
        drive_manager.download_file(transcript_file["id"], transcript_path)
        logger.info(f"Downloaded transcript file to: {transcript_path}")
        
        # Download chat log if available
        chat_log_path = None
        if chat_file:
            chat_log_path = os.path.join(temp_dir, "chat_log.txt")
            drive_manager.download_file(chat_file["id"], chat_log_path)
            logger.info(f"Downloaded chat log file to: {chat_log_path}")
        
        # Define analysis files to generate
        analysis_files = {
            "executive_summary": "executive_summary.md",
            "pedagogical_analysis": "pedagogical_analysis.md",
            "aha_moments": "aha_moments.md",
            "engagement_analysis": "engagement_metrics.json",
            "concise_summary": "concise_summary.md"
        }
        
        # Map file names to URL keys in the report
        file_to_url_key = {
            "executive_summary.md": "executive_summary_url",
            "pedagogical_analysis.md": "pedagogical_analysis_url",
            "aha_moments.md": "aha_moments_url",
            "engagement_metrics.json": "engagement_metrics_url",
            "concise_summary.md": "concise_summary_url"
        }
        
        # Determine which analyses to generate
        analysis_types_to_generate = []
        
        for analysis_type, file_name in analysis_files.items():
            # Skip if file exists in Drive
            if file_name in file_names:
                logger.info(f"Skipping {analysis_type} generation as {file_name} already exists in Drive")
                continue
                
            # Skip if URL exists in report
            url_key = file_to_url_key.get(file_name)
            if url_key and url_key in existing_insight_urls and existing_insight_urls[url_key]:
                logger.info(f"Skipping {analysis_type} generation as URL exists in report: {existing_insight_urls[url_key]}")
                continue
                
            # Add to list of analyses to generate
            if analysis_type != "concise_summary":  # We'll handle concise summary separately
                analysis_types_to_generate.append(analysis_type)
                logger.info(f"Need to generate {analysis_type} (file {file_name} not found)")
        
        # If no analyses need to be generated, we can skip the API call
        if not analysis_types_to_generate:
            logger.info(f"All analysis files already exist, skipping generation")
            return True
        
        # Generate analysis
        logger.info(f"Generating analysis for transcript: {', '.join(analysis_types_to_generate)}")
        request = AnalysisRequest(
            transcript_path=transcript_path,
            chat_log_path=chat_log_path,
            analysis_types=analysis_types_to_generate,
            participant_school_mapping={}
        )
        
        # Try to generate analysis with exponential backoff for rate limiting
        max_retries = 5
        current_retry = 0
        current_backoff = backoff_time
        
        while current_retry < max_retries:
            try:
                result = await generate_analysis(request)
                break
            except Exception as e:
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    current_retry += 1
                    if current_retry >= max_retries:
                        logger.error(f"Maximum retries ({max_retries}) exceeded for rate limiting. Marking folder as failed.")
                        drive_manager.create_marker_file(folder_id, ".processing_failed")
                        return False
                    
                    logger.warning(f"Rate limit exceeded. Retry {current_retry}/{max_retries}. Waiting {current_backoff} seconds before retrying...")
                    await asyncio.sleep(current_backoff)
                    current_backoff *= 2  # Double the backoff time for each retry
                else:
                    logger.error(f"Error generating analysis: {e}")
                    drive_manager.create_marker_file(folder_id, ".processing_failed")
                    return False
        else:
            # This will only execute if the while loop completes without a break
            logger.error("Failed to generate analysis after all retries")
            drive_manager.create_marker_file(folder_id, ".processing_failed")
            return False
        
        # Upload results to Drive and collect URLs
        insight_urls = {}
        
        # Upload executive summary
        if "executive_summary" in analysis_types_to_generate:
            executive_summary_path = os.path.join(temp_dir, "executive_summary.md")
            with open(executive_summary_path, "w") as f:
                f.write(result.executive_summary)
            
            file_id = drive_manager.upload_file(
                file_path=executive_summary_path,
                parent_id=folder_id,
                file_name="executive_summary.md"
            )
            logger.info(f"Uploaded executive summary with ID: {file_id}")
            
            # Get the webViewLink
            file = drive_manager.service.files().get(
                fileId=file_id,
                fields='webViewLink',
                supportsAllDrives=True
            ).execute()
            
            insight_urls["executive_summary_url"] = file.get('webViewLink', '')
        
        # Upload pedagogical analysis
        if "pedagogical_analysis" in analysis_types_to_generate:
            pedagogical_analysis_path = os.path.join(temp_dir, "pedagogical_analysis.md")
            with open(pedagogical_analysis_path, "w") as f:
                f.write(result.pedagogical_analysis)
            
            file_id = drive_manager.upload_file(
                file_path=pedagogical_analysis_path,
                parent_id=folder_id,
                file_name="pedagogical_analysis.md"
            )
            logger.info(f"Uploaded pedagogical analysis with ID: {file_id}")
            
            # Get the webViewLink
            file = drive_manager.service.files().get(
                fileId=file_id,
                fields='webViewLink',
                supportsAllDrives=True
            ).execute()
            
            insight_urls["pedagogical_analysis_url"] = file.get('webViewLink', '')
        
        # Upload aha moments
        if "aha_moments" in analysis_types_to_generate:
            aha_moments_path = os.path.join(temp_dir, "aha_moments.md")
            with open(aha_moments_path, "w") as f:
                f.write(result.aha_moments)
            
            file_id = drive_manager.upload_file(
                file_path=aha_moments_path,
                parent_id=folder_id,
                file_name="aha_moments.md"
            )
            logger.info(f"Uploaded aha moments with ID: {file_id}")
            
            # Get the webViewLink
            file = drive_manager.service.files().get(
                fileId=file_id,
                fields='webViewLink',
                supportsAllDrives=True
            ).execute()
            
            insight_urls["aha_moments_url"] = file.get('webViewLink', '')
        
        # Upload engagement analysis
        if "engagement_analysis" in analysis_types_to_generate:
            engagement_analysis_path = os.path.join(temp_dir, "engagement_metrics.json")
            with open(engagement_analysis_path, "w") as f:
                json.dump(result.engagement_metrics, f, indent=2)
            
            file_id = drive_manager.upload_file(
                file_path=engagement_analysis_path,
                parent_id=folder_id,
                file_name="engagement_metrics.json"
            )
            logger.info(f"Uploaded engagement metrics with ID: {file_id}")
            
            # Get the webViewLink
            file = drive_manager.service.files().get(
                fileId=file_id,
                fields='webViewLink',
                supportsAllDrives=True
            ).execute()
            
            insight_urls["engagement_metrics_url"] = file.get('webViewLink', '')
        
        # Generate concise summary if executive summary was generated
        if "executive_summary" in analysis_types_to_generate and "concise_summary.md" not in file_names:
            try:
                logger.info(f"Generating concise summary from executive summary")
                
                # Use the executive summary we just generated
                concise_summary = await generate_concise_summary_from_text(result.executive_summary)
                
                # Upload concise summary
                concise_summary_path = os.path.join(temp_dir, "concise_summary.md")
                with open(concise_summary_path, "w") as f:
                    f.write(concise_summary)
                
                file_id = drive_manager.upload_file(
                    file_path=concise_summary_path,
                    parent_id=folder_id,
                    file_name="concise_summary.md"
                )
                logger.info(f"Uploaded concise summary with ID: {file_id}")
                
                # Get the webViewLink
                file = drive_manager.service.files().get(
                    fileId=file_id,
                    fields='webViewLink',
                    supportsAllDrives=True
                ).execute()
                
                insight_urls["concise_summary_url"] = file.get('webViewLink', '')
                
            except Exception as e:
                logger.error(f"Error generating concise summary: {e}")
                # Continue even if concise summary generation fails
        
        # Update the report with insight URLs
        if insight_urls:
            from app.services.analysis import update_report_with_insight_urls
            success = await update_report_with_insight_urls(folder_name, insight_urls)
            if success:
                logger.info(f"Updated report with insight URLs for {folder_name}")
            else:
                logger.warning(f"Failed to update report with insight URLs for {folder_name}")
        
        # Create marker file to indicate successful processing
        drive_manager.create_marker_file(folder_id, ".processed")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing session folder: {e}")
        drive_manager.create_marker_file(folder_id, ".processing_failed")
        return False

async def process_course_folder(drive_manager: DriveManager, folder_id: str, folder_name: str, temp_dir: str) -> int:
    """
    Process a course folder by finding and processing all session folders.
    
    Args:
        drive_manager: Drive manager instance
        folder_id: ID of the course folder
        folder_name: Name of the course folder
        temp_dir: Directory for temporary files
        
    Returns:
        Number of successfully processed sessions
    """
    logger.info(f"Processing course folder: {folder_name}")
    
    # List all session folders
    session_folders = drive_manager.list_folders(folder_id)
    
    processed_count = 0
    for folder in session_folders:
        logger.info(f"Processing session folder: {folder['name']}")
        success = await process_session_folder(drive_manager, folder["id"], folder["name"], temp_dir)
        if success:
            processed_count += 1
            
    return processed_count

async def main():
    """Main function to process recordings in Drive."""
    parser = argparse.ArgumentParser(description="Process recordings in Google Drive")
    parser.add_argument("--temp-dir", type=str, default="./temp", help="Temporary directory for downloads")
    parser.add_argument("--course", type=str, help="Process only a specific course")
    parser.add_argument("--log-level", type=str, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        default="INFO", help="Set the logging level")
    parser.add_argument("--retry-failed", action="store_true", help="Retry previously failed folders")
    parser.add_argument("--backoff-time", type=int, default=60, 
                        help="Time to wait before retrying after rate limit (seconds)")
    
    args = parser.parse_args()
    
    # Set logging level based on command-line argument
    logger.setLevel(getattr(logging, args.log_level))
    
    # Create temp directory
    os.makedirs(args.temp_dir, exist_ok=True)
    
    logger.info("Starting Drive processing")
    
    # Initialize Drive manager
    drive_manager = DriveManager()
    
    # Process all course folders
    course_folders = drive_manager.list_folders(drive_manager.root_folder_id)
    
    for course_folder in course_folders:
        course_name = course_folder["name"]
        
        # Skip if not the specified course
        if args.course and course_name != args.course:
            logger.debug(f"Skipping course folder: {course_name}")
            continue
            
        logger.info(f"Processing course folder: {course_name}")
        
        # Get all session folders
        session_folders = drive_manager.list_folders(course_folder["id"])
        
        for session_folder in session_folders:
            session_name = session_folder["name"]
            logger.info(f"Processing session folder: {session_name}")
            
            # Process session folder
            await process_session_folder(
                drive_manager=drive_manager,
                folder_id=session_folder["id"],
                folder_name=session_name,
                temp_dir=args.temp_dir,
                retry_failed=args.retry_failed,
                backoff_time=args.backoff_time
            )
            
    logger.info("Drive processing completed")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 