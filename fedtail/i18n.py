"""Interface strings. Add a language by adding a dict with the same keys."""

import locale
import os

_STRINGS = {
    "ru": {
        "months": "янв фев мар апр мая июн июл авг сен окт ноя дек",
        # lanes
        "lane_people": "Люди", "lane_comments": "Комменты к моим", "lane_mentions": "Упоминания",
        "lane_bots": "Боты", "lane_mine": "Мои записи и комменты", "lane_local": "Локальная",
        "lane_requests": "Заявки", "lane_subs": "Подписки",
        "lists_header": "Списки", "list_new": "Новый список…", "list_name_q": "Название списка:",
        "list_rename": "Переименовать…", "list_delete": "Удалить список",
        "list_delete_q": "Удалить список «{title}»? Люди из него никуда не денутся.",
        "list_exclusive": "Исключающий",
        "list_exclusive_tip": "Кто в этом списке, того нет в «Людях» и «Ботах» — только здесь",
        "list_created": "Список «{title}» создан", "add_to_list": "В список",
        "list_added": "Добавил в список", "list_removed": "Убрал из списка",
        "sub_thread": "Подписаться на тред", "unsub_thread": "Отписаться от треда",
        "subscribed": "Подписан", "subbed": "Подписался: новое в треде будет в «Подписках»",
        "unsubbed": "Отписался: тред больше не придёт, даже если ты в нём напишешь",
        "sub_tip": "Новые комменты в этом треде — в ленту «Подписки», как на Point",
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
        "find_placeholder": "Найти в ленте: текст, имя, @ник, #id…",
        "find_prev": "Предыдущее (Shift+Enter, Shift+F3)",
        "find_next": "Следующее (Enter, F3)", "find_close": "Закрыть (Esc)",
        "find_none": "не найдено в загруженном", "find_count": "{i} из {n}",
        "find_deeper": "Глубже", "find_searching": "ищу в архиве…",
        "find_deeper_tip": "Искать во всём, что сохранено для этой ленты, и подгрузить "
                           "ленту до найденного",
        "find_archive_none": "и в архиве нет; «Ещё старее» внизу ленты подтянет с сервера",
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
        "media_tip": "Двойной клик — подпись к картинке (alt). "
                     "Картинки можно перетаскивать сюда и вставлять Ctrl+V",
        "viewer_title": "Картинка",
        "viewer_keys": "← → или колесо — листать · двойной клик/Z — 1:1 · "
                       "S — сохранить · O — в браузере · Esc/клик — закрыть",
        "save_image": "Сохранить картинку", "saved_to": "Сохранено: {path}",
        "save_failed": "Не сохранилось: {err}",
        "attach": "Приложить…", "detach": "Убрать", "discard": "Выкинуть",
        "close": "Закрыть", "close_tip": "Закрыть окно, черновик останется",
        "camel_hint": "♿ {tags}: напиши с большими буквами внутри слов (#GeorgiaNews) — "
                      "экранные дикторы прочтут по словам, а не одной кашей",
        "cw_add": "Предупреждение", "alt_set": "есть подпись",
        "cw_add_tip": "Спрятать текст под предупреждение (CW): его покажут по кнопке",
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
        "notify_comments_n": ["{n} новый коммент к твоим", "{n} новых коммента к твоим",
                              "{n} новых комментов к твоим"],
        "notify_mentions_n": ["{n} новое упоминание", "{n} новых упоминания",
                              "{n} новых упоминаний"],
        "notify_requests_n": ["{n} новая заявка в подписчики", "{n} новые заявки в подписчики",
                              "{n} новых заявок в подписчики"],
        "notify_lane_n": ["{n} новый пост в ленте «{lane}»", "{n} новых поста в ленте «{lane}»",
                          "{n} новых постов в ленте «{lane}»"],
        "notify_comments_one": "Коммент от {name}", "notify_mentions_one": "Упоминание от {name}",
        "notify_requests_one": "Просится в подписчики: {name}",
        "notify_lane_one": "{name} в ленте «{lane}»", "notify_from": "от {names}",
        "notify_act_favourite_n": ["★ {n} в избранное", "★ {n} в избранное", "★ {n} в избранное"],
        "notify_act_reblog_n": ["⟳ {n} продвижение", "⟳ {n} продвижения", "⟳ {n} продвижений"],
        "notify_act_follow_n": ["{n} новый подписчик", "{n} новых подписчика",
                                "{n} новых подписчиков"],
        "notify_act_other_n": ["{n} событие", "{n} события", "{n} событий"],
        "lane_activity": "Активность", "activity_none": "Пока никто ничего.",
        "act_favourite": "★ в избранное", "act_reblog": "⟳ продвижение",
        "act_follow": "подписка на тебя", "act_poll": "опрос закончился",
        "act_update": "пост изменён", "act_status": "новый пост",
        "act_more": "и ещё {n}",
        "open_action": "Открыть",
        "notify_more": " (и ещё {n})",
        "new_options": "В конфиге не упомянуто новых опций: {n}. "
                       "Запусти python3 -m fedtail --update-config — "
                       "допишет их закомментированными.",
        "deleted": "Удалено.", "sent": "Отправлено.", "error": "Ошибка: {err}",
        "not_in_cache": "Этого поста нет в кеше — обнови ленту.",
        "delete_q_title": "Удалить?", "delete_q": "Удалить пост насовсем?\n\n{text}",
        "about_text": "<b>fedtail {version}</b><br>Клиент федиверса для тех, кто помнит Point."
                      "<br>Лицензия GPL-3.0-or-later.",
        "made_by": "написан нейросетью Claude<br>под присмотром кожаного мешка",
        "made_by_long": "Код написан нейросетью Claude (Anthropic) — от первой строки до "
                        "иконки. Кожаный мешок придумывал, тестировал и ругался.",
        "about_build": "Сборка: {commit}, {date}", "about_env": "Python {py} · Qt {qt}",
        "about_profile": "Профиль «{profile}»: {acct} на {server}",
        "debug_menu": "Отладка", "debug_logs": "Открыть папку логов",
        "debug_report": "Собрать отчёт для разбора",
        "debug_stacks": "Записать стеки потоков и статистику",
        "debug_stacks_done": "Записано в журнал",
        "debug_report_done": "Отчёт: {path} — его и присылай (токена и базы там нет)",
        "follow": "Подписаться", "unfollow": "Отписаться", "follow_requested": "Запрос отправлен",
        "mention": "Упомянуть", "acc_locked": "подписка по одобрению",
        "acc_since": "с {date}", "acc_follows_you": "читает тебя",
        "tag_info": "посты с этим тегом, какие знает твой сервер",
        "resolving": "Ищу через свой сервер: {url}",
        "resolve_browser": "Не нашлось — открываю в браузере",
        "my_profile": "Мой профиль", "edit_profile": "Редактировать профиль",
        "profile_title": "Профиль", "profile_name": "Имя", "profile_bio": "О себе",
        "profile_fields": "Поля профиля (сайт, где ещё искать, …)",
        "field_name": "название", "field_value": "значение",
        "profile_locked": "Подтверждать новых подписчиков вручную",
        "profile_bot": "Это бот (автоматический аккаунт)",
        "profile_discoverable": "Показывать в каталоге профилей и рекомендациях",
        "no_header": "шапки нет", "image_loading": "картинка грузится…",
        "image_failed": "картинка не загрузилась — клик откроет",
        "change_avatar": "Сменить аватар…", "change_header": "Сменить шапку…",
        "cancel": "Отмена", "save": "Сохранить", "saving": "сохраняю…",
        "profile_saved": "Профиль сохранён",
        "posts_n": ["{n} пост", "{n} поста", "{n} постов"],
        "followers_n": ["{n} подписчик", "{n} подписчика", "{n} подписчиков"],
        "following_n": ["{n} подписка", "{n} подписки", "{n} подписок"],
    },
    "en": {
        "months": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
        "lane_people": "People", "lane_comments": "Replies to me", "lane_mentions": "Mentions",
        "lane_bots": "Bots", "lane_mine": "My posts & replies", "lane_local": "Local",
        "lane_requests": "Follow requests", "lane_subs": "Subscriptions",
        "lists_header": "Lists", "list_new": "New list…", "list_name_q": "List name:",
        "list_rename": "Rename…", "list_delete": "Delete list",
        "list_delete_q": "Delete the list “{title}”? The people in it stay where they are.",
        "list_exclusive": "Exclusive",
        "list_exclusive_tip": "Whoever is in this list is not in People and Bots — only here",
        "list_created": "List “{title}” created", "add_to_list": "Add to list",
        "list_added": "Added to the list", "list_removed": "Removed from the list",
        "sub_thread": "Follow thread", "unsub_thread": "Unfollow thread",
        "subscribed": "Following", "subbed": "Following: new comments go to Subscriptions",
        "unsubbed": "Unfollowed: this thread won't come back, even if you comment in it",
        "sub_tip": "New comments in this thread go to the Subscriptions lane, like on Point",
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
        "find_placeholder": "Find in this lane: text, name, @handle, #id…",
        "find_prev": "Previous (Shift+Enter, Shift+F3)",
        "find_next": "Next (Enter, F3)", "find_close": "Close (Esc)",
        "find_none": "not found in what's loaded", "find_count": "{i} of {n}",
        "find_deeper": "Deeper", "find_searching": "searching the archive…",
        "find_deeper_tip": "Search everything stored for this lane and load the lane down to "
                           "the match",
        "find_archive_none": "not in the archive either; \"Older\" at the lane's end asks "
                             "the server",
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
        "media_tip": "Double-click to describe (alt text). Drop pictures here or paste with Ctrl+V",
        "viewer_title": "Image",
        "viewer_keys": "← → or wheel: flip · double-click/Z: 1:1 · "
                       "S: save · O: browser · Esc/click: close",
        "save_image": "Save picture", "saved_to": "Saved: {path}",
        "save_failed": "Couldn't save: {err}",
        "attach": "Attach…", "detach": "Remove", "discard": "Discard",
        "close": "Close", "close_tip": "Close the window, the draft stays",
        "camel_hint": "♿ {tags}: capitalise the words inside (#GeorgiaNews) — screen "
                      "readers will read it word by word, not as one mumble",
        "cw_add": "Content warning", "alt_set": "described",
        "cw_add_tip": "Hide the text behind a warning (CW); readers open it with a click",
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
        "notify_comments_n": ["{n} new reply to you", "{n} new replies to you"],
        "notify_mentions_n": ["{n} new mention", "{n} new mentions"],
        "notify_requests_n": ["{n} new follow request", "{n} new follow requests"],
        "notify_lane_n": ["{n} new post in “{lane}”", "{n} new posts in “{lane}”"],
        "notify_comments_one": "Reply from {name}", "notify_mentions_one": "Mention from {name}",
        "notify_requests_one": "Wants to follow you: {name}",
        "notify_lane_one": "{name} in “{lane}”", "notify_from": "from {names}",
        "notify_act_favourite_n": ["★ {n} favourite", "★ {n} favourites"],
        "notify_act_reblog_n": ["⟳ {n} boost", "⟳ {n} boosts"],
        "notify_act_follow_n": ["{n} new follower", "{n} new followers"],
        "notify_act_other_n": ["{n} event", "{n} events"],
        "lane_activity": "Activity", "activity_none": "Nothing yet.",
        "act_favourite": "★ favourited", "act_reblog": "⟳ boosted",
        "act_follow": "followed you", "act_poll": "poll ended",
        "act_update": "post edited", "act_status": "new post",
        "act_more": "and {n} more",
        "open_action": "Open",
        "notify_more": " (and {n} more)",
        "new_options": "Your config doesn't mention {n} new option(s). "
                       "Run python3 -m fedtail --update-config to add them, commented out.",
        "deleted": "Deleted.", "sent": "Sent.", "error": "Error: {err}",
        "not_in_cache": "This post is not cached — refresh the lane.",
        "delete_q_title": "Delete?", "delete_q": "Delete this post for good?\n\n{text}",
        "about_text": "<b>fedtail {version}</b><br>A fediverse client for people who miss Point."
                      "<br>License GPL-3.0-or-later.",
        "made_by": "written by Claude, an AI<br>supervised by a meatbag",
        "made_by_long": "The code is written by Claude (Anthropic), an AI — from the first "
                        "line to the icon. A meatbag came up with it, tested it and swore.",
        "about_build": "Build: {commit}, {date}", "about_env": "Python {py} · Qt {qt}",
        "about_profile": "Profile “{profile}”: {acct} at {server}",
        "debug_menu": "Debugging", "debug_logs": "Open the logs folder",
        "debug_report": "Make a report for diagnosis",
        "debug_stacks": "Write thread stacks and stats",
        "debug_stacks_done": "Written to the log",
        "debug_report_done": "Report: {path} — send that one (no token, no database inside)",
        "follow": "Follow", "unfollow": "Unfollow", "follow_requested": "Requested",
        "mention": "Mention", "acc_locked": "approves followers",
        "acc_since": "since {date}", "acc_follows_you": "follows you",
        "tag_info": "posts with this tag that your server knows",
        "resolving": "Looking it up through your server: {url}",
        "resolve_browser": "Not found — opening in the browser",
        "my_profile": "My profile", "edit_profile": "Edit profile",
        "profile_title": "Profile", "profile_name": "Name", "profile_bio": "About me",
        "profile_fields": "Profile fields (website, where else to find you, …)",
        "field_name": "label", "field_value": "content",
        "profile_locked": "Approve new followers by hand",
        "profile_bot": "This is a bot (automated account)",
        "profile_discoverable": "Show in the profile directory and suggestions",
        "no_header": "no header", "image_loading": "loading picture…",
        "image_failed": "picture didn't load — click to open",
        "change_avatar": "Change avatar…", "change_header": "Change header…",
        "cancel": "Cancel", "save": "Save", "saving": "saving…",
        "profile_saved": "Profile saved",
        "posts_n": ["{n} post", "{n} posts"],
        "followers_n": ["{n} follower", "{n} followers"],
        "following_n": ["{n} following", "{n} following"],
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
