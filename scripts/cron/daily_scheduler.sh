#!/bin/bash

# Daily Zoom Extraction Scheduler
# This script runs continuously in the background and executes daily extractions at scheduled times

PROJECT_DIR="/Users/rajeshpanchanathan/Documents/genwise/projects/zoom-extraction-system"
LOG_DIR="$PROJECT_DIR/logs"

# Ensure we're in the right directory
cd "$PROJECT_DIR"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Log startup
echo "$(date): Daily Zoom extraction scheduler started" >> "$LOG_DIR/scheduler.log"

# Function to check if it's time to run personal extraction (1:00 AM)
check_personal_time() {
    current_hour=$(date +%H)
    current_minute=$(date +%M)
    
    if [[ "$current_hour" == "01" && "$current_minute" == "00" ]]; then
        return 0  # It's time
    else
        return 1  # Not time yet
    fi
}

# Function to check if it's time to run admin extraction (3:00 AM)
check_admin_time() {
    current_hour=$(date +%H)
    current_minute=$(date +%M)
    
    if [[ "$current_hour" == "03" && "$current_minute" == "00" ]]; then
        return 0  # It's time
    else
        return 1  # Not time yet
    fi
}

# Track if we've already run today
personal_run_file="$LOG_DIR/.personal_run_$(date +%Y%m%d)"
admin_run_file="$LOG_DIR/.admin_run_$(date +%Y%m%d)"

# Main loop
while true; do
    current_time=$(date)
    
    # Check personal extraction time
    if check_personal_time && [[ ! -f "$personal_run_file" ]]; then
        echo "$(date): Starting personal daily extraction" >> "$LOG_DIR/scheduler.log"
        "$PROJECT_DIR/scripts/cron/run_personal_daily.sh"
        touch "$personal_run_file"
        echo "$(date): Personal daily extraction completed" >> "$LOG_DIR/scheduler.log"
    fi
    
    # Check admin extraction time  
    if check_admin_time && [[ ! -f "$admin_run_file" ]]; then
        echo "$(date): Starting admin daily extraction" >> "$LOG_DIR/scheduler.log"
        "$PROJECT_DIR/scripts/cron/run_admin_daily.sh"
        touch "$admin_run_file"
        echo "$(date): Admin daily extraction completed" >> "$LOG_DIR/scheduler.log"
    fi
    
    # Clean up old run files (older than 7 days)
    find "$LOG_DIR" -name ".personal_run_*" -mtime +7 -delete 2>/dev/null
    find "$LOG_DIR" -name ".admin_run_*" -mtime +7 -delete 2>/dev/null
    
    # Sleep for 60 seconds before checking again
    sleep 60
done






