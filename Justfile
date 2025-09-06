# Justfile for restic ansible role testing and development

# Test the wrapper script with a specific backup
# Usage: just test-backup <backup_name> [config_dir] [cache_dir]
test-backup backup_name config_dir="~/.config/restic-backup" cache_dir="~/.cache/restic":
    python3 files/restic-backup-wrapper.py {{backup_name}} {{config_dir}} {{cache_dir}} restic

# Dry run - show what the wrapper script would do without executing
# Usage: just dry-run-backup <backup_name> [config_dir] [cache_dir]
dry-run-backup backup_name config_dir="~/.config/restic-backup" cache_dir="~/.cache/restic":
    echo "Would run: python3 files/restic-backup-wrapper.py {{backup_name}} {{config_dir}} {{cache_dir}} restic"
    echo "Environment file: {{config_dir}}/{{backup_name}}.env"
    echo "This would:"
    echo "1. Load environment from {{config_dir}}/{{backup_name}}.env"
    echo "2. Execute restic backup with configured settings"
    echo "3. Send email notification if backup fails (and email is configured)"