#!/bin/bash
# Script to set up daily processing cron job

# Get the absolute path of the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_PATH="$PROJECT_DIR/scripts/daily_processing.py"
LOG_DIR="$PROJECT_DIR/logs"
ENV_FILE="$PROJECT_DIR/.env"

# Make sure the script is executable
chmod +x "$SCRIPT_PATH"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

# Get Python executable path
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    PYTHON_PATH=$(which python)
    if [ -z "$PYTHON_PATH" ]; then
        echo "Error: Python executable not found"
        exit 1
    fi
fi

echo "Using Python at: $PYTHON_PATH"
echo "Project directory: $PROJECT_DIR"
echo "Script path: $SCRIPT_PATH"

# Create the cron job command
# Run daily at 3:00 AM - overwrite the log file each day instead of appending
CRON_CMD="0 3 * * * cd $PROJECT_DIR && source $ENV_FILE && $PYTHON_PATH $SCRIPT_PATH > $LOG_DIR/cron_daily_processing.log 2>&1"

# Check if cron job already exists
EXISTING_CRON=$(crontab -l 2>/dev/null | grep -F "$SCRIPT_PATH")

if [ -n "$EXISTING_CRON" ]; then
    echo "Cron job already exists:"
    echo "$EXISTING_CRON"
    
    read -p "Do you want to replace it? (y/n): " REPLACE
    if [ "$REPLACE" != "y" ]; then
        echo "Keeping existing cron job."
        exit 0
    fi
    
    # Remove existing cron job
    crontab -l 2>/dev/null | grep -v -F "$SCRIPT_PATH" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo "Cron job added successfully:"
echo "$CRON_CMD"

# Add email configuration to .env if not already present
if ! grep -q "SMTP_SERVER" "$ENV_FILE"; then
    echo "" >> "$ENV_FILE"
    echo "# Email notification settings" >> "$ENV_FILE"
    echo "SMTP_SERVER=smtp.gmail.com" >> "$ENV_FILE"
    echo "SMTP_PORT=587" >> "$ENV_FILE"
    echo "SMTP_USERNAME=" >> "$ENV_FILE"
    echo "SMTP_PASSWORD=" >> "$ENV_FILE"
    echo "SENDER_EMAIL=" >> "$ENV_FILE"
    echo "RECIPIENT_EMAIL=" >> "$ENV_FILE"
    
    echo ""
    echo "Email notification settings added to .env file."
    echo "Please edit $ENV_FILE to add your email credentials."
fi

echo ""
echo "Setup complete. The daily processing will run at 3:00 AM every day."
echo "You can test it now by running:"
echo "cd $PROJECT_DIR && source $ENV_FILE && $PYTHON_PATH $SCRIPT_PATH" 