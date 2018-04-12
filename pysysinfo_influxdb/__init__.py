from collections import ChainMap, namedtuple
from typing import List, Dict, Set

import psutil


def _prefixed(nt: namedtuple, prefix):
    """Convert a named tuple into a dict with prefixed names."""
    result = {}
    for key, value in nt._asdict().items():
        result[prefix + key] = value
    return result


def _split_tags_and_fields(values, tag_names: Set[str] = set([])):
    tags = {}
    fields = {}
    for key, value in values.items():
        if key in tag_names:
            tags[key] = value
        else:
            fields[key] = value
    return dict(fields=fields, tags=tags)


def _parse(nt: namedtuple, prefix: str, tag_names: Set[str] = set([])):
    return _split_tags_and_fields(_prefixed(nt, prefix), tag_names)


def _prefixed_items_from_list(items: List[namedtuple], item_prefix, prefix, tag_names: Set[str] = set([])):
    """Convert a named tuple into a dict with prefixed names."""
    result = {}
    for index, nt in enumerate(items):
        result["%s%d" % (item_prefix, index)] = _parse(nt, prefix, tag_names)
    return result


def _prefixed_items_from_dict(values: Dict[str, namedtuple], item_prefix, prefix, tag_names: Set[str] = set([])):
    """Convert a named tuple into a dict with prefixed names."""
    result = {}
    for key, nt in values.items():
        result["%s%s" % (item_prefix, key)] = _parse(nt, prefix, tag_names)
    return result


def get_cpu_stats():
    fields = dict(
        count_physical=psutil.cpu_count(False),
        count_logical=psutil.cpu_count(True),
    )
    fields.update(_prefixed(psutil.cpu_freq(False), "freq_"))
    fields.update(psutil.cpu_stats()._asdict())

    result = {"cpu": {"fields": fields, "tags": {}}}

    result.update(_prefixed_items_from_list(psutil.cpu_freq(True), "cpu", "freq_"))

    return result


def get_vm_stats():
    return dict(virtual_memory=_parse(psutil.virtual_memory(), ""))


def get_swap_stats():
    return dict(swap=_parse(psutil.swap_memory(), ""))


def get_disk_io_stats():
    result = {}
    result["disk"] = _parse(psutil.disk_io_counters(False), "")
    result.update(_prefixed_items_from_dict(psutil.disk_io_counters(True), "disk_", ""))
    return result


def get_net_io_stats():
    result = {}
    result["net"] = _parse(psutil.net_io_counters(False), "")
    result.update(_prefixed_items_from_dict(psutil.net_io_counters(True), "net_", ""))
    return result


def get_fan_stats():
    result = {}
    for sysname, items in psutil.sensors_fans().items():
        result.update(_prefixed_items_from_list(items, "fan_" + sysname + "_", "", {"label"}))
    return result


def get_all_stats():
    result = ChainMap(
        get_cpu_stats(),
        get_vm_stats(),
        get_swap_stats(),
        get_disk_io_stats(),
        get_net_io_stats(),
        get_fan_stats(),
    )
    return result
