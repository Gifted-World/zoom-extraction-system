# macOS Scheduled Jobs for Zoom Extraction

This document explains how to run the Zoom extraction jobs on macOS, both manually and automatically.

## Setup Overview

The system uses macOS LaunchAgents instead of traditional cron jobs because:

1. LaunchAgents are more reliable on macOS than cron jobs
2. LaunchAgents will run even if the system was asleep at the scheduled time
3. They provide better error handling and logging

## Scheduled Jobs

Two LaunchAgents have been configured:

1. **Personal Account Extraction** (`com.genwise.personal.zoom.extraction`)
   - Runs daily at 1:00 AM IST
   - Downloads recordings from personal Zoom account
   - Logs to `logs/personal_daily_download_YYYYMMDD.log`

2. **Admin Account Extraction** (`com.genwise.admin.zoom.extraction`) 
   - Runs daily at 3:00 AM IST
   - Downloads recordings from admin Zoom account
   - Logs to `logs/admin_daily_download_YYYYMMDD.log`

## Manual Run Scripts

For testing or on-demand runs, you can use:

1. `scripts/run_personal_manual.sh` - Runs personal account extraction
2. `scripts/run_admin_manual.sh` - Runs admin account extraction

These scripts create detailed log files in the `logs/` directory.

## Checking Status

To check the status of scheduled jobs:

```bash
launchctl list | grep genwise
```

## Modifying Schedule

To change the schedule:

1. Edit `scripts/setup_launchd_jobs.sh`
2. Update the `Hour` and `Minute` values 
3. Run `./scripts/setup_launchd_jobs.sh` to reinstall the jobs

## Troubleshooting

If jobs aren't running:

1. Check if they're properly loaded: `launchctl list | grep genwise`
2. Verify permissions: `.env` file must be readable
3. Check log files in `logs/` directory 
4. Try running the manual scripts to diagnose issues

You can also remove and reinstall the jobs:

```bash
launchctl unload ~/Library/LaunchAgents/com.genwise.personal.zoom.extraction.plist
launchctl unload ~/Library/LaunchAgents/com.genwise.admin.zoom.extraction.plist
./scripts/setup_launchd_jobs.sh
```
