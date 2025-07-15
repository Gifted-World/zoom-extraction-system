from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from typing import List, Optional, Dict
import os
import tempfile
import json
import logging

from app.models.schemas import AnalysisRequest, AnalysisResult, BatchProcessRequest
from app.services.vtt_parser import parse_vtt
from app.services.analysis import generate_analysis
from app.services.drive_manager import upload_to_drive, create_folder_structure

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/analyze", response_model=AnalysisResult)
async def analyze_transcript(
    transcript_file: UploadFile = File(...),
    chat_log_file: Optional[UploadFile] = None,
    course_name: str = Form(...),
    session_number: int = Form(...),
    session_name: str = Form(...),
    session_date: str = Form(...),
    analysis_types: str = Form("executive_summary,pedagogical_analysis,aha_moments,engagement_analysis"),
    participant_school_mapping: Optional[str] = Form(None)
):
    """
    Analyze a transcript file and optionally a chat log file.
    """
    try:
        # Save uploaded files to temp directory
        with tempfile.NamedTemporaryFile(delete=False, suffix=".vtt") as temp_transcript:
            temp_transcript.write(await transcript_file.read())
            transcript_path = temp_transcript.name
        
        chat_log_path = None
        if chat_log_file:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as temp_chat:
                temp_chat.write(await chat_log_file.read())
                chat_log_path = temp_chat.name
        
        # Parse participant-school mapping if provided
        mapping = {}
        if participant_school_mapping:
            mapping = json.loads(participant_school_mapping)
        
        # Create analysis request
        request = AnalysisRequest(
            transcript_path=transcript_path,
            chat_log_path=chat_log_path,
            analysis_types=analysis_types.split(","),
            participant_school_mapping=mapping
        )
        
        # Generate analysis
        result = await generate_analysis(request)
        
        # Upload to Google Drive
        folder_path = await create_folder_structure(
            course_name=course_name,
            session_number=session_number,
            session_name=session_name,
            session_date=session_date
        )
        
        await upload_to_drive(
            transcript_path=transcript_path,
            chat_log_path=chat_log_path,
            analysis_result=result,
            folder_path=folder_path
        )
        
        # Clean up temp files
        os.unlink(transcript_path)
        if chat_log_path:
            os.unlink(chat_log_path)
        
        return result
    
    except Exception as e:
        logger.error(f"Error analyzing transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch", response_model=Dict[str, str])
async def batch_process(request: BatchProcessRequest):
    """
    Batch process recordings from Zoom.
    """
    try:
        # This would trigger a background task to process recordings
        return {"status": "Processing started", "message": "Batch processing initiated"}
    
    except Exception as e:
        logger.error(f"Error starting batch process: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/courses", response_model=List[str])
async def list_courses():
    """
    List all available courses.
    """
    try:
        # This would list courses from Google Drive
        return ["Course 1", "Course 2"]  # Placeholder
    
    except Exception as e:
        logger.error(f"Error listing courses: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{course_name}", response_model=List[Dict[str, str]])
async def list_sessions(course_name: str):
    """
    List all sessions for a course.
    """
    try:
        # This would list sessions from Google Drive
        return [
            {"id": "1", "name": "Session 1", "date": "2023-01-01"},
            {"id": "2", "name": "Session 2", "date": "2023-01-08"}
        ]  # Placeholder
    
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analysis/{session_id}/{analysis_type}", response_model=Dict[str, str])
async def get_analysis(session_id: str, analysis_type: str):
    """
    Get a specific analysis for a session.
    """
    try:
        # This would retrieve analysis from Google Drive
        return {"content": "Analysis content here"}  # Placeholder
    
    except Exception as e:
        logger.error(f"Error getting analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 