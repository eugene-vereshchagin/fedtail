# Что умеет fedtail и чего пока нет

[English summary below](#english)

Состояние на версию **0.10.0** (17.10.2026). Рядом — что умеют другие клиенты: **M** — Mastodon
web, **T** — Tusky, **I** — Ivory, **P** — Phanpy, **E** — Elk, **K** — Tokodon. Про чужие
клиенты — по знаниям на середину 2026 года, без проверки каждого вживую. Что из этого
поддерживает конкретный сервер (особенно GoToSocial), проверяй на своей ноде: fedtail
сам прячет то, чего сервер не умеет.

Главный принцип: **любое поведение — пункт в конфиге.** В колонке «Конфиг» — где оно
включается и выключается (`секция.ключ`, полный справочник — `config.example.toml`).

Статусы: **есть** · **частично** · **нет** · **в планах** · **не будем**.
⭐ — так больше ни у кого из перечисленных.

Таблица обновляется вместе с кодом: сделал пункт — поправь строку здесь и в CHANGELOG.

## Чтение

| Что | Статус | Конфиг | API / протокол | У других |
|---|---|---|---|---|
| Home, Локальная, Федерация | есть | `lanes.enabled` | timelines/home, public | все |
| ⭐ Боты отдельной лентой | есть | `lanes.enabled`, `lanes.extra_bots` | `account.bot` | — |
| Списки как ленты: создать, переименовать, исключающие | есть | `[lists]` | lists, timelines/list | M T I P E K |
| ⭐ Кто в списке — уходит из общих лент вместе с бустами | есть | `lists.hide_members`, `lists.hide_in` | своё | — |
| Лента хэштега, подписка на теги | есть | — | timelines/tag, tags/:name/follow | все |
| «Мои лайки» | есть | `"favourites"` в `lanes.enabled` | /api/v1/favourites | M T I |
| Личные сообщения отдельной лентой | есть | `"direct"` в `lanes.enabled`, `lanes.direct_apart` | visibility=direct | все |
| ⭐ Тред деревом, комменты с номерами `/1 /2` | есть | — | statuses/:id/context | P — отступами |
| ⭐ Тред целиком: ответы с сервера автора | есть | `feed.complete_threads` | ActivityPub replies + search resolve | M 4.5+ на сервере |
| Тред дорастает, когда Mastodon 4.5+ дособрал ответы | есть | `feed.complete_threads` | заголовок `Mastodon-Async-Refresh` | M |
| ⭐ Подписки на треды, как `S #abc` на Point | есть | `[subs]` | своё | — |
| Режим «Беседами» (тред одной карточкой) | есть | `feed.remember_choices` | своё | P — похоже |
| Всё / Только посты / Новое над лентой | есть | `lanes.posts_only`, `feed.remember_choices` | своё | — |
| Позиция чтения общая с другими клиентами | есть | `read.sync_markers` | /api/v1/markers | M T I P |
| ⭐ Порядок «старое сверху», ничего не прыгает | есть | `feed.order`, `feed.start_at`, `feed.on_new` | своё | — |
| Карточки ссылок | есть | `feed.link_cards` = full / text / off | `status.card` | все |
| Эмодзи серверов картинками | есть | `feed.custom_emoji` | `emojis` у поста и аккаунта | все |
| Цитаты: показ | есть | `feed.quotes` = card / link / off | `status.quote` | M 4.5+ I P E |
| Чувствительные картинки под шторкой | есть | `feed.sensitive_media` | `status.sensitive` | все |
| CW разворачиваются сами | есть | `ui.expand_cw` | `spoiler_text` | настраивается у всех |
| ⭐ Режим «искусство»: CW, шторки, фильтры сервера и «Пожаловаться» — разом прочь | есть | `ui.arts_mode` (вкл. по умолчанию) | — | нет ни у кого одним переключателем |
| Опросы: смотреть, голосовать | есть | — | polls/:id, votes | все |
| История правок | есть | — | statuses/:id/history | M I P E |
| Перевод поста сервером | есть | `feed.translate` | statuses/:id/translate | M I P E |
| Закреплённые посты в профиле | есть | `feed.profile_pinned` | statuses?pinned=true | все |
| Рекомендуемые теги и люди в профиле | есть | `feed.profile_featured` | featured_tags, endorsements | M |
| ⭐ Профиль малознакомого человека дополняется с его сервера | есть | `feed.remote_profiles`, `feed.remote_posts` | ActivityPub outbox | — |
| ⭐ Подписчики и подписки с сервера человека | есть | `feed.remote_people` | ActivityPub followers / following | — |
| ⭐ Честные счётчики лайков и бустов | есть | `feed.honest_counters` (выкл.) | API сервера автора без токена | — |
| Объявления сервера | есть | `ui.announcements` | /api/v1/announcements | M P E |
| Живой поток вместо ожидания опроса | есть | `poll.stream`, `poll.interval_seconds` | streaming (WebSocket) | M P E K |
| ⭐ Поиск по ленте Ctrl+F (текст, ник, `#id`, подписи) | есть | — | своё, по локальной базе | — |
| Ссылки на посты и профили открываются внутри | есть | `ui.links_in_app` | search?resolve=true | I P E |
| Картинки: просмотрщик, сохранение, сетка | есть | `ui.image_viewer`, `ui.save_dir`, `ui.media_grid` | — | все |
| Подписи к картинкам (alt) | есть | `ui.alt_text` | `description` | все |
| Видео и аудио внутри окна; гифки крутятся в ленте | есть | `ui.video_player`, `ui.gifv` | media_attachments | все |
| Сгруппированные уведомления | частично | `activity.types` | /api/v2/notifications | M I P |
| Коллекции (Mastodon 4.6) | нет | — | /api/v1/collections | M 4.6 |
| Тренды, рекомендации, каталог | не будем | — | trends, suggestions, directory | M I P E |

Видео сейчас показывается кадром с ▶, играет браузер. Уведомления о лайках и бустах fedtail
группирует сам в ленте «Лайки и бусты», серверную группировку v2 не использует.
Тренды — не наш стиль: в ленте то, на что подписался.

## Писать

| Что | Статус | Конфиг | API / протокол | У других |
|---|---|---|---|---|
| Панель поста внутри окна, черновики | есть | `ui.compose`, `post.drafts_autosave` | statuses | все |
| ⭐ Ответ не шире исходного, по умолчанию «подписчикам» | есть | `post.reply_never_wider`, `post.default_visibility` | visibility | — |
| Markdown, где сервер умеет | есть | `account.markdown`, `post.plain_posts` | content_type | GTS, Akkoma |
| Картинки: перетащить, вставить, подпись | есть | `post.alt_reminder` | /api/v2/media | все |
| Фокус картинки | есть | `post.focus_point` | focus | M I |
| Пометить свои картинки чувствительными | есть | — | sensitive | все |
| Дополнение `#тегов` | есть | `post.complete_tags` | своё + подписки на теги | все |
| Дополнение `@ников` | есть | `post.complete_mentions` | accounts/search | все |
| Дополнение `:эмодзи:` | есть | `post.complete_emoji` | /api/v1/custom_emojis | все |
| ⭐ Подсказка CamelCase для хэштегов | есть | `post.camelcase_hint` | своё | — |
| Язык поста | есть | `post.language`, `post.languages` | language | все |
| Опрос в посте | есть | — | poll[options] | все |
| Цитировать пост; кто может цитировать мои | есть | `post.quote_action`, `post.quote_policy` | quoted_status_id, quote_approval_policy | M 4.5+ I P |
| Кто может отвечать, бустить, лайкать (GoToSocial) | есть | `post.who_can_reply`, `post.who_can_boost`, `post.who_can_like` | interaction_policy | GTS-клиенты |
| Отложенный пост | есть | `post.schedule` | scheduled_at, scheduled_statuses | M I P |
| Редактировать, удалить свой пост | есть | — | PUT statuses/:id, source | все |
| Закрепить свой пост | есть | — | statuses/:id/pin | все |
| ⭐ Командная строка как на Point (`#a3f текст`, `S #a3f`, `@ник`) | есть | `ui.command_line` | своё | — |

## Люди и порядок

| Что | Статус | Конфиг | API / протокол | У других |
|---|---|---|---|---|
| Подписки, заявки в подписчики | есть | — | follow, follow_requests | все |
| Скрыть, заблокировать, фильтры слов | есть | — | mutes, blocks, /api/v2/filters | все |
| Заблокировать целый сервер | есть | — | /api/v1/domain_blocks | M I P |
| Пожаловаться модераторам | есть | `post.report_forward` | /api/v1/reports | все |
| Личная заметка о человеке | есть | — | accounts/:id/note | M I |
| Колокольчик на посты человека | есть | `activity.types` | follow notify=true | M T I |
| Уведомления от незнакомцев — отдельно | есть | `notify.filtered` | /api/v2/notifications/policy, requests | M 4.3+ |
| Свой профиль: имя, о себе, поля, аватар | есть | — | update_credentials | M I P E K |

## Приложение

| Что | Статус | Конфиг | У других |
|---|---|---|---|
| ⭐ Уведомления рабочего стола с уровнями приватности | есть | `[notify]`: `lanes`, `privacy`, `when_focused` | K — без приватности |
| Число непрочитанного на иконке и в трее | есть | `ui.icon_count`, `ui.themed_icon` | K |
| Esc закрывает ленты, а не окно; трей | есть | `ui.esc`, `ui.close_to_tray` | — |
| С чего начинать при запуске | есть | `ui.start_lane` | — |
| Несколько аккаунтов; все в одном окне | есть | `ui.merge`, `ui.switch_closes` | I P E K |
| ⭐ Темы файлами: Juick, Point, BnW, терминал и др. | есть | `ui.theme` | светлая и тёмная у всех |
| Всё хранится локально, читается без сети | есть | — | T — частично |
| Открыт сутками без раздувания: давно не открытые ленты отпускают карточки | есть | `ui.unload_hidden_minutes`, `ui.image_cache_mb` | — |
| Клавиши j/k по постам, r/f/b/m/o | есть | `ui.post_keys` | M P E I |
| Экранные дикторы | частично | `ui.alt_text` | M T I |
| ⭐ Конфиг файлом по главам, без окна настроек | есть | `--update-config`, `--rebuild-config` | — |
| Подробный журнал для отчётов об ошибках; логи старой версии удаляются сами | есть | `[debug]` | — |
| Linux: из исходников, одним файлом, deb-пакет | есть | — | K |
| Windows: один .exe | есть | — | M P E — в браузере |

Подписи к картинкам и имена кнопок для дикторов есть, но вживую с Orca интерфейс не проверяли.

## Интерфейсы

| Что | Статус | Конфиг | Заметка |
|---|---|---|---|
| Окно на Qt | есть | `ui.frontend = "qt"` | основной |
| Команды в терминале: `lanes`, `show`, `tail`, `post`, `read` | есть | `[cli]` | без Qt |
| Терминальный интерфейс (Textual) | есть | `ui.frontend = "tui"`, `[tui]` | работает по ssh |
| Веб на localhost | есть | `ui.frontend = "web"`, `[web]` | вход по ключу из профиля |
| GTK4 + libadwaita | в планах | — | |
| Toga (BeeWare) | в планах | — | на попробовать |

## ActivityPub напрямую

Всё — без твоего токена, к чужому серверу уходит только твой IP.

| Что | Статус | Конфиг |
|---|---|---|
| Коллекция ответов автора: тред целиком | есть | `feed.complete_threads` |
| Mastodon-Async-Refresh: сервер сам дособирает тред | есть | `feed.complete_threads` |
| Старые посты человека из его outbox | есть | `feed.remote_profiles`, `feed.remote_posts` |
| Подписчики и подписки с сервера человека | есть | `feed.remote_people` |
| Честные счётчики с сервера автора | есть | `feed.honest_counters` |

## Планы

| Что | Статус | Заметка |
|---|---|---|
| Закладки, тишина, редактирование, опросы | есть | 0.2–0.4 |
| Мультиаккаунт | есть | 0.3 |
| Порт под Windows, сборки одним файлом | есть | 0.4–0.5 |
| «Как у всех, но настраиваемо»: markers, карточки, эмодзи, цитаты, @ники, ЛС, отложенные, перевод, жалобы… | есть | 0.8 |
| CLI | есть | 0.9 |
| TUI, веб, deb-пакет | есть | 0.10 |
| GTK4, Toga | в планах | |
| Свой apt-репозиторий | в планах | из deb-пакетов релизов |
| Установщик и подпись для Windows | в планах | когда будут пользователи на Windows |
| Видео и аудио внутри окна | есть | 0.11 |
| Коллекции Mastodon 4.6 | в планах | когда появятся в GoToSocial |
| XMPP-шлюз | не будем | убран из очереди |
| Подписка на старые треды пачкой | не будем | убрана из очереди |

<a id="english"></a>
## English

The state of things as of **0.10.0**, next to Mastodon web, Tusky, Ivory, Phanpy, Elk and
Tokodon. Every behaviour has its config switch, named in the tables (`section.key`; the full
reference is `config.example.toml`).

**Has:** Home, Local, Federated, a Bots lane, lists as lanes (members leave the general lanes),
hashtags, My likes, Direct messages; whole threads as numbered trees, filled from the author's
server and by Mastodon-Async-Refresh; thread subscriptions; conversations view; All / Posts /
New; read position shared through markers; link cards; custom emoji; quote posts (showing,
quoting, who may quote); sensitive media covered (or, with `ui.arts_mode`, the default: no CW folding, no covers, no server-filter folding, no Report item); polls (voting and creating); edit history;
translation; pinned and featured on profiles; profiles, followers and follows filled in from
the person's own server (ActivityPub outbox and collections); honest counters; announcements;
live stream; find in lane; in-app links; the composer panel with drafts, Markdown, alt text,
focus point, completion of #tags, @names and :emoji:, CamelCase hint, languages, scheduled
posts, GoToSocial interaction policies; a Point-style command line; mutes, blocks, filters,
server blocks, reports, notes, the bell, filtered notifications; desktop notifications with
privacy levels; unread counts on the icon; several accounts in one window; themes as files;
j/k keys; a config in chapters; the Qt window, terminal commands, a Textual TUI and a web UI
on localhost; Linux one-file, deb and Windows .exe builds.

**Partly:** video and audio play in the browser; notification grouping is fedtail's own;
screen readers not tested live.

**Planned:** GTK4 and Toga front ends, an apt repository, a Windows installer and signing,
in-window media, Mastodon 4.6 collections. **Not planned:** trends and suggestions, an XMPP
gateway.
