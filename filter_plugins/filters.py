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


class FilterModule(object):
    def filters(self):
        return {"extend": extend, "as_list": as_list}
