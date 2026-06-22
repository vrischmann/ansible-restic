#!/usr/bin/env python3
"""
Restic backup failure notifier.

Triggered by systemd via OnFailure= from a restic-backup-<name>.service unit.
Reads SMTP configuration from the failed backup's environment file and emails
the failed unit's recent journal output, so a single notification covers both
the pre-backup phase (e.g. a database dump run via ExecStartPre) and the
backup itself (ExecStart).

When RESTIC_EMAIL_NOTIFICATIONS_ENABLED is not "true" for the failed backup,
this script exits 0 without sending anything, so the OnFailure wiring can be
attached unconditionally to every backup unit.

Usage: restic-backup-notify.py <failed_unit_name> <config_dir> <mode>
  failed_unit_name : full unit name, e.g. restic-backup-server-data.service
  config_dir       : directory holding the backup's <name>.env file
  mode             : "server" or "user" (selects the journalctl namespace)
"""

import os
import smtplib
import ssl
import subprocess
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email(
    subject,
    body,
    to_emails,
    from_email,
    smtp_server,
    smtp_port,
    smtp_user=None,
    smtp_password=None,
    use_tls=True,
):
    """Send an email using smtplib. Returns True on success."""
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if use_tls and smtp_port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                if use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}", file=sys.stderr)
        return False


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


def get_email_config(env_vars):
    """Return an email config dict, or None if notifications are disabled.

    Fails fast (exits 1) when notifications are enabled but misconfigured, so
    a missing SMTP setting surfaces as a failed notify unit rather than a
    silent no-op.
    """
    if env_vars.get("RESTIC_EMAIL_NOTIFICATIONS_ENABLED", "").lower() != "true":
        return None

    errors = []

    def check(name):
        value = env_vars.get(name, "").strip()
        if not value:
            errors.append(
                f"{name} is required when RESTIC_EMAIL_NOTIFICATIONS_ENABLED is true"
            )
        return value

    to_emails = check("RESTIC_EMAIL_TO")
    from_email = check("RESTIC_EMAIL_FROM")
    smtp_server = check("RESTIC_EMAIL_SMTP_SERVER")
    smtp_port = check("RESTIC_EMAIL_SMTP_PORT")
    smtp_user = check("RESTIC_EMAIL_SMTP_USER")
    smtp_password = check("RESTIC_EMAIL_SMTP_PASSWORD")
    smtp_tls = check("RESTIC_EMAIL_SMTP_TLS")

    if errors:
        error_msg = "Email notification configuration errors:\n" + "\n".join(
            f"  - {error}" for error in errors
        )
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    return {
        "to_emails": [email.strip() for email in to_emails.split(",")],
        "from_email": from_email,
        "smtp_server": smtp_server,
        "smtp_port": int(smtp_port),
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "use_tls": smtp_tls.lower() == "true",
    }


def backup_name_from_unit(unit_name):
    """restic-backup-server-data.service -> server-data"""
    name = unit_name
    for suffix in (".service", ".timer"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    prefix = "restic-backup-"
    if name.startswith(prefix):
        name = name[len(prefix) :]
    return name


def get_failed_journal(unit_name, mode):
    """Return the recent journal output for the failed unit."""
    cmd = ["journalctl"]
    if mode == "user":
        cmd.append("--user")
    cmd += ["-u", unit_name, "-n", "300", "--no-pager", "-o", "short-iso"]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        return f"(failed to read journal: {e})\n"


def main():
    if len(sys.argv) != 4:
        print("Usage: restic-backup-notify.py <failed_unit_name> <config_dir> <mode>")
        sys.exit(1)

    failed_unit_name = sys.argv[1]
    config_dir = sys.argv[2]
    mode = sys.argv[3]

    backup_name = backup_name_from_unit(failed_unit_name)

    env_file = f"{config_dir}/{backup_name}.env"
    try:
        env_vars = load_environment_file(env_file)
    except FileNotFoundError:
        print(f"Environment file not found: {env_file}", file=sys.stderr)
        # No config to act on; nothing to do.
        sys.exit(0)
    except Exception as e:
        print(f"Error loading environment file {env_file}: {e}", file=sys.stderr)
        sys.exit(0)

    email_config = get_email_config(env_vars)
    if email_config is None:
        print(f"Email notifications disabled for backup '{backup_name}'; not sending.")
        sys.exit(0)

    journal = get_failed_journal(failed_unit_name, mode)

    hostname = os.uname().nodename
    subject = f"FAILED: Backup '{backup_name}' on {hostname}"
    body = f"""Restic backup failed on {hostname}

Backup Name: {backup_name}
Failed Unit: {failed_unit_name}
Hostname: {hostname}
Date: {datetime.now()}
Repository: {env_vars.get("RESTIC_REPOSITORY", "Unknown")}

Recent journal for {failed_unit_name}:
{journal}

See the full journal with: journalctl -u {failed_unit_name}
"""

    send_email(
        subject=subject,
        body=body,
        to_emails=email_config["to_emails"],
        from_email=email_config["from_email"],
        smtp_server=email_config["smtp_server"],
        smtp_port=email_config["smtp_port"],
        smtp_user=email_config["smtp_user"],
        smtp_password=email_config["smtp_password"],
        use_tls=email_config["use_tls"],
    )

    # Always exit 0: the backup already failed, and a second failed unit would
    # only confuse the picture. Email-send failures are logged to stderr above.
    sys.exit(0)


if __name__ == "__main__":
    main()
