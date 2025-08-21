#!/bin/bash

# Setup script for macOS LaunchAgents to run daily Zoom extraction
# This script creates and loads LaunchAgent .plist files for both personal and admin accounts

PROJECT_DIR="/Users/rajeshpanchanathan/Documents/genwise/projects/zoom-extraction-system"
LOG_DIR="$PROJECT_DIR/logs"

echo "Setting up LaunchAgents for daily Zoom extraction..."

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Create Personal Account LaunchAgent
cat > ~/Library/LaunchAgents/com.genwise.personal.zoom.extraction.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.genwise.personal.zoom.extraction</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/scripts/cron/run_personal_daily.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>1</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/personal_launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/personal_launchd_error.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

# Create Admin Account LaunchAgent
cat > ~/Library/LaunchAgents/com.genwise.admin.zoom.extraction.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.genwise.admin.zoom.extraction</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/scripts/cron/run_admin_daily.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>3</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/admin_launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/admin_launchd_error.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

# Load the LaunchAgents
echo "Loading personal extraction LaunchAgent..."
launchctl load ~/Library/LaunchAgents/com.genwise.personal.zoom.extraction.plist

echo "Loading admin extraction LaunchAgent..."
launchctl load ~/Library/LaunchAgents/com.genwise.admin.zoom.extraction.plist

# Verify they're loaded
echo "Verifying LaunchAgents are loaded..."
launchctl list | grep genwise

echo ""
echo "✅ Setup complete!"
echo "📅 Personal extraction will run daily at 1:00 AM IST"
echo "📅 Admin extraction will run daily at 3:00 AM IST"
echo "📝 Logs will be written to: $LOG_DIR/"
echo ""
echo "To check status: launchctl list | grep genwise"
echo "To manually test: ./scripts/cron/run_personal_daily.sh"
echo "To manually test: ./scripts/cron/run_admin_daily.sh"