#!/usr/bin/env python3
"""
Script to rotate logs, keeping only the most recent logs.
This script deletes old daily processing logs, keeping only the specified number of days.
"""

import os
import sys
import glob
import argparse
from datetime import datetime, timedelta

# Add the parent directory to the path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

def rotate_logs(days_to_keep=30, log_dir=None):
    """
    Delete log files older than the specified number of days.
    
    Args:
        days_to_keep: Number of days of logs to keep
        log_dir: Directory containing the logs (default: project_root/logs)
    """
    if log_dir is None:
        log_dir = os.path.join(parent_dir, "logs")
    
    if not os.path.exists(log_dir):
        print(f"Log directory not found: {log_dir}")
        return
    
    # Get all daily processing log files
    log_pattern = os.path.join(log_dir, "daily_processing_*.log")
    log_files = glob.glob(log_pattern)
    
    if not log_files:
        print("No log files found.")
        return
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    # Track deleted and kept files
    deleted_files = 0
    kept_files = 0
    
    for log_file in log_files:
        # Extract date from filename
        try:
            filename = os.path.basename(log_file)
            date_str = filename.replace("daily_processing_", "").replace(".log", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            
            # Delete if older than cutoff
            if file_date < cutoff_date:
                os.remove(log_file)
                deleted_files += 1
            else:
                kept_files += 1
                
        except (ValueError, Exception) as e:
            print(f"Error processing {log_file}: {e}")
    
    print(f"Log rotation complete: {deleted_files} files deleted, {kept_files} files kept.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rotate log files, keeping only recent ones")
    parser.add_argument("--days", type=int, default=30, help="Number of days of logs to keep")
    parser.add_argument("--log-dir", type=str, help="Directory containing logs (default: project_root/logs)")
    
    args = parser.parse_args()
    rotate_logs(args.days, args.log_dir) 