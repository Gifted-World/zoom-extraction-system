import webvtt
import re
from typing import List, Dict, Optional, Tuple
import logging

from app.models.schemas import TranscriptSegment, Transcript

logger = logging.getLogger(__name__)

def parse_vtt(file_path: str) -> List[TranscriptSegment]:
    """
    Parse a VTT file and extract segments with speaker information.
    
    Args:
        file_path: Path to the VTT file
        
    Returns:
        List of TranscriptSegment objects
    """
    try:
        vtt = webvtt.read(file_path)
        segments = []
        
        for caption in vtt:
            # Extract timing information
            start_time = caption.start
            end_time = caption.end
            
            # Extract speaker and text
            text = caption.text
            speaker = None
            
            # Try to extract speaker information (format: "Speaker Name: Text")
            speaker_match = re.match(r'^(.*?):\s*(.*)', text, re.DOTALL)
            if speaker_match:
                speaker = speaker_match.group(1).strip()
                text = speaker_match.group(2).strip()
            
            segment = TranscriptSegment(
                start_time=start_time,
                end_time=end_time,
                speaker=speaker,
                text=text
            )
            segments.append(segment)
        
        return segments
    
    except Exception as e:
        logger.error(f"Error parsing VTT file: {e}")
        raise

def extract_meeting_metadata(segments: List[TranscriptSegment]) -> Tuple[str, str]:
    """
    Extract meeting topic and host from transcript segments.
    
    Args:
        segments: List of transcript segments
        
    Returns:
        Tuple of (topic, host)
    """
    # Default values
    topic = "Unknown Topic"
    host = "Unknown Host"
    
    # Try to find meeting metadata in the first few segments
    for segment in segments[:10]:  # Check only first 10 segments
        # Look for meeting title patterns
        title_match = re.search(r'meeting\s+title[:\s]+(.+)', segment.text, re.IGNORECASE)
        if title_match:
            topic = title_match.group(1).strip()
            continue
        
        # Look for host information
        host_match = re.search(r'host(?:ed)?\s+by[:\s]+(.+)', segment.text, re.IGNORECASE)
        if host_match:
            host = host_match.group(1).strip()
            continue
    
    return topic, host

def calculate_speaker_stats(segments: List[TranscriptSegment]) -> Dict[str, Dict]:
    """
    Calculate statistics for each speaker in the transcript.
    
    Args:
        segments: List of transcript segments
        
    Returns:
        Dictionary mapping speaker names to their statistics
    """
    stats = {}
    
    for segment in segments:
        if not segment.speaker:
            continue
        
        speaker = segment.speaker
        if speaker not in stats:
            stats[speaker] = {
                "total_segments": 0,
                "total_words": 0,
                "total_duration_seconds": 0,
                "first_timestamp": segment.start_time,
                "last_timestamp": segment.end_time
            }
        
        # Update stats
        stats[speaker]["total_segments"] += 1
        stats[speaker]["total_words"] += len(segment.text.split())
        
        # Calculate duration
        start_time_parts = segment.start_time.split(':')
        end_time_parts = segment.end_time.split(':')
        
        start_seconds = int(start_time_parts[0]) * 3600 + int(start_time_parts[1]) * 60 + float(start_time_parts[2])
        end_seconds = int(end_time_parts[0]) * 3600 + int(end_time_parts[1]) * 60 + float(end_time_parts[2])
        
        duration = end_seconds - start_seconds
        stats[speaker]["total_duration_seconds"] += duration
        
        # Update last timestamp
        stats[speaker]["last_timestamp"] = segment.end_time
    
    return stats

def merge_consecutive_segments(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
    """
    Merge consecutive segments from the same speaker.
    
    Args:
        segments: List of transcript segments
        
    Returns:
        List of merged transcript segments
    """
    if not segments:
        return []
    
    merged_segments = []
    current_segment = segments[0]
    
    for segment in segments[1:]:
        # If same speaker, merge
        if segment.speaker == current_segment.speaker:
            current_segment.end_time = segment.end_time
            current_segment.text += " " + segment.text
        else:
            # Different speaker, add current segment to result and start a new one
            merged_segments.append(current_segment)
            current_segment = segment
    
    # Add the last segment
    merged_segments.append(current_segment)
    
    return merged_segments 