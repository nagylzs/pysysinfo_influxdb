import psutil
import os
import copy

from collections import ChainMap, namedtuple
from typing import List, Dict, Set


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


def _prefixed_items_from_dict(values: Dict[str, namedtuple], item_prefix, prefix, tag_names: Set[str] = set([]),
                              cumulative=False):
    """Convert a named tuple into a dict with prefixed names."""
    result = {}
    for key, nt in values.items():
        item_key = "%s%s" % (item_prefix, key)
        item = _parse(nt, prefix, tag_names)
        if cumulative:
            item = _cumulative_diff(item, item_key)
        result[item_key] = item
    return result


_prev_values = {}


def _cumulative_diff(item, key):
    """Return a version that converts cumulative field values to their differences."""
    global _prev_values
    if key in _prev_values:
        # Subsequent item, return difference from previous
        prev = _prev_values[key]
        _prev_values[key] = item

        result = copy.deepcopy(item)
        for fname in result["fields"]:
            result["fields"][fname] -= prev["fields"][fname]

        return result
    else:
        # First item, no difference, return zeros.
        _prev_values[key] = item
        result = copy.deepcopy(item)
        fields = result["fields"]
        for fname in fields:
            fields[fname] = 0
        return result


try:
    _gla = os.getloadavg
except AttributeError:
    _gla = None


def get_load_stats():
    global _gla
    if _gla:
        load = _gla()
        return {
            "load": {
                "fields": {
                    "load_1min": load[0],
                    "load_5min": load[1],
                    "load_15min": load[2],
                },
                "tags": {},
            }
        }
    else:
        return {}


_has_cpu_info = None


def get_cpu_stats():
    global _has_cpu_info
    if _has_cpu_info is None:
        _has_cpu_info = psutil.cpu_freq() is not None
    if not _has_cpu_info:
        return {}
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
    disk = _parse(psutil.disk_io_counters(perdisk=False, nowrap=True), "")
    result["disk"] = _cumulative_diff(disk, "disk")
    result.update(_prefixed_items_from_dict(
        psutil.disk_io_counters(perdisk=True, nowrap=True),
        item_prefix="disk_", prefix="", cumulative=True
    ))
    return result


def get_net_io_stats():
    result = {}
    net = _parse(psutil.net_io_counters(pernic=False, nowrap=True), "")
    result["net"] = _cumulative_diff(net, "net")
    result.update(_prefixed_items_from_dict(
        psutil.net_io_counters(pernic=True, nowrap=True),
        item_prefix="net_", prefix="", cumulative=True))
    return result


def get_fan_stats():
    result = {}
    for sysname, items in psutil.sensors_fans().items():
        result.update(_prefixed_items_from_list(items, "fan_" + sysname + "_", "", {"label"}))
    return result


def get_all_stats():
    result = ChainMap(
        get_load_stats(),
        get_cpu_stats(),
        get_vm_stats(),
        get_swap_stats(),
        get_disk_io_stats(),
        get_net_io_stats(),
        get_fan_stats(),
    )
    return result
