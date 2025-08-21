# Zoom Extraction System - Just Commands
# Run with: just <command-name>

# Git operations
git-status:
    git status

git-add:
    git add .

git-commit message:
    git commit -m "{{message}}"

git-push:
    git push origin main

git-pull:
    git pull origin main

# Daily operations
daily-extraction:
    ./scripts/cron/daily_scheduler.sh

run-personal:
    python scripts/extract_personal_videos.py

run-admin:
    python scripts/extract_admin_videos.py

# Verification and monitoring
verify-sync:
    python scripts/verify_drive_sync.py

check-storage:
    python scripts/check_personal_storage.py

# Cron and scheduling
setup-cron:
    ./scripts/cron/setup_launchd_jobs.sh

start-scheduler:
    nohup ./scripts/cron/daily_scheduler.sh > /dev/null 2>&1 &

stop-scheduler:
    pkill -f daily_scheduler

# Testing
test-auth:
    python scripts/test_zoom_auth.py --account personal

test-admin:
    python scripts/test_zoom_auth.py --account primary

# Cleanup
clean-logs:
    rm -f logs/*.log logs/.run_*

clean-temp:
    rm -rf scripts/temp/*

# Help
default:
    @echo "Available commands:"
    @echo "  git-status, git-add, git-commit <message>, git-push, git-pull"
    @echo "  daily-extraction, run-personal, run-admin"
    @echo "  verify-sync, check-storage"
    @echo "  setup-cron, start-scheduler, stop-scheduler"
    @echo "  test-auth, test-admin"
    @echo "  clean-logs, clean-temp"
    @echo ""
    @echo "Example: just git-commit 'Update extraction logic'"
