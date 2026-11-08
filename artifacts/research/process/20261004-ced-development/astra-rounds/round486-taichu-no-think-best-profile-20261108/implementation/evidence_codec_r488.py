"""JSON-native semantics plus explicit, deterministic set evidence."""

import json
import sys
import traceback
from pathlib import Path


def normalize(value, pointer="", events=None, active=None):
    events = [] if events is None else events
    active = set() if active is None else active
    if value is None:
        return value
    native = next((base for base in (bool, str, int, float, dict, list, tuple, set, frozenset)
                   if isinstance(value, base)), None)
    if native is None:
        raise TypeError("unsupported evidence type at " + pointer + ": " + type(value).__name__)
    if type(value) is not native:
        events.append({"json_pointer": pointer, "python_type": type(value).__module__ + "." + type(value).__qualname__,
                       "native_base": native.__name__, "encoding": "stdlib JSON native subclass semantics"})
    if native in (bool, str, int, float):
        return value
    if id(value) in active:
        raise ValueError("circular evidence reference at " + pointer)
    active.add(id(value))
    try:
        if native is dict:
            result = {}
            for key, item in value.items():
                # stdlib validates keys, including subclasses, without skipkeys or str coercion.
                encoded_key = next(iter(json.loads(json.dumps({key: None}, allow_nan=False))))
                location = pointer + "/" + encoded_key.replace("~", "~0").replace("/", "~1")
                if key is not None and type(key) not in (str, bool, int, float):
                    base = next(base for base in (bool, str, int, float) if isinstance(key, base))
                    events.append({"json_pointer": location, "position": "dict_key",
                                   "python_type": type(key).__module__ + "." + type(key).__qualname__,
                                   "native_base": base.__name__, "encoding": "stdlib JSON native key semantics"})
                result[key] = normalize(item, location, events, active)
            return result
        if native in (set, frozenset):
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


def finalize_evidence(state, paths, raw, primary_text=""):
    """Never replace a primary runtime exception with a reporting exception."""
    try:
        for path in paths:
            write_evidence(path, state)
        return True
    except Exception:
        secondary = traceback.format_exc()
        text = primary_text + "\nSECONDARY EVIDENCE WRITE ERROR\n" + secondary
        with (Path(raw) / "secondary-evidence-error.txt").open("x") as stream:
            stream.write(text)
        print(text, file=sys.stderr, flush=True)
        return False
