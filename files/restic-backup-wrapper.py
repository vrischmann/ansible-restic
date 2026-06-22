#!/usr/bin/env python3
"""
Restic backup wrapper.

Runs `restic backup` for a named backup definition, streaming restic's output
straight to stdout/stderr (so it lands in the systemd journal) and exiting with
restic's exit code.

Failure notifications are handled by the separate restic-backup-notify service,
triggered via OnFailure= on the backup unit. This wrapper deliberately does no
notification itself.

Usage: restic-backup-wrapper.py <backup_name> <config_dir> <cache_dir> <restic_binary>
"""

import os
import sys
import subprocess
from datetime import datetime


def load_environment_file(env_file):
    """Load KEY=VALUE pairs from an environment file."""
    env_vars = {}
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()
    return env_vars


def run_backup(backup_name, config_dir, cache_dir, restic_binary, env_vars):
    """Execute restic backup, streaming output to stdout/stderr."""
    env = os.environ.copy()
    env.update(env_vars)

    cmd = [
        restic_binary,
        "backup",
        "--json",
        "--exclude-caches",
        "--exclude-file",
        f"{config_dir}/{backup_name}.excludes",
        "--cache-dir",
        cache_dir,
        "--files-from",
        f"{config_dir}/{backup_name}.files",
    ]

    print(f"Starting restic backup {backup_name} at {datetime.now()}")
    print(f"Executing: {' '.join(cmd)}")
    sys.stdout.flush()

    try:
        # Inherit stdout/stderr so restic's output streams directly into the
        # systemd journal. Its exit code becomes our exit code.
        result = subprocess.run(cmd, env=env)
        exit_code = result.returncode
    except Exception as e:
        print(f"Failed to execute backup command: {e}", file=sys.stderr)
        return 1

    print(f"Backup completed with exit code: {exit_code}")
    print(f"Backup finished at {datetime.now()}")
    return exit_code


def main():
    if len(sys.argv) != 5:
        print(
            "Usage: restic-backup-wrapper.py <backup_name> <config_dir> <cache_dir> <restic_binary>"
        )
        sys.exit(2)

    backup_name = sys.argv[1]
    config_dir = sys.argv[2]
    cache_dir = sys.argv[3]
    restic_binary = sys.argv[4]

    env_file = f"{config_dir}/{backup_name}.env"
    try:
        env_vars = load_environment_file(env_file)
    except Exception as e:
        print(f"Error loading environment file {env_file}: {e}", file=sys.stderr)
        sys.exit(1)

    exit_code = run_backup(backup_name, config_dir, cache_dir, restic_binary, env_vars)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
