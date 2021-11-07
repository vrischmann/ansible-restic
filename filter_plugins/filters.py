from ansible.module_utils.common.collections import is_iterable


def extend(a, b):
    a.extend(b)
    return a


class FilterModule(object):
    def filters(self):
        return {"extend": extend}
