"""TOML config: defaults, validation, friendly errors.

The app never writes the user's config. If it's missing, the commented
example is copied there once so there's something to edit.
"""

import copy
import re
import tomllib
from importlib import resources

from . import presets, taggroups

DEFAULTS = {
    "account": {"markdown": "auto"},
    "ui": {
        "frontend": "auto",
        "adwaita": "auto",
        "accessibility": "auto",
        "gtk_headerbar": "auto",
        "desktop_entry": True,
        "language": "auto",
        "theme": "system",
        "font_size": 0,
        "fonts": "theme",
        "font": "",
        "mono_font": "",
        "tray": True,
        "close_to_tray": True,
        "esc": "curtain",
        "switch_closes": True,
        "compose": "inline",
        "compose_size": 0,
        "account_colors": True,
        "act_as": True,
        "start_lane": "none",
        "merge": [],
        "sidebar_footer": True,
        "sidebar_groups": True,
        "sidebar_width": 272,
        "command_line": True,
        "whats_this": False,
        "expand_cw": True,
        "bookmark_button": True,
        "additional_highlight": True,
        "arts_mode": True,
        "max_width": 760,
        "layout": "single",
        "open_columns": False,
        "themes_by_layout": "auto",
        "roster_on_top": False,
        "roster_threads": 15,
        "faces": True,
        "dock_commands": True,
        "split_tabs": "keep",
        "icons": "theme",
        "columns": [],
        "column_width": 460,
        "default_columns": 4,
        "message_percent": 100,
        "image_height": 360,
        "image_viewer": "internal",
        "video_player": "internal",
        "video_decode": "software",
        "gifv": "play",
        "gifv_max": 3,
        "gifv_fps": 12,
        "image_upscale": 2,
        "save_dir": "",
        "links_in_app": True,
        "image_cache_mb": 64,
        "image_decode": 'box',
        "image_disk_mb": 1000,
        "video_disk_mb": 10000,
        "unload_hidden_minutes": 10,
        "keep_hidden_lanes": 3,
        "app_icon": "possum",
        "themed_icon": True,
        "icon_count": ["to_me", "replies", "mentions", "subs", "commented", "important",
                       "requests"],
        "icon_count_except": [],
        "actions": "both",
        "post_keys": True,
        "number_keys": "alt",      # a lane by its number: Alt+1…9, Ctrl+1…9 or both
        "pin_tabs": False,         # a tab's right click: pinned (no ×, Ctrl+W passes it)
        "announcements": 'banner',
        "media_grid": 'natural',
        "alt_text": 'tooltip',
    },
    "feed": {
        "order": "oldest_first",
        "start_at": "first_unread",
        "on_new": "keep_position",
        "show_reply_context": True,
        "thread_indent_max": 8,
        "reply_context_chars": 160,
        "mute_tags_shown": 3,
        "link_chars": 40,
        "thread_news": True,
        "page_size": 40,
        "catch_up_limit": 400,
        "render_limit": 300,
        "older_ahead": False,     # the end of a lane in sight: a page older by itself
        "repeat_boosts": False,
        "first_run_mark_read": True,
        "honest_counters": False,
        "counts_minutes": 5,
        "tag_click": "author",
        "counters_via_accounts": True,
        "remember_choices": False,
        "complete_threads": True,
        "thread_from": "mixed",
        "thread_recheck_minutes": 0,
        "thread_recheck_for_minutes": 30,
        "thread_followed_only": False,
        "thread_progress": False,  # "fetching replies: 3 of 12" over an open thread
        "open_at": "post",         # a thread opened from a card: at it, or "first_unread"
        "comment_ids": "post",     # a comment's #id: its post's and number (#a3f/2), or "own"
        "around_post": False,
        "why_home": False,
        "stats": False,            # "Statistics" in the ≡ menu: the week, day by day
        "link_cards": 'full',
        "custom_emoji": True,
        "emoji": True,
        "quotes": 'card',
        "remote_profiles": True,
        "prefetch": 'previews',
        "per_person_follow": True,
        "show_moved": True,
        "old_days": 30,
        "collapse_tags": True,
        "server_info": True,
        "long_form": True,
        "text_markup": True,
        "follow_date_note": True,
        "forget_unfollowed": True,
        "following_max": 1000,
        "search_limit": 20,
        "home_hide": False,
        "aliases": False,
        "nick_colors": False,      # "Name colour…" on a profile: their name in my colour
        "remote_posts": 20,
        "remote_people": True,
        "sensitive_media": 'hide',
        "profile_pinned": True,
        "translate": True,
        "translate_all": False,
        "translate_auto": False,   # posts in languages I neither read nor write: translated
        "translate_backend": "server",  # "server" (its /translate) or "libretranslate"
        "translate_url": "",       # LibreTranslate's address (https://…)
        "translate_key": "",       # its API key, if it asks for one
        "profile_featured": True,
        "profile_show": "posts",
    },
    "read": {
        "mark_read": "on_scroll",
        "read_button": False,
        "dwell_ms": 350,
        "unfocused_seconds": 5,
        "sync_markers": True,
    },
    "lanes": {
        "preset": "fedtail",
        "enabled": [],
        "extra_bots": [],
        "posts_only": [],
        "languages": [],
        "languages_in": ["federated", "local", "tags"],
        "detect_language": "untagged",
        "detect_min_words": 12,
        "detect_among": "auto",   # langdetect's profiles: Latin and Cyrillic, or "all"
        "tag_groups": [],
        "custom": [],
        "unsorted": True,
        "browse_keep": 200,
        "browse_fill_pages": 5,
        "funnel_fill_pages": 5,
        "browse_start": "last",
        "browse_start_hours": 2,
        "bubble": [],
        "federated_extra": [],
        "tags_extra": [],
        "extra_minutes": 10,
        "extra_posts": 20,
        "rss_items": 60,
        "rss_summary_chars": 1200,
        "tags_one_request": False,
    },
    "post": {
        "default_visibility": "private",
        "send_timeout": 90,
        "reply_never_wider": True,
        "drafts_autosave": True,
        "autosave_ms": 700,
        "cw_field": False,
        "reply_warning": "copy",   # a reply starts with the post's warning, or none
        "camelcase_hint": True,
        "plain_posts": True,
        "language": "",
        "languages": ["ru", "en", "ka", "uk"],
        "spellcheck": True,
        "spell_languages": [],
        "complete_mentions": True,
        "complete_tags": True,
        "report_forward": True,
        "quote_policy": '',
        "quote_action": True,
        "invite": True,
        "who_can_reply": '',
        "who_can_boost": '',
        "who_can_like": '',
        "schedule": True,
        "alt_reminder": True,
        "lang_check": False,       # the text reads as another language: ask before sending
        "link_quote": False,       # a post's link at the end of the text: a quote of it
        "send_in_background": False,  # the editor closes at once; the post goes after
        "scheduled_to_draft": False,  # "Back to the editor" on a scheduled post
        "drafts_place": False,     # "Drafts" in the ≡ menu: every kept draft
        "redraft": True,
        "resize_images": True,
        "chain": True,
        "preview": True,
        "format_bar": "left",
        "complete_emoji": True,
        "focus_point": True,
        "quote_prefix": "> ",
    },
    "notify": {
        "enabled": True,
        "lanes": ["direct", "to_me", "replies", "mentions", "subs", "commented", "important",
                  "activity", "requests"],
        "except": [],
        "privacy": "full",
        "max_lines": 3,
        "seconds": 0,
        "when_focused": False,
        "backend": "auto",
        "filtered": 'remind',
    },
    "sound": {
        "enabled": "auto",
        "lanes": ["direct", "to_me", "replies", "mentions", "subs", "commented", "important",
                  "requests"],
        "except": [],
        "online": True,
        "sent": True,
        "when_focused": True,
        "scheme": "theme",
        "volume": 80,
        "player": "auto",
        "min_gap_seconds": 3,
    },
    "activity": {
        "types": ["favourite", "reblog", "follow"],
        "approvals": True,
        "requests": True,
        "my_follows": True,
        "names_shown": 3,
        "unfollows": True,
        "unfollows_minutes": 60,
        "unfollows_max": 5000,
        "unfollows_mass": 10,
        "unlikes": False,
        "unlikes_days": 3,
        "unlikes_posts": 20,
        "server_notices": True,
        "server_groups": True,
    },
    "lists": {
        "enabled": True,
        "hide_members": "all",
        "hide_in": ["home", "bots", "federated", "local"],
        "refresh_minutes": 10,
    },
    "subs": {
        "auto": ["posts", "comments"],
        "interval_minutes": 5,
        "active_days": 14,
        "max_threads": 30,
        "leave_mutes": True,
    },
    "poll": {
        "interval_seconds": 90,
        "stream_gap_seconds": 10,
        "stream": 'auto',
        "slow_minutes": 0,
        "announcements_minutes": 30,
    },
    "sync": {
        "url": "",
        "folder": "",
        "webdav": "",        # a WebDAV folder spoken directly (the password: data dir)
        "webdav_user": "",
        "read": True,
        "threads": True,
        "lanes": True,
        "drafts": True,
        "activity": True,
        "tiles": True,
        "lane_rules": False,
        "people": False,
        "interval_seconds": 60,
    },
    "net": {
        "proxy": "",               # http://host:port, socks5h://host:port; "" — none (or env)
        "proxy_at_login": False,   # a proxy field in the login window
    },
    "storage": {
        "max_mb": 1024,
        "keep_per_lane": 3000,
        "keep_activity": 3000,
        "gc_hours": 6,
        "grace_hours": 48,
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
        "leak_samples": 12,
        "object_census": True,
        "tracemalloc": False,
        "report_repo": "",
        "issue_repo": "",
        "raw_json": False,
    },
    "tui": {
        "theme": "",
        "sound": "bell",
        "lanes_width": 26,
        "show_context": True,
        "pictures": "auto",
        "picture_rows": 8,
        "viewer": "auto",
        "video": "auto",
    },
    "web": {
        "host": "127.0.0.1",
        "port": 8765,
        "open_browser": True,
    },
    "phone": {
        "overview": "tiles",
        "layout": "auto",
        "push": "auto",
        "stream": "always",        # the live stream: "always", "wifi" (Wi-Fi only), "off"
    },
    "cli": {
        "enabled": True,
        "color": "auto",
        "max_lines": 0,
        "tail_lanes": [],
    },
}

CHOICES = {
    ("lanes", "browse_start"): {"last", "hours", "newest"},
    ("feed", "thread_from"): {"local", "mixed", "remote"},
    ("feed", "open_at"): {"post", "first_unread"},
    ("feed", "comment_ids"): {"post", "own"},
    ("feed", "tag_click"): {"author", "everywhere"},
    ("ui", "number_keys"): {"alt", "ctrl", "both"},
    ("feed", "translate_backend"): {"server", "libretranslate"},
    ("phone", "stream"): {"always", "wifi", "off"},
    ("ui", "layout"): {'single', 'split'},
    ("ui", "themes_by_layout"): {"auto", "on", "off"},
    ("ui", "app_icon"): {'possum', 'bubble'},
    ("ui", "icons"): {'theme', 'desktop', 'own', 'additional', 'words'},
    ("ui", "split_tabs"): {'keep', 'close'},
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
    ("post", "format_bar"): {"left", "right", "top", "bottom", "off"},
    ("post", "reply_warning"): {"copy", "none"},
    ("feed", "sensitive_media"): {'show', 'hide'},
    ("feed", "quotes"): {'card', 'link', 'off'},
    ("feed", "link_cards"): {'text', 'off', 'full'},
    ("account", "markdown"): {"auto", "on", "off"},
    ("ui", "frontend"): {"auto", "qt", "tui", "web", "gtk"},
    ("ui", "adwaita"): {"auto", "on", "off"},
    ("ui", "accessibility"): {"auto", "on", "off"},
    ("ui", "gtk_headerbar"): {"auto", "on", "off"},
    ("ui", "language"): {"auto", "ru", "en"},
    ("ui", "image_viewer"): {"internal", "browser"},
    ("ui", "video_player"): {"internal", "browser"},
    ("ui", "video_decode"): {"software", "hardware"},
    ("ui", "gifv"): {"play", "click"},
    ("ui", "actions"): {"both", "icons", "text"},
    ("feed", "order"): {"oldest_first", "newest_first"},
    ("feed", "profile_show"): {"posts", "all", "media"},
    ("feed", "start_at"): {"first_unread", "newest"},
    ("feed", "on_new"): {"keep_position", "jump_to_newest", "hold"},
    ("read", "mark_read"): {"on_scroll", "on_open", "manual"},
    ("notify", "privacy"): {"full", "sender", "count"},
    ("notify", "backend"): {"auto", "desktop", "tray"},
    ("post", "default_visibility"): {"public", "unlisted", "private", "direct", "server"},
    ("debug", "level"): {"debug", "info", "warning"},
    ("debug", "mode"): {"auto", "on", "off"},
    ("cli", "color"): {"auto", "always", "never"},
    ("phone", "overview"): {"tiles", "list"},
    ("phone", "layout"): {"auto", "one", "two", "three"},
    ("phone", "push"): {"auto", "off"},
    ("ui", "esc"): {"curtain", "tray", "off"},
    ("ui", "fonts"): {"theme", "system", "custom"},
    ("ui", "compose"): {"inline", "window"},
    ("lists", "hide_members"): {"all", "exclusive", "off"},
    ("tui", "pictures"): {"auto", "blocks", "key", "off", "inline"},  # inline: before 0.19
    ("tui", "viewer"): {"auto", "app"},
    ("tui", "video"): {"auto", "window", "terminal", "browser"},
    ("tui", "sound"): {"bell", "scheme", "off"},
    ("sound", "enabled"): {"auto", "on", "off"},
    ("lanes", "detect_language"): {"off", "untagged", "always"},
    ("lanes", "detect_among"): {"auto", "all"},
    ("lanes", "preset"): set(presets.names()),
}
# the lanes some set has (fedtail/data/presets.toml), and Unsorted
LANE_NAMES = set(presets.known_names()) | {"unsorted"}
# options that name lanes: their old names are read as the new ones
LANE_LISTS = [("lanes", "enabled"), ("lanes", "posts_only"), ("notify", "lanes"),
              ("notify", "except"), ("sound", "lanes"), ("sound", "except"),
              ("ui", "icon_count"), ("ui", "icon_count_except"), ("ui", "columns"),
              ("ui", "start_lane"),
              ("lists", "hide_in"), ("cli", "tail_lanes"), ("lanes", "languages_in")]
ACTIVITY_TYPES = {"favourite", "reblog", "follow", "poll", "update", "status"}
SUBS_AUTO = {"posts", "comments"}
SYNC_WHAT = ("read", "threads", "lanes", "drafts", "activity", "tiles",
             "lane_rules", "people")  # sync.<each>
MINIMUM = {
    ("lanes", "browse_start_hours"): 1,
    ("lanes", "browse_fill_pages"): 0,
    ("lanes", "funnel_fill_pages"): 0,
    ("ui", "message_percent"): 20,
    ("poll", "announcements_minutes"): 0,
    ("ui", "gifv_fps"): 1,
    ("ui", "gifv_max"): 1,
    ("feed", "link_chars"): 0,
    ("post", "autosave_ms"): 100,
    ("read", "unfocused_seconds"): 0,
    ("read", "dwell_ms"): 0,
    ("ui", "default_columns"): 1,
    ("feed", "mute_tags_shown"): 0,
    ("feed", "reply_context_chars"): 20,
    ("feed", "thread_indent_max"): 0,
    ("notify", "seconds"): 0,
    ("notify", "max_lines"): 1,
    ("activity", "names_shown"): 1,
    ("feed", "search_limit"): 1,
    ("feed", "following_max"): 40,
    ("lanes", "rss_summary_chars"): 100,
    ("lanes", "rss_items"): 1,
    ("lanes", "extra_posts"): 1,
    ("feed", "thread_recheck_for_minutes"): 1,
    ("feed", "thread_recheck_minutes"): 0,
    ("feed", "counts_minutes"): 0,
    ("sound", "min_gap_seconds"): 0,
    ("poll", "interval_seconds"): 30,
    ("sync", "interval_seconds"): 15,
    ("poll", "stream_gap_seconds"): 0,
    ("poll", "slow_minutes"): 0,
    ("subs", "interval_minutes"): 1,
    ("tui", "picture_rows"): 2,
    ("lists", "refresh_minutes"): 1,
    ("debug", "log_mb"): 1,
    ("ui", "image_cache_mb"): 16,
    ("ui", "unload_hidden_minutes"): 0,
    ("ui", "keep_hidden_lanes"): 0,
    ("debug", "keep_mb"): 20,
    ("debug", "stall_ms"): 0,
    ("debug", "leak_samples"): 3,
    ("subs", "active_days"): 1,
    ("subs", "max_threads"): 1,
    ("feed", "page_size"): 1,
    ("lanes", "detect_min_words"): 1,
    ("lanes", "browse_keep"): 20,
    ("lanes", "extra_minutes"): 1,
    ("activity", "unfollows_minutes"): 10,
    ("activity", "unfollows_max"): 0,
    ("activity", "unfollows_mass"): 1,
    ("activity", "unlikes_days"): 1,
    ("activity", "unlikes_posts"): 1,
    ("feed", "remote_posts"): 1,
    ("feed", "catch_up_limit"): 1,
    ("feed", "render_limit"): 20,
    ("ui", "font_size"): 0,
    ("ui", "roster_threads"): 0,
    ("ui", "max_width"): 0,
    ("ui", "column_width"): 280,
    ("ui", "sidebar_width"): 180,
    ("ui", "compose_size"): 0,
    ("ui", "image_disk_mb"): 0,
    ("ui", "video_disk_mb"): 0,
    ("post", "send_timeout"): 10,
    ("feed", "old_days"): 0,
    ("ui", "image_height"): 80,
    ("ui", "image_upscale"): 1,
}


class ConfigError(Exception):
    pass


# ---- the file's layout ------------------------------------------------------------------
# config.toml is laid out by what one sets up (the settings window's chapters, the same
# order): its tables are these. Inside the program every option keeps the section it was
# born in (cfg["ui"]["theme"] — what DEFAULTS has): validate() reads both the file's
# tables and the older ones ([ui], [feed], [read], [subs], [poll], [account] — files of
# 0.20 and before), config_edit writes where the file's layout puts an option (and
# takes the older line out), `--rebuild-config` moves a whole older file.
# tests/test_config_layout.py holds this, DEFAULTS, both example files and the settings
# window to one another.
def _keys(section, names):
    return [(section, k) for k in names.split()]


FILE_LAYOUT = (
    ("appearance", _keys("ui", "language theme font_size fonts font mono_font max_width "
                               "faces icons app_icon themed_icon adwaita gtk_headerbar "
                               "accessibility")
     + _keys("feed", "emoji custom_emoji text_markup")),
    ("window", _keys("ui", "frontend layout open_columns columns column_width default_columns "
                           "message_percent "
                           "themes_by_layout roster_on_top roster_threads split_tabs "
                           "dock_commands sidebar_groups sidebar_width sidebar_footer "
                           "start_lane tray close_to_tray esc post_keys number_keys pin_tabs "
                           "command_line "
                           "whats_this compose compose_size icon_count icon_count_except "
                           "desktop_entry")),
    ("lanes", _keys("lanes", "preset enabled extra_bots posts_only unsorted browse_keep "
                             "browse_fill_pages funnel_fill_pages browse_start "
                             "browse_start_hours custom "
                             "tag_groups languages languages_in "
                             "detect_language "
                             "detect_min_words detect_among federated_extra tags_extra bubble "
                             "extra_minutes extra_posts rss_items rss_summary_chars "
                             "tags_one_request")),
    ("lists", _keys("lists", "enabled hide_members hide_in refresh_minutes")),
    ("reading", _keys("feed", "order start_at on_new page_size catch_up_limit render_limit "
                              "older_ahead remember_choices first_run_mark_read "
                              "stats")
     + _keys("read", "mark_read read_button dwell_ms unfocused_seconds")),
    ("card", _keys("feed", "show_reply_context thread_indent_max reply_context_chars "
                           "mute_tags_shown link_chars thread_news repeat_boosts quotes link_cards "
                           "old_days collapse_tags long_form sensitive_media around_post "
                           "why_home")
     + _keys("ui", "arts_mode expand_cw actions bookmark_button additional_highlight "
             "links_in_app")
     + _keys("feed", "show_moved honest_counters counts_minutes tag_click "
             "counters_via_accounts "
             "translate "
                     "translate_all translate_auto translate_backend translate_url "
                     "translate_key")),
    ("threads", _keys("feed", "complete_threads thread_from thread_recheck_minutes "
                              "thread_recheck_for_minutes "
                              "thread_followed_only thread_progress open_at "
                              "comment_ids")
     + _keys("subs", "auto interval_minutes active_days max_threads leave_mutes")),
    ("people", _keys("feed", "remote_profiles remote_people remote_posts server_info "
                             "profile_show profile_pinned profile_featured per_person_follow "
                             "follow_date_note forget_unfollowed following_max search_limit "
                             "home_hide aliases "
                             "nick_colors")),
    ("media", _keys("ui", "image_height media_grid alt_text image_viewer video_player "
                          "video_decode gifv gifv_max gifv_fps image_upscale save_dir")
     + _keys("feed", "prefetch")
     + _keys("ui", "image_cache_mb image_decode image_disk_mb video_disk_mb "
                   "unload_hidden_minutes keep_hidden_lanes")),
    ("post", _keys("post", "default_visibility send_timeout reply_never_wider drafts_autosave "
                           "autosave_ms cw_field reply_warning camelcase_hint plain_posts language "
                           "languages spellcheck "
                           "spell_languages complete_mentions complete_tags complete_emoji "
                           "report_forward quote_policy quote_action quote_prefix invite "
                           "who_can_reply who_can_boost who_can_like schedule alt_reminder "
                           "redraft resize_images focus_point chain preview format_bar lang_check "
                           "link_quote send_in_background scheduled_to_draft drafts_place")
     + _keys("account", "markdown")),
    ("notify", _keys("notify", "enabled lanes except privacy max_lines seconds when_focused "
                               "backend filtered")
     + _keys("ui", "announcements")),
    ("sound", _keys("sound", "enabled lanes except online sent when_focused scheme volume "
                             "player min_gap_seconds")),
    ("activity", _keys("activity", "types approvals requests my_follows names_shown unfollows "
                                   "unfollows_minutes unfollows_max unfollows_mass unlikes "
                                   "unlikes_days unlikes_posts server_notices "
                                   "server_groups")),
    ("accounts", _keys("ui", "merge switch_closes account_colors act_as")),
    ("sync", _keys("sync", "url folder webdav webdav_user interval_seconds read threads "
                           "lanes drafts activity tiles lane_rules people")
     + _keys("read", "sync_markers")),
    ("server", _keys("poll", "interval_seconds stream stream_gap_seconds slow_minutes "
                             "announcements_minutes")
     + _keys("net", "proxy proxy_at_login")),
    ("storage", _keys("storage", "max_mb keep_per_lane keep_activity gc_hours grace_hours")),
    ("debug", _keys("debug", "level mode log_dir log_mb keep_mb stats_minutes trim_memory "
                             "watchdog_seconds stall_ms slow_request_seconds rss_warn_mb "
                             "leak_samples object_census tracemalloc report_repo "
                             "issue_repo raw_json")),
    ("cli", _keys("cli", "enabled color max_lines tail_lanes")),
    ("tui", _keys("tui", "theme sound lanes_width show_context pictures picture_rows viewer "
                         "video")),
    ("web", _keys("web", "host port open_browser")),
    ("phone", _keys("phone", "overview layout push stream")),
)
# (internal section, key) → the file's table; (the file's table, key) → internal section
FILE_TABLE = {opt: table for table, opts in FILE_LAYOUT for opt in opts}
INTERNAL = {(table, key): section for table, opts in FILE_LAYOUT for section, key in opts}
FILE_TABLES = tuple(t for t, _o in FILE_LAYOUT)


def file_place(section, key):
    """Where the file keeps an option, named either way (the program's section or the
    file's table) → (table, key); as given when it is neither."""
    if (section, key) in INTERNAL:
        return section, key
    return FILE_TABLE.get((section, key), section), key


def internal_place(section, key):
    """The program's (section, key) of an option named either way."""
    if (section, key) in INTERNAL:
        return INTERNAL[(section, key)], key
    return section, key


def older_place(section, key):
    """Where a file of 0.20 and before had it (the program's section), when that isn't
    where the file keeps it now; else None."""
    inner = internal_place(section, key)
    return inner if file_place(*inner)[0] != inner[0] else None


# options taken out, as the file names them → what to say instead of "unknown"
# options taken out, by the names a file may give them (this layout's and 0.20's): what
# says it now, in place of "unknown key"
_RULES_SAY = "the lanes' rules say it now (lanes.preset, [[lanes.custom]]: docs/en/dev/feeds.md)"
GONE = {
    "reading.build_at_once": "reading.build_at_once is gone: only the cards near the screen "
                             "are built now, however long the lane (0.22)",
    "feed.build_at_once": "feed.build_at_once is gone: only the cards near the screen are "
                          "built now, however long the lane (0.22)",
    "lanes.mentions_all": f"lanes.mentions_all is gone (0.21): {_RULES_SAY}",
    "lanes.direct_apart": f"lanes.direct_apart is gone (0.21): {_RULES_SAY} — a private "
                          "post stays out of the other lanes while a lane of them is shown "
                          "(apart = \"direct\")",
    "lanes.bots_in_home": f"lanes.bots_in_home is gone (0.21): {_RULES_SAY}",
    "subs.replies_to_me": f"subs.replies_to_me is gone (0.21): {_RULES_SAY}",
    "threads.replies_to_me": f"threads.replies_to_me is gone (0.21): {_RULES_SAY}",
}


def from_file(user):
    """The file's tables (either layout) → ({section: {key: value}} as the program keeps
    them, [options found in their older places], [unknown keys of the file's tables]).
    An option set in both places: the file's own wins. A table neither layout knows
    stays as it is (validate says so)."""
    out, older, unknown, own = {}, [], [], set()
    for table, values in user.items():
        if not isinstance(values, dict):
            out[table] = values
            continue
        if table not in FILE_TABLES or table in DEFAULTS:
            out.setdefault(table, {})  # validate speaks of a table it doesn't know
        for key, val in values.items():
            if (table, key) in INTERNAL:
                section = INTERNAL[(table, key)]
                own.add((section, key))
            elif table in DEFAULTS:
                section = table  # the older layout — or an older name validate knows
                if key in DEFAULTS[table]:
                    if (section, key) in own:
                        continue
                    older.append(f"{table}.{key}")
            else:
                if table in FILE_TABLES:
                    unknown.append(f"{table}.{key}")
                    continue
                section = table
            out.setdefault(section, {})[key] = val
    return out, older, unknown


_INNER_NAME = re.compile(r"\b(ui|feed|read|subs|poll|account)\.([a-z_]+)\b")


def file_names(text):
    """Words about options with each named as the file names it now (ui.theme →
    appearance.theme) — what validate says is what the person finds in the file."""
    def one(m):
        table = FILE_TABLE.get((m.group(1), m.group(2)))
        return f"{table}.{m.group(2)}" if table else m.group(0)
    return _INNER_NAME.sub(one, text)


def to_file(cfg_like):
    """{section: {key: value}} the program's way → the file's tables (for rebuilding a
    file of the older layout)."""
    out = {}
    for section, values in cfg_like.items():
        if not isinstance(values, dict):
            out[section] = values
            continue
        for key, val in values.items():
            table = FILE_TABLE.get((section, key), section)
            out.setdefault(table, {})[key] = val
    return out


EXAMPLE_LANGS = ("ru", "en")


def example_name(lang):
    """The reference file's name for a language: config.example.ru.toml…"""
    return f"config.example.{lang}.toml"


def example_text(lang="ru"):
    """The reference config of this version: every option at its default with an
    explanation, in Russian or in English (the same options, values and order)."""
    if lang not in EXAMPLE_LANGS:
        lang = "en"
    return resources.files("fedtail").joinpath("data", example_name(lang)).read_text("utf-8")


_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")


def language_of(text, fallback="ru"):
    """Which language a config file's explanations are in: the first line says it
    ("конфиг профиля" / "profile config"); failing that, the comments' letters decide."""
    head = text.lstrip().split("\n", 1)[0]
    if "конфиг профиля" in head:
        return "ru"
    if "profile config" in head:
        return "en"
    comments = "".join(x for x in text.splitlines() if x.lstrip().startswith("#"))
    if not comments.strip():
        return fallback
    cyr = len(_CYRILLIC.findall(comments))
    return "ru" if cyr > len(comments) * 0.1 else "en"


def default_language():
    """The language a brand-new config is written in: Russian on a Russian desktop,
    English everywhere else."""
    from .. import i18n
    return "ru" if i18n.detect() == "ru" else "en"


def _type_name(v):
    return {bool: "true/false", int: "number", str: "string", list: "list"}.get(type(v), "value")


def validate(user):
    """Merge user config over defaults. Returns (config, warnings) or raises ConfigError."""
    cfg = copy.deepcopy(DEFAULTS)
    warnings, errors = [], []
    user, older, unknown = from_file(user)
    warnings += [GONE.get(name, f"unknown key {name} — ignored") for name in unknown]
    if older:
        warnings.append(f"options in their places of 0.20 and before: {', '.join(older[:6])}"
                        + (" …" if len(older) > 6 else "")
                        + " — `--rebuild-config` puts the file in the new chapters")
    for section, values in user.items():
        if section not in DEFAULTS:
            warnings.append(f"unknown section [{section}] — ignored")
            continue
        if not isinstance(values, dict):
            errors.append(f"[{section}] must be a section, not a value")
            continue
        for key, val in values.items():
            if (section, key) == ("sound", "enabled") and isinstance(val, bool):
                val = "on" if val else "off"  # the first 0.19 dev builds had true/false
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
            if (section, key) == ("sync", "what"):
                # 0.19: a switch of its own for each thing that travels
                if isinstance(val, list):
                    for k in SYNC_WHAT:
                        if k not in values:
                            cfg["sync"][k] = k in val
                warnings.append("sync.what is now a switch for each: sync.read, sync.threads, "
                                "sync.lanes, sync.drafts, sync.activity, sync.tiles")
                continue
            if section == "sync" and key in ("enabled", "backend"):
                # gone in 0.19: sync is on when it has somewhere to go (url or folder)
                warnings.append(f"sync.{key} is gone: sync works when sync.url or "
                                "sync.folder is set, and is off without them")
                continue
            if key not in DEFAULTS[section]:
                from .config_update import RENAMED
                if (section, key) in RENAMED:  # an older name: say what it is now
                    warnings.append(f"{section}.{key} is {section}.{RENAMED[(section, key)][0]} "
                                    "now — `--update-config` moves it")
                else:  # taken out: what says it now (GONE), else just unknown
                    warnings.append(GONE.get(f"{section}.{key}",
                                             f"unknown key {section}.{key} — ignored"))
                continue
            default = DEFAULTS[section][key]
            # bool is a subclass of int: check it strictly
            if type(val) is not type(default):
                errors.append(f"{section}.{key} must be {_type_name(default)}, got {val!r}")
                continue
            if (section, key) == ("lanes", "preset"):  # "own": before every lane was a rule
                val = presets.OLD_NAMES.get(val, val)
            if (section, key) == ("post", "format_bar") and val in ("auto", "on"):
                val = "left"  # 0.22 dev: on/off first, where they stand came after
            if (section, key) == ("ui", "layout") and val in ("qip", "columns"):
                # "qip" was split's old name; "columns" is no layout of its own: the single
                # window opening with its lanes side by side (ui.open_columns)
                if val == "columns":
                    cfg["ui"]["open_columns"] = True
                    warnings.append('ui.layout = "columns" is ui.layout = "single" with '
                                    "ui.open_columns = true now")
                val = "split" if val == "qip" else "single"
            choices = CHOICES.get((section, key))
            if choices and val not in choices:
                errors.append(f"{section}.{key} = {val!r}; allowed: {', '.join(sorted(choices))}")
                continue
            low = MINIMUM.get((section, key))
            if low is not None and val < low:
                errors.append(f"{section}.{key} must be at least {low}")
                continue
            cfg[section][key] = val

    # lanes by their names before 0.15 ("people", "comments"…) are the same lanes now
    from .lanes import canonical
    for section, key in LANE_LISTS:
        val = cfg[section][key]
        if isinstance(val, list) and all(isinstance(x, str) for x in val):
            cfg[section][key] = list(dict.fromkeys(canonical(x) for x in val))
        else:
            cfg[section][key] = canonical(val)
    # pairs that pick lanes (lanes.chosen): "all" in the first, "list:Друзья" in both
    wanted = cfg["notify"]["lanes"] + cfg["ui"]["icon_count"] + cfg["sound"]["lanes"]
    picking = wanted + cfg["notify"]["except"] + cfg["ui"]["icon_count_except"] + \
        cfg["sound"]["except"]
    # free lanes ([[lanes.custom]]) are named "custom:<name>" in these lists
    free = {canonical(str(c.get("name"))) for c in cfg["lanes"].get("custom") or []
            if isinstance(c, dict) and c.get("name")}
    bad = [x for x in cfg["lanes"]["enabled"] + cfg["lanes"]["posts_only"] +
           picking + cfg["lists"]["hide_in"]
           if x not in LANE_NAMES | {"lists"} and x not in free
           and not taggroups.is_tags(x)  # a lane of tags ("tags:…"), made in the window
           # notify.lanes = ["all"]: everything, the except list takes away
           and not (x == "all" and x in wanted)
           # one list: "list:Друзья" (its title, or its id)
           and not (x in picking and isinstance(x, str)
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
    vol = cfg["sound"]["volume"]
    if not 0 <= vol <= 100:
        errors.append(f"sound.volume = {vol}: from 0 to 100")
    from .remote import cleartext_ok
    url = cfg["sync"]["url"]
    # where a secret goes (the journal's, an invite code, a password, an API key):
    # https://, http:// only to a machine here or at home — the host as parsed, not a
    # prefix ("http://localhost.evil.example" isn't localhost)
    for section, key in (("sync", "url"), ("sync", "webdav"), ("feed", "translate_url")):
        where = str(cfg[section].get(key) or "")
        if where and not (where.startswith(("https://", "http://")) and cleartext_ok(where)):
            errors.append(f"{section}.{key} = {where!r}: https:// (http:// only to this "
                          "computer or one at home)")
    if url and cfg["sync"]["folder"]:
        errors.append("sync.url and sync.folder are both set: one place to meet, not two")
    if not isinstance(cfg["lanes"]["custom"], list):
        errors.append("lanes.custom: tables [[lanes.custom]], one per lane")
    else:
        from .custom import load as load_custom
        warnings += load_custom(cfg)[1]
    if not all(isinstance(x, str) for x in cfg["lanes"]["extra_bots"]):
        errors.append("lanes.extra_bots must be a list of strings")
    langs = [cfg["post"]["language"]] + cfg["post"]["languages"]
    bad_merge = [x for x in cfg["ui"]["merge"]
                 if not (isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", x))]
    if bad_merge:
        errors.append(f"ui.merge: {bad_merge} — profile names, or [\"all\"]")
    start = cfg["ui"]["start_lane"]
    if start not in {"none", "last"} | LANE_NAMES | free:
        errors.append(f"ui.start_lane = {start!r}; allowed: none, last or a lane: "
                      f"{', '.join(sorted(LANE_NAMES))}")
    bad_lang = [x for x in langs
                if x and not (isinstance(x, str) and re.fullmatch(r"[a-z]{2,3}", x))]
    if bad_lang:
        errors.append(f"post.language(s): {bad_lang} — two or three small letters (ISO 639), "
                      f"like \"ru\" or \"en\"")
    bad_read = [x for x in cfg["lanes"]["languages"]
                if not (isinstance(x, str) and re.fullmatch(r"[a-z]{2,3}", x))]
    if bad_read:
        errors.append(f"lanes.languages: {bad_read} — two or three small letters (ISO 639), "
                      f"like \"ru\" or \"en\"")
    bad_in = [x for x in cfg["lanes"]["languages_in"]
              if x not in LANE_NAMES | {"lists", "tags"}]
    if bad_in:
        errors.append(f"lanes.languages_in: unknown lanes {bad_in}; known: "
                      f"{', '.join(sorted(LANE_NAMES))}, lists, tags")
    errors = [file_names(e) for e in errors]
    warnings = [w if w.startswith("options in their places") else file_names(w)
                for w in warnings]
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


PROXY_SCHEMES = ("http", "https", "socks5", "socks5h", "socks4")
_PROXY_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy",
               "all_proxy")
_proxy_set = None  # the proxy this run put into the environment (net.proxy), or None


def proxy_ok(proxy):
    """"" or scheme://host:port with a scheme requests can speak (socks: PySocks)."""
    from urllib.parse import urlsplit
    proxy = (proxy or "").strip()
    if not proxy:
        return True
    try:
        p = urlsplit(proxy)
        return p.scheme in PROXY_SCHEMES and bool(p.hostname) and p.port is not None
    except ValueError:
        return False


def apply_proxy(cfg):
    """net.proxy: the whole of fedtail (the API, pictures, the stream, sync, login) goes
    through it — requests and urllib take it from the environment, so it is put there.
    "" leaves the environment as the system set it (and takes back one put there
    before, when the settings change it on the go)."""
    global _proxy_set
    import os
    proxy = str((cfg.get("net") or {}).get("proxy") or "").strip()
    if proxy and not proxy_ok(proxy):
        proxy = ""
    if proxy == (_proxy_set or ""):
        return
    for name in _PROXY_VARS:
        if proxy:
            os.environ[name] = proxy
        elif _proxy_set is not None and os.environ.get(name) == _proxy_set:
            del os.environ[name]
    _proxy_set = proxy or None


def load(path):
    """Read config file (creating the commented example if absent)."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(example_text(default_language()), "utf-8")
    try:
        with open(path, "rb") as f:
            user = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None
    cfg, warnings = validate(user)
    apply_proxy(cfg)
    return cfg, warnings
