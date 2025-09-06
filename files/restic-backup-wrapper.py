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
import threading
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
        "smtp_port": int(smtp_port),
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "use_tls": smtp_tls.lower() == "true",
    }


def stream_output(pipe, stdout_lines, stderr_lines, is_stderr=False):
    """Stream output from pipe to stdout/stderr and capture lines"""
    for line in iter(pipe.readline, ''):
        if is_stderr:
            print(line, end='', file=sys.stderr)
            stderr_lines.append(line)
        else:
            print(line, end='')
            stdout_lines.append(line)


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
        # Start subprocess with pipes for streaming
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Capture output for notifications while streaming
        stdout_lines = []
        stderr_lines = []

        # Start threads to stream stdout and stderr
        stdout_thread = threading.Thread(target=stream_output, args=(process.stdout, stdout_lines, stderr_lines, False))
        stderr_thread = threading.Thread(target=stream_output, args=(process.stderr, stdout_lines, stderr_lines, True))

        stdout_thread.start()
        stderr_thread.start()

        # Wait for process to complete
        exit_code = process.wait()

        # Wait for output threads to finish
        stdout_thread.join()
        stderr_thread.join()

        # Combine captured output for notifications
        output = ''.join(stdout_lines) + ''.join(stderr_lines)

        print(f"Backup completed with exit code: {exit_code}")
        print(f"Backup finished at {datetime.now()}")

        return exit_code, output

    except Exception as e:
        error_msg = f"Failed to execute backup command: {e}"
        print(error_msg)
        return 1, error_msg


def send_notification(backup_name, exit_code, output, email_config, env_vars):
    """Send email notification"""

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

Please check the system logs for more details"""

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
    if exit_code != 0 and email_config:
        send_notification(backup_name, exit_code, output, email_config, env_vars)

    # Exit with the backup exit code
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
