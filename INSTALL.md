# Installation Guide

## Quick Start

1. **Run the setup script:**
   ```bash
   python3 setup.py
   ```

2. **Initialize git repository:**
   ```bash
   ./setup_git.sh
   ```

3. **Configure credentials in `.env` file**

4. **Test the system:**
   ```bash
   python3 scripts/simple_daily_extraction.py
   ```

## Manual Installation

### 1. Prerequisites

- Python 3.8+
- pip or conda
- Google Cloud Console account
- Zoom Pro account with API access

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
# Zoom API Credentials
ZOOM_CLIENT_ID=your_zoom_client_id
ZOOM_CLIENT_SECRET=your_zoom_client_secret
ZOOM_ACCOUNT_ID=your_zoom_account_id

# Google Drive API
GOOGLE_CREDENTIALS_FILE=path/to/service-account.json
GOOGLE_DRIVE_ROOT_FOLDER=your_folder_id
GOOGLE_SHARED_DRIVE_ID=your_shared_drive_id
```

### 4. Set Up Google Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable APIs:
   - Google Drive API
   - Google Sheets API
4. Create service account:
   - Go to IAM & Admin > Service Accounts
   - Create service account
   - Download JSON key file
5. Share your Google Drive folder with the service account email

### 5. Set Up Zoom API

1. Go to [Zoom Marketplace](https://marketplace.zoom.us/)
2. Create "Server-to-Server OAuth" app
3. Get Client ID, Client Secret, Account ID
4. Add scopes:
   - `recording:read:admin`
   - `user:read:admin`
   - `meeting:read:admin`

### 6. Test Installation

```bash
python3 scripts/simple_daily_extraction.py
```

### 7. Set Up Cron Job

```bash
crontab -e
```

Add line:
```bash
0 3 * * * source /full/path/to/.env && python3 /full/path/to/scripts/simple_daily_extraction.py > /full/path/to/logs/cron.log 2>&1
```

## Troubleshooting

### Permission Errors
- Ensure service account has "Content Manager" permissions
- Check if APIs are enabled in Google Cloud Console

### Zoom API Errors
- Verify API scopes in Zoom app configuration
- Check if accounts have recording permissions

### Missing Files
- Zoom recordings may take 24-48 hours to be available
- Check if Smart Recording is enabled for chapters/highlights

## Directory Structure

```
zoom-extraction-system/
├── app/
│   └── services/          # Core service modules
├── scripts/
│   └── simple_daily_extraction.py  # Main extraction script
├── config.py              # Configuration settings
├── .env                   # Environment variables
├── requirements.txt       # Python dependencies
└── logs/                  # Log files
```

## Support

Check the main README.md for detailed documentation and troubleshooting guides.