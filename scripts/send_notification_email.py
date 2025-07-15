#!/usr/bin/env python
"""
Script to send email notifications when new sessions are extracted.
This script will:
1. Check how many new sessions were extracted in the latest run
2. If there are new sessions, send an email to the hosts with links to the report
3. CC rajesh@genwise.in and vishnu@genwise.in
"""

import os
import sys
import json
import smtplib
import argparse
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

# Add the parent directory to the path so we can import from the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# Set up logging
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_filename = os.path.join(log_dir, f"email_notification_{timestamp}.log")

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

def send_email(
    recipient_email: str,
    subject: str,
    body_html: str,
    cc_emails: List[str] = None
) -> bool:
    """
    Send an email using Gmail SMTP.
    
    Args:
        recipient_email: Email address of the recipient
        subject: Email subject
        body_html: HTML body of the email
        cc_emails: List of email addresses to CC
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Email configuration
        sender_email = config.GMAIL_USERNAME
        sender_password = config.GMAIL_APP_PASSWORD
        
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender_email
        message["To"] = recipient_email
        
        if cc_emails:
            message["Cc"] = ", ".join(cc_emails)
            all_recipients = [recipient_email] + cc_emails
        else:
            all_recipients = [recipient_email]
        
        # Add HTML content
        html_part = MIMEText(body_html, "html")
        message.attach(html_part)
        
        # Connect to Gmail SMTP server
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, all_recipients, message.as_string())
            
        logger.info(f"Email sent to {recipient_email} with CC: {cc_emails}")
        return True
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False

def check_for_new_sessions(report_path: str, previous_report_path: str = None) -> List[Dict]:
    """
    Check for new sessions by comparing the current report with the previous one.
    
    Args:
        report_path: Path to the current report
        previous_report_path: Path to the previous report (if available)
        
    Returns:
        List of new session data
    """
    try:
        # Read current report
        current_df = pd.read_csv(report_path)
        
        # If no previous report, consider all sessions as new
        if not previous_report_path or not os.path.exists(previous_report_path):
            logger.info(f"No previous report found. Considering all {len(current_df)} sessions as new.")
            return current_df.to_dict('records')
        
        # Read previous report
        previous_df = pd.read_csv(previous_report_path)
        
        # Find new sessions by comparing Meeting UUIDs
        current_uuids = set(current_df["Meeting UUID"])
        previous_uuids = set(previous_df["Meeting UUID"])
        new_uuids = current_uuids - previous_uuids
        
        # Filter current dataframe to only include new sessions
        new_sessions = current_df[current_df["Meeting UUID"].isin(new_uuids)]
        
        logger.info(f"Found {len(new_sessions)} new sessions out of {len(current_df)} total sessions.")
        return new_sessions.to_dict('records')
    except Exception as e:
        logger.error(f"Error checking for new sessions: {e}")
        return []

def format_date(date_str: str) -> str:
    """
    Format a date string from ISO format to "dd mmm yyyy".
    
    Args:
        date_str: Date string in ISO format (YYYY-MM-DDThh:mm:ssZ)
        
    Returns:
        Formatted date string (dd mmm yyyy)
    """
    try:
        # Parse the ISO date
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(date_str)
        
        # Format to "dd mmm yyyy"
        return dt.strftime("%d %b %Y")
    except Exception:
        return date_str

def generate_email_for_host(host_email: str, host_name: str, sessions: List[Dict], report_url: str) -> str:
    """
    Generate an email for a specific host with their sessions.
    
    Args:
        host_email: Email address of the host
        host_name: Name of the host
        sessions: List of session data for this host
        report_url: URL to the Zoom report
        
    Returns:
        HTML email body
    """
    # Start with greeting
    email_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .footer {{ font-size: 12px; color: #777; margin-top: 30px; }}
            a {{ color: #0066cc; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>New Zoom Recordings Processed</h2>
            <p>Hello {host_name},</p>
            <p>The following Zoom recording(s) from your sessions have been processed:</p>
            
            <table>
                <tr>
                    <th>Date</th>
                    <th>Meeting Topic</th>
                    <th>Duration</th>
                    <th>Links</th>
                </tr>
    """
    
    # Add each session to the table
    for session in sessions:
        # Format the date
        date = format_date(session.get("Start Time", ""))
        
        # Create links section
        links = []
        if session.get("Zoom Video URL"):
            links.append(f'<a href="{session["Zoom Video URL"]}">Video</a>')
        if session.get("Executive Summary URL"):
            links.append(f'<a href="{session["Executive Summary URL"]}">Executive Summary</a>')
        if session.get("Concise Summary URL"):
            links.append(f'<a href="{session["Concise Summary URL"]}">Concise Summary</a>')
        if session.get("Pedagogical Analysis URL"):
            links.append(f'<a href="{session["Pedagogical Analysis URL"]}">Pedagogical Analysis</a>')
        
        links_html = " | ".join(links)
        
        # Add row to table
        email_body += f"""
                <tr>
                    <td>{date}</td>
                    <td>{session.get("Meeting Topic", "Unknown")}</td>
                    <td>{session.get("Duration (minutes)", "N/A")} mins</td>
                    <td>{links_html}</td>
                </tr>
        """
    
    # Add footer with link to full report
    email_body += f"""
            </table>
            
            <p>You can access the full report with all recordings here:</p>
            <p><a href="{report_url}">{report_url}</a></p>
            
            <p>If you have any questions or need assistance, please contact rajesh@genwise.in.</p>
            
            <div class="footer">
                <p>This is an automated message from the Insights from Online Courses system.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return email_body

def send_notifications(new_sessions: List[Dict], report_url: str) -> None:
    """
    Send email notifications to hosts about their new sessions.
    
    Args:
        new_sessions: List of new session data
        report_url: URL to the Zoom report
    """
    if not new_sessions:
        logger.info("No new sessions to send notifications for.")
        return
    
    # Group sessions by host email
    host_sessions = {}
    for session in new_sessions:
        host_email = session.get("Host Email")
        host_name = session.get("Host Name", "Instructor")
        
        if not host_email or host_email == "Unknown":
            logger.warning(f"Missing host email for session: {session.get('Meeting Topic')}")
            continue
        
        if host_email not in host_sessions:
            host_sessions[host_email] = {
                "name": host_name,
                "sessions": []
            }
        
        host_sessions[host_email]["sessions"].append(session)
    
    # CC emails
    cc_emails = ["rajesh@genwise.in", "vishnu@genwise.in"]
    
    # Send email to each host
    for host_email, data in host_sessions.items():
        host_name = data["name"]
        sessions = data["sessions"]
        
        # Generate subject with session count
        subject = f"New Zoom Recording{'s' if len(sessions) > 1 else ''} Processed - {sessions[0].get('Meeting Topic', 'Your Session')}"
        if len(sessions) > 1:
            subject = f"New Zoom Recordings Processed - {len(sessions)} Sessions"
        
        # Generate email body
        email_body = generate_email_for_host(host_email, host_name, sessions, report_url)
        
        # Send email
        success = send_email(host_email, subject, email_body, cc_emails)
        
        if success:
            logger.info(f"Notification email sent to {host_email} for {len(sessions)} sessions")
        else:
            logger.error(f"Failed to send notification email to {host_email}")

def main():
    """Main function to send notification emails."""
    parser = argparse.ArgumentParser(description="Send notification emails for new Zoom recordings")
    parser.add_argument("--report-path", type=str, default="./temp/zoom_recordings_report.csv", 
                        help="Path to the current Zoom recordings report")
    parser.add_argument("--previous-report-path", type=str, 
                        help="Path to the previous Zoom recordings report (optional)")
    parser.add_argument("--report-url", type=str, required=True,
                        help="URL to the Zoom report on Google Drive")
    parser.add_argument("--log-level", type=str, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                        default="INFO", help="Set the logging level")
    
    args = parser.parse_args()
    
    # Set logging level based on command-line argument
    logger.setLevel(getattr(logging, args.log_level))
    
    logger.info("Starting notification email process")
    
    # Check for new sessions
    new_sessions = check_for_new_sessions(args.report_path, args.previous_report_path)
    
    # Send notifications
    send_notifications(new_sessions, args.report_url)
    
    logger.info("Notification email process completed")

if __name__ == "__main__":
    main() 