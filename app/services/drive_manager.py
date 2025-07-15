import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config
from app.models.schemas import AnalysisResult

logger = logging.getLogger(__name__)

def get_drive_service():
    """
    Get an authenticated Google Drive service instance.
    """
    try:
        credentials = service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        
        service = build('drive', 'v3', credentials=credentials)
        return service
    
    except Exception as e:
        logger.error(f"Error creating Google Drive service: {e}")
        raise

async def create_folder_structure(
    course_name: str,
    session_number: int,
    session_name: str,
    session_date: str
) -> Dict[str, str]:
    """
    Create the folder structure in Google Drive.
    
    Args:
        course_name: Name of the course
        session_number: Number of the session (can be 0 if not applicable)
        session_name: Name of the session
        session_date: Date of the session in 'YYYY-MM-DD' format
        
    Returns:
        Dictionary with folder IDs
    """
    try:
        service = get_drive_service()
        
        # Format folder names based on templates
        course_folder_name = config.FOLDER_STRUCTURE["course_folder"].format(course_name=course_name)
        
        # For session folder, include session number only if it's greater than 0
        if session_number > 0:
            session_folder_display_name = f"Session_{session_number}_{session_name}_{session_date}"
        else:
            session_folder_display_name = f"{session_name}_{session_date}"
            
        # Check if course folder exists
        if config.USE_SHARED_DRIVE:
            # When using a shared drive
            query = f"name = '{course_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{config.GOOGLE_DRIVE_ROOT_FOLDER}' in parents and trashed = false"
            results = service.files().list(
                q=query,
                corpora="drive",
                driveId=config.GOOGLE_SHARED_DRIVE_ID,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()
        else:
            # When using My Drive
            query = f"name = '{course_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and '{config.GOOGLE_DRIVE_ROOT_FOLDER}' in parents and trashed = false"
            results = service.files().list(q=query).execute()
        
        if results.get('files'):
            course_folder_id = results['files'][0]['id']
            logger.info(f"Found existing course folder: {course_folder_name}")
        else:
            # Create course folder
            if config.USE_SHARED_DRIVE:
                file_metadata = {
                    'name': course_folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'driveId': config.GOOGLE_SHARED_DRIVE_ID,
                    'parents': [config.GOOGLE_DRIVE_ROOT_FOLDER]
                }
                
                course_folder = service.files().create(
                    body=file_metadata,
                    fields='id',
                    supportsAllDrives=True
                ).execute()
            else:
                file_metadata = {
                    'name': course_folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [config.GOOGLE_DRIVE_ROOT_FOLDER]
                }
                
                course_folder = service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
            
            course_folder_id = course_folder.get('id')
            logger.info(f"Created new course folder: {course_folder_name}")
        
        # Check if session folder exists
        if config.USE_SHARED_DRIVE:
            query = f"name = '{session_folder_display_name}' and mimeType = 'application/vnd.google-apps.folder' and '{course_folder_id}' in parents and trashed = false"
            results = service.files().list(
                q=query,
                corpora="drive",
                driveId=config.GOOGLE_SHARED_DRIVE_ID,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True
            ).execute()
        else:
            query = f"name = '{session_folder_display_name}' and mimeType = 'application/vnd.google-apps.folder' and '{course_folder_id}' in parents and trashed = false"
            results = service.files().list(q=query).execute()
        
        if results.get('files'):
            session_folder_id = results['files'][0]['id']
            logger.info(f"Found existing session folder: {session_folder_display_name}")
        else:
            # Create session folder
            if config.USE_SHARED_DRIVE:
                file_metadata = {
                    'name': session_folder_display_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [course_folder_id]
                }
                
                session_folder = service.files().create(
                    body=file_metadata,
                    fields='id',
                    supportsAllDrives=True
                ).execute()
            else:
                file_metadata = {
                    'name': session_folder_display_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [course_folder_id]
                }
                
                session_folder = service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
            
            session_folder_id = session_folder.get('id')
            logger.info(f"Created new session folder: {session_folder_display_name}")
        
        return {
            'course_folder_id': course_folder_id,
            'session_folder_id': session_folder_id
        }
    
    except Exception as e:
        logger.error(f"Error creating folder structure: {e}")
        raise

async def upload_file(
    file_path: str,
    folder_id: str,
    file_name: str,
    mime_type: str = 'application/octet-stream'
) -> Dict[str, Any]:
    """
    Upload a file to Google Drive.
    
    Args:
        file_path: Path to the file
        folder_id: ID of the folder to upload to
        file_name: Name to give the file in Google Drive
        mime_type: MIME type of the file
        
    Returns:
        Dictionary with file metadata including id and webViewLink
    """
    try:
        service = get_drive_service()
        
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        media = MediaFileUpload(
            file_path,
            mimetype=mime_type,
            resumable=True
        )
        
        # Use shared drive if configured
        if hasattr(config, 'USE_SHARED_DRIVE') and config.USE_SHARED_DRIVE:
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink',
                supportsAllDrives=True
            ).execute()
        else:
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink'
            ).execute()
        
        return file
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise

async def upload_content(
    content: str,
    folder_id: str,
    file_name: str,
    mime_type: str = 'text/plain'
) -> str:
    """
    Upload content as a file to Google Drive.
    
    Args:
        content: Content to upload
        folder_id: ID of the folder to upload to
        file_name: Name to give the file in Google Drive
        mime_type: MIME type of the content
        
    Returns:
        ID of the uploaded file
    """
    try:
        # Create temporary file
        temp_file_path = f"/tmp/{file_name}"
        with open(temp_file_path, 'w') as f:
            f.write(content)
        
        # Upload file
        file_id = await upload_file(
            file_path=temp_file_path,
            folder_id=folder_id,
            file_name=file_name,
            mime_type=mime_type
        )
        
        # Clean up temp file
        os.remove(temp_file_path)
        
        return file_id
    
    except Exception as e:
        logger.error(f"Error uploading content: {e}")
        raise

async def upload_to_drive(
    transcript_path: str,
    chat_log_path: Optional[str],
    analysis_result: AnalysisResult,
    folder_path: Dict[str, str]
) -> Dict[str, str]:
    """
    Upload transcript, chat log, and analysis results to Google Drive.
    
    Args:
        transcript_path: Path to the transcript file
        chat_log_path: Path to the chat log file (optional)
        analysis_result: Analysis results
        folder_path: Dictionary with folder IDs
        
    Returns:
        Dictionary with file IDs
    """
    try:
        session_folder_id = folder_path['session_folder_id']
        file_ids = {}
        
        # Upload transcript
        file_ids['transcript'] = await upload_file(
            file_path=transcript_path,
            folder_id=session_folder_id,
            file_name=config.FOLDER_STRUCTURE["files"]["transcript"],
            mime_type='text/vtt'
        )
        
        # Upload chat log if available
        if chat_log_path:
            file_ids['chat_log'] = await upload_file(
                file_path=chat_log_path,
                folder_id=session_folder_id,
                file_name=config.FOLDER_STRUCTURE["files"]["chat_log"],
                mime_type='text/plain'
            )
        
        # Upload analysis results
        if analysis_result.executive_summary:
            file_ids['executive_summary'] = await upload_content(
                content=analysis_result.executive_summary,
                folder_id=session_folder_id,
                file_name=config.FOLDER_STRUCTURE["files"]["executive_summary"],
                mime_type='text/markdown'
            )
        
        if analysis_result.pedagogical_analysis:
            file_ids['pedagogical_analysis'] = await upload_content(
                content=analysis_result.pedagogical_analysis,
                folder_id=session_folder_id,
                file_name=config.FOLDER_STRUCTURE["files"]["pedagogical_analysis"],
                mime_type='text/markdown'
            )
        
        if analysis_result.aha_moments:
            file_ids['aha_moments'] = await upload_content(
                content=analysis_result.aha_moments,
                folder_id=session_folder_id,
                file_name=config.FOLDER_STRUCTURE["files"]["aha_moments"],
                mime_type='text/markdown'
            )
        
        if analysis_result.engagement_metrics:
            file_ids['engagement_metrics'] = await upload_content(
                content=json.dumps(analysis_result.engagement_metrics, indent=2),
                folder_id=session_folder_id,
                file_name=config.FOLDER_STRUCTURE["files"]["engagement_metrics"],
                mime_type='application/json'
            )
        
        # Upload combined analysis
        analysis_json = analysis_result.dict()
        file_ids['analysis'] = await upload_content(
            content=json.dumps(analysis_json, indent=2),
            folder_id=session_folder_id,
            file_name=config.FOLDER_STRUCTURE["files"]["analysis"],
            mime_type='application/json'
        )
        
        return file_ids
    
    except Exception as e:
        logger.error(f"Error uploading to Drive: {e}")
        raise 