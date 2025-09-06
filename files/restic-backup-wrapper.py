#!/usr/bin/env python3
"""
Restic backup wrapper with optional email notifications
Handles backup execution and failure notifications based on environment variables
"""

import os
import sys
import subprocess
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


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
    """Send email using Python's smtplib"""

    # Create message
    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")

    # Attach body
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        # Create SMTP connection
        if use_tls and smtp_port == 465:
            # SSL/TLS connection
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)
        else:
            # Start with plain connection, upgrade to TLS if requested
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
    """Load environment variables from file"""
    env_vars = {}
    try:
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    except Exception as e:
        print(f"Error loading environment file {env_file}: {e}", file=sys.stderr)
        sys.exit(1)
    return env_vars


def get_email_config(env_vars):
    """Get email configuration from environment variables loaded from .env file"""
    # Check if email notifications are enabled
    if env_vars.get("RESTIC_EMAIL_NOTIFICATIONS_ENABLED", "").lower() != "true":
        return None

    # Validate required configuration when email notifications are enabled
    errors = []

    # Check RESTIC_EMAIL_TO
    to_emails = env_vars.get("RESTIC_EMAIL_TO", "").strip()
    if not to_emails:
        errors.append(
            "RESTIC_EMAIL_TO is required when RESTIC_EMAIL_NOTIFICATIONS_ENABLED is true"
        )
    else:
        # Validate email addresses
        email_list = [email.strip() for email in to_emails.split(",")]
        for email in email_list:
            if not email or "@" not in email or "." not in email:
                errors.append(f"Invalid email address in RESTIC_EMAIL_TO: {email}")

    # Check RESTIC_EMAIL_FROM
    from_email = env_vars.get("RESTIC_EMAIL_FROM", "").strip()
    if not from_email:
        errors.append(
            "RESTIC_EMAIL_FROM is required when RESTIC_EMAIL_NOTIFICATIONS_ENABLED is true"
        )
    elif "@" not in from_email or "." not in from_email:
        errors.append(f"Invalid email address in RESTIC_EMAIL_FROM: {from_email}")

    # Check RESTIC_EMAIL_SMTP_SERVER
    smtp_server = env_vars.get("RESTIC_EMAIL_SMTP_SERVER", "").strip()
    if not smtp_server:
        errors.append(
            "RESTIC_EMAIL_SMTP_SERVER is required when RESTIC_EMAIL_NOTIFICATIONS_ENABLED is true"
        )

    # Check RESTIC_EMAIL_SMTP_PORT
    smtp_port_str = env_vars.get("RESTIC_EMAIL_SMTP_PORT", "").strip()
    if not smtp_port_str:
        errors.append(
            "RESTIC_EMAIL_SMTP_PORT is required when RESTIC_EMAIL_NOTIFICATIONS_ENABLED is true"
        )
    else:
        try:
            smtp_port = int(smtp_port_str)
            if smtp_port < 1 or smtp_port > 65535:
                errors.append(
                    f"Invalid SMTP port in RESTIC_EMAIL_SMTP_PORT: {smtp_port}"
                )
        except ValueError:
            errors.append(
                f"Invalid SMTP port in RESTIC_EMAIL_SMTP_PORT: {smtp_port_str}"
            )

    # Check RESTIC_EMAIL_SMTP_USER
    smtp_user = env_vars.get("RESTIC_EMAIL_SMTP_USER", "").strip()
    if not smtp_user:
        errors.append(
            "RESTIC_EMAIL_SMTP_USER is required when RESTIC_EMAIL_NOTIFICATIONS_ENABLED is true"
        )

    # Check RESTIC_EMAIL_SMTP_PASSWORD
    smtp_password = env_vars.get("RESTIC_EMAIL_SMTP_PASSWORD", "").strip()
    if not smtp_password:
        errors.append(
            "RESTIC_EMAIL_SMTP_PASSWORD is required when RESTIC_EMAIL_NOTIFICATIONS_ENABLED is true"
        )

    # Check RESTIC_EMAIL_SMTP_TLS
    smtp_tls = env_vars.get("RESTIC_EMAIL_SMTP_TLS", "").strip()
    if not smtp_tls:
        errors.append(
            "RESTIC_EMAIL_SMTP_TLS is required when RESTIC_EMAIL_NOTIFICATIONS_ENABLED is true"
        )
    elif smtp_tls.lower() not in ["true", "false"]:
        errors.append(
            f"RESTIC_EMAIL_SMTP_TLS must be 'true' or 'false', got: {smtp_tls}"
        )

    # Fail fast if there are any validation errors
    if errors:
        error_msg = "Email notification configuration errors:\n" + "\n".join(
            f"  - {error}" for error in errors
        )
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    # Build configuration with validated values (no defaults when enabled)
    return {
        "to_emails": [email.strip() for email in to_emails.split(",")],
        "from_email": from_email,
        "smtp_server": smtp_server,
        "smtp_port": int(smtp_port_str),
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "use_tls": smtp_tls.lower() == "true",
    }


def run_backup(backup_name, config_dir, cache_dir, restic_binary, env_vars):
    """Execute restic backup and capture output"""

    # Set up environment
    env = os.environ.copy()
    env.update(env_vars)

    # Build command
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

    # Execute backup
    print(f"Starting restic backup {backup_name} at {datetime.now()}")
    print(f"Executing: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        # Combine stdout and stderr for logging
        output = result.stdout + result.stderr
        exit_code = result.returncode

        print(f"Backup completed with exit code: {exit_code}")
        print(f"Backup finished at {datetime.now()}")

        return exit_code, output

    except Exception as e:
        error_msg = f"Failed to execute backup command: {e}"
        print(error_msg)
        return 1, error_msg


def send_notification(backup_name, exit_code, output, email_config, env_vars):
    """Send email notification if backup failed"""
    if exit_code == 0 or not email_config:
        return

    hostname = os.uname().nodename
    subject = f"FAILED: Backup '{backup_name}' on {hostname}"

    body = f"""Restic backup failed on {hostname}

Backup Name: {backup_name}
Exit Code: {exit_code}
Hostname: {hostname}
Date: {datetime.now()}
Repository: {env_vars.get("RESTIC_REPOSITORY", "Unknown")}

Backup Log:
{output}

Please check the system logs for more details:
journalctl -u restic-backup-{backup_name}.service"""

    # Send email
    email_sent = send_email(
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

    if not email_sent:
        print("ERROR: Failed to send email notification", file=sys.stderr)


def main():
    if len(sys.argv) != 5:
        print(
            "Usage: restic-backup-wrapper.py <backup_name> <config_dir> <cache_dir> <restic_binary>"
        )
        sys.exit(1)

    backup_name = sys.argv[1]
    config_dir = sys.argv[2]
    cache_dir = sys.argv[3]
    restic_binary = sys.argv[4]

    # Load environment variables
    env_file = f"{config_dir}/{backup_name}.env"
    env_vars = load_environment_file(env_file)

    # Get email configuration from environment variables
    email_config = get_email_config(env_vars)

    # Run backup
    exit_code, output = run_backup(
        backup_name, config_dir, cache_dir, restic_binary, env_vars
    )

    # Send notification if backup failed
    send_notification(backup_name, exit_code, output, email_config, env_vars)

    # Exit with the backup exit code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
