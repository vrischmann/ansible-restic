# Restic

Deploy [restic](https://restic.net/) backups using systemd services and timers.

This role has two modes:
* `user` which adds user-wide services and timers (for your normal user).
* `server` which adds system-wide services and timers.

# Installation

Install the role from Ansible Galaxy:

```sh
ansible-galaxy install vrischmann.restic
```

Or add it to a `requirements.yml`:

```yaml
- name: vrischmann.restic
```

# Requirements

* You need restic installed and your repositories already initialized.
* Ansible 2.9 or newer (see `meta/main.yml`).
* A systemd-based host. The role targets Fedora and Debian; other systemd distributions may work but are not tested.

# Role Variables

| Name                          | Required | Description
| --------------                | -------- | -----------------------------------
| `restic_binary`               | no       | Full path of the restic binary.
| `restic_backup_mode`          | yes      | Backup mode (either "user" or "server").
| `restic_user_home`            | no       | Home directory of the user (if running in "user" mode).
| `restic_user_name`            | no       | Name of the user (if running in "user" mode).
| `restic_user_group`           | no       | Group of the user (if running in "user" mode).
| `restic_backups`              | yes      | List of backup definitions for restic.
| `restic_conf_directory`       | no       | Configuration directory (if running in "server" mode).

## Backup definition

The `restic_backups` list contains N items defining the backups.

Each backup definition must contain the following information:
* The name of the repository (used for the systemd services: only use alphanumeric characters)
* The environment variables for restic to use the repository
* The calendar spec for the systemd timer.
* The directories to backup

It can also contain a list of directories to exclude.

It can also contain optional hooks, rendered straight into the systemd unit:

* `exec_start_pre`: a command (or path to a script) run before the backup. systemd runs it as `ExecStartPre`, so it completes before restic starts, and a non-zero exit aborts the whole backup. Use this to produce files (for example a database dump) that restic then backs up.
* `exec_stop_post`: a command (or path to a script) run after the backup, regardless of success or failure (systemd `ExecStopPost`). Use this to clean up anything `exec_start_pre` created, so a failed run never leaves a stale artifact behind.

Either field accepts a single command (string) or a list of commands. With a list the role renders one `ExecStartPre=` / `ExecStopPost=` line per item, in order. Use a list when you need several commands on the same hook, for example a cleanup script plus a metric-writer that records the run outcome for monitoring (systemd injects `$SERVICE_RESULT`, `$EXIT_CODE`, and `$EXIT_STATUS` into every `ExecStopPost` command).

These are generic systemd hooks; the role itself knows nothing about databases. See [Backing up databases](#backing-up-databases) below.

### Failure notifications

The role sends email on backup failures via a systemd `OnFailure=` hook. When a backup unit fails for any reason (a failed `exec_start_pre`, or restic itself exiting non-zero), systemd starts a small `restic-backup-notify@<unit>.service` unit that reads the failed backup's `.env` and emails the unit's recent journal output. This covers both the pre-backup phase and the backup itself.

The notify unit is wired up for every backup unconditionally; whether it actually sends is controlled by the backup's environment. To enable email notifications, add the following environment variables to your backup definition's `env` section:

**Note:** When `RESTIC_EMAIL_NOTIFICATIONS_ENABLED` is set to `true`, the configuration will be validated and the notify unit will fail fast if required settings are missing or invalid. No default values are used for SMTP configuration when notifications are enabled.

| Environment Variable | Required | Description | Default |
| -------------------- | -------- | ----------- | ------- |
| `RESTIC_EMAIL_NOTIFICATIONS_ENABLED` | no | Enable email notifications (`true`/`false`) | `false` |
| `RESTIC_EMAIL_TO` | yes (if enabled) | Comma-separated list of recipient email addresses | - |
| `RESTIC_EMAIL_FROM` | yes (if enabled) | Sender email address | - |
| `RESTIC_EMAIL_SMTP_SERVER` | yes (if enabled) | SMTP server hostname | - |
| `RESTIC_EMAIL_SMTP_PORT` | yes (if enabled) | SMTP server port | - |
| `RESTIC_EMAIL_SMTP_USER` | yes (if enabled) | SMTP authentication username | - |
| `RESTIC_EMAIL_SMTP_PASSWORD` | yes (if enabled) | SMTP authentication password | - |
| `RESTIC_EMAIL_SMTP_TLS` | yes (if enabled) | Use TLS for SMTP connection (`true`/`false`) | - |

For example this defines two repositories:

```yaml
restic_backups:
  - name: remote-scaleway
    env:
      AWS_ACCESS_KEY_ID: "{{ restic_scaleway_aws_access_key_id }}"
      AWS_SECRET_ACCESS_KEY: "{{ restic_scaleway_aws_secret_access_key }}"
      RESTIC_REPOSITORY: "s3:s3.fr-par.scw.cloud/foobar/home"
      RESTIC_PASSWORD: "{{ restic_remote_password }}"
    calendar_spec: "*-*-* *:00/15:00"
    backup_directories:
      - /home/vincent
    excludes:
      - /home/vincent/tmp

  - name: remote-linode
    env:
      AWS_ACCESS_KEY_ID: "{{ restic_linode_aws_access_key_id }}"
      AWS_SECRET_ACCESS_KEY: "{{ restic_linode_aws_secret_access_key }}"
      RESTIC_REPOSITORY: "s3:eu-central-1.linodeobjects.com/foobar/barbaz"
      RESTIC_PASSWORD: "{{ restic_remote_password }}"
      # Email notifications for this backup
      RESTIC_EMAIL_NOTIFICATIONS_ENABLED: "true"
      RESTIC_EMAIL_TO: "admin@example.com,backup@example.com"
      RESTIC_EMAIL_FROM: "restic-backup@myserver.example.com"
      RESTIC_EMAIL_SMTP_SERVER: "smtp.gmail.com"
      RESTIC_EMAIL_SMTP_PORT: "587"
      RESTIC_EMAIL_SMTP_USER: "backup@example.com"
      RESTIC_EMAIL_SMTP_PASSWORD: "{{ vault_smtp_password }}"
      RESTIC_EMAIL_SMTP_TLS: "true"
    calendar_spec: "*-*-* *:00/15:00"
    backup_directories:
      - /data/media
    excludes:
      - /data/media/Movies
```

# Common patterns

## Backing up databases

Databases aren't files on disk, so the role can't point restic at them directly. The pattern is: dump the database to disk in `exec_start_pre`, back up the dump directory like any other path, then clean it up in `exec_stop_post`. Because both hooks live in the same systemd unit, the dump and the backup always run together, fail together, and notify together. The role owns none of this; your playbook writes the dump script and references it.

### PostgreSQL example

A backup definition that includes the dump directory and runs the dump before each run:

```yaml
restic_backups:
  - name: server-data
    env:
      RESTIC_REPOSITORY: "s3:.../server-data"
      RESTIC_PASSWORD: "{{ restic_remote_password }}"
    calendar_spec: "*-*-* 03:00:00"
    backup_directories:
      - /etc
      - /var/backups/restic-pg/server-data   # written by the dump script
    exec_start_pre: /usr/local/bin/pg-dump-server-data.sh
    exec_stop_post: /usr/local/bin/pg-dump-cleanup.sh
```

Drop the dump script in place with your playbook:

```sh
#!/bin/sh
# /usr/local/bin/pg-dump-server-data.sh
set -eu

DUMP_DIR=/var/backups/restic-pg/server-data
mkdir -p "$DUMP_DIR"

# Globals (roles, tablespaces) once.
runuser -u postgres -- pg_dumpall --globals-only \
  --file="$DUMP_DIR/globals.sql"

# Each database in directory format (good dedup, parallel-friendly).
for db in appdb metrics; do
  runuser -u postgres -- pg_dump --format=directory --file="$DUMP_DIR/$db" "$db"
done
```

```sh
#!/bin/sh
# /usr/local/bin/pg-dump-cleanup.sh
rm -rf /var/backups/restic-pg/server-data
```

# License

MIT
