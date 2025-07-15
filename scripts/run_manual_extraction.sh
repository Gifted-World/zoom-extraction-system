#!/bin/bash
# Script to manually run the extraction process

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Default dates (yesterday to today)
START_DATE=$(date -v-1d +%Y-%m-%d)
END_DATE=$(date +%Y-%m-%d)
SEND_EMAILS=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --start-date)
        START_DATE="$2"
        shift
        shift
        ;;
        --end-date)
        END_DATE="$2"
        shift
        shift
        ;;
        --send-emails)
        SEND_EMAILS=true
        shift
        ;;
        *)
        shift
        ;;
    esac
done

echo "Running manual extraction from $START_DATE to $END_DATE"

# Make a backup of the current report for comparison
if [ -f "$PROJECT_DIR/temp/zoom_recordings_report.csv" ]; then
    cp "$PROJECT_DIR/temp/zoom_recordings_report.csv" "$PROJECT_DIR/temp/zoom_recordings_report_previous.csv"
fi

# Run the extraction
cd "$PROJECT_DIR" && python scripts/extract_historical_recordings.py --start-date "$START_DATE" --end-date "$END_DATE" --temp-dir "$PROJECT_DIR/temp"

# Send email notifications if requested
if [ "$SEND_EMAILS" = true ] && [ -n "$ZOOM_REPORT_URL" ]; then
    echo "Sending email notifications..."
    python "$PROJECT_DIR/scripts/send_notification_email.py" --report-url "$ZOOM_REPORT_URL" --report-path "$PROJECT_DIR/temp/zoom_recordings_report.csv" --previous-report-path "$PROJECT_DIR/temp/zoom_recordings_report_previous.csv"
fi
