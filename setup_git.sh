#!/bin/bash

# Script to initialize git repository for Zoom Daily Extraction System

echo "Initializing git repository..."
git init

echo "Adding files to git..."
git add .

echo "Creating initial commit..."
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

echo "Git repository initialized successfully!"
echo ""
echo "Next steps:"
echo "1. Create a GitHub repository"
echo "2. Add remote origin: git remote add origin <your-repo-url>"
echo "3. Push to GitHub: git push -u origin main"
echo ""
echo "Repository structure:"
git log --oneline
echo ""
echo "Files in repository:"
git ls-files