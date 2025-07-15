#!/bin/bash
# Script to update the Zoom report ID in the environment variables

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found."
    exit 1
fi

# New report ID
NEW_REPORT_ID="1efsf_Y9eJ-rV5sEi9Fo9ng3R2PQPEueacuXlMg0CbAQ"

# Update or add ZOOM_REPORT_ID in .env file
if grep -q "ZOOM_REPORT_ID" .env; then
    # Update existing ZOOM_REPORT_ID
    sed -i '' "s|ZOOM_REPORT_ID=.*|ZOOM_REPORT_ID=\"$NEW_REPORT_ID\"|" .env
else
    # Add new ZOOM_REPORT_ID after ZOOM_REPORT_URL
    sed -i '' '/ZOOM_REPORT_URL/a\
ZOOM_REPORT_ID=\"'$NEW_REPORT_ID'\"
' .env
fi

echo "Updated ZOOM_REPORT_ID in .env file to: $NEW_REPORT_ID"
echo "This ID will be used for all future report updates." 