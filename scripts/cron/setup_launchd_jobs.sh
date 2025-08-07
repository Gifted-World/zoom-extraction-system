#!/bin/bash

# Setup Launch Agent for personal and admin account downloads
# This is a more reliable way to schedule jobs on macOS than cron

PROJECT_DIR="/Users/rajeshpanchanathan/Documents/genwise/projects/zoom-extraction-system"
CONDA_BASE="/Users/rajeshpanchanathan/miniforge3"
ENV_FILE="$PROJECT_DIR/.env"
LOG_DIR="$PROJECT_DIR/logs"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"

# Create launch agents directory if it doesn't exist
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

# Personal account extraction launch agent
PERSONAL_PLIST="$LAUNCH_AGENTS_DIR/com.genwise.personal.zoom.extraction.plist"
cat > "$PERSONAL_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.genwise.personal.zoom.extraction</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>/bin/bash -c \"cd $PROJECT_DIR && source $ENV_FILE && source $CONDA_BASE/etc/profile.d/conda.sh && conda activate base && python $PROJECT_DIR/scripts/extract_personal_videos.py --start-date \\$(date -v-1d +%Y-%m-%d) --end-date \\$(date +%Y-%m-%d) > $LOG_DIR/personal_daily_download_\\$(date +%Y%m%d).log 2>&1\"</string>
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
</dict>
</plist>
EOF

# Admin account extraction launch agent
ADMIN_PLIST="$LAUNCH_AGENTS_DIR/com.genwise.admin.zoom.extraction.plist"
cat > "$ADMIN_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.genwise.admin.zoom.extraction</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>/bin/bash -c \"cd $PROJECT_DIR && source $ENV_FILE && source $CONDA_BASE/etc/profile.d/conda.sh && conda activate base && python $PROJECT_DIR/scripts/extract_admin_videos.py --start-date \\$(date -v-1d +%Y-%m-%d) --end-date \\$(date +%Y-%m-%d) > $LOG_DIR/admin_daily_download_\\$(date +%Y%m%d).log 2>&1\"</string>
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
</dict>
</plist>
EOF

# Load the launch agents
launchctl load "$PERSONAL_PLIST"
launchctl load "$ADMIN_PLIST"

echo "Launch agents installed successfully."
echo "Personal extraction will run at 1:00 AM daily."
echo "Admin extraction will run at 3:00 AM daily."
echo ""
echo "To check their status, run:"
echo "launchctl list | grep genwise"
echo ""
echo "To run them immediately for testing:"
echo "launchctl start com.genwise.personal.zoom.extraction"
echo "launchctl start com.genwise.admin.zoom.extraction"