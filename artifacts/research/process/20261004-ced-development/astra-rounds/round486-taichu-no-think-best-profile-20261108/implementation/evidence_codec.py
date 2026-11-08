"""R487: deterministic JSON evidence with explicit set representations."""

import json
from pathlib import Path


def normalize(value, pointer="", events=None, active=None):
    events = [] if events is None else events
    active = set() if active is None else active
    if value is None or type(value) in (str, bool, int, float):
        return value
    if type(value) not in (dict, list, tuple, set, frozenset):
        raise TypeError("unsupported evidence type at " + pointer + ": " + type(value).__name__)
    if id(value) in active:
        raise ValueError("circular evidence reference at " + pointer)
    active.add(id(value))
    try:
        if type(value) is dict:
            return {key: normalize(item, pointer + "/" + str(key).replace("~", "~0").replace("/", "~1"),
                                   events, active) for key, item in value.items()}
        if type(value) in (set, frozenset):
            def canonical(item):
                return json.dumps(normalize(item), sort_keys=True, ensure_ascii=False, allow_nan=False)

            ordered = sorted(value, key=canonical)
            events.append({"json_pointer": pointer, "python_type": type(value).__name__,
                           "element_count": len(value), "encoding": "array sorted by canonical JSON"})
        else:
            ordered = value
        return [normalize(item, pointer + "/" + str(index), events, active)
                for index, item in enumerate(ordered)]
    finally:
        active.remove(id(value))


def write_evidence(path, value):
    path = Path(path)
    events = []
    safe = normalize(value, events=events)
    encoded = json.dumps(safe, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    sidecar = json.dumps({"source_file": str(path), "representations": events,
                          "original_in_memory_values_unchanged": True}, indent=2,
                         ensure_ascii=False, allow_nan=False) + "\n"
    with path.open("x") as stream:
        stream.write(encoded)
    if events:
        with path.with_name(path.name + ".serialization.json").open("x") as stream:
            stream.write(sidecar)
