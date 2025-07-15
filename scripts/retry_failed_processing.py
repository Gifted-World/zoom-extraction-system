#!/usr/bin/env python
"""
Script to retry processing of failed sessions with longer wait times.
This script will:
1. Connect to Google Drive
2. Find all session folders marked as failed (.processing_failed)
3. Retry processing with increased backoff times
4. Update the report with insight URLs

Usage:
    python scripts/retry_failed_processing.py [--temp-dir TEMP_DIR] [--course COURSE] [--backoff-time BACKOFF_TIME] [--log-level LOG_LEVEL]
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
log_filename = os.path.join(log_dir, f"retry_failed_{timestamp}.log")

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

async def find_and_retry_failed_sessions(drive_manager: DriveManager, temp_dir: str, course_filter: str = None, backoff_time: int = 300):
    """
    Find and retry all failed sessions.
    
    Args:
        drive_manager: Drive manager instance
        temp_dir: Directory for temporary files
        course_filter: Optional course name to filter by
        backoff_time: Time to wait before retrying after rate limit (seconds)
    """
    logger.info("Finding failed sessions...")
    
    # Get all course folders
    course_folders = drive_manager.list_folders(drive_manager.root_folder_id)
    
    total_failed = 0
    total_retried = 0
    total_succeeded = 0
    
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
                total_failed += 1
                logger.info(f"Found failed session: {session_name}")
                
                # Delete the failed marker
                for file in files:
                    if file["name"] == ".processing_failed":
                        drive_manager.delete_file(file["id"])
                        logger.info(f"Deleted failed marker for session: {session_name}")
                        break
                
                # Retry processing with increased backoff time
                logger.info(f"Retrying processing for session: {session_name} with backoff time: {backoff_time}s")
                total_retried += 1
                
                success = await process_session_folder(
                    drive_manager=drive_manager,
                    folder_id=session_folder["id"],
                    folder_name=session_name,
                    temp_dir=temp_dir,
                    retry_failed=True,
                    backoff_time=backoff_time
                )
                
                if success:
                    total_succeeded += 1
                    logger.info(f"Successfully processed session: {session_name}")
                else:
                    logger.error(f"Failed to process session: {session_name}")
                
                # Add delay between sessions to avoid rate limits
                logger.info(f"Waiting 60 seconds before next session...")
                await asyncio.sleep(60)
    
    logger.info(f"Retry summary:")
    logger.info(f"  - Total failed sessions found: {total_failed}")
    logger.info(f"  - Total sessions retried: {total_retried}")
    logger.info(f"  - Total sessions successfully processed: {total_succeeded}")
    logger.info(f"  - Success rate: {(total_succeeded / total_retried * 100) if total_retried > 0 else 0:.1f}%")

async def main():
    """Main function to retry failed sessions."""
    parser = argparse.ArgumentParser(description="Retry processing of failed sessions")
    parser.add_argument("--temp-dir", type=str, default="./temp", help="Temporary directory for downloads")
    parser.add_argument("--course", type=str, help="Process only a specific course")
    parser.add_argument("--backoff-time", type=int, default=300, 
                        help="Initial time to wait before retrying after rate limit (seconds)")
    parser.add_argument("--log-level", type=str, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        default="INFO", help="Set the logging level")
    
    args = parser.parse_args()
    
    # Set logging level based on command-line argument
    logger.setLevel(getattr(logging, args.log_level))
    
    # Create temp directory
    os.makedirs(args.temp_dir, exist_ok=True)
    
    logger.info("Starting retry of failed sessions")
    
    # Initialize Drive manager
    drive_manager = DriveManager()
    
    # Find and retry failed sessions
    await find_and_retry_failed_sessions(
        drive_manager=drive_manager,
        temp_dir=args.temp_dir,
        course_filter=args.course,
        backoff_time=args.backoff_time
    )
    
    logger.info("Retry process completed")

if __name__ == "__main__":
    asyncio.run(main()) 