#!/usr/bin/env python
"""
Script to process transcripts in smaller batches with delays between each batch.
This helps to avoid rate limiting issues with the Claude API.

Usage:
    python scripts/process_batch.py [--batch-size BATCH_SIZE] [--delay DELAY] [--temp-dir TEMP_DIR] [--course COURSE] [--log-level LOG_LEVEL]
"""

import os
import sys
import argparse
import logging
import asyncio
from datetime import datetime

# Add the parent directory to the path so we can import from the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.process_drive_recordings import DriveManager, process_session_folder

# Set up logging with timestamped log file
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_filename = os.path.join(log_dir, f"batch_processing_{timestamp}.log")

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

async def process_in_batches(drive_manager: DriveManager, temp_dir: str, batch_size: int = 3, delay: int = 600, course_filter: str = None):
    """
    Process sessions in batches with delays between each batch.
    
    Args:
        drive_manager: Drive manager instance
        temp_dir: Directory for temporary files
        batch_size: Number of sessions to process in each batch
        delay: Delay in seconds between batches
        course_filter: Optional course name to filter by
    """
    logger.info(f"Processing in batches of {batch_size} with {delay}s delay between batches")
    
    # Get all course folders
    course_folders = drive_manager.list_folders(drive_manager.root_folder_id)
    
    # Collect all sessions that need processing
    sessions_to_process = []
    
    for course_folder in course_folders:
        course_name = course_folder["name"]
        
        # Skip if not the specified course
        if course_filter and course_name != course_filter:
            logger.debug(f"Skipping course folder: {course_name}")
            continue
            
        logger.info(f"Checking course folder: {course_name}")
        
        # Get all session folders
        session_folders = drive_manager.list_folders(course_folder["id"])
        
        for session_folder in session_folders:
            session_name = session_folder["name"]
            
            # Check if this session needs processing
            files = drive_manager.list_files(session_folder["id"])
            file_names = [file["name"] for file in files]
            
            # Skip if already processed or failed
            if ".processed" in file_names:
                logger.debug(f"Skipping already processed session: {session_name}")
                continue
                
            # Check if transcript exists
            has_transcript = False
            for file in files:
                if file["name"].lower().endswith(".vtt") or file["name"] == "transcript.vtt":
                    has_transcript = True
                    break
            
            if not has_transcript:
                logger.debug(f"Skipping session without transcript: {session_name}")
                continue
            
            # Check if any analysis files are missing
            analysis_files = [
                "executive_summary.md",
                "pedagogical_analysis.md",
                "aha_moments.md",
                "engagement_metrics.json"
            ]
            
            needs_processing = False
            for analysis_file in analysis_files:
                if analysis_file not in file_names:
                    needs_processing = True
                    break
            
            if needs_processing:
                sessions_to_process.append({
                    "folder_id": session_folder["id"],
                    "folder_name": session_name
                })
    
    total_sessions = len(sessions_to_process)
    logger.info(f"Found {total_sessions} sessions that need processing")
    
    # Process in batches
    batch_count = 0
    success_count = 0
    
    for i in range(0, total_sessions, batch_size):
        batch_count += 1
        batch = sessions_to_process[i:i+batch_size]
        logger.info(f"Processing batch {batch_count} ({len(batch)} sessions)")
        
        # Process each session in the batch
        batch_tasks = []
        for session in batch:
            task = asyncio.create_task(process_session_folder(
                drive_manager=drive_manager,
                folder_id=session["folder_id"],
                folder_name=session["folder_name"],
                temp_dir=temp_dir
            ))
            batch_tasks.append(task)
        
        # Wait for all tasks in this batch to complete
        results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        # Count successes
        for result in results:
            if result is True:  # successful processing
                success_count += 1
        
        # Wait before processing the next batch
        if i + batch_size < total_sessions:
            logger.info(f"Waiting {delay}s before next batch...")
            await asyncio.sleep(delay)
    
    logger.info(f"Batch processing completed")
    logger.info(f"Total sessions: {total_sessions}")
    logger.info(f"Successfully processed: {success_count}")
    logger.info(f"Failed: {total_sessions - success_count}")

async def main():
    """Main function to process in batches."""
    parser = argparse.ArgumentParser(description="Process transcripts in batches")
    parser.add_argument("--batch-size", type=int, default=3, 
                        help="Number of sessions to process in each batch")
    parser.add_argument("--delay", type=int, default=600, 
                        help="Delay in seconds between batches")
    parser.add_argument("--temp-dir", type=str, default="./temp", 
                        help="Temporary directory for downloads")
    parser.add_argument("--course", type=str, 
                        help="Process only a specific course")
    parser.add_argument("--log-level", type=str, 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        default="INFO", help="Set the logging level")
    
    args = parser.parse_args()
    
    # Set logging level based on command-line argument
    logger.setLevel(getattr(logging, args.log_level))
    
    # Create temp directory
    os.makedirs(args.temp_dir, exist_ok=True)
    
    logger.info("Starting batch processing")
    
    # Initialize Drive manager
    drive_manager = DriveManager()
    
    # Process in batches
    await process_in_batches(
        drive_manager=drive_manager,
        temp_dir=args.temp_dir,
        batch_size=args.batch_size,
        delay=args.delay,
        course_filter=args.course
    )
    
    logger.info("Batch processing completed")

if __name__ == "__main__":
    asyncio.run(main()) 