# AGENTS.md

Project-specific instructions for AI coding agents working on ansible-restic.

This is an Ansible role (Galaxy namespace `vrischmann`, role `restic`), not an
application. It deploys restic backups via systemd services and timers.

## Project rules

- Two deployment modes, `user` and `server`, are selected by the
  `restic_backup_mode` variable and dispatched in `tasks/main.yml`. Code paths
  live under `tasks/<mode>.yml` and `templates/<mode>/`; touch both when a
  change applies to both modes.
- The systemd backup services are enabled but must never be `state: started`
  by the role; starting them runs a real backup. Keep the existing `enabled:
  true` without `state: started` on the service task (see the NOTE in
  `tasks/user.yml` and `tasks/server.yml`).
- `files/restic-backup-notify.py` is shipped verbatim to the target host and is
  the only Python in the repo. It is type-checked with mypy (the
  `.mypy_cache/` is git-ignored); keep it stdlib-only and runnable on the
  target's Python 3.
- The rendered `.env` files hold repository credentials and SMTP passwords;
  they are written mode `0600`. Never log them or change that mode.
- Variable names, the backup-definition schema, and the env-var contract for
  email notifications are owned by `README.md`. Do not restate them here or in
  code comments; update `README.md` when they change.
- The role ships a custom `extend` filter from `filter_plugins/filters.py`;
  prefer it over reinventing list concatenation in templates.
- `meta/main.yml` declares supported platforms (Fedora, Debian) and
  `min_ansible_version`; keep changes consistent with the systemd features the
  templates assume.

## Commands

There is no `justfile` or `Makefile`. The two checks worth running are:

```
mypy files/restic-backup-notify.py
ansible-playbook --syntax-check <consuming-playbook>
```

There is no recipe file; adapt the playbook path to a real consumer of this role.

## Testing

There is no automated test suite and no CI configured. Validation is manual:
run the role against a throwaway host (or `--check`) for each mode before
considering a change done.

## Final validation

```
mypy files/restic-backup-notify.py
ansible-lint .                          # if ansible-lint is installed
ansible-playbook --syntax-check <consuming-playbook>
```
