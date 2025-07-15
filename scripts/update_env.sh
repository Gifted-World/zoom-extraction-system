#!/bin/bash
# Script to update the .env file with shared drive ID

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found."
    exit 1
fi

# Check if GOOGLE_SHARED_DRIVE_ID already exists in .env
if grep -q "GOOGLE_SHARED_DRIVE_ID" .env; then
    echo "GOOGLE_SHARED_DRIVE_ID already exists in .env file."
    echo "You can manually update it by editing the .env file."
    exit 0
fi

# Add GOOGLE_SHARED_DRIVE_ID after GOOGLE_DRIVE_ROOT_FOLDER
sed -i '' '/GOOGLE_DRIVE_ROOT_FOLDER/a\
# Add your shared drive ID here - create a shared drive in Google Drive and get its ID from the URL\
GOOGLE_SHARED_DRIVE_ID=''\
' .env

echo "Added GOOGLE_SHARED_DRIVE_ID to .env file."
echo "Please edit the .env file and add your shared drive ID."
echo "You can create a shared drive in Google Drive and get its ID from the URL." 