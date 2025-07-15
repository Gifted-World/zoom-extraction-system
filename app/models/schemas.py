from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime


class ZoomWebhookEvent(BaseModel):
    """Model for Zoom webhook event payload."""
    event: str
    payload: Dict[str, Any]
    event_ts: int


class AISummary(BaseModel):
    """Model for Zoom AI-generated summary."""
    summary: str
    next_steps: Optional[List[str]] = None


class SmartChapter(BaseModel):
    """Model for Zoom smart recording chapter."""
    start_time: str
    end_time: str
    label: str


class SmartHighlight(BaseModel):
    """Model for Zoom smart recording highlight."""
    start_time: str
    end_time: str
    text: str


class ZoomRecording(BaseModel):
    """Model for Zoom recording information."""
    uuid: str
    id: int
    account_id: str
    host_id: str
    topic: str
    type: int
    start_time: datetime
    timezone: str
    duration: int
    total_size: int
    recording_count: int
    share_url: Optional[str] = None
    recording_files: List[Dict[str, Any]]
    ai_summary: Optional[AISummary] = None
    smart_recording_chapters: Optional[List[SmartChapter]] = None
    smart_recording_highlights: Optional[List[SmartHighlight]] = None


class TranscriptSegment(BaseModel):
    """Model for a segment of a transcript."""
    start_time: str
    end_time: str
    speaker: Optional[str] = None
    text: str


class Transcript(BaseModel):
    """Model for a full transcript."""
    meeting_id: str
    topic: str
    start_time: datetime
    duration: int
    segments: List[TranscriptSegment]


class SessionMetadata(BaseModel):
    """Model for session metadata."""
    course_name: str
    session_number: int
    session_name: str
    date: str
    meeting_id: str
    host_id: str


class AnalysisRequest(BaseModel):
    """Model for requesting an analysis."""
    transcript_path: str
    chat_log_path: Optional[str] = None
    analysis_types: List[str] = Field(default=["executive_summary", "pedagogical_analysis", "aha_moments", "engagement_analysis"])
    participant_school_mapping: Optional[Dict[str, str]] = None


class AnalysisResult(BaseModel):
    """Model for analysis results."""
    executive_summary: Optional[str] = None
    pedagogical_analysis: Optional[str] = None
    aha_moments: Optional[str] = None
    engagement_metrics: Optional[Dict[str, Any]] = None
    ai_summary: Optional[AISummary] = None
    smart_chapters: Optional[List[SmartChapter]] = None
    smart_highlights: Optional[List[SmartHighlight]] = None


class BatchProcessRequest(BaseModel):
    """Model for batch processing request."""
    zoom_account_id: str
    from_date: datetime
    to_date: Optional[datetime] = None
    course_filter: Optional[str] = None 