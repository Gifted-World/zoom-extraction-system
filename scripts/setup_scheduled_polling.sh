#!/bin/bash
# Script to set up scheduled polling for Zoom recordings at 8pm IST every day
# This replaces the need for webhooks by periodically checking for new recordings

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "Project directory: $PROJECT_DIR"

# Create temp directory if it doesn't exist
mkdir -p "$PROJECT_DIR/temp"

# Create a temporary crontab file
TEMP_CRONTAB=$(mktemp)

# Export the current crontab
crontab -l > "$TEMP_CRONTAB" 2>/dev/null || echo "# Creating new crontab" > "$TEMP_CRONTAB"

# Check if the cron job already exists
if grep -q "extract_historical_recordings.py" "$TEMP_CRONTAB"; then
    echo "Cron job for Zoom recording extraction already exists. Updating..."
    # Remove the existing cron job
    sed -i '' '/extract_historical_recordings.py/d' "$TEMP_CRONTAB"
fi

# Add the new cron job to run at 8pm IST every day
# This will extract recordings from the past 24 hours
# After extraction, it will send email notifications
echo "# Zoom recording extraction - runs at 8pm IST every day" >> "$TEMP_CRONTAB"
echo "0 20 * * * cd $PROJECT_DIR && python scripts/extract_historical_recordings.py --start-date \$(date -v-1d +\%Y-\%m-\%d) --end-date \$(date +\%Y-\%m-\%d) --temp-dir $PROJECT_DIR/temp >> $PROJECT_DIR/logs/scheduled_extraction_\$(date +\%Y\%m\%d).log 2>&1 && python scripts/update_csv_format.py --csv-path $PROJECT_DIR/temp/zoom_recordings_report.csv >> $PROJECT_DIR/logs/scheduled_extraction_\$(date +\%Y\%m\%d).log 2>&1 && python scripts/send_notification_email.py --report-url \"\$ZOOM_REPORT_URL\" --report-path $PROJECT_DIR/temp/zoom_recordings_report.csv --previous-report-path $PROJECT_DIR/temp/zoom_recordings_report_previous.csv >> $PROJECT_DIR/logs/email_notification_\$(date +\%Y\%m\%d).log 2>&1 && cp $PROJECT_DIR/temp/zoom_recordings_report.csv $PROJECT_DIR/temp/zoom_recordings_report_previous.csv" >> "$TEMP_CRONTAB"

# Install the new crontab
crontab "$TEMP_CRONTAB"
rm "$TEMP_CRONTAB"

echo "Scheduled polling has been set up to run at 8pm IST every day."
echo "It will check for recordings created in the past 24 hours."
echo "Email notifications will be sent to hosts when new recordings are processed."
echo "Logs will be saved in the logs directory."

# Create a script to manually run the extraction
cat > "$PROJECT_DIR/scripts/run_manual_extraction.sh" << 'EOF'
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
EOF

# Make the manual script executable
chmod +x "$PROJECT_DIR/scripts/run_manual_extraction.sh"

echo ""
echo "A script for manual extraction has been created at:"
echo "$PROJECT_DIR/scripts/run_manual_extraction.sh"
echo ""
echo "You can run it with custom dates like this:"
echo "./scripts/run_manual_extraction.sh --start-date 2023-01-01 --end-date 2023-01-31"
echo ""
echo "To send email notifications after manual extraction, add the --send-emails flag:"
echo "./scripts/run_manual_extraction.sh --start-date 2023-01-01 --end-date 2023-01-31 --send-emails"
echo ""
echo "IMPORTANT: Set the ZOOM_REPORT_URL environment variable with the Google Sheet URL:"
echo "export ZOOM_REPORT_URL=\"https://docs.google.com/spreadsheets/d/your-sheet-id/edit\""
