# Setup Commands for Zoom Daily Extraction System

## 1. Navigate to the repository
```bash
cd /Users/rajeshpanchanathan/Documents/genwise/projects/zoom-extraction-system
```

## 2. Initialize git repository
```bash
git init
git add .
git commit -m "Initial commit: Zoom Daily Extraction System

- Multi-account Zoom recording extraction
- Google Drive file organization  
- Google Sheets reporting with real-time updates
- Automated cron job scheduling
- Smart Recording support (chapters/highlights)
- Duplicate file cleanup and management
- Comprehensive logging and error handling

🤖 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## 3. Create GitHub repository
1. Go to GitHub.com
2. Create new repository: `zoom-extraction-system`
3. Don't initialize with README (we already have one)

## 4. Push to GitHub
```bash
git remote add origin https://github.com/YOUR_USERNAME/zoom-extraction-system.git
git branch -M main
git push -u origin main
```

## 5. Set up the system
```bash
# Install dependencies
python3 setup.py

# Configure .env file with your credentials
nano .env

# Test the system
python3 scripts/simple_daily_extraction.py
```

## 6. Set up cron job
```bash
crontab -e
# Add this line:
0 3 * * * source /Users/rajeshpanchanathan/Documents/genwise/projects/zoom-extraction-system/.env && python3 /Users/rajeshpanchanathan/Documents/genwise/projects/zoom-extraction-system/scripts/simple_daily_extraction.py > /Users/rajeshpanchanathan/Documents/genwise/projects/zoom-extraction-system/logs/cron_daily_extraction.log 2>&1
```

## Repository Structure
```
zoom-extraction-system/
├── README.md              # Main documentation
├── INSTALL.md             # Installation guide
├── LICENSE                # MIT License
├── .env.example           # Environment template
├── .gitignore            # Git ignore rules
├── setup.py              # Setup script
├── config.py             # Configuration
├── requirements.txt      # Python dependencies
├── app/                  # Core application
│   └── services/         # Service modules
├── scripts/              # Extraction scripts
│   └── simple_daily_extraction.py  # Main script
└── logs/                 # Log files
```

## Key Features
✅ Multi-account Zoom extraction (4 accounts)
✅ Google Drive file organization
✅ Google Sheets real-time reporting
✅ Automated cron job scheduling
✅ Smart Recording support
✅ Duplicate file cleanup
✅ Comprehensive logging
✅ Error handling and recovery