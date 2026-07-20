from ansible.module_utils.common.collections import is_iterable


def extend(a, b):
    a.extend(b)
    return a


def as_list(value):
    """Normalize a scalar or iterable into a list.

    Strings are wrapped as a single-element list so they are not iterated
    character-by-character when a template loops over the value. Used to let
    hook fields (`exec_start_pre`, `exec_stop_post`) accept either a single
    command or a list of commands.
    """
    if isinstance(value, str):
        return [value]
    if is_iterable(value):
        return list(value)
    return [value]


def _hook_list(value):
    """Coerce a hook value (None, str, or list) into a list, with None -> []."""
    if value is None:
        return []
    return as_list(value)


# Scope-level fields copied verbatim onto every unit of a scope.
_SCOPE_COMMON_FIELDS = ("backup_directories", "excludes")
# Hook fields that may be set at scope and/or target level and are merged.
_HOOK_FIELDS = ("exec_start_pre", "exec_stop_post")


def flatten_backup_targets(backups):
    """Expand the ``restic_backups`` list into one dict per systemd unit.

    Each item is a *scope*. A scope with a ``targets`` list fans out to one
    unit per target; a scope without ``targets`` is a single legacy unit (so
    existing single-repository definitions keep working unchanged).

    Scope-level fields (``backup_directories``, ``excludes``) are shared by
    every unit of the scope, which is what removes the duplication of backing
    up the same data to several repositories. Hooks (``exec_start_pre``,
    ``exec_stop_post``) may be set at scope level, at target level, or both;
    target hooks are appended after scope hooks, so a scope can hold the shared
    dump/cleanup scripts while each target adds its own (for example a metrics
    label that differs per destination).

    Each returned dict carries flat fields so the per-unit task loop and the
    templates never deal with nesting::

        unit_name    systemd unit suffix (``restic-backup-<unit_name>``)
        scope_name   scope name; names the shared ``.files``/``.excludes``
        env          restic environment for this target
        calendar_spec, backup_directories, excludes
        exec_start_pre, exec_stop_post   (merged, when defined)

    A target's unit name is ``<scope><suffix>``. The suffix defaults to
    ``-<target.name>`` and can be overridden with ``target.unit_suffix``; pass
    an empty string for an unsuffixed "primary" destination (useful to keep
    pre-existing unit names during a migration).
    """
    units = []
    for scope in backups:
        scope_name = scope["name"]
        common = {f: scope[f] for f in _SCOPE_COMMON_FIELDS if f in scope}
        scope_hooks = {h: _hook_list(scope.get(h)) for h in _HOOK_FIELDS}

        targets = scope.get("targets")
        if targets is not None:
            for target in targets:
                suffix = target.get("unit_suffix", f"-{target['name']}")
                merged_hooks = {}
                for h in _HOOK_FIELDS:
                    chain = scope_hooks[h] + _hook_list(target.get(h))
                    if chain:
                        merged_hooks[h] = chain
                units.append({
                    "unit_name": f"{scope_name}{suffix}",
                    "scope_name": scope_name,
                    "env": target["env"],
                    "calendar_spec": target["calendar_spec"],
                    **common,
                    **merged_hooks,
                })
        else:
            hooks = {h: v for h, v in scope_hooks.items() if v}
            units.append({
                "unit_name": scope_name,
                "scope_name": scope_name,
                "env": scope["env"],
                "calendar_spec": scope["calendar_spec"],
                **common,
                **hooks,
            })
    return units


class FilterModule(object):
    def filters(self):
        return {
            "extend": extend,
            "as_list": as_list,
            "flatten_backup_targets": flatten_backup_targets,
        }
