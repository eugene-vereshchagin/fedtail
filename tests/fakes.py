"""In-memory fake of the Mastodon API, good enough for core and smoke tests."""

from fedtail.core.api import ApiError

ME = {"id": "ME", "acct": "veresk", "username": "veresk", "display_name": "Вереск",
      "bot": False, "avatar_static": "", "url": "https://example.test/@veresk", "note": ""}


def acct(i, name, bot=False):
    return {"id": i, "acct": name, "username": name.split("@")[0], "display_name": name,
            "bot": bot, "avatar_static": "", "url": f"https://example.test/@{name}", "note": ""}


BOB = acct("B", "bob@mastodon.social")
NEWS = acct("N", "georgia_news", bot=True)


def status(i, account, reply_to=None, reply_acc=None, minute=0, vis="private", text="text"):
    return {
        "id": i, "account": account, "in_reply_to_id": reply_to,
        "in_reply_to_account_id": reply_acc,
        "created_at": f"2099-10-14T10:{minute:02d}:00.000Z", "visibility": vis,
        "content": f"<p>{text}</p>", "spoiler_text": "", "mentions": [],
        "media_attachments": [], "replies_count": 0, "favourites_count": 0,
        "reblogs_count": 0, "favourited": False, "reblogged": False,
        "url": f"https://example.test/s/{i}", "uri": f"https://example.test/s/{i}",
    }


def _sid(x):
    return x["id"].rjust(10, "0")


def _page(items, limit, max_id=None, min_id=None):
    """Mastodon paging over a newest-first list of dicts with sortable 'id'."""
    items = sorted(items, key=_sid, reverse=True)
    if max_id:
        items = [x for x in items if _sid(x) < max_id.rjust(10, "0")]
    if min_id:
        newer = [x for x in items if _sid(x) > min_id.rjust(10, "0")]
        return newer[-limit:]  # the page right after min_id, still newest-first
    return items[:limit]


class FakeApi:
    """Use FakeApi.world to share state between instances created by Core."""
    world = None

    def __init__(self, server="https://example.test", token=None, session=None):
        self.base = server if server.startswith("http") else "https://" + server
        self.token = token
        w = FakeApi.world
        if w is None:
            w = FakeApi.world = World()
        self.w = w

    def register_app(self):
        return {"client_id": "cid", "client_secret": "sec"}

    def authorize_url(self, client_id):
        return f"{self.base}/oauth/authorize?client_id={client_id}"

    def get_token(self, cid, sec, code):
        if code.strip() != "good":
            raise ApiError(400, "bad code")
        return "tok"

    def me(self):
        if self.w.fail_auth:
            raise ApiError(401, "nope")
        return ME

    def instance(self):
        return {"version": "0.20.0 git-abc (gotosocial)",
                "configuration": {"statuses": {"max_characters": 5000,
                                               "max_media_attachments": 10}}}

    def get(self, path, params=None):
        return BOB

    def home(self, limit=40, max_id=None, min_id=None):
        self.w.calls.append(("home", max_id, min_id))
        return _page(self.w.home, limit, max_id, min_id)

    def local(self, limit=40, max_id=None, min_id=None):
        return _page(self.w.local, limit, max_id, min_id)

    def account_statuses(self, acc_id, limit=40, max_id=None, min_id=None):
        mine = [s for s in self.w.statuses.values() if s["account"]["id"] == acc_id]
        return _page(mine, limit, max_id, min_id)

    def mentions(self, limit=40, max_id=None, min_id=None):
        return _page(self.w.notifications, limit, max_id, min_id)

    def notifications(self, types, limit=40, max_id=None, min_id=None):
        return _page([n for n in self.w.activity if n["type"] in types], limit, max_id, min_id)

    def relationship(self, acc_id):
        return {"id": acc_id, "following": acc_id in self.w.following,
                "followed_by": False, "requested": False}

    def follow(self, acc_id, on=True):
        (self.w.following.add if on else self.w.following.discard)(acc_id)
        return self.relationship(acc_id)

    def tag_timeline(self, tag, limit=40, max_id=None, min_id=None):
        tagged = [s for s in self.w.statuses.values() if f"#{tag}".lower() in
                  s["content"].lower()]
        return _page(tagged, limit, max_id, min_id)

    def search(self, q, kind=None, resolve=True, limit=5):
        ql = q.lower().lstrip("@#")
        st = [s for s in self.w.statuses.values() if s.get("url") == q]
        accs = {s["account"]["id"]: s["account"] for s in self.w.statuses.values()}
        acc = [a for a in accs.values() if a.get("url") == q or ql in a["acct"].lower()]
        tags = [{"name": t, "url": f"https://example.test/tags/{t}", "following": t in
                 self.w.followed_tags} for t in ("linux", "georgia") if ql and ql in t]
        return {"statuses": st[:limit], "accounts": acc[:limit], "hashtags": tags}

    def get_page(self, path, params=None):
        return [], None

    def following(self, acc_id, max_id=None):
        return [a for a in self.w.accounts() if a["id"] in self.w.following], None

    def followers(self, acc_id, max_id=None):
        return list(self.w.accounts())[:2], None

    def relationships(self, ids):
        return [self.relationship(i) for i in ids]

    def tag(self, name):
        return {"name": name, "url": f"https://example.test/tags/{name}",
                "following": name in self.w.followed_tags}

    def follow_tag(self, name, on=True):
        (self.w.followed_tags.add if on else self.w.followed_tags.discard)(name)
        return self.tag(name)

    def followed_tags(self):
        return [self.tag(n) for n in sorted(self.w.followed_tags)]

    def status(self, sid):
        if sid not in self.w.statuses:
            raise ApiError(404, "not found")
        return self.w.statuses[sid]

    def context(self, sid):
        all_ = self.w.statuses
        anc, cur = [], all_[sid]
        while cur.get("in_reply_to_id") in all_:
            cur = all_[cur["in_reply_to_id"]]
            anc.insert(0, cur)
        desc, frontier = [], {sid}
        changed = True
        while changed:
            changed = False
            for s in all_.values():
                if s.get("in_reply_to_id") in frontier and s["id"] not in frontier:
                    frontier.add(s["id"])
                    desc.append(s)
                    changed = True
        return {"ancestors": anc, "descendants": desc}

    def verify_credentials(self):
        me = dict(ME, source={"note": "о себе", "fields": [{"name": "сайт", "value": "x.org"}]})
        me.update(self.w.profile)
        return me

    def update_credentials(self, **changes):
        self.w.profile_updates.append(changes)
        for k in ("display_name", "locked", "bot", "discoverable"):
            if changes.get(k) is not None:
                self.w.profile[k] = changes[k]
        return self.verify_credentials()

    def follow_requests(self):
        return list(self.w.requests)

    # lists: {id: {"id", "title", "exclusive", "members": set()}}
    def lists(self):
        return [{"id": i, "title": x["title"], "exclusive": x["exclusive"]}
                for i, x in self.w.lists.items()]

    def list_timeline(self, list_id, limit=40, max_id=None, min_id=None):
        members = self.w.lists[list_id]["members"]
        return _page([s for s in self.w.home if s["account"]["id"] in members],
                     limit, max_id, min_id)

    def list_accounts(self, list_id):
        return [{"id": a} for a in sorted(self.w.lists[list_id]["members"])]

    def create_list(self, title, exclusive=False):
        self.w.seq += 1
        i = f"L{self.w.seq}"
        self.w.lists[i] = {"title": title, "exclusive": exclusive, "members": set()}
        return {"id": i, "title": title, "exclusive": exclusive}

    def update_list(self, list_id, title, exclusive):
        self.w.lists[list_id].update(title=title, exclusive=exclusive)
        return {"id": list_id, "title": title, "exclusive": exclusive}

    def delete_list(self, list_id):
        self.w.lists.pop(list_id)

    def list_add(self, list_id, acc_id):
        self.w.lists[list_id]["members"].add(acc_id)

    def list_remove(self, list_id, acc_id):
        self.w.lists[list_id]["members"].discard(acc_id)

    def upload_media(self, path, description=""):
        return {"id": "m1", "url": "https://example.test/m1.png"}

    def post_status(self, text, visibility="private", in_reply_to_id=None, spoiler_text="",
                    media_ids=(), markdown=False):
        self.w.seq += 1
        reply_acc = self.w.statuses[in_reply_to_id]["account"]["id"] if in_reply_to_id else None
        st = status(str(self.w.seq), ME, in_reply_to_id, reply_acc, minute=59, vis=visibility,
                    text=text)
        self.w.posted.append((text, visibility, in_reply_to_id, markdown))
        self.w.add(st, home=True)
        return st

    def delete_status(self, sid):
        self.w.statuses.pop(sid, None)
        self.w.home = [s for s in self.w.home if s["id"] != sid]

    def favourite(self, sid, on=True):
        st = dict(self.w.statuses[sid], favourited=on)
        self.w.statuses[sid] = st
        return st

    def reblog(self, sid, on=True):
        st = dict(self.w.statuses[sid], reblogged=on)
        self.w.statuses[sid] = st
        return {"id": "rb" + sid, "reblog": st, "account": ME}

    def authorize_follow(self, acc_id):
        self.w.requests = [a for a in self.w.requests if a["id"] != acc_id]

    reject_follow = authorize_follow


class World:
    def __init__(self):
        self.statuses, self.home, self.local, self.notifications = {}, [], [], []
        self.requests = []
        self.posted = []
        self.calls = []
        self.seq = 1000
        self.fail_auth = False
        self.profile = {}
        self.lists = {}
        self.activity = []
        self.following = set()
        self.followed_tags = set()
        self.profile_updates = []

    def accounts(self):
        return list({s["account"]["id"]: s["account"] for s in self.statuses.values()}.values())

    def act(self, i, kind, account, st=None, minute=0):
        n = {"id": i, "type": kind, "account": account, "status": st,
             "created_at": f"2099-10-14T11:{minute:02d}:00.000Z"}
        self.activity.append(n)
        return n

    def add(self, st, home=False, mention=False):
        self.statuses[st["id"]] = st
        if home:
            self.home.append(st)
        if mention:
            self.notifications.append({"id": "n" + st["id"], "type": "mention",
                                       "created_at": st["created_at"], "status": st})
        return st

