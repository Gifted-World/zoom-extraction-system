# Zoom Transcript Insights Scripts

This directory contains scripts to help with extracting and processing Zoom recordings.

## Prerequisites

Before using these scripts, make sure you have:

1. Set up your environment variables (see `env_template.sh` in the root directory)
2. Installed all required dependencies (`pip install -r ../requirements.txt`)
3. Configured your Zoom API credentials and Google Drive API credentials

### Zoom API Setup

When creating your Zoom OAuth app, make sure to add the following scopes:

- `recording:read:admin` - Required to list recordings
- `recording:write:admin` - Required to manage recordings
- `cloud_recording:read:list_account_recordings:master` - Required for account-level access (optional, as the script now falls back to user-level access)
- `cloud_recording:read:list_user_recordings:admin` - Required for user-level access

### Google Drive Setup

Create a service account and share your Google Drive folder with the service account email.

## Scripts

### 1. Extract Historical Recordings

**File:** `extract_historical_recordings.py`

This script extracts historical recordings from Zoom and saves them to Google Drive. It will:

1. Authenticate with Zoom API
2. Fetch list of past recordings within a date range
3. Download VTT transcripts and chat logs for each recording
4. Create appropriate folder structure in Google Drive
5. Upload transcripts and chat logs to Google Drive
6. Create a metadata file with recording details (including video URLs)
7. Generate a summary report in Google Sheets

**Arguments:**

- `--start-date`: Start date in YYYY-MM-DD format (default: 30 days ago)
- `--end-date`: End date in YYYY-MM-DD format (default: today)
- `--user-email`: Email of specific user to get recordings for (optional)
- `--temp-dir`: Directory for temporary files (default: ./temp)
- `--log-level`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL) (default: INFO)

**Features:**
- Skips already processed recordings (checks for existing metadata)
- Captures meeting metadata including video URLs and chat logs
- Creates a comprehensive summary report in Google Sheets
- Detailed logging with configurable verbosity

### 2. Process Drive Recordings

**File:** `process_drive_recordings.py`

This script processes recordings stored in Google Drive and generates insights using Claude API. It will:

1. Connect to Google Drive
2. Find all course folders
3. Find all session folders with unprocessed transcripts
4. For each transcript, generate insights using Claude API
5. Save insights in the same folder

**Arguments:**

- `--course`: Process only a specific course (optional)
- `--temp-dir`: Directory for temporary files (default: ./temp)
- `--log-level`: Set logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL) (default: INFO)
- `--retry-failed`: Retry previously failed folders (default: false)
- `--backoff-time`: Time to wait before retrying after rate limit in seconds (default: 60)

**Features:**
- Graceful handling of API rate limits and overloaded errors
- Uses chat logs for additional context when available
- Skips already processed folders
- Marks failed folders for later retry
- Detailed logging with configurable verbosity

## Usage Examples

### Extract recordings from the past 30 days:

```bash
python scripts/extract_historical_recordings.py
```

### Extract recordings from a specific date range:

```bash
python scripts/extract_historical_recordings.py --start-date 2025-01-01 --end-date 2025-07-06
```

### Extract recordings from a specific user:

```bash
python scripts/extract_historical_recordings.py --user-email sowmya@genwise.in
```

### Process all recordings in Google Drive:

```bash
python scripts/process_drive_recordings.py
```

### Process recordings for a specific course:

```bash
python scripts/process_drive_recordings.py --course "Critical Thinking Through History"
```

### Retry previously failed processing:

```bash
python scripts/process_drive_recordings.py --retry-failed --backoff-time 120
```

## Logging

All scripts in this directory use a consistent logging system:

- Log files are stored in the `logs/` directory with timestamped filenames
- Each script run creates a new log file (e.g., `zoom_extraction_20230615_120000.log`)
- Logs include both console output and file output
- You can control verbosity with the `--log-level` parameter
- Use `DEBUG` level to see full OAuth scopes and detailed API interactions
- Sensitive information (like tokens) is masked in the logs

## Folder Structure

The scripts create and expect the following folder structure in Google Drive:

```
Root Folder/
├── Course Name 1/
│   ├── Session_1_Introduction_2023-01-01/
│   │   ├── transcript.vtt
│   │   ├── executive_summary.md
│   │   ├── pedagogical_analysis.md
│   │   ├── aha_moments.md
│   │   └── engagement_metrics.json
│   └── Session_2_Advanced_Topics_2023-01-08/
│       └── ...
└── Course Name 2/
    └── ...
```

## Webhook Integration

The webhook integration is implemented in `app/api/webhook.py`. When a new recording is available in Zoom, a notification is sent to the webhook endpoint, which automatically processes the recording and saves the insights to Google Drive.

To set up the webhook:

1. Deploy the application to a server with a public URL
2. In your Zoom App settings, add a webhook endpoint with the URL: `https://your-domain.com/webhook/recording-completed`
3. Subscribe to the `recording.completed` event
4. Get the webhook verification token and add it to your `.env` file as `ZOOM_WEBHOOK_SECRET`

## Troubleshooting

If you encounter issues:

1. Check the log files in the `logs/` directory for detailed error information
2. Verify your API credentials and permissions
3. Make sure your Google Drive service account has access to the root folder
4. Check that your Zoom account has the necessary permissions to access recordings
5. For "Invalid access token" or scope-related errors, verify that your Zoom app has all required scopes
6. If using Server-to-Server OAuth, make sure your Zoom account has the appropriate plan level that supports this feature
7. For Google Drive errors about "missing fields client_email, token_uri", make sure your credentials file is valid and properly formatted
8. Ensure you've shared your Google Drive folder with the service account email address