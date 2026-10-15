"""TOML config: defaults, validation, friendly errors.

The app never writes the user's config. If it's missing, the commented
example is copied there once so there's something to edit.
"""

import copy
import tomllib
from importlib import resources

DEFAULTS = {
    "account": {"markdown": "auto"},
    "ui": {
        "frontend": "qt",
        "language": "auto",
        "theme": "system",
        "font_size": 0,
        "close_to_tray": True,
        "notifications": True,
        "expand_cw": True,
        "max_width": 760,
        "image_height": 360,
        "image_viewer": "internal",
        "image_upscale": 2,
    },
    "feed": {
        "order": "oldest_first",
        "start_at": "first_unread",
        "on_new": "keep_position",
        "show_reply_context": True,
        "page_size": 40,
        "catch_up_limit": 400,
        "render_limit": 300,
        "first_run_mark_read": True,
    },
    "read": {"mark_read": "on_scroll"},
    "lanes": {
        "enabled": ["people", "comments", "mentions", "bots", "mine", "local", "requests"],
        "extra_bots": [],
        "posts_only": [],
    },
    "post": {
        "default_visibility": "private",
        "reply_never_wider": True,
        "drafts_autosave": True,
    },
    "poll": {"interval_seconds": 90},
}

CHOICES = {
    ("account", "markdown"): {"auto", "on", "off"},
    ("ui", "frontend"): {"qt"},
    ("ui", "language"): {"auto", "ru", "en"},
    ("ui", "theme"): {"system", "terminal"},
    ("ui", "image_viewer"): {"internal", "browser"},
    ("feed", "order"): {"oldest_first", "newest_first"},
    ("feed", "start_at"): {"first_unread", "newest"},
    ("feed", "on_new"): {"keep_position", "jump_to_newest"},
    ("read", "mark_read"): {"on_scroll", "on_open", "manual"},
    ("post", "default_visibility"): {"public", "unlisted", "private", "direct"},
}
LANE_NAMES = {"people", "comments", "mentions", "bots", "mine", "local", "requests"}
MINIMUM = {
    ("poll", "interval_seconds"): 30,
    ("feed", "page_size"): 1,
    ("feed", "catch_up_limit"): 1,
    ("feed", "render_limit"): 20,
    ("ui", "font_size"): 0,
    ("ui", "max_width"): 0,
    ("ui", "image_height"): 80,
    ("ui", "image_upscale"): 1,
}


class ConfigError(Exception):
    pass


def example_text():
    return resources.files("fedtail").joinpath("data/config.example.toml").read_text("utf-8")


def _type_name(v):
    return {bool: "true/false", int: "number", str: "string", list: "list"}.get(type(v), "value")


def validate(user):
    """Merge user config over defaults. Returns (config, warnings) or raises ConfigError."""
    cfg = copy.deepcopy(DEFAULTS)
    warnings, errors = [], []
    for section, values in user.items():
        if section not in DEFAULTS:
            warnings.append(f"unknown section [{section}] — ignored")
            continue
        if not isinstance(values, dict):
            errors.append(f"[{section}] must be a section, not a value")
            continue
        for key, val in values.items():
            if key not in DEFAULTS[section]:
                warnings.append(f"unknown key {section}.{key} — ignored")
                continue
            default = DEFAULTS[section][key]
            # bool is a subclass of int: check it strictly
            if type(val) is not type(default):
                errors.append(f"{section}.{key} must be {_type_name(default)}, got {val!r}")
                continue
            choices = CHOICES.get((section, key))
            if choices and val not in choices:
                errors.append(f"{section}.{key} = {val!r}; allowed: {', '.join(sorted(choices))}")
                continue
            low = MINIMUM.get((section, key))
            if low is not None and val < low:
                errors.append(f"{section}.{key} must be at least {low}")
                continue
            cfg[section][key] = val

    bad = [x for x in cfg["lanes"]["enabled"] + cfg["lanes"]["posts_only"]
           if x not in LANE_NAMES]
    if bad:
        errors.append(f"lanes: unknown lanes {bad}; known: {', '.join(sorted(LANE_NAMES))}")
    if not cfg["lanes"]["enabled"]:
        errors.append("lanes.enabled is empty — nothing to show")
    if not all(isinstance(x, str) for x in cfg["lanes"]["extra_bots"]):
        errors.append("lanes.extra_bots must be a list of strings")
    if errors:
        raise ConfigError("\n".join(errors))
    return cfg, warnings


def load(path):
    """Read config file (creating the commented example if absent)."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(example_text(), "utf-8")
    try:
        with open(path, "rb") as f:
            user = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None
    return validate(user)
