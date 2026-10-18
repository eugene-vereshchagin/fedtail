"""TOML config: defaults, validation, friendly errors.

The app never writes the user's config. If it's missing, the commented
example is copied there once so there's something to edit.
"""

import copy
import re
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
        "esc": "curtain",
        "switch_closes": True,
        "compose": "inline",
        "compose_size": 0,
        "start_lane": "none",
        "merge": [],
        "sidebar_footer": True,
        "sidebar_groups": True,
        "command_line": True,
        "expand_cw": True,
        "bookmark_button": True,
        "arts_mode": True,
        "max_width": 760,
        "image_height": 360,
        "image_viewer": "internal",
        "video_player": "internal",
        "gifv": "play",
        "image_upscale": 2,
        "save_dir": "",
        "links_in_app": True,
        "image_cache_mb": 128,
        "image_decode": 'box',
        "image_disk_mb": 1000,
        "video_disk_mb": 10000,
        "unload_hidden_minutes": 10,
        "themed_icon": True,
        "icon_count": ["comments", "mentions", "subs", "requests"],
        "actions": "both",
        "post_keys": True,
        "announcements": 'banner',
        "media_grid": 'natural',
        "alt_text": 'tooltip',
    },
    "feed": {
        "order": "oldest_first",
        "start_at": "first_unread",
        "on_new": "keep_position",
        "show_reply_context": True,
        "page_size": 40,
        "catch_up_limit": 400,
        "render_limit": 300,
        "build_at_once": 40,
        "first_run_mark_read": True,
        "honest_counters": False,
        "counters_via_accounts": True,
        "remember_choices": False,
        "complete_threads": True,
        "link_cards": 'full',
        "custom_emoji": True,
        "quotes": 'card',
        "remote_profiles": True,
        "prefetch": 'all',
        "follow_date_note": True,
        "remote_posts": 20,
        "remote_people": True,
        "sensitive_media": 'hide',
        "profile_pinned": True,
        "translate": True,
        "profile_featured": True,
    },
    "read": {
        "mark_read": "on_scroll",
        "read_button": False,
        "sync_markers": True,
    },
    "lanes": {
        "enabled": ["global", "people", "local", "bots", "mine", "direct", "mentions", "comments",
                    "subs", "bookmarks", "activity", "requests"],
        "extra_bots": [],
        "posts_only": [],
        "mentions_all": False,
        "direct_apart": True,
    },
    "post": {
        "default_visibility": "private",
        "reply_never_wider": True,
        "drafts_autosave": True,
        "cw_field": False,
        "camelcase_hint": True,
        "plain_posts": True,
        "language": "",
        "languages": ["ru", "en", "ka", "uk"],
        "complete_mentions": True,
        "complete_tags": True,
        "report_forward": True,
        "quote_policy": '',
        "quote_action": True,
        "who_can_reply": '',
        "who_can_boost": '',
        "who_can_like": '',
        "schedule": True,
        "alt_reminder": True,
        "complete_emoji": True,
        "focus_point": True,
    },
    "notify": {
        "enabled": True,
        "lanes": ["direct", "comments", "mentions", "subs", "activity", "requests"],
        "privacy": "full",
        "when_focused": False,
        "backend": "auto",
        "filtered": 'remind',
    },
    "activity": {
        "types": ["favourite", "reblog", "follow"],
        "approvals": True,
    },
    "lists": {
        "enabled": True,
        "hide_members": "all",
        "hide_in": ["people", "bots", "global", "local"],
        "refresh_minutes": 10,
    },
    "subs": {
        "auto": ["posts", "comments"],
        "interval_minutes": 5,
        "active_days": 14,
        "max_threads": 30,
        "replies_to_me": False,
    },
    "poll": {
        "interval_seconds": 90,
        "stream_gap_seconds": 10,
        "stream": 'auto',
    },
    "debug": {
        "level": "debug",
        "mode": "auto",
        "log_dir": "",
        "log_mb": 10,
        "keep_mb": 500,
        "stats_minutes": 5,
        "trim_memory": True,
        "watchdog_seconds": 8,
        "stall_ms": 250,
        "slow_request_seconds": 5,
        "rss_warn_mb": 1500,
    },
    "tui": {
        "theme": "",
        "lanes_width": 26,
        "show_context": True,
    },
    "web": {
        "host": "127.0.0.1",
        "port": 8765,
        "open_browser": True,
    },
    "cli": {
        "enabled": True,
        "color": "auto",
        "max_lines": 0,
        "tail_lanes": [],
    },
}

CHOICES = {
    ("poll", "stream"): {'auto', 'off'},
    ("ui", "image_decode"): {'box', 'full'},
    ("feed", "prefetch"): {'previews', 'all', 'off'},
    ("ui", "alt_text"): {'caption', 'tooltip'},
    ("ui", "media_grid"): {'natural', 'square'},
    ("notify", "filtered"): {'menu', 'remind', 'off'},
    ("ui", "announcements"): {'off', 'banner'},
    ("post", "who_can_like"): {'', 'followers', 'mentioned', 'everyone', 'me', 'following'},
    ("post", "who_can_boost"): {'', 'followers', 'mentioned', 'everyone', 'me', 'following'},
    ("post", "who_can_reply"): {'', 'followers', 'mentioned', 'everyone', 'me', 'following'},
    ("post", "quote_policy"): {'', 'public', 'followers', 'nobody'},
    ("feed", "sensitive_media"): {'show', 'hide'},
    ("feed", "quotes"): {'card', 'link', 'off'},
    ("feed", "link_cards"): {'text', 'off', 'full'},
    ("account", "markdown"): {"auto", "on", "off"},
    ("ui", "frontend"): {"qt", "tui", "web"},
    ("ui", "language"): {"auto", "ru", "en"},
    ("ui", "image_viewer"): {"internal", "browser"},
    ("ui", "video_player"): {"internal", "browser"},
    ("ui", "gifv"): {"play", "click"},
    ("ui", "actions"): {"both", "icons", "text"},
    ("feed", "order"): {"oldest_first", "newest_first"},
    ("feed", "start_at"): {"first_unread", "newest"},
    ("feed", "on_new"): {"keep_position", "jump_to_newest"},
    ("read", "mark_read"): {"on_scroll", "on_open", "manual"},
    ("notify", "privacy"): {"full", "sender", "count"},
    ("notify", "backend"): {"auto", "desktop", "tray"},
    ("post", "default_visibility"): {"public", "unlisted", "private", "direct", "server"},
    ("debug", "level"): {"debug", "info", "warning"},
    ("debug", "mode"): {"auto", "on", "off"},
    ("cli", "color"): {"auto", "always", "never"},
    ("ui", "esc"): {"curtain", "tray", "off"},
    ("ui", "compose"): {"inline", "window"},
    ("lists", "hide_members"): {"all", "exclusive", "off"},
}
LANE_NAMES = {"people", "comments", "mentions", "subs", "bookmarks", "activity", "bots", "mine",
              "local", "global", "requests", "direct", "favourites"}
ACTIVITY_TYPES = {"favourite", "reblog", "follow", "poll", "update", "status"}
SUBS_AUTO = {"posts", "comments"}
MINIMUM = {
    ("poll", "interval_seconds"): 30,
    ("poll", "stream_gap_seconds"): 0,
    ("subs", "interval_minutes"): 1,
    ("lists", "refresh_minutes"): 1,
    ("debug", "log_mb"): 1,
    ("ui", "image_cache_mb"): 16,
    ("ui", "unload_hidden_minutes"): 0,
    ("debug", "keep_mb"): 20,
    ("debug", "stall_ms"): 0,
    ("subs", "active_days"): 1,
    ("subs", "max_threads"): 1,
    ("feed", "page_size"): 1,
    ("feed", "remote_posts"): 1,
    ("feed", "catch_up_limit"): 1,
    ("feed", "render_limit"): 20,
    ("feed", "build_at_once"): 0,
    ("ui", "font_size"): 0,
    ("ui", "max_width"): 0,
    ("ui", "compose_size"): 0,
    ("ui", "image_disk_mb"): 0,
    ("ui", "video_disk_mb"): 0,
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
            if (section, key) == ("debug", "keep"):  # 0.3: a size for the folder instead
                warnings.append("debug.keep is gone: debug.keep_mb caps the log folder")
                continue
            if (section, key) == ("lists", "exclusive_hides") and "hide_members" not in values:
                # replaced in 0.3: hiding now covers every list unless told otherwise
                if val is False:
                    cfg["lists"]["hide_members"] = "off"
                warnings.append('lists.exclusive_hides is now lists.hide_members '
                                '("all", "exclusive" or "off")')
                continue
            if (section, key) == ("ui", "esc_hides") and "esc" not in values:
                # replaced in 0.3: false still means Esc does nothing; true was the old
                # default (to the tray) and now gets the new default, the curtain
                if val is False:
                    cfg["ui"]["esc"] = "off"
                warnings.append('ui.esc_hides is now ui.esc ("curtain", "tray" or "off")')
                continue
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

    bad = [x for x in cfg["lanes"]["enabled"] + cfg["lanes"]["posts_only"] +
           cfg["notify"]["lanes"] + cfg["ui"]["icon_count"] + cfg["lists"]["hide_in"]
           if x not in LANE_NAMES | {"lists"}
           # notify.lanes may name one list: "list:Друзья" (its title, or its id)
           and not (x in cfg["notify"]["lanes"] and isinstance(x, str)
                    and x.startswith("list:") and len(x) > 5)]
    if bad:
        errors.append(f"lanes: unknown lanes {bad}; known: {', '.join(sorted(LANE_NAMES))}")
    if "all" in cfg["activity"]["types"]:  # everything there is, now and later
        cfg["activity"]["types"] = sorted(ACTIVITY_TYPES)
    bad_types = [x for x in cfg["activity"]["types"] if x not in ACTIVITY_TYPES]
    if bad_types:
        errors.append(f"activity.types: unknown {bad_types}; "
                      f"known: {', '.join(sorted(ACTIVITY_TYPES))}")
    bad_auto = [x for x in cfg["subs"]["auto"] if x not in SUBS_AUTO]
    if bad_auto:
        errors.append(f"subs.auto: unknown {bad_auto}; known: {', '.join(sorted(SUBS_AUTO))}")
    if not cfg["lanes"]["enabled"]:
        errors.append("lanes.enabled is empty — nothing to show")
    if not all(isinstance(x, str) for x in cfg["lanes"]["extra_bots"]):
        errors.append("lanes.extra_bots must be a list of strings")
    langs = [cfg["post"]["language"]] + cfg["post"]["languages"]
    bad_merge = [x for x in cfg["ui"]["merge"]
                 if not (isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", x))]
    if bad_merge:
        errors.append(f"ui.merge: {bad_merge} — profile names, or [\"all\"]")
    start = cfg["ui"]["start_lane"]
    if start not in {"none", "last"} | LANE_NAMES:
        errors.append(f"ui.start_lane = {start!r}; allowed: none, last or a lane: "
                      f"{', '.join(sorted(LANE_NAMES))}")
    bad_lang = [x for x in langs
                if x and not (isinstance(x, str) and re.fullmatch(r"[a-z]{2,3}", x))]
    if bad_lang:
        errors.append(f"post.language(s): {bad_lang} — two or three small letters (ISO 639), "
                      f"like \"ru\" or \"en\"")
    if errors:
        raise ConfigError("\n".join(errors))
    return cfg, warnings


# ui.arts_mode: the whole post as its author wrote it. Frontends ask these instead of
# reading the separate switches it overrides (server filters and the report item are
# checked where they act).
def expand_cw(cfg):
    """Content warnings open from the start."""
    return bool(cfg["ui"].get("arts_mode") or cfg["ui"]["expand_cw"])


def sensitive_media(cfg):
    """feed.sensitive_media as it applies now: "show" or "hide"."""
    if cfg["ui"].get("arts_mode"):
        return "show"
    return cfg["feed"].get("sensitive_media", "hide")


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
