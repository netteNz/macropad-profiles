# Loads /profiles/*.py. Each file defines one `app` dict (Adafruit Hotkeys
# format plus optional fields). Profiles are data only: apart from `app`,
# the module is discarded, and every action is checked to contain nothing
# but ints, floats, strs, lists and the {"host", "fallback"} dict, so a
# profile can't smuggle in callables.
import os
import sys

PLAY_PAUSE = 0xCD  # ConsumerControlCode.PLAY_PAUSE
KNOB_NAMES = ("system_volume", "spotify_volume")
LABEL_MAX = 6
_NVM_MAGIC = 0xA5
_NVM_LEN = 32


def _ascii(s):
    # terminalio only has ASCII glyphs.
    return "".join(c if 32 <= ord(c) < 127 else "?" for c in s)


def _check_seq(seq, where):
    if not isinstance(seq, list):
        seq = [seq]
    for item in seq:
        if isinstance(item, (int, float, str)):
            continue
        if isinstance(item, list) and all(isinstance(c, (int, float)) for c in item):
            continue
        raise ValueError("%s: unsupported item %r" % (where, item))
    return seq


def _check_action(action, where):
    if isinstance(action, dict):
        if not isinstance(action.get("host"), str):
            raise ValueError(where + ": host action needs a 'host' string")
        return {
            "host": action["host"],
            "fallback": _check_seq(action.get("fallback", []), where),
        }
    return _check_seq(action, where)


def _check_knob(knob, where):
    if knob in KNOB_NAMES:
        return knob
    if isinstance(knob, tuple) and len(knob) == 3 and knob[0] == "keys":
        return ("keys", _check_seq(knob[1], where), _check_seq(knob[2], where))
    if isinstance(knob, tuple) and len(knob) == 2 and knob[0] == "host":
        return ("host", str(knob[1]))
    raise ValueError("%s: bad knob %r" % (where, knob))


def validate(app, fname):
    """Returns a normalized copy of `app`, or raises ValueError."""
    if not isinstance(app, dict):
        raise ValueError(fname + ": `app` must be a dict")
    name = app.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(fname + ": missing name")
    macros = app.get("macros")
    if not isinstance(macros, (list, tuple)) or len(macros) != 12:
        raise ValueError(fname + ": need exactly 12 macros")
    out_macros = []
    for i, m in enumerate(macros):
        where = "%s key %d" % (fname, i + 1)
        if not isinstance(m, tuple) or len(m) != 3:
            raise ValueError(where + ": expected (color, label, action)")
        color, label, action = m
        label = _ascii(label or "")
        if len(label) > LABEL_MAX:
            print("profiles: %s: label %r truncated" % (where, label))
            label = label[:LABEL_MAX]
        out_macros.append((int(color), label, _check_action(action, where)))
    leds = app.get("leds", "static")
    if leds not in ("static", "rainbow"):
        raise ValueError(fname + ": leds must be 'static' or 'rainbow'")
    apps = app.get("apps", [])
    if not isinstance(apps, (list, tuple)) or not all(isinstance(a, str) for a in apps):
        raise ValueError(fname + ": apps must be a list of exe names")
    return {
        "name": _ascii(name),
        "order": int(app.get("order", 0)),
        "file": fname,
        "apps": [a.lower() for a in apps],
        "knob": _check_knob(app.get("knob", "system_volume"), fname),
        "press": _check_action(app.get("press", [[PLAY_PAUSE]]), fname + " press"),
        "leds": leds,
        "macros": out_macros,
    }


def _import_app(modname):
    full = "profiles." + modname
    __import__(full)
    app = sys.modules[full].app
    # Drop the module so only the dict stays in RAM.
    del sys.modules[full]
    try:
        delattr(sys.modules["profiles"], modname)
    except (AttributeError, KeyError):
        pass
    return app


def load_all(path="/profiles", listdir=os.listdir, importer=_import_app):
    profiles = []
    for fname in listdir(path):
        # Skip __init__ and macOS "._foo.py" droppings.
        if fname[0] in "_.":
            continue
        if fname.endswith(".py"):
            modname = fname[:-3]
        elif fname.endswith(".mpy"):
            modname = fname[:-4]
        else:
            continue
        try:
            profiles.append(validate(importer(modname), fname))
        except Exception as e:  # one bad file must not take down the pad
            print("profiles: skipping %s: %s" % (fname, e))
    profiles.sort(key=lambda p: (p["order"], p["file"]))
    return profiles


# Last-used profile in NVM: [magic, len, name bytes]. NVM is one 4 KB flash
# sector and any overwrite erases it, so only write when the name changed.


def _nvm():
    import microcontroller

    return microcontroller.nvm


def load_last(profiles, nvm=None):
    try:
        nvm = nvm if nvm is not None else _nvm()
        if nvm[0] == _NVM_MAGIC:
            name = bytes(nvm[2 : 2 + nvm[1]]).decode()
            for i, p in enumerate(profiles):
                if p["name"] == name:
                    return i
    except Exception as e:
        print("profiles: nvm read failed:", e)
    return 0


def save_last(name, nvm=None):
    data = name.encode()[: _NVM_LEN - 2]
    blob = bytes([_NVM_MAGIC, len(data)]) + data
    try:
        nvm = nvm if nvm is not None else _nvm()
        if bytes(nvm[0 : len(blob)]) != blob:
            nvm[0 : len(blob)] = blob  # single assignment = single erase
    except Exception as e:
        print("profiles: nvm write failed:", e)
