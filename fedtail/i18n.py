"""Interface strings. Add a language by adding a dict with the same keys."""

import locale
import os

_STRINGS = {
    "ru": {
        "months": "янв фев мар апр мая июн июл авг сен окт ноя дек",
        # lanes
        "lane_people": "Люди", "lane_comments": "Комменты к моим", "lane_mentions": "Упоминания",
        "lane_bots": "Боты", "lane_mine": "Мои записи и комменты", "lane_local": "Локальная",
        "lane_requests": "Заявки",
        # visibility
        "vis_public": "🌐 Публично", "vis_unlisted": "🔓 Не в общих лентах",
        "vis_private": "🔒 Только подписчикам", "vis_direct": "✉ Лично упомянутым",
        # media
        "media_video": "видео", "media_audio": "аудио", "media_image": "картинка",
        "media_gifv": "гифка", "media_unknown": "файл",
        # card
        "boosted_by": "♻ {name} продвинул", "bot": "бот",
        "ctx_loading": "в ответ на… (загружаю)",
        "ctx_missing": "в ответ на пост, который мне не виден",
        "ctx_reply": "в ответ {name}: «{text}»",
        "cw_show": "показать", "cw_hide": "скрыть",
        "reply": "Ответить", "thread": "Тред", "delete": "Удалить",
        "faved": "В избранном", "boosted": "Продвинуто", "more": "Ещё",
        "copy_link": "Скопировать ссылку", "copy_id": "Скопировать {id}",
        "short_id_tip": "Короткий номер поста — для командной строки, как #abc на Point",
        "unread_tip": "Новое", "came_from": "ты пришёл отсюда",
        "to_new": "К новому", "show_all": "Всё", "new_n": ["{n} новое", "{n} новых", "{n} новых"],
        "new_below": "дальше новое", "menu": "Меню", "open_themes": "Открыть папку тем",
        "you_replied": "ты ответил {when}: «{text}»",
        "fav": "В избранное", "unfav": "убрать из избранного", "boost": "Продвинуть",
        "unboost": "отменить продвижение", "open_browser": "открыть в браузере",
        # feed
        "posts_only": "Только посты", "posts_only_tip": "Скрыть комментарии и ответы",
        "to_first_unread": "↧ к первому новому", "mark_all_read": "Всё прочитано",
        "older_up": "▲ раньше", "older_down": "▼ раньше", "no_older": "раньше ничего нет",
        "unread_n": ["{n} новое", "{n} новых", "{n} новых"], "all_read": "всё прочитано",
        "thread_loading": "тред…",
        "thread_info": ["пост и {n} ответ", "пост и {n} ответа", "пост и {n} ответов"],
        "loading": "загружаю…", "load_failed": "не загрузилось: {err}", "refresh": "Обновить",
        "no_requests": "Заявок нет.", "profile": "профиль",
        "approve": "✔ пустить", "reject": "✘ отказать",
        # compose
        "compose_new": "Новый пост", "compose_reply": "Ответ",
        "cw_placeholder": "Предупреждение / заголовок под катом (можно пусто)",
        "text_placeholder": "Пиши.", "text_placeholder_md": "Пиши. Markdown работает.",
        "media_tip": "Двойной клик — подпись к картинке (alt)",
        "viewer_title": "Картинка",
        "viewer_keys": "← → или колесо — листать · двойной клик/Z — 1:1 · "
                       "O — в браузере · Esc/клик — закрыть",
        "attach": "Приложить…", "detach": "Убрать", "discard": "Выкинуть",
        "close": "Закрыть", "close_tip": "Закрыть окно, черновик останется",
        "boost_time": "продвинуто {when}",
        "send": "Отправить (Ctrl+Enter)", "sending": "Отправляю…",
        "draft_restored": "Восстановлен черновик.", "draft_saved": "Черновик сохранён.",
        "discard_q_title": "Выкинуть?", "discard_q": "Выкинуть этот текст насовсем?",
        "no_alt": "без подписи", "media_limit": "Сервер разрешает не больше {n} вложений.",
        "media_files": "Картинки, видео, звук",
        "alt_title": "Подпись", "alt_prompt": "Что на картинке (для тех, кто её не видит):",
        "send_failed": "Не отправилось",
        "send_failed_text": "{err}\n\nТекст сохранён в черновике, можно повторить.",
        # login
        "login_title": "Вход — профиль {profile}", "login_server": "Адрес сервера:",
        "login_step1": "1. Открыть страницу входа в браузере",
        "login_hint": "Залогинься там, разреши доступ и вставь сюда показанный код:",
        "login_step2": "2. Войти",
        "login_browser_opened": "Браузер открыт. Если не открылся — вот ссылка:\n{url}",
        # window
        "write": "Написать", "menu_file": "&Файл", "menu_help": "&Справка",
        "open_config": "Открыть конфиг", "open_data": "Открыть папку данных",
        "relogin": "Перелогиниться…", "quit": "Выход", "about": "О программе", "show": "Показать",
        "connecting": "Подключаюсь…", "connected": "@{acct} на {server}",
        "server_down": "Сервер не отвечает: {err}. Попробую ещё раз через 20 секунд.",
        "auth_failed_title": "Сервер не пускает",
        "auth_failed": "Токен больше не принимается. Залогинься заново.",
        "tray_new": "{title} — новых: {n}",
        "notify_comment": "Коммент к твоему", "notify_mention": "Упоминание",
        "notify_more": " (и ещё {n})",
        "new_options": "В конфиге не упомянуто новых опций: {n}. "
                       "Запусти python3 -m fedtail --update-config — "
                       "допишет их закомментированными.",
        "deleted": "Удалено.", "sent": "Отправлено.", "error": "Ошибка: {err}",
        "not_in_cache": "Этого поста нет в кеше — обнови ленту.",
        "delete_q_title": "Удалить?", "delete_q": "Удалить пост насовсем?\n\n{text}",
        "about_text": "<b>fedtail {version}</b><br>Клиент федиверса для тех, кто помнит Point."
                      "<br>Лицензия GPL-3.0-or-later.",
    },
    "en": {
        "months": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
        "lane_people": "People", "lane_comments": "Replies to me", "lane_mentions": "Mentions",
        "lane_bots": "Bots", "lane_mine": "My posts & replies", "lane_local": "Local",
        "lane_requests": "Follow requests",
        "vis_public": "🌐 Public", "vis_unlisted": "🔓 Unlisted",
        "vis_private": "🔒 Followers only", "vis_direct": "✉ Mentioned only",
        "media_video": "video", "media_audio": "audio", "media_image": "image",
        "media_gifv": "gif", "media_unknown": "file",
        "boosted_by": "♻ boosted by {name}", "bot": "bot",
        "ctx_loading": "in reply to… (loading)",
        "ctx_missing": "in reply to a post I can't see",
        "ctx_reply": "in reply to {name}: “{text}”",
        "cw_show": "show", "cw_hide": "hide",
        "reply": "Reply", "thread": "Thread", "delete": "Delete",
        "faved": "Favourited", "boosted": "Boosted", "more": "More",
        "copy_link": "Copy link", "copy_id": "Copy {id}",
        "short_id_tip": "Short post number — for the command line, like #abc on Point",
        "unread_tip": "New", "came_from": "you came from here",
        "to_new": "To new", "show_all": "All", "new_n": ["{n} new", "{n} new"],
        "new_below": "new below", "menu": "Menu", "open_themes": "Open themes folder",
        "you_replied": "you replied {when}: “{text}”",
        "fav": "Favourite", "unfav": "unfavourite", "boost": "Boost",
        "unboost": "undo boost", "open_browser": "open in browser",
        "posts_only": "Posts only", "posts_only_tip": "Hide replies",
        "to_first_unread": "↧ first unread", "mark_all_read": "Mark all read",
        "older_up": "▲ older", "older_down": "▼ older", "no_older": "nothing older",
        "unread_n": ["{n} unread", "{n} unread"], "all_read": "all read",
        "thread_loading": "thread…", "thread_info": ["post and {n} reply", "post and {n} replies"],
        "loading": "loading…", "load_failed": "failed to load: {err}", "refresh": "Refresh",
        "no_requests": "No follow requests.", "profile": "profile",
        "approve": "✔ accept", "reject": "✘ reject",
        "compose_new": "New post", "compose_reply": "Reply",
        "cw_placeholder": "Content warning / summary (optional)",
        "text_placeholder": "Write.", "text_placeholder_md": "Write. Markdown works.",
        "media_tip": "Double-click to add a description (alt text)",
        "viewer_title": "Image",
        "viewer_keys": "← → or wheel: flip · double-click/Z: 1:1 · "
                       "O: browser · Esc/click: close",
        "attach": "Attach…", "detach": "Remove", "discard": "Discard",
        "close": "Close", "close_tip": "Close the window, the draft stays",
        "boost_time": "boosted {when}",
        "send": "Send (Ctrl+Enter)", "sending": "Sending…",
        "draft_restored": "Draft restored.", "draft_saved": "Draft saved.",
        "discard_q_title": "Discard?", "discard_q": "Throw this text away for good?",
        "no_alt": "no description", "media_limit": "The server allows at most {n} attachments.",
        "media_files": "Images, video, audio",
        "alt_title": "Description",
        "alt_prompt": "What's in the image (for those who can't see it):",
        "send_failed": "Not sent",
        "send_failed_text": "{err}\n\nThe text is kept as a draft, you can retry.",
        "login_title": "Log in — profile {profile}", "login_server": "Server address:",
        "login_step1": "1. Open the login page in the browser",
        "login_hint": "Log in there, allow access and paste the code you get here:",
        "login_step2": "2. Log in",
        "login_browser_opened": "Browser opened. If it didn't, here's the link:\n{url}",
        "write": "Write", "menu_file": "&File", "menu_help": "&Help",
        "open_config": "Open config", "open_data": "Open data folder",
        "relogin": "Log in again…", "quit": "Quit", "about": "About", "show": "Show",
        "connecting": "Connecting…", "connected": "@{acct} on {server}",
        "server_down": "Server is not answering: {err}. Retrying in 20 seconds.",
        "auth_failed_title": "Access denied",
        "auth_failed": "The token is no longer accepted. Please log in again.",
        "tray_new": "{title} — new: {n}",
        "notify_comment": "Reply to you", "notify_mention": "Mention",
        "notify_more": " (and {n} more)",
        "new_options": "Your config doesn't mention {n} new option(s). "
                       "Run python3 -m fedtail --update-config to add them, commented out.",
        "deleted": "Deleted.", "sent": "Sent.", "error": "Error: {err}",
        "not_in_cache": "This post is not cached — refresh the lane.",
        "delete_q_title": "Delete?", "delete_q": "Delete this post for good?\n\n{text}",
        "about_text": "<b>fedtail {version}</b><br>A fediverse client for people who miss Point."
                      "<br>License GPL-3.0-or-later.",
    },
}

_lang = "en"


def detect():
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var)
        if v:
            return v[:2].lower()
    try:
        return (locale.getlocale()[0] or "en")[:2].lower()
    except ValueError:
        return "en"


def setup(language="auto"):
    global _lang
    lang = detect() if language == "auto" else language
    _lang = lang if lang in _STRINGS else "en"


def _plural_index(lang, n):
    n = abs(int(n))
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return 0
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return 1
        return 2
    return 0 if n == 1 else 1


def _(key, **kw):
    lang = _lang if key in _STRINGS[_lang] else "en"
    s = _STRINGS[lang].get(key) or key
    if isinstance(s, list):  # plural forms, chosen by n
        s = s[min(_plural_index(lang, kw.get("n", 0)), len(s) - 1)]
    return s.format(**kw) if kw else s


def months():
    return _("months").split()


def keys(lang):
    return set(_STRINGS[lang])
