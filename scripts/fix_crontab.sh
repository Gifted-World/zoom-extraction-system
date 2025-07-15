#!/bin/bash
# Script to fix the crontab

# Create a temporary crontab file
TEMP_CRONTAB=$(mktemp)

# Export the current crontab
crontab -l > "$TEMP_CRONTAB"

# Replace 'python' with the full path to python
sed -i '' 's|python scripts|/Users/rajeshpanchanathan/miniforge3/bin/python scripts|g' "$TEMP_CRONTAB"

# Install the new crontab
crontab "$TEMP_CRONTAB"
rm "$TEMP_CRONTAB"

echo "Crontab has been updated with the full path to python." 