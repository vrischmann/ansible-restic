Role Name
=========

Deploy [restic](https://restic.net/) backups using systemd services and timers.

This role has two modes:
* `user` which adds user-wide services and timers (for your normal user).
* `server` which adds system-wide services and timers.

Requirements
------------

You need restic installed and your repositories already initialized.

Role Variables
--------------

| Name                          | Required | Description
| --------------                | -------- | -----------------------------------
| `restic_binary`               | yes      | Full path of the restic binary.
| `restic_backup_mode`          | yes      | Backup mode (either "user" or "server").
| `restic_user_home`            | no       | Home directory of the user (if running in "user" mode).
| `restic_user_name`            | no       | Name of the user (if running in "user" mode).
| `restic_user_group`           | no       | Group of the user (if running in "user" mode).
| `restic_default_excludes`     | no       | List of directories or files to exclude from backups.
| `restic_specific_excludes`    | no       | List of directories or files to exclude from backups.
| `restic_backups`              | yes      | List of backup definitions for restic.
| `restic_conf_directory`       | no       | Configuration directory (if running in "server" mode).

## Default and specific excludes

You might have the same basic excludes for a single ansible group, for example I have a "workstation" group
shared by my desktop and laptop. Each of these also has specific excludes.

To configure this properly, you should define `restic_default_excludes` in your group vars and `restic_specific_excludes` in each host vars.

For example:

`group_vars/workstation`:
```yaml
restic_default_excludes:
- /var/log
```
`host_vars/desktop`:
```yaml
restic_specific_excludes:
- /opt/stuff
- /home/vincent/dont_touch_this
```
`host_vars/laptop`:
```yaml
restic_specific_excludes:
- /home/vincent/dont_touch_this_either
```

## Backup definition

This role assumes that a single host will always backup the same data to 1 or more repositories; for example you could backup
to Amazon S3, rsync.net, your own SFTP server, etc.

The `restic_backups` list therefore contains N items defining the repositories.

Each backup definition must contain the following information:
* The name of the repository (used for the systemd services: only use alphanumeric characters)
* The environment variables for restic to use the repository
* The calendar spec for the systemd timer.

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

  - name: remote-linode
    env:
      AWS_ACCESS_KEY_ID: "{{ restic_linode_aws_access_key_id }}"
      AWS_SECRET_ACCESS_KEY: "{{ restic_linode_aws_secret_access_key }}"
      RESTIC_REPOSITORY: "s3:eu-central-1.linodeobjects.com/foobar/barbaz"
      RESTIC_PASSWORD: "{{ restic_remote_password }}"
    calendar_spec: "*-*-* *:00/15:00"
```

License
-------

MIT
