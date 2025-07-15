#!/usr/bin/env python
"""
Script to reset failed sessions and process them in batches.
This script will:
1. Connect to Google Drive
2. Find all session folders marked as failed (.processing_failed)
3. Remove the failed marker
4. Process them in batches with delays

Usage:
    python scripts/reset_and_process_failed.py [--batch-size BATCH_SIZE] [--delay DELAY] [--temp-dir TEMP_DIR] [--course COURSE] [--log-level LOG_LEVEL]
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
log_filename = os.path.join(log_dir, f"reset_and_process_{timestamp}.log")

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

async def find_and_process_failed_sessions(drive_manager: DriveManager, temp_dir: str, batch_size: int = 2, delay: int = 900, course_filter: str = None, backoff_time: int = 600):
    """
    Find failed sessions, reset them, and process them in batches.
    
    Args:
        drive_manager: Drive manager instance
        temp_dir: Directory for temporary files
        batch_size: Number of sessions to process in each batch
        delay: Delay in seconds between batches
        course_filter: Optional course name to filter by
        backoff_time: Time to wait before retrying after rate limit (seconds)
    """
    logger.info("Finding failed sessions...")
    
    # Get all course folders
    course_folders = drive_manager.list_folders(drive_manager.root_folder_id)
    
    # Collect all failed sessions
    failed_sessions = []
    
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
            
            # Check if this session is marked as failed
            files = drive_manager.list_files(session_folder["id"])
            file_names = [file["name"] for file in files]
            
            if ".processing_failed" in file_names:
                logger.info(f"Found failed session: {session_name}")
                
                # Remove the failed marker file
                for file in files:
                    if file["name"] == ".processing_failed":
                        try:
                            # Use the service directly to delete the file
                            drive_manager.service.files().delete(
                                fileId=file["id"],
                                supportsAllDrives=True
                            ).execute()
                            logger.info(f"Deleted failed marker for session: {session_name}")
                        except Exception as e:
                            logger.error(f"Error deleting failed marker: {e}")
                        break
                
                # Add to list of sessions to process
                failed_sessions.append({
                    "folder_id": session_folder["id"],
                    "folder_name": session_name
                })
    
    total_sessions = len(failed_sessions)
    logger.info(f"Found {total_sessions} failed sessions to process")
    
    # Process in batches
    batch_count = 0
    success_count = 0
    
    for i in range(0, total_sessions, batch_size):
        batch_count += 1
        batch = failed_sessions[i:i+batch_size]
        logger.info(f"Processing batch {batch_count} ({len(batch)} sessions)")
        
        # Process each session in the batch
        for session in batch:
            logger.info(f"Processing session: {session['folder_name']}")
            
            success = await process_session_folder(
                drive_manager=drive_manager,
                folder_id=session["folder_id"],
                folder_name=session["folder_name"],
                temp_dir=temp_dir,
                retry_failed=True,
                backoff_time=backoff_time
            )
            
            if success:
                success_count += 1
                logger.info(f"Successfully processed session: {session['folder_name']}")
            else:
                logger.error(f"Failed to process session: {session['folder_name']}")
            
            # Add a small delay between sessions in the same batch
            if session != batch[-1]:
                logger.info(f"Waiting 30 seconds before next session in batch...")
                await asyncio.sleep(30)
        
        # Wait before processing the next batch
        if i + batch_size < total_sessions:
            logger.info(f"Waiting {delay}s before next batch...")
            await asyncio.sleep(delay)
    
    logger.info(f"Processing completed")
    logger.info(f"Total sessions: {total_sessions}")
    logger.info(f"Successfully processed: {success_count}")
    logger.info(f"Failed: {total_sessions - success_count}")

async def main():
    """Main function to reset and process failed sessions."""
    parser = argparse.ArgumentParser(description="Reset and process failed sessions in batches")
    parser.add_argument("--batch-size", type=int, default=2, 
                        help="Number of sessions to process in each batch")
    parser.add_argument("--delay", type=int, default=900, 
                        help="Delay in seconds between batches")
    parser.add_argument("--temp-dir", type=str, default="./temp", 
                        help="Temporary directory for downloads")
    parser.add_argument("--course", type=str, 
                        help="Process only a specific course")
    parser.add_argument("--backoff-time", type=int, default=600,
                        help="Initial time to wait before retrying after rate limit (seconds)")
    parser.add_argument("--log-level", type=str, 
                        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        default="INFO", help="Set the logging level")
    
    args = parser.parse_args()
    
    # Set logging level based on command-line argument
    logger.setLevel(getattr(logging, args.log_level))
    
    # Create temp directory
    os.makedirs(args.temp_dir, exist_ok=True)
    
    logger.info("Starting reset and process of failed sessions")
    
    # Initialize Drive manager
    drive_manager = DriveManager()
    
    # Find and process failed sessions
    await find_and_process_failed_sessions(
        drive_manager=drive_manager,
        temp_dir=args.temp_dir,
        batch_size=args.batch_size,
        delay=args.delay,
        course_filter=args.course,
        backoff_time=args.backoff_time
    )
    
    logger.info("Reset and process completed")

if __name__ == "__main__":
    asyncio.run(main()) 