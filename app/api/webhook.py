from fastapi import APIRouter, Request, HTTPException, Depends, Header, BackgroundTasks
import hmac
import hashlib
import json
import logging
import tempfile
import os
from typing import Optional, Dict, Any
from datetime import datetime

import config
from app.models.schemas import ZoomWebhookEvent, AnalysisRequest
from app.services.zoom_client import get_recording_info, download_transcript
from app.services.analysis import generate_analysis
from app.services.drive_manager import create_folder_structure, upload_to_drive

router = APIRouter()
logger = logging.getLogger(__name__)

async def verify_webhook_signature(
    request: Request,
    x_zm_signature: Optional[str] = Header(None),
    x_zm_request_timestamp: Optional[str] = Header(None)
):
    """
    Verify the webhook signature from Zoom.
    
    If webhook secret is not configured, skip verification.
    """
    if not config.ZOOM_WEBHOOK_SECRET:
        logger.warning("Zoom webhook secret not configured, skipping signature verification")
        return True
    
    # For Zoom webhook validation challenge
    body_bytes = await request.body()
    body_text = body_bytes.decode('utf-8')
    
    # Check if this is a validation request
    try:
        body_json = json.loads(body_text)
        if body_json.get("event") == "endpoint.url_validation":
            logger.info("Received Zoom validation challenge")
            plainToken = body_json.get("payload", {}).get("plainToken", "")
            if plainToken:
                # Compute hash
                hash_object = hmac.new(
                    config.ZOOM_WEBHOOK_SECRET.encode('utf-8'),
                    plainToken.encode('utf-8'),
                    hashlib.sha256
                )
                encrypted_token = hash_object.hexdigest()
                
                # Return the challenge response
                return {
                    "plainToken": plainToken,
                    "encryptedToken": encrypted_token
                }
    except (json.JSONDecodeError, AttributeError):
        # Not a JSON body or doesn't have the expected structure
        pass
    
    if not x_zm_signature or not x_zm_request_timestamp:
        raise HTTPException(status_code=401, detail="Missing Zoom signature headers")
    
    # Compute hash
    message = f"v0:{x_zm_request_timestamp}:{body_text}"
    hash_object = hmac.new(
        config.ZOOM_WEBHOOK_SECRET.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    )
    signature = f"v0={hash_object.hexdigest()}"
    
    # Verify signature
    if not hmac.compare_digest(signature, x_zm_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    return True

async def process_recording_task(meeting_uuid: str, meeting_info: Dict[str, Any]):
    """
    Background task to process a recording.
    
    Args:
        meeting_uuid: UUID of the meeting
        meeting_info: Meeting information from Zoom API
    """
    try:
        logger.info(f"Processing recording for meeting {meeting_uuid}")
        
        # Extract meeting metadata
        topic = meeting_info.get("topic", "Unknown Meeting")
        start_time = meeting_info.get("start_time", datetime.now().isoformat())
        
        # Parse meeting topic to extract course and session info
        # Expected format: "Course Name - Session X: Session Name"
        course_name = "Unknown Course"
        session_number = 0
        session_name = topic
        
        try:
            parts = topic.split(" - ")
            if len(parts) >= 2:
                course_name = parts[0].strip()
                session_part = parts[1].strip()
                
                # Extract session number
                if "Session" in session_part and ":" in session_part:
                    session_number = int(session_part.split(":")[0].replace("Session", "").strip())
                    session_name = session_part.split(":")[1].strip()
        except Exception as e:
            logger.warning(f"Could not parse meeting topic '{topic}': {e}")
        
        # Format date
        session_date = start_time.split("T")[0] if "T" in start_time else datetime.now().strftime("%Y-%m-%d")
        
        # Get recording info from Zoom API
        recording_info = await get_recording_info(meeting_uuid)
        
        # Check if transcript is available
        transcript_file = None
        for file in recording_info.get("recording_files", []):
            if file.get("file_type") == "TRANSCRIPT":
                transcript_file = file
                break
        
        if not transcript_file:
            logger.warning(f"No transcript available for meeting {meeting_uuid}")
            return
        
        # Download transcript
        with tempfile.NamedTemporaryFile(delete=False, suffix=".vtt") as temp_transcript:
            transcript_path = temp_transcript.name
            
        success = await download_transcript(transcript_file.get("download_url"), transcript_path)
        if not success:
            logger.error(f"Failed to download transcript for meeting {meeting_uuid}")
            return
        
        # Create analysis request
        request = AnalysisRequest(
            transcript_path=transcript_path,
            chat_log_path=None,
            analysis_types=["executive_summary", "pedagogical_analysis", "aha_moments", "engagement_analysis"],
            participant_school_mapping={}
        )
        
        # Generate analysis
        result = await generate_analysis(request)
        
        # Create folder structure in Drive
        folder_path = await create_folder_structure(
            course_name=course_name,
            session_number=session_number,
            session_name=session_name,
            session_date=session_date
        )
        
        # Upload to Drive
        await upload_to_drive(
            transcript_path=transcript_path,
            chat_log_path=None,
            analysis_result=result,
            folder_path=folder_path
        )
        
        # Clean up
        os.unlink(transcript_path)
        
        logger.info(f"Successfully processed recording for meeting {meeting_uuid}")
    except Exception as e:
        logger.error(f"Error processing recording for meeting {meeting_uuid}: {e}")

@router.post("/recording-completed")
async def recording_completed(
    event: ZoomWebhookEvent,
    background_tasks: BackgroundTasks,
    verified: bool = Depends(verify_webhook_signature)
):
    """
    Handle webhook notification for recording completed events.
    """
    try:
        if event.event != "recording.completed":
            return {"status": "ignored", "message": f"Event type {event.event} not handled"}
        
        # Extract meeting UUID and info from payload
        meeting_object = event.payload.get("object", {})
        meeting_uuid = meeting_object.get("uuid")
        
        if not meeting_uuid:
            raise HTTPException(status_code=400, detail="Missing meeting UUID in payload")
        
        # Start background task to process the recording
        background_tasks.add_task(process_recording_task, meeting_uuid, meeting_object)
        
        return {
            "status": "success",
            "message": "Recording webhook received, processing started",
            "meeting_uuid": meeting_uuid
        }
    
    except Exception as e:
        logger.error(f"Error processing recording webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def webhook_health():
    """
    Health check endpoint for Zoom webhook verification.
    """
    return {"status": "ok"}

@router.post("/deauthorization")
async def app_deauthorized(
    event: ZoomWebhookEvent,
    verified: bool = Depends(verify_webhook_signature)
):
    """
    Handle webhook notification for app deauthorization events.
    This is triggered when a user removes your app's access to their Zoom account.
    """
    try:
        if event.event != "app.deauthorized":
            return {"status": "ignored", "message": f"Event type {event.event} not handled"}
        
        # Extract account info from payload
        account_id = event.payload.get("account_id", "unknown")
        user_id = event.payload.get("user_id", "unknown")
        
        logger.warning(f"App deauthorized by account {account_id}, user {user_id}")
        
        # Here you could add code to clean up any resources associated with this account
        
        return {
            "status": "success",
            "message": "Deauthorization webhook received",
            "account_id": account_id
        }
    
    except Exception as e:
        logger.error(f"Error processing deauthorization webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/meeting-deleted")
async def meeting_deleted(
    event: ZoomWebhookEvent,
    verified: bool = Depends(verify_webhook_signature)
):
    """
    Handle webhook notification for meeting deleted events.
    This is triggered when a meeting is deleted in Zoom.
    """
    try:
        if event.event != "meeting.deleted":
            return {"status": "ignored", "message": f"Event type {event.event} not handled"}
        
        # Extract meeting info from payload
        meeting_object = event.payload.get("object", {})
        meeting_id = meeting_object.get("id", "unknown")
        meeting_uuid = meeting_object.get("uuid", "unknown")
        
        logger.info(f"Meeting deleted: ID {meeting_id}, UUID {meeting_uuid}")
        
        # Here you could add code to clean up any resources associated with this meeting
        # For example, mark the meeting as deleted in your database
        
        return {
            "status": "success",
            "message": "Meeting deleted webhook received",
            "meeting_id": meeting_id,
            "meeting_uuid": meeting_uuid
        }
    
    except Exception as e:
        logger.error(f"Error processing meeting deleted webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 