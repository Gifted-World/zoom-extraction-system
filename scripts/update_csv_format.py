#!/usr/bin/env python
"""
Script to update the CSV format by adding a Date column and ensuring URLs don't spill over.
"""

import os
import sys
import pandas as pd
from datetime import datetime
import argparse
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def format_date(date_str):
    """Format a date string from ISO format to dd mmm yyyy."""
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d %b %Y")
    except Exception:
        return date_str

def update_csv_format(csv_path):
    """Update the CSV format by adding a Date column and ensuring URLs don't spill over."""
    try:
        # Read the CSV file
        df = pd.read_csv(csv_path)
        logger.info(f"Read CSV file with {len(df)} rows")
        
        # Remove unwanted columns
        if "Meeting Password" in df.columns:
            df = df.drop(columns=["Meeting Password"])
            logger.info("Removed Meeting Password column")
        
        if "Drive Video URL" in df.columns:
            df = df.drop(columns=["Drive Video URL"])
            logger.info("Removed Drive Video URL column")
        
        # Add Date column if it doesn't exist
        if "Date" not in df.columns and "Start Time" in df.columns:
            df["Date"] = df["Start Time"].apply(format_date)
            logger.info("Added Date column")
            
            # Reorder columns to put Date after Host Email
            cols = list(df.columns)
            date_index = cols.index("Date")
            cols.pop(date_index)
            
            # Find the position after Host Email
            if "Host Email" in cols:
                host_email_index = cols.index("Host Email")
                cols.insert(host_email_index + 1, "Date")
            else:
                cols.insert(0, "Date")
            
            df = df[cols]
            logger.info("Reordered columns to put Date in the right position")
        
        # Save the updated CSV with proper URL formatting
        with pd.option_context('display.max_colwidth', None):
            df.to_csv(csv_path, index=False)
        logger.info(f"Saved updated CSV to {csv_path}")
        
        return True
    except Exception as e:
        logger.error(f"Error updating CSV format: {e}")
        return False

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Update CSV format")
    parser.add_argument("--csv-path", type=str, required=True, help="Path to the CSV file")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.csv_path):
        logger.error(f"CSV file not found: {args.csv_path}")
        return 1
    
    success = update_csv_format(args.csv_path)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
