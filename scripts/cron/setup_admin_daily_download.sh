#!/bin/bash
# Script to set up daily admin Zoom recording download

# Get the absolute path of the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_PATH="$PROJECT_DIR/scripts/extract_admin_videos.py"
LOG_DIR="$PROJECT_DIR/logs"
ENV_FILE="$PROJECT_DIR/.env"

# Make sure the script is executable
chmod +x "$SCRIPT_PATH"

# Create logs directory if it doesn't exist and ensure permissions are correct
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"
echo "Logs will be saved to: $LOG_DIR"

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

# Get conda info
CONDA_BASE=$(conda info --base)
if [ -z "$CONDA_BASE" ]; then
    echo "Error: conda installation not found"
    exit 1
fi

echo "Using conda at: $CONDA_BASE"
echo "Project directory: $PROJECT_DIR"
echo "Script path: $SCRIPT_PATH"

# Create the cron job command - run daily at 3:00 AM (2 hours after personal account)
# Gets recordings from the past 24 hours only
CRON_CMD="0 3 * * * cd $PROJECT_DIR && source $ENV_FILE && source $CONDA_BASE/etc/profile.d/conda.sh && conda activate base && python $SCRIPT_PATH --start-date \$(date -v-1d +\\%Y-\\%m-\\%d) --end-date \$(date +\\%Y-\\%m-\\%d) > $LOG_DIR/admin_daily_download_\$(date +\\%Y\\%m\\%d).log 2>&1"

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

echo ""
echo "Setup complete. The daily download will run at 3:00 AM every day."
echo "It will download recordings from the previous 24 hours only."
echo ""
echo "You can test it now by running:"
echo "cd $PROJECT_DIR && source $ENV_FILE && conda activate base && python $SCRIPT_PATH --start-date \$(date -v-1d +%Y-%m-%d) --end-date \$(date +%Y-%m-%d)"