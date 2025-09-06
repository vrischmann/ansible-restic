# Justfile for restic ansible role testing and development

# Run the wrapper script manually for scaleway backup
test-scaleway:
    python3 files/restic-backup-wrapper.py scaleway ~/.config/restic-backup ~/.cache/restic restic

# Test the wrapper script with a different backup name
test-backup backup_name config_dir="~/.config/restic-backup" cache_dir="~/.cache/restic":
    python3 files/restic-backup-wrapper.py {{backup_name}} {{config_dir}} {{cache_dir}} restic

# Show what the wrapper script would do without actually running restic
dry-run-scaleway:
    echo "Would run: python3 files/restic-backup-wrapper.py scaleway ~/.config/restic-backup ~/.cache/restic restic"
    echo "Environment file: ~/.config/restic-backup/scaleway.env"
    echo "This would:"
    echo "1. Load environment from ~/.config/restic-backup/scaleway.env"
    echo "2. Execute restic backup with configured settings"
    echo "3. Send email notification if backup fails (and email is configured)"