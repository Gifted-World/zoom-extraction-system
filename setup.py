#!/usr/bin/env python3
"""
Setup script for Zoom Daily Extraction System
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")

def install_dependencies():
    """Install required Python packages"""
    print("📦 Installing dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True)
        print("✅ Dependencies installed successfully")
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        sys.exit(1)

def create_env_file():
    """Create .env file from template if it doesn't exist"""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if not env_file.exists():
        if env_example.exists():
            print("📝 Creating .env file from template...")
            with open(env_example, 'r') as src, open(env_file, 'w') as dst:
                dst.write(src.read())
            print("✅ .env file created - please configure your credentials")
        else:
            print("❌ .env.example file not found")
            return False
    else:
        print("✅ .env file already exists")
    
    return True

def create_logs_directory():
    """Create logs directory if it doesn't exist"""
    logs_dir = Path("logs")
    if not logs_dir.exists():
        logs_dir.mkdir()
        print("✅ Created logs directory")
    else:
        print("✅ Logs directory already exists")

def check_google_credentials():
    """Check if Google credentials file exists"""
    print("🔍 Checking Google credentials...")
    
    # Check if .env file has the credentials path
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith("GOOGLE_CREDENTIALS_FILE="):
                    creds_path = line.split("=", 1)[1].strip()
                    if creds_path and creds_path != "path/to/service-account.json":
                        if Path(creds_path).exists():
                            print("✅ Google credentials file found")
                            return True
                        else:
                            print(f"❌ Google credentials file not found at: {creds_path}")
                            return False
    
    print("⚠️  Google credentials not configured in .env file")
    return False

def print_next_steps():
    """Print setup completion message and next steps"""
    print("\n" + "="*60)
    print("🎉 Setup completed successfully!")
    print("="*60)
    print("\n📋 Next steps:")
    print("1. Configure your .env file with:")
    print("   - Zoom API credentials (primary and personal accounts)")
    print("   - Google Drive API credentials")
    print("   - Google Drive folder ID")
    print("   - Google Shared Drive ID")
    print()
    print("2. Set up Google Service Account:")
    print("   - Create service account in Google Cloud Console")
    print("   - Enable Google Drive API and Google Sheets API")
    print("   - Download JSON credentials file")
    print("   - Share your Drive folder with service account email")
    print()
    print("3. Test the system:")
    print("   python3 scripts/simple_daily_extraction.py")
    print()
    print("4. Set up cron job:")
    print("   crontab -e")
    print("   Add: 0 3 * * * source /path/to/.env && python3 /path/to/scripts/simple_daily_extraction.py")
    print()
    print("📚 See README.md for detailed setup instructions")

def main():
    """Main setup function"""
    print("🚀 Setting up Zoom Daily Extraction System...")
    print()
    
    check_python_version()
    install_dependencies()
    create_env_file()
    create_logs_directory()
    check_google_credentials()
    
    print_next_steps()

if __name__ == "__main__":
    main()