import logging
import json
import os
from typing import Dict, Any, List, Optional, Tuple
import asyncio

import anthropic
from anthropic import Anthropic
from google.oauth2 import service_account
from googleapiclient.discovery import build

import config
from app.models.schemas import AnalysisRequest, AnalysisResult, TranscriptSegment
from app.services.vtt_parser import parse_vtt, merge_consecutive_segments
from app.services.api_queue import api_queue

logger = logging.getLogger(__name__)

async def generate_analysis(request: AnalysisRequest) -> AnalysisResult:
    """
    Generate analysis for a transcript.
    
    Args:
        request: Analysis request with transcript path and options
        
    Returns:
        Analysis result with generated insights
    """
    try:
        # Parse the transcript
        segments = parse_vtt(request.transcript_path)
        merged_segments = merge_consecutive_segments(segments)
        
        # Format transcript for Claude
        transcript_text = format_transcript_for_claude(merged_segments)
        
        # Load chat log if available
        chat_text = ""
        if request.chat_log_path:
            try:
                with open(request.chat_log_path, "r", encoding="utf-8") as f:
                    chat_text = f.read()
                logger.info(f"Loaded chat log: {len(chat_text)} characters")
            except Exception as e:
                logger.warning(f"Error loading chat log: {e}")
        
        # Initialize result
        result = AnalysisResult()
        
        # Process analysis types sequentially with delays between them
        for analysis_type in request.analysis_types:
            logger.info(f"Generating {analysis_type}...")
            
            if analysis_type == "executive_summary":
                result.executive_summary = await generate_executive_summary(transcript_text, chat_text)
                
            elif analysis_type == "pedagogical_analysis":
                result.pedagogical_analysis = await generate_pedagogical_analysis(transcript_text, chat_text)
                
            elif analysis_type == "aha_moments":
                result.aha_moments = await generate_aha_moments(transcript_text, chat_text)
                
            elif analysis_type == "engagement_analysis":
                result.engagement_metrics = await generate_engagement_metrics(transcript_text, chat_text, request.participant_school_mapping)
            
            # Add delay between analysis types to avoid rate limits
            if analysis_type != request.analysis_types[-1]:
                delay = 5  # 5 seconds between analysis types
                logger.info(f"Waiting {delay}s before next analysis type")
                await asyncio.sleep(delay)
        
        return result
    
    except Exception as e:
        logger.error(f"Error generating analysis: {e}")
        raise

def format_transcript_for_claude(segments: List[TranscriptSegment]) -> str:
    """
    Format transcript segments for Claude.
    
    Args:
        segments: List of transcript segments
        
    Returns:
        Formatted transcript text
    """
    formatted_text = ""
    for segment in segments:
        formatted_text += f"{segment.speaker}: {segment.text}\n\n"
    return formatted_text

async def generate_executive_summary(transcript_text: str, chat_text: str = "") -> str:
    """
    Generate executive summary for a transcript.
    
    Args:
        transcript_text: Formatted transcript text
        chat_text: Chat log text (optional)
        
    Returns:
        Executive summary
    """
    prompt = config.CLAUDE_PROMPTS["executive_summary"].format(transcript=transcript_text)
    
    if chat_text:
        prompt += f"\n\nAdditional context from chat log:\n{chat_text}"
    
    try:
        response = await call_claude(prompt)
        return response
    except Exception as e:
        logger.error(f"Error generating executive summary: {e}")
        raise

async def generate_pedagogical_analysis(transcript_text: str, chat_text: str = "") -> str:
    """
    Generate pedagogical analysis for a transcript.
    
    Args:
        transcript_text: Formatted transcript text
        chat_text: Chat log text (optional)
        
    Returns:
        Pedagogical analysis
    """
    prompt = config.CLAUDE_PROMPTS["pedagogical_analysis"].format(transcript=transcript_text)
    
    if chat_text:
        prompt += f"\n\nAdditional context from chat log:\n{chat_text}"
    
    try:
        response = await call_claude(prompt)
        return response
    except Exception as e:
        logger.error(f"Error generating pedagogical analysis: {e}")
        raise

async def generate_aha_moments(transcript_text: str, chat_text: str = "") -> str:
    """
    Generate AHA moments for a transcript.
    
    Args:
        transcript_text: Formatted transcript text
        chat_text: Chat log text (optional)
        
    Returns:
        AHA moments
    """
    prompt = config.CLAUDE_PROMPTS["aha_moments"].format(transcript=transcript_text)
    
    if chat_text:
        prompt += f"\n\nAdditional context from chat log:\n{chat_text}"
    
    try:
        response = await call_claude(prompt)
        return response
    except Exception as e:
        logger.error(f"Error generating AHA moments: {e}")
        raise

async def generate_engagement_metrics(transcript_text: str, chat_text: str = "", school_mapping: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Generate engagement metrics for a transcript.
    
    Args:
        transcript_text: Formatted transcript text
        chat_text: Chat log text (optional)
        school_mapping: Mapping of participants to schools
        
    Returns:
        Engagement metrics
    """
    school_mapping_str = json.dumps(school_mapping or {}, indent=2)
    prompt = config.CLAUDE_PROMPTS["engagement_analysis"].format(
        transcript=transcript_text,
        school_mapping=school_mapping_str
    )
    
    if chat_text:
        prompt += f"\n\nAdditional context from chat log:\n{chat_text}"
    
    try:
        response = await call_claude(prompt)
        
        # Try to parse the response as JSON
        try:
            # Look for JSON block in the response
            import re
            json_match = re.search(r'```json\n(.*?)\n```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                metrics = json.loads(json_str)
            else:
                # Fallback: try to parse the entire response
                metrics = json.loads(response)
            
            return metrics
        except json.JSONDecodeError:
            # If parsing fails, return the raw response
            logger.warning("Failed to parse engagement metrics as JSON")
            return {"raw_response": response}
    
    except Exception as e:
        logger.error(f"Error generating engagement metrics: {e}")
        raise

async def call_claude(prompt: str, max_tokens: int = 4000) -> str:
    """
    Call Claude API with a prompt using the queue system.
    
    Args:
        prompt: Prompt to send to Claude
        max_tokens: Maximum tokens in the response
        
    Returns:
        Claude's response
    """
    try:
        # Use the API queue to manage rate limits
        logger.info(f"Queuing Claude API request with prompt length: {len(prompt)} chars")
        response = await api_queue.add_request(prompt, max_tokens)
        logger.info(f"Received Claude API response: {len(response)} chars")
        return response
    
    except Exception as e:
        logger.error(f"Error calling Claude API: {e}")
        raise

async def update_report_with_insight_urls(session_name: str, insight_urls: Dict[str, str]) -> bool:
    """
    Update the Zoom Report with insight URLs for a session.
    
    Args:
        session_name: Name of the session
        insight_urls: Dictionary with insight URLs
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the report ID from environment
        report_id = os.environ.get("ZOOM_REPORT_ID", "")
        if not report_id:
            logger.info("No report ID found in environment variables, skipping report update")
            return False
            
        logger.info(f"Updating report with insight URLs for: {session_name}")
        
        # Set up Google Sheets API client
        credentials = service_account.Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE, 
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        sheets_service = build("sheets", "v4", credentials=credentials)
        
        # First get the sheet metadata to find the actual sheet name
        sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=report_id).execute()
        sheets = sheet_metadata.get('sheets', '')
        
        if not sheets:
            logger.info("No sheets found in the spreadsheet")
            return False
            
        # Use the first sheet's title
        sheet_title = sheets[0]['properties']['title']
        logger.info(f"Using sheet: {sheet_title}")
        
        # Get the spreadsheet values
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=report_id,
            range=f"{sheet_title}!A1:Q1000"
        ).execute()
            
        values = result.get('values', [])
        if not values:
            logger.info("No data found in report")
            return False
            
        # Find the session in the report
        session_row_index = None
        for i, row in enumerate(values):
            if len(row) > 0 and session_name in row[0]:
                session_row_index = i
                break
                
        if session_row_index is None:
            logger.info(f"Session {session_name} not found in report")
            return False
            
        # Get the headers
        headers = values[0]
        
        # Map column names to indices
        url_columns = {
            "Executive Summary URL": insight_urls.get("executive_summary_url", ""),
            "Pedagogical Analysis URL": insight_urls.get("pedagogical_analysis_url", ""),
            "Aha Moments URL": insight_urls.get("aha_moments_url", ""),
            "Engagement Metrics URL": insight_urls.get("engagement_metrics_url", ""),
            "Concise Summary URL": insight_urls.get("concise_summary_url", "")
        }
        
        # Prepare updates
        updates = []
        for header, url in url_columns.items():
            if not url:
                continue
                
            try:
                col_index = headers.index(header)
                # Convert to A1 notation
                col_letter = chr(ord('A') + col_index)
                cell_range = f"{sheet_title}!{col_letter}{session_row_index + 1}"
                
                updates.append({
                    "range": cell_range,
                    "values": [[url]]
                })
            except ValueError:
                logger.warning(f"Column '{header}' not found in report")
        
        if not updates:
            logger.info("No updates to make")
            return False
            
        # Apply updates
        body = {
            "valueInputOption": "USER_ENTERED",
            "data": updates
        }
        
        result = sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=report_id,
            body=body
        ).execute()
        
        logger.info(f"Updated {len(updates)} cells in report")
        return True
        
    except Exception as e:
        logger.error(f"Error updating report with insight URLs: {e}")
        return False

async def generate_concise_summary_from_text(executive_summary: str) -> str:
    """
    Generate a concise summary from an executive summary.
    
    Args:
        executive_summary: Executive summary text
        
    Returns:
        Concise summary
    """
    prompt = f"""
You're creating a concise 3-5 line summary for school leaders based on this executive summary.
Focus on the most important insights and outcomes.
Make it clear, direct, and actionable.

Executive Summary:
{executive_summary}
"""
    
    try:
        response = await call_claude(prompt, max_tokens=1000)
        return response
    except Exception as e:
        logger.error(f"Error generating concise summary: {e}")
        raise 