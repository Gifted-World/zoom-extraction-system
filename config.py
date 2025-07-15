import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'app.log')

# Google API configuration
GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
GOOGLE_TOKEN_FILE = os.getenv('GOOGLE_TOKEN_FILE', 'token.json')
GOOGLE_SHARED_DRIVE_ID = os.getenv('GOOGLE_SHARED_DRIVE_ID')
USE_SHARED_DRIVE = bool(GOOGLE_SHARED_DRIVE_ID)  # True if GOOGLE_SHARED_DRIVE_ID is set

# Zoom API configuration
ZOOM_API_KEY = os.getenv('ZOOM_API_KEY')
ZOOM_API_SECRET = os.getenv('ZOOM_API_SECRET')
ZOOM_ACCOUNT_ID = os.getenv('ZOOM_ACCOUNT_ID')
ZOOM_CLIENT_ID = os.getenv('ZOOM_CLIENT_ID')
ZOOM_CLIENT_SECRET = os.getenv('ZOOM_CLIENT_SECRET')
ZOOM_BASE_URL = os.getenv('ZOOM_BASE_URL', 'https://api.zoom.us/v2')

# Personal Zoom account configuration
PERSONAL_ZOOM_CLIENT_ID = os.getenv('PERSONAL_ZOOM_CLIENT_ID')
PERSONAL_ZOOM_CLIENT_SECRET = os.getenv('PERSONAL_ZOOM_CLIENT_SECRET')
PERSONAL_ZOOM_ACCOUNT_ID = os.getenv('PERSONAL_ZOOM_ACCOUNT_ID')

# Google Drive configuration
GOOGLE_DRIVE_ROOT_FOLDER = os.getenv('GOOGLE_DRIVE_ROOT_FOLDER', '13ROvu8sxhEllgFKI5O13LnYI0RIR78PJ')

# Webhook configuration
WEBHOOK_SECRET_TOKEN = os.getenv('WEBHOOK_SECRET_TOKEN', 'your-secret-token')

# Application configuration
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')
TESTING = os.getenv('TESTING', 'False').lower() in ('true', '1', 't')

# Claude API configuration
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Email configuration
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_RECIPIENTS = os.getenv('EMAIL_RECIPIENTS', '').split(',')
EMAIL_SMTP_SERVER = os.getenv('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', 587))

# Report configuration
ZOOM_REPORT_ID = os.getenv('ZOOM_REPORT_ID')

# Report columns
INSIGHT_COLUMNS = [
    "Executive Summary URL",
    "Pedagogical Analysis URL",
    "Aha Moments URL",
    "Engagement Metrics URL",
    "Concise Summary URL"
]

# AI Summary columns
AI_SUMMARY_COLUMNS = [
    "AI Summary URL",
    "AI Next Steps URL",
    "Smart Chapters URL",
    "Smart Highlights URL"
]

# Folder structure for new sessions (simplified)
FOLDER_STRUCTURE = {
    "course_folder": "{course_name}",
    "session_folder": "{session_name}_{session_date}",
    "files": {
        "transcript": "transcript.vtt",
        "ai_summary": "ai_summary.json",
        "ai_next_steps": "ai_next_steps.json", 
        "smart_chapters": "smart_chapters.json",
        "smart_highlights": "smart_highlights.json",
        "zoom_video_url": "zoom_video_url.txt",
        "metadata": "session_metadata.json"
    }
}
