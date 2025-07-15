#!/usr/bin/env python3
"""
Daily extraction cron script for Zoom recordings.
This script runs the simple daily extraction and sends email notifications.
"""

import os
import sys
import json
import logging
import smtplib
import asyncio
import subprocess
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional

# Add the parent directory to the path so we can import from the app
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

import config

# Set up logging
log_dir = os.path.join(parent_dir, "logs")
os.makedirs(log_dir, exist_ok=True)

log_file = os.path.join(log_dir, f"daily_extraction_cron_{datetime.now().strftime('%Y-%m-%d')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def send_notification_email(subject: str, body: str):
    """Send email notification with the daily extraction results."""
    try:
        msg = MIMEMultipart()
        msg['From'] = config.SENDER_EMAIL
        msg['To'] = config.RECIPIENT_EMAIL
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        server.starttls()
        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email notification sent successfully to {config.RECIPIENT_EMAIL}")
        
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")

def parse_extraction_log(log_file: str) -> Dict:
    """Parse the extraction log file to get statistics."""
    stats = {
        "sessions_processed": 0,
        "errors": 0,
        "sessions_details": [],
        "error_details": []
    }
    
    try:
        with open(log_file, 'r') as f:
            log_content = f.read()
            
        # Count successfully processed sessions
        sessions = []
        for line in log_content.split('\n'):
            if "Successfully processed session:" in line:
                # Extract session name from log line
                session_name = line.split("Successfully processed session: ")[1]
                sessions.append(session_name)
            elif "Files saved:" in line:
                # Extract files saved info
                files_info = line.split("Files saved: ")[1]
                if sessions:
                    stats["sessions_details"].append({
                        "name": sessions[-1],
                        "files": files_info
                    })
            elif "ERROR" in line:
                stats["errors"] += 1
                stats["error_details"].append(line)
        
        stats["sessions_processed"] = len(sessions)
        
        # Look for final completion message
        if "Daily extraction completed:" in log_content:
            completion_line = [line for line in log_content.split('\n') if "Daily extraction completed:" in line][-1]
            if completion_line:
                # Extract numbers from: "Daily extraction completed: 2 processed, 0 errors"
                parts = completion_line.split("Daily extraction completed: ")[1]
                if " processed, " in parts:
                    processed_str = parts.split(" processed, ")[0]
                    errors_str = parts.split(" processed, ")[1].split(" errors")[0]
                    stats["sessions_processed"] = int(processed_str)
                    stats["errors"] = int(errors_str)
        
    except Exception as e:
        logger.error(f"Error parsing log file: {e}")
        stats["error_details"].append(f"Error parsing log file: {e}")
    
    return stats

async def run_daily_extraction():
    """Run the daily extraction script."""
    start_time = datetime.now()
    logger.info("Starting daily Zoom extraction cron job")
    
    # Run the simple daily extraction script
    extraction_script = os.path.join(parent_dir, "scripts", "simple_daily_extraction.py")
    extraction_log = os.path.join(log_dir, f"daily_extraction_{datetime.now().strftime('%Y%m%d')}.log")
    
    success = False
    try:
        # Run the extraction script
        result = subprocess.run([
            sys.executable, extraction_script
        ], capture_output=True, text=True, timeout=1800)  # 30 minute timeout
        
        success = result.returncode == 0
        
        if success:
            logger.info("Daily extraction script completed successfully")
        else:
            logger.error(f"Daily extraction script failed with return code: {result.returncode}")
            logger.error(f"Error output: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        logger.error("Daily extraction script timed out after 30 minutes")
    except Exception as e:
        logger.error(f"Error running daily extraction script: {e}")
    
    # Parse the extraction log for statistics
    stats = parse_extraction_log(extraction_log)
    
    # Calculate processing time
    end_time = datetime.now()
    processing_time = end_time - start_time
    
    # Prepare email notification
    status = "SUCCESS" if success and stats["errors"] == 0 else "PARTIAL SUCCESS" if success else "FAILURE"
    
    subject = f"Zoom Daily Extraction: {status} ({datetime.now().strftime('%Y-%m-%d')})"
    
    # Create the email body
    body = f"""
Zoom Daily Extraction Report
============================
Date: {datetime.now().strftime('%Y-%m-%d')}
Status: {status}
Processing Time: {processing_time}
Sessions Processed: {stats["sessions_processed"]}
Errors: {stats["errors"]}

"""
    
    # Add session details
    if stats["sessions_details"]:
        body += "Sessions Processed:\n"
        body += "-------------------\n"
        for i, session in enumerate(stats["sessions_details"], 1):
            body += f"{i}. {session['name']}\n"
            body += f"   Files saved: {session['files']}\n\n"
    else:
        body += "No sessions processed today.\n\n"
    
    # Add Smart Recording information
    body += "Smart Recording Status:\n"
    body += "----------------------\n"
    body += "Smart Recording chapters and highlights will be extracted automatically\n"
    body += "if the feature is enabled in your Zoom account settings before meetings.\n\n"
    
    # Add file location information
    body += "File Location:\n"
    body += "-------------\n"
    body += f"All files are saved to Google Drive folder: {config.GOOGLE_DRIVE_ROOT_FOLDER}\n"
    body += "Files extracted for each session:\n"
    body += "• transcript.vtt (VTT format with timestamps)\n"
    body += "• ai_summary.json (AI-generated summary)\n"
    body += "• ai_next_steps.json (AI-generated next steps)\n"
    body += "• smart_chapters.json (if Smart Recording enabled)\n"
    body += "• smart_highlights.json (if Smart Recording enabled)\n"
    body += "• zoom_video_url.txt (URL to Zoom video)\n"
    body += "• session_metadata.json (meeting metadata)\n\n"
    
    # Add errors if any
    if stats["error_details"]:
        body += "Errors:\n"
        body += "-------\n"
        for error in stats["error_details"][:10]:  # Limit to first 10 errors
            body += f"{error}\n"
        if len(stats["error_details"]) > 10:
            body += f"... and {len(stats['error_details']) - 10} more errors\n"
        body += "\n"
    
    body += f"For detailed logs, see: {log_file}\n"
    body += f"Extraction logs: {extraction_log}\n"
    
    # Send email notification
    send_notification_email(subject, body)
    
    logger.info(f"Daily extraction cron job completed in {processing_time}")
    logger.info(f"Status: {status}")
    
    return success

if __name__ == "__main__":
    asyncio.run(run_daily_extraction())