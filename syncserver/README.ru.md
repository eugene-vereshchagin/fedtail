# fedtail-sync

[In English](README.md)

Место встречи устройств одного аккаунта федиверса для
[fedtail](https://github.com/eugene-vereshchagin/fedtail): каждое устройство присылает сюда
зашифрованный журнал — прочитанное, подписки и заглушенные треды, ленты, черновики — и
забирает журналы остальных. Прочесть их сервер не может: они зашифрованы (AES-256-GCM)
ключом, который есть только у устройств. Он знает лишь чьи они, какого размера и когда.

Чьи: устройство присылает токен своего аккаунта, ограниченный `read:accounts` (им можно
только узнать «кто я»), и называет свой сервер; fedtail-sync спрашивает у того сервера, чей
это токен, и складывает журнал под этим именем. Своих аккаунтов и паролей у него нет.

Один файл, только стандартная библиотека Python (3.11+), SQLite. Версия 1.0.0,
протокол 1 ([PROTOCOL.md](PROTOCOL.md)); изменения — [CHANGELOG.md](CHANGELOG.md). Лицензия
GPL-3.0-or-later.

```sh
python3 fedtail_sync.py --version
python3 fedtail_sync.py --config /srv/fedtail-sync/config.toml
```

## Установка


Это один файл на стандартной библиотеке: [`fedtail_sync.py`](fedtail_sync.py)
(Python 3.11+, SQLite). Скопируй его на сервер — больше ничего от fedtail там не нужно.

Своя папка, например `/srv/fedtail-sync/`, — в ней файл, его конфиг и база; системный
пользователь для него:

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin fedtail-sync
sudo mkdir -p /srv/fedtail-sync
sudo cp fedtail_sync.py /srv/fedtail-sync/
sudo chown -R fedtail-sync: /srv/fedtail-sync
```

`/srv/fedtail-sync/config.toml`:

```toml
listen = "127.0.0.1:8471"
db = "/srv/fedtail-sync/sync.db"
instances = ["your.server"]   # whose people are served; ["*"] — anyone's (public servers only)
quota_mb = 20                 # per account; a year of reading is a few MB
max_blob_kb = 512
requests_per_minute = 120     # per account
keep_days = 0                 # 0: kept until the account deletes its journal
total_mb = 1024               # all accounts together; 0 — no cap
timeout_seconds = 30          # a silent connection is dropped (a whole request: twice that)
max_connections = 64          # served at once; more are closed at the door
requests_per_minute_per_ip = 240
verifications_per_minute_per_ip = 10   # token checks at a fediverse server, per address
verifications_per_minute = 60          # ... in all
client_ip_header = "CF-Connecting-IP"  # behind cloudflared/nginx on this machine; "" — none
```

Юнит systemd, `/etc/systemd/system/fedtail-sync.service`:

```ini
[Unit]
Description=fedtail-sync
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 /srv/fedtail-sync/fedtail_sync.py --config /srv/fedtail-sync/config.toml
User=fedtail-sync
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/srv/fedtail-sync
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload && sudo systemctl enable --now fedtail-sync
curl -s http://127.0.0.1:8471/v1        # {"fedtail-sync": 1}
```

Говорит он обычным HTTP на localhost; TLS делается перед ним, на его собственном имени
(например, `sync.твой.домен`) — сервер федиверса не трогаем.

**Cloudflare Tunnel** (туннель из дашборда): Zero Trust → Networks → Tunnels → твой
туннель → Published application routes (Public Hostname) → добавить: поддомен `sync`,
твой домен, путь пустой, сервис `http://127.0.0.1:8471`. Именно `http`, а не `https`
(TLS делает Cloudflare), и `127.0.0.1`, а не `localhost` (тот может уйти в IPv6, где
сервер не слушает). DNS-запись появится сама. Если туннель настроен файлом — то же
правилом ingress:

```yaml
  - hostname: sync.your.domain
    service: http://127.0.0.1:8471
```

**nginx** — отдельный `server { … }`:

```nginx
server {
    server_name sync.your.domain;
    # listen / ssl_certificate — как у остальных твоих сайтов
    location / {
        proxy_pass http://127.0.0.1:8471;
        client_max_body_size 1m;
    }
}
```

**Caddy**:

```
sync.your.domain {
    reverse_proxy 127.0.0.1:8471
}
```

Проверка снаружи: `curl -s https://sync.твой.домен/v1` → `{"fedtail-sync": 1}`. Твои
люди пишут этот адрес в `sync.url` и делают `fedtail sync login`.

## Как он себя защищает

Он смотрит в интернет, поэтому все ограничения включены по умолчанию (значения выше — и
есть умолчания, кроме `client_ip_header`):

| что можно попробовать | что этому мешает |
|---|---|
| открыть соединения и молчать или слать по байту раз в полминуты | обрыв после `timeout_seconds` тишины; на весь запрос — вдвое больше |
| открыть тысячи соединений | одновременно не больше `max_connections`, остальные закрываются сразу |
| завалить запросами | `requests_per_minute_per_ip` на адрес, `requests_per_minute` на аккаунт |
| слать случайные токены, чтобы сервер долбил проверками чей-то сервер федиверса | известному токену верит 10 минут, отказанный отказан минуту; настоящие проверки ограничены на адрес и всего (`verifications_per_minute_per_ip`, `verifications_per_minute`) |
| врать в `Content-Length`, не указывать его, слать кусками (chunked) | отказ до чтения (411, 400, 413); тело короче обещанного не держит поток |
| забить диск | `quota_mb` на аккаунт и `total_mb` на всех (с `"*"` любой со своим сервером может наплодить аккаунтов) |
| заставить его сходить в твою локалку (с `"*"`) | только публичные адреса, проверка на уже открытом соединении — имя, сменившее адрес между проверкой и запросом, ловится; за редиректами не ходит, так что токен никуда больше не уходит |
| выведать его внутренности | ошибка внутри отвечает «internal error», подробности — только в его лог |

**За прокси на той же машине** — cloudflared, nginx, Caddy — все запросы приходят с
127.0.0.1, и лимиты на адрес считали бы весь мир одним клиентом. Укажи в `client_ip_header`
заголовок, куда прокси кладёт настоящий адрес: `CF-Connecting-IP` у Cloudflare, `X-Real-IP`
у nginx с `proxy_set_header X-Real-IP $remote_addr;`. Ему верят только от локального
соседа и только если в нём адрес — клиент так лимит не обойдёт. Если слушать не на
127.0.0.1, сервер при старте предупредит: он говорит обычным HTTP.

Тесты на каждое из этого — в [`tests/test_security.py`](tests/test_security.py); CI гоняет их
вместе с bandit на каждый пуш, и без них релиз не выйдет.

Что хранит сервер: для каждого аккаунта (его id на его сервере) — зашифрованные куски со
случайным id устройства и временем. Что пишет в лог: строку на запрос — адрес, путь,
ответ, — никогда не токен. `DELETE /v1/blobs` с токеном аккаунта удаляет весь его журнал.

## Люди с других серверов

`instances = ["*"]` обслуживает любого, чей сервер подтвердит токен (только публичные
адреса: в твою локальную сеть сервер никогда не ходит). Журналы зашифрованы, так что это
стоит места на диске и трафика, а не приватности; квота и лимит запросов держат это
маленьким. Бета-тестер с другого сервера прописывает в конфиге тот же
`url = "https://sync.твой.домен"`.


## Тесты

```sh
python3 -m unittest discover -s tests -t .      # из этой папки; только стандартная библиотека
python3 tools/coverage.py --fail-under 100      # покрытие строк (Python 3.12+), должно быть 100 %
```

`tests/test_server.py` — журнал, лимиты, проверка токена, старые журналы, конфиг и сама
программа; `tests/test_security.py` — все способы повесить его, завалить, забить диск или
натравить на кого-то. Об уязвимости — приватно: [SECURITY](https://github.com/eugene-vereshchagin/fedtail/security/advisories/new).
