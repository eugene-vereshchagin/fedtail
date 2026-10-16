# Альфа-тест fedtail

[English below](#english)

Спасибо, что пробуешь. fedtail — ранняя версия: что-то будет ломаться, и это нормально;
главное — чтобы каждая поломка оставила след, по которому её можно починить.

## Поставить

Debian 13 (trixie), KDE или любой другой рабочий стол:

```sh
sudo apt install python3-pyside6.qtwidgets python3-pyside6.qtdbus python3-requests \
    qt6-image-formats-plugins libnotify-bin fonts-noto-color-emoji
git clone https://github.com/eugene-vereshchagin/fedtail.git
cd fedtail
python3 -m fedtail                      # первый запуск: адрес сервера → вход в браузере
python3 -m fedtail --install-desktop    # пункт в меню и иконка (по желанию)
```

Обновиться: `git pull`, затем `python3 -m fedtail --update-config` — допишет в конфиг новые
настройки с пояснениями (твои значения не трогает), и перезапусти программу.

Подойдёт любой сервер с API Mastodon: GoToSocial, Mastodon, Akkoma, Friendica. Заходи
обычной учётной записью, не админской.

## Что посмотреть в первую очередь

- **Треды.** Открой обсуждение (кнопка «Тред» или клик по времени поста): оно деревом,
  с номерами `/1 /2 …`, целиком — и ответы, которые твой сервер не получал, подтянутся
  через пару секунд. Тот же тред, открытый из разных мест, должен выглядеть одинаково.
- **Ничего не теряется.** Закрой ленты Esc, оставь программу на ночь — утром слева
  счётчики, новое ждёт непрочитанным, лента открывается там, где ты остановился.
- **Ответы мне, подписки на треды** (кнопка «Подписаться» над тредом, `S #abc` в
  командной строке): ответы в твоих тредах приходят, даже если тебя не упомянули.
- **Уведомления**: меню ≡ → «Отладка» → «Проверить уведомление».
- **Командная строка** внизу (`Ctrl+L`, `?` — справка), как на Point.
- **Несколько аккаунтов**: правый клик по своей аватарке.
- **Темы**: `ui.theme` в конфиге (≡ → «Открыть конфиг»), список — там же в пояснении.

## Нашёл проблему

1. Опиши в двух словах: что делал, что ждал, что получилось. Скриншот — очень помогает.
2. Приложи журнал: файл `~/fedtail-logs/<профиль>/latest.log` (профиль обычно `default`).
   Если программа уже перезапускалась — файлы там же, по дате и часу в имени.
   Или одним архивом: `python3 -m fedtail --bug-report` — он появится в домашней папке.
3. Окно зависло — сначала `kill -USR1 <pid>` (pid есть в журнале), потом присылай.

В журнале нет токена и текстов постов: только адреса запросов, id постов, время и ошибки.
Архив `--bug-report` не берёт ни токен, ни базу. Конфиг в него попадает — посмотри, нет ли
там того, чем делиться не хочешь.

<a id="english"></a>
## English

Thanks for trying fedtail. It's early: things will break, and each breakage should leave a
trace to fix it by.

**Install** (Debian 13): the `apt install` line above, `git clone`, `python3 -m fedtail`;
`--install-desktop` adds a menu entry. **Update:** `git pull`, then
`python3 -m fedtail --update-config`.

**Try first:** whole threads (a tree, numbered, filled from other servers); nothing lost
(Esc closes the lanes, new things wait unread); replies to me and thread subscriptions;
notifications (≡ → Debugging → Send a test notification); the command line (`Ctrl+L`,
`?`); several accounts (right-click your avatar); themes (`ui.theme`).

**Found a problem:** say what you did, expected and got (a screenshot helps), and attach
`~/fedtail-logs/<profile>/latest.log` or the archive from `python3 -m fedtail --bug-report`.
A frozen window: `kill -USR1 <pid>` first. Logs hold no token and no post texts; the
archive holds no token and no database, but does include your config.
