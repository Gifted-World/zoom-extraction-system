#!/bin/bash

# Script to manually run personal account extraction
# Uses proper paths with direct executable command, not launchd

PROJECT_DIR="/Users/rajeshpanchanathan/Documents/genwise/projects/zoom-extraction-system"
CONDA_BASE="/Users/rajeshpanchanathan/miniforge3"
LOG_DIR="$PROJECT_DIR/logs"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Set timestamp for log file
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Run the personal account extraction
cd "$PROJECT_DIR" && \
  source "$PROJECT_DIR/.env" && \
  source "$CONDA_BASE/etc/profile.d/conda.sh" && \
  conda activate base && \
  python "$PROJECT_DIR/scripts/extract_personal_videos.py" --limit 1 > "$LOG_DIR/personal_manual_$TIMESTAMP.log" 2>&1

# Check if the script ran successfully
if [ $? -eq 0 ]; then
  echo "Personal account extraction completed successfully."
  echo "Log file: $LOG_DIR/personal_manual_$TIMESTAMP.log"
else
  echo "Personal account extraction failed."
  echo "Check log file: $LOG_DIR/personal_manual_$TIMESTAMP.log"
fi
