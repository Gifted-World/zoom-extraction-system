#!/usr/bin/env python3
"""
Verify that all Zoom recordings are present in Google Drive folders
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from app.services.drive_manager import get_drive_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

def get_oauth_token(account_type="primary"):
    """Get OAuth token for specified account type"""
    try:
        if account_type == "personal":
            client_id = config.PERSONAL_ZOOM_CLIENT_ID
            client_secret = config.PERSONAL_ZOOM_CLIENT_SECRET
            account_id = config.PERSONAL_ZOOM_ACCOUNT_ID
        else:
            client_id = config.ZOOM_CLIENT_ID
            client_secret = config.ZOOM_CLIENT_SECRET
            account_id = config.ZOOM_ACCOUNT_ID
        
        url = "https://zoom.us/oauth/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "account_credentials",
            "account_id": account_id,
            "client_id": client_id,
            "client_secret": client_secret
        }
        
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        
        return response.json()["access_token"]
    except Exception as e:
        logger.error(f"Error getting OAuth token for {account_type}: {e}")
        return None

def get_all_recordings(account_type="primary"):
    """Get all recordings from Zoom account"""
    token = get_oauth_token(account_type)
    if not token:
        return []
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Use the working endpoint for personal account
    if account_type == "personal":
        url = "https://api.zoom.us/v2/accounts/me/recordings"
    else:
        url = "https://api.zoom.us/v2/accounts/me/recordings"  # Use same working endpoint for admin
    
    all_recordings = []
    next_page_token = None
    page = 1
    
    while True:
        try:
            # Use a longer date range to get ALL recordings (past year)
            from_date = "2024-08-21"  # Start from 1 year ago
            to_date = datetime.now().strftime("%Y-%m-%d")
            
            params = {
                "page_size": 300,
                "next_page_token": next_page_token,
                "from": from_date,
                "to": to_date
            }
            
            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to get recordings: {response.status_code} - {response.text}")
                break
            
            data = response.json()
            meetings = data.get("meetings", [])
            logger.info(f"Page {page}: Found {len(meetings)} meetings")
            
            all_recordings.extend(meetings)
            
            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break
            
            page += 1
            
        except Exception as e:
            logger.error(f"Error getting page {page}: {e}")
            break
    
    return all_recordings

def get_drive_files(account_type="primary"):
    """Get list of files in Google Drive folder"""
    try:
        drive_service = get_drive_service()
        
        # Get the target folder ID based on account type
        if account_type == "personal":
            folder_id = "19qJC5y1HP7OZuia3KzaCWN7BDCwVl1x9"  # Personal folder ID from env
        else:
            folder_id = "1zApRgh9bjUKtNJAp_gH_krOPodI8zWkH"  # Admin folder
        
        # List all files in the folder
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id,name,size,createdTime)",
            pageSize=1000
        ).execute()
        
        files = results.get('files', [])
        logger.info(f"Found {len(files)} files in Drive folder for {account_type} account")
        
        return files
        
    except Exception as e:
        logger.error(f"Error getting Drive files: {e}")
        return []

def verify_sync(account_type="primary"):
    """Verify that all Zoom recordings are in Google Drive"""
    print(f"\n🔍 Verifying {account_type.upper()} account sync...")
    print("=" * 60)
    
    # Get all Zoom recordings
    print("📥 Getting Zoom recordings...")
    zoom_recordings = get_all_recordings(account_type)
    print(f"   Found {len(zoom_recordings)} meetings in Zoom")
    
    # Get Drive files
    print("📁 Getting Google Drive files...")
    
    # Show which folder we're checking
    if account_type == "personal":
        folder_id = "19qJC5y1HP7OZuia3KzaCWN7BDCwVl1x9"
        print(f"   Checking personal folder: {folder_id}")
    else:
        folder_id = "1zApRgh9bjUKtNJAp_gH_krOPodI8zWkH"
        print(f"   Checking admin folder: {folder_id}")
    
    drive_files = get_drive_files(account_type)
    print(f"   Found {len(drive_files)} files in Drive")
    
    # Analyze Zoom recordings
    zoom_files = []
    total_zoom_size = 0
    
    for meeting in zoom_recordings:
        meeting_id = meeting.get("id", "")
        topic = meeting.get("topic", "Unknown")
        start_time = meeting.get("start_time", "")[:10] if meeting.get("start_time") else "Unknown"
        
        for recording in meeting.get("recording_files", []):
            file_type = recording.get("recording_type", "unknown")
            file_size = recording.get("file_size", 0)
            file_name = recording.get("file_name", "")
            
            zoom_files.append({
                "meeting_id": meeting_id,
                "topic": topic,
                "date": start_time,
                "file_type": file_type,
                "file_name": file_name,
                "file_size": file_size
            })
            total_zoom_size += file_size
    
    print(f"   Total Zoom files: {len(zoom_files)}")
    print(f"   Total Zoom size: {total_zoom_size / (1024**3):.2f} GB")
    
    # Check Drive files
    drive_file_names = [f["name"] for f in drive_files]
    drive_total_size = sum(int(f.get("size", 0)) for f in drive_files)
    
    print(f"   Total Drive size: {drive_total_size / (1024**3):.2f} GB")
    
    # Find missing files
    missing_files = []
    for zoom_file in zoom_files:
        # Create expected Drive filename
        expected_name = f"{zoom_file['topic']}_{zoom_file['date']}_{zoom_file['file_type']}"
        expected_name = expected_name.replace("/", "-").replace(":", "-")[:100]  # Sanitize
        
        # Check if any Drive file contains the meeting info
        found = False
        for drive_file in drive_files:
            if (zoom_file['meeting_id'] in drive_file['name'] or 
                zoom_file['topic'][:30] in drive_file['name'] or
                zoom_file['date'] in drive_file['name']):
                found = True
                break
        
        if not found:
            missing_files.append(zoom_file)
    
    print(f"\n📊 Sync Status:")
    print(f"   Files in Zoom: {len(zoom_files)}")
    print(f"   Files in Drive: {len(drive_files)}")
    print(f"   Missing files: {len(missing_files)}")
    
    if missing_files:
        print(f"\n❌ Missing files:")
        for missing in missing_files[:10]:  # Show first 10
            print(f"   - {missing['topic']} ({missing['date']}) - {missing['file_type']}")
        if len(missing_files) > 10:
            print(f"   ... and {len(missing_files) - 10} more")
    else:
        print(f"\n✅ All files are synced!")
    
    return {
        "zoom_files": len(zoom_files),
        "drive_files": len(drive_files),
        "missing_files": len(missing_files),
        "zoom_size_gb": total_zoom_size / (1024**3),
        "drive_size_gb": drive_total_size / (1024**3)
    }

if __name__ == "__main__":
    print("🔍 Verifying Zoom to Google Drive Sync")
    print("=" * 60)
    
    # Check both accounts
    personal_stats = verify_sync("personal")
    admin_stats = verify_sync("primary")
    
    print("\n" + "=" * 60)
    print("📋 SUMMARY")
    print("=" * 60)
    print(f"Personal Account:")
    print(f"  Zoom: {personal_stats['zoom_files']} files, {personal_stats['zoom_size_gb']:.2f} GB")
    print(f"  Drive: {personal_stats['drive_files']} files, {personal_stats['drive_size_gb']:.2f} GB")
    print(f"  Missing: {personal_stats['missing_files']} files")
    
    print(f"\nAdmin Account:")
    print(f"  Zoom: {admin_stats['zoom_files']} files, {admin_stats['zoom_size_gb']:.2f} GB")
    print(f"  Drive: {admin_stats['drive_files']} files, {admin_stats['drive_size_gb']:.2f} GB")
    print(f"  Missing: {admin_stats['missing_files']} files")
    
    total_missing = personal_stats['missing_files'] + admin_stats['missing_files']
    if total_missing == 0:
        print(f"\n🎉 PERFECT SYNC! All files are in Google Drive!")
    else:
        print(f"\n⚠️  {total_missing} files are missing from Google Drive")
