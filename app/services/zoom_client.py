import requests
import logging
import time
import json
import os
import tempfile
from typing import Dict, Any, Optional, Literal

import config
from app.models.schemas import ZoomRecording

logger = logging.getLogger(__name__)

def get_oauth_token(account_type: Literal["primary", "personal"] = "primary") -> str:
    """
    Get an OAuth token for Zoom API authentication.
    
    Args:
        account_type: Type of account to generate token for ("primary" or "personal")
        
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
        
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        return token_data["access_token"]
    
    except Exception as e:
        logger.error(f"Error getting OAuth token: {e}")
        raise

async def get_recording_info(meeting_uuid: str, account_type: Literal["primary", "personal"] = "primary") -> ZoomRecording:
    """
    Get recording information from Zoom API.
    
    Args:
        meeting_uuid: UUID of the meeting
        account_type: Type of account to use ("primary" or "personal")
        
    Returns:
        ZoomRecording object with recording information
    """
    try:
        token = get_oauth_token(account_type)
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Include AI summary and smart recording data in the response
        params = {
            "include_fields": "ai_summary"
        }
        
        url = f"{config.ZOOM_BASE_URL}/meetings/{meeting_uuid}/recordings"
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        return ZoomRecording(**data)
    
    except Exception as e:
        logger.error(f"Error getting recording info: {e}")
        raise

async def download_transcript(download_url: str, file_path: str = None, account_type: Literal["primary", "personal"] = "primary") -> bool:
    """
    Download a transcript file from Zoom.
    
    Args:
        download_url: URL to download the transcript
        file_path: Path to save the transcript file (optional)
        account_type: Type of account to use ("primary" or "personal")
        
    Returns:
        True if download was successful, False otherwise
    """
    try:
        token = get_oauth_token(account_type)
        
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.get(download_url, headers=headers)
        response.raise_for_status()
        
        # If file_path is provided, save to that path
        if file_path:
            with open(file_path, 'wb') as f:
                f.write(response.content)
        # Otherwise save to temp file
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".vtt") as temp_file:
                temp_file.write(response.content)
                return temp_file.name
        
        return True
    
    except Exception as e:
        logger.error(f"Error downloading transcript: {e}")
        return False

async def list_recordings(from_date: str, to_date: Optional[str] = None, account_type: Literal["primary", "personal"] = "primary") -> Dict[str, Any]:
    """
    List recordings for the account.
    
    Args:
        from_date: Start date in 'YYYY-MM-DD' format
        to_date: End date in 'YYYY-MM-DD' format (optional)
        account_type: Type of account to use ("primary" or "personal")
        
    Returns:
        Dictionary with recording information
    """
    try:
        token = get_oauth_token(account_type)
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        params = {
            "from": from_date,
            "to": to_date or from_date,
            "page_size": 100
        }
        
        # Select the appropriate account ID based on account type
        if account_type == "personal" and config.PERSONAL_ZOOM_ACCOUNT_ID:
            account_id = config.PERSONAL_ZOOM_ACCOUNT_ID
        else:
            account_id = config.ZOOM_ACCOUNT_ID
            
        url = f"{config.ZOOM_BASE_URL}/accounts/{account_id}/recordings"
        
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        
        return response.json()
    
    except Exception as e:
        logger.error(f"Error listing recordings: {e}")
        raise 

async def save_ai_data(meeting_data: Dict[str, Any], base_folder_path: str) -> Dict[str, str]:
    """
    Save AI-generated data (AI summary, smart chapters, smart highlights) to files.
    
    Args:
        meeting_data: Meeting data from Zoom API
        base_folder_path: Base folder path to save files
        
    Returns:
        Dictionary with file paths
    """
    import json
    import os
    
    result = {}
    
    # Save AI summary if available
    if "ai_summary" in meeting_data and meeting_data["ai_summary"]:
        ai_summary_path = os.path.join(base_folder_path, config.FOLDER_STRUCTURE["files"]["ai_summary"])
        with open(ai_summary_path, "w") as f:
            json.dump(meeting_data["ai_summary"], f, indent=2)
        result["ai_summary"] = ai_summary_path
    
    # Save smart chapters if available
    if "smart_recording_chapters" in meeting_data and meeting_data["smart_recording_chapters"]:
        chapters_path = os.path.join(base_folder_path, config.FOLDER_STRUCTURE["files"]["smart_chapters"])
        with open(chapters_path, "w") as f:
            json.dump(meeting_data["smart_recording_chapters"], f, indent=2)
        result["smart_chapters"] = chapters_path
    
    # Save smart highlights if available
    if "smart_recording_highlights" in meeting_data and meeting_data["smart_recording_highlights"]:
        highlights_path = os.path.join(base_folder_path, config.FOLDER_STRUCTURE["files"]["smart_highlights"])
        with open(highlights_path, "w") as f:
            json.dump(meeting_data["smart_recording_highlights"], f, indent=2)
        result["smart_highlights"] = highlights_path
    
    return result 