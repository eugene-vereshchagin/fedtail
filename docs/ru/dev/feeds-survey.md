# Ленты других клиентов — нашими атомами

**Что это:** обзор (27 окт 2026) лент популярных клиентов и серверов федиверса: каждая записана
атомами из [feeds.md](feeds.md), плюс чего в наших атомах не хватает и какие заготовки из этого
выходят. «(?)» — не сверено с первоисточником (докой или кодом); проверить, прежде чем
опираться.

## 1. Кого смотрели

| группа | клиенты | насколько точно |
|---|---|---|
| веб | Mastodon web (простой и расширенный), Phanpy, Elk, Semaphore | Mastodon, Phanpy — код и доки; Elk, Semaphore — в основном (?) |
| телефоны | Tusky, Fedilab, Megalodon, Moshidon, официальные приложения Mastodon, Ice Cubes, Ivory, Mona | Tusky, Ice Cubes — код; Ivory, Mona — страницы магазинов, обзоры; Fedilab, официальные — в основном (?) |
| серверы со своими лентами | Misskey (Sharkey, Firefish), Akkoma / Pleroma, GoToSocial | Misskey — код бэкенда; Akkoma — дока API; GoToSocial — доки, частью (?) |
| десктоп | Tokodon, Tuba, Whalebird, TheDesk | всё (?) |

## 2. Ленты, записанные атомами

Только то, что отличается от простой ленты «один эндпоинт, всё подряд»; обычные Home / Local /
Federated / списки / закладки / лайки есть у всех.

| клиент | лента | атомами | переключатели на ленте |
|---|---|---|---|
| Mastodon web | Home | `source=home` (в ней подписанные теги; участники `exclusive`-списков — вон) | бусты / ответы / цитаты — на клиенте; API 5.0: `exclude_reblogs/replies/quotes` на сервере |
| Mastodon web | Живые ленты | `source=local` / `federated` / federated минус local (`remote=true`) | только медиа |
| Mastodon web | Хештег | `tags:<spec>` с any / all / none, ≤ 4 тегов | только локальные |
| Mastodon web | Список | `list:<id>`; ответы — `replies_policy`: никому / участникам списка / любым подпискам | скрыть участников из Home (`exclusive`) |
| Mastodon web | Уведомления | `event=*` + `me=mention`; группы (`group_key`) для лайк/буст/подписка | на тип: всплывашка / пуш / показ / звук; Все / Упоминания |
| Mastodon web | Отфильтрованные уведомления | `event`, `author` = не подписан я / не подписан на меня / новый (< 30 дн) / под модерацией / бот | на категорию: принять / в фильтр / выкинуть |
| Phanpy | Home | `source=home`, повторные бусты склеены | карусель бустов; «новые посты» — только если пришёл не буст |
| Phanpy | Упоминания | `me=mention` + `kind=quote`; Личное — `source=direct` | «только подписки» (`author=followed`) |
| Phanpy | Хештег | `tags:<spec>`, любой из ≤ 5 | только медиа (сеткой), другой сервер |
| Phanpy | Публичные / Тренды | `local` / `federated` / тренды **любого сервера**, без входа | — |
| Phanpy | Catch-up | `source=home` за окно (1 ч … 12 ч+), без моих и отфильтрованных; каждый пост в одной категории: отфильтрованное > группа > буст > цитата > подписанный тег > ответ > пост | сортировка: время / ответы / лайки / бусты / «плотность»; по авторам; топ ссылок; «с прошлого catch-up» |
| Elk | Home | `source=home`, цепочка ответов — одним тредом | (?) |
| Tusky | Home | `source=home` | бусты / ответы / **самобусты** (только Home) |
| Tusky | Хештег | `tags:<spec>`, любой из (?) | — |
| Fedilab | все ленты | как источник | бусты / ответы на Home, Local, Public и списках (3.44) |
| Fedilab | Лента тегов | `tags:<spec>` any / all / none (?) | только медиа, NSFW (?) |
| Fedilab | Чужой сервер | публичная лента другого сервера без учётки там | — |
| Fedilab | Арт | `tags:mastoart` + `has=media`, картинками | — |
| Megalodon | Edit timelines | Local / Federated / список / тег — переключаемыми лентами внутри Home, у каждой имя и значок | скрыть ответы / бусты в Home |
| Megalodon | Bubble | `timelines/bubble` Akkoma | — |
| Ice Cubes | Home | `source=home` | без медиа, **без ботов**; дотягивает, если фильтры опустошили страницу |
| Ice Cubes | Группа тегов | `tags:<spec>` any, заголовок и значок, синкается | — |
| Ice Cubes | Хештег на стене | `account:<id>` + `has="tag:x"` | — |
| Ice Cubes | Ссылка / Цитаты | `timelines/link?url=` / цитаты одного поста | — |
| Ivory | Список хештегов | ≤ 4 тегов в одной ленте | — |
| Ivory | Уведомления | упоминания и события вместе, точка непрочитанного только для упоминаний | плоско или группами |
| Mona | Сохранённый фильтр | любая лента + фильтр из многих критериев, отдельной вкладкой | репосты — по аккаунту |
| Misskey | Social (гибрид) | `source=home` ∪ (`source=local`, `kind=post`) ∪ локальные ответы мне | файлы / реноуты / ответы |
| Misskey | Local | `source=local`; ответы — только себе и мне, если не «с ответами» | файлы / реноуты / ответы |
| Misskey | Список | `list:<id>`; ответ входит, если он себе, мне или участник помечен «с ответами» | на участника: с ответами |
| Misskey | Home | ответы подписки другим — по каждой подписке (`withReplies`) | мои реноуты, реноуты моего, локальные реноуты |
| Misskey | Антенна | правило над всем приходящим: источник (home / all / users / users-blacklist / list), ключевые слова — ИЛИ из И-групп по тексту + CW, исключения так же, регистр, с ответами, с файлом, только локальные, без ботов | само правило; только с момента создания, ≤ 200 нот; засыпает без дела |
| Akkoma | Bubble | `source=federated` + `author="domain:…"` из набора, выбранного админом | только медиа, `reply_visibility` |
| Akkoma | любая | `reply_visibility`: все / `following` (`parent` ∈ мои, подписки) / `self` (`me=reply`) | `with_muted` |
| Akkoma | Личка | `visibility=direct` плоской лентой; беседы по участникам | — |
| TheDesk | Интегрированная | `home` ∪ `local` в одной колонке (?) | слова / regex на колонку (?) |
| Tuba | Home | `source=home` (?) | скрыть ответы / бусты (?) |

## 3. Чего не хватает нашим атомам

| что | где видели | предложение для [feeds.md](feeds.md) |
|---|---|---|
| лента выбранных мной чужих серверов («пузырь») | Akkoma, Sharkey, Firefish, Megalodon | `author = "domain:{a,b,c}"` поверх `federated` — помощь сервера не нужна; `timelines/bubble` Akkoma — источником, где есть |
| публичная лента чужого сервера без учётки там | Phanpy, Fedilab, Ice Cubes, Mona | источник `remote:<host>` (local / federated / тренды), токен туда не уходит |
| тренды | все | источник `trends` (посты) — только просмотр |
| посты с одной ссылкой; цитаты одного поста | Mastodon 4.3+, Ice Cubes | источники `link:<url>`, `quotes:<id>` |
| тег на стене одного человека | Ice Cubes | `account:<id>` + `has = "tag:x"`, серверу — как `tagged=` |
| самобуст; мой буст; буст моего | Tusky, Misskey | `kind = "self_boost"`; `me = "my_boost"`; `boost_of_mine` уже есть |
| ответы, у которых родитель мой или подписки | Akkoma, списки Mastodon, Misskey | ось `parent` есть; добавить в заготовки переключателем |
| ответы по автору («этот — с ответами») | Misskey (по подписке, по участнику списка) | условие `author = "@x@host", kind = "reply"` — работает уже; ⋯ профиля «с ответами в моих лентах» пишет его |
| автор: новый аккаунт, не подписан на меня, недавно подписался, под модерацией | политика уведомлений Mastodon | значения `author`: `new` (< 30 дн), `not_follower`, `new_follower` (< 3 дн), `limited` |
| слова: ИЛИ из И-групп, по тексту, CW, alt-текстам, вариантам опроса; регистр; regex | антенны Misskey, Ivory | ключ `text = [["a", "b"], ["c"]]` (внешний — ИЛИ, внутренний — И), `text_in = ["text", "cw", "alt", "poll"]`, `text_case`, `text_regex` |
| лента за окно времени, отсортированная не по времени | Catch-up Phanpy | `mode = "catch_up"` у ленты, с `window` и `sort` (время / ответы / лайки / бусты / плотность); не атом, а способ чтения |
| одна категория на пост с приоритетом | Catch-up Phanpy | переключатели из §4 feeds.md с `priority`: пост идёт только в первый чип, который его взял |
| бусты в сторонке; цепочка ответов одним блоком | Phanpy, Elk | показ, не атомы: `feed.boost_strip`, `feed.fold_threads` |
| какой контекст серверных фильтров у ленты | Tusky, Mastodon | `filter_context` у ленты: по умолчанию от её источников (home, public, notifications, account) |
| лента засыпает без дела | Misskey | ленты «подряд», не открытые `lanes.dormant_days`, перестают опрашивать свои источники |
| убрать один пост из ленты | Misskey 2026.6 | ⋯ «не в этой ленте»: исключение `none = [{ id = … }]`, его держит ядро, синкается |

Где мы уже лучше лучших: новая лента наполняется из того, что лежит в базе, а не только с
момента создания (антенны Misskey стартуют пустыми и держат 200); пост читается один раз на все
ленты; место чтения помнится на ленту и синкается.

## 4. Заготовки

Заготовка — набор лент на правилах (`lanes.preset = "…"`); `[[lanes.custom]]` добавляют к ней
или заменяют её ленты по имени. Первая — то, что fedtail показывает сейчас.

| заготовка | ленты | у кого подсмотрено |
|---|---|---|
| `fedtail` (по умолчанию) | Home, Боты, Local, Federated, Мои посты, Личка, Упоминания, Ответы мне, Подписки, Закладки, Активность, Запросы | нынешние ленты |
| `point` | Лента: посты home + подписки, чип «Комменты» выкл.; Посты: мои + ответы на мои посты; Ответы и упоминания вместе; Личка; Активность | автора |
| `mastodon` | Home (чипы: бусты, ответы), Уведомления (события и упоминания вместе, чип «Только упоминания»), Local, Federated, Личка, Закладки, Лайки | Mastodon web, Ivory |
| `social` | Social: home ∪ посты local ∪ ответы мне; Local; Federated; Упоминания; Личка; Активность | Misskey |
| `quiet` | Home без бустов старше 2 дней и самобустов, ответы только мне и подпискам (чип); Упоминания только от подписок (чип); Личка; Активность только подписок | `following` Akkoma, «только подписки» Phanpy, Tusky |
| `bubble` | `fedtail` + Пузырь: federated со списка серверов в `lanes.bubble` | Akkoma, Sharkey |
| `pictures` | `fedtail` + Картинки: home ∪ local с медиа, сеткой | Арт Fedilab, «только медиа» Mastodon |
| `catch_up` | `fedtail` + Сводка: home за 12 ч, чипы по категориям, сортировка по лайкам | Phanpy |

## 5. Ждёт решения

* Новые атомы из §3: все или какие первыми?
* `quiet` и `point`: какие чипы включены по умолчанию?
* Catch-up как режим ленты — сейчас или после того, как заработают сами ленты?
* Пузырь: только свой список или ещё и серверный (`timelines/bubble`), где он есть?

## 6. Источники

* Mastodon: [timelines](https://docs.joinmastodon.org/methods/timelines/),
  [notifications](https://docs.joinmastodon.org/methods/notifications/),
  [grouped notifications](https://docs.joinmastodon.org/methods/grouped_notifications/),
  [lists](https://docs.joinmastodon.org/methods/lists/),
  [markers](https://docs.joinmastodon.org/methods/markers/),
  [4.3.0](https://github.com/mastodon/mastodon/releases/tag/v4.3.0), код веб-интерфейса
  (`app/javascript/mastodon/features/*/column_settings`, `notifications/components/policy_controls.tsx`)
* Phanpy: [README](https://github.com/cheeaun/phanpy), `src/pages/catchup.jsx`,
  `src/components/shortcuts-settings.jsx`, `src/components/timeline.jsx`
* Elk: [features](https://docs.elk.zone/guide/features); Semaphore:
  [user guide](https://raw.githubusercontent.com/NickColley/semaphore/main/docs/User-Guide.md)
* Tusky: [FAQ](https://tusky.app/faq/), `TabData.kt`, `TimelineViewModel.kt`,
  `NotificationsViewModel.kt` в [репо](https://github.com/tuskyapp/Tusky)
* Fedilab: [F-Droid](https://f-droid.org/en/packages/fr.gouv.etalab.mastodon); Megalodon:
  [README](https://github.com/sk22/megalodon); Moshidon:
  [F-Droid](https://f-droid.org/en/packages/org.joinmastodon.android.moshinda)
* Ice Cubes: [репо](https://github.com/Dimillian/IceCubesApp), `TimelineFilter.swift`;
  Ivory: [App Store](https://apps.apple.com/app/id6444602274); Mona:
  [MacStories](https://www.macstories.net/reviews/mona-a-unique-mix-of-customization-options-and-features-you-wont-find-in-any-other-mastodon-app/)
* Misskey: [timelines](https://misskey-hub.net/en/docs/for-users/features/timeline/),
  [antennas](https://misskey-hub.net/en/docs/for-users/features/antenna/), в бэкенде
  `models/Antenna.ts`, `core/AntennaService.ts`, `endpoints/notes/*-timeline.ts` в
  [репо](https://github.com/misskey-dev/misskey)
* Akkoma: [differences in the Mastodon API](https://docs.akkoma.dev/stable/development/API/differences_in_mastoapi_responses/);
  GoToSocial: [posts](https://docs.gotosocial.org/en/latest/user_guide/posts/)
