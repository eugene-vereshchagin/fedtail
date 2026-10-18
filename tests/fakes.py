"""In-memory fake of the Mastodon API, good enough for core and smoke tests."""

from fedtail.core.api import ApiError

ME = {"id": "ME", "acct": "mira", "username": "mira", "display_name": "Мира",
      "bot": False, "avatar_static": "", "url": "https://example.test/@mira", "note": ""}


def acct(i, name, bot=False):
    return {"id": i, "acct": name, "username": name.split("@")[0], "display_name": name,
            "bot": bot, "avatar_static": "", "url": f"https://example.test/@{name}", "note": ""}


BOB = acct("B", "bob@social.example")
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
    worlds = {}  # server -> World, for more than one account at once

    def __init__(self, server="https://example.test", token=None, session=None):
        self.base = server if server.startswith("http") else "https://" + server
        self.token = token
        w = FakeApi.worlds.get(self.base) or FakeApi.world
        if w is None:
            w = FakeApi.world = World()
        self.w = w

    def register_app(self):
        return {"client_id": "cid", "client_secret": "sec"}

    def authorize_url(self, client_id):
        return f"{self.base}/oauth/authorize?client_id={client_id}"

    def revoke(self, cid, sec, token):
        self.w.revoked.append(token)

    def get_token(self, cid, sec, code):
        if code.strip() != "good":
            raise ApiError(400, "bad code")
        return "tok"

    def me(self):
        if self.w.fail_auth:
            raise ApiError(401, "nope")
        return self.w.me

    def instance(self):
        return {"version": "0.20.0 git-abc (gotosocial)",
                "configuration": {"statuses": {"max_characters": 5000,
                                               "max_media_attachments": 10}}}

    def get(self, path, params=None):
        return BOB

    def home(self, limit=40, max_id=None, min_id=None):
        self.w.calls.append(("home", max_id, min_id))
        return _page(self.w.home, limit, max_id, min_id)

    def federated(self, limit=40, max_id=None, min_id=None):
        return _page(self.w.local + self.w.home, limit, max_id, min_id)

    def local(self, limit=40, max_id=None, min_id=None):
        return _page(self.w.local, limit, max_id, min_id)

    def account_statuses(self, acc_id, limit=40, max_id=None, min_id=None):
        mine = [s for s in self.w.statuses.values() if s["account"]["id"] == acc_id]
        return _page(mine, limit, max_id, min_id)

    def notification_policy(self):
        if self.w.policy is None:
            raise ApiError(404, "not found")
        return dict(self.w.policy, summary={"pending_requests_count": len(self.w.held)})

    def set_notification_policy(self, **fields):
        self.w.policy.update(fields)
        return self.notification_policy()

    def notification_requests(self):
        if self.w.policy is None:
            raise ApiError(404, "not found")
        return list(self.w.held)

    def answer_notification_request(self, rid, accept):
        self.w.answered.append((rid, accept))
        self.w.held = [r for r in self.w.held if r["id"] != rid]
        return {}

    def announcements(self):
        return [dict(a) for a in self.w.announcements]

    def dismiss_announcement(self, aid):
        for a in self.w.announcements:
            if a["id"] == aid:
                a["read"] = True
        return {}

    def scheduled(self):
        return list(self.w.scheduled)

    def cancel_scheduled(self, sid):
        self.w.scheduled = [s for s in self.w.scheduled if s["id"] != sid]
        return {}

    def domain_blocks(self):
        return sorted(self.w.blocked_domains)

    def block_domain(self, domain, on=True):
        (self.w.blocked_domains.add if on else self.w.blocked_domains.discard)(domain)
        return {}

    def set_note(self, acc_id, text):
        self.w.notes[acc_id] = text
        return {"id": acc_id, "note": text}

    def report(self, acc_id, status_ids=(), comment="", forward=False, category="other"):
        self.w.reports.append((acc_id, list(status_ids), comment, forward, category))
        return {"id": "r1"}

    def custom_emojis(self):
        return list(self.w.emoji)

    def featured_tags(self, acc_id):
        if acc_id not in self.w.featured:
            raise ApiError(404, "not found")
        return self.w.featured[acc_id].get("tags", [])

    def endorsements(self, acc_id):
        return self.w.featured.get(acc_id, {}).get("people", [])

    def pinned(self, acc_id):
        return [s for s in self.w.statuses.values()
                if s["account"]["id"] == acc_id and s.get("pinned")]

    def pin(self, sid, on=True):
        self.w.statuses[sid]["pinned"] = on
        return self.w.statuses[sid]

    def mentions(self, limit=40, max_id=None, min_id=None):
        return _page(self.w.notifications, limit, max_id, min_id)

    def notifications(self, types, limit=40, max_id=None, min_id=None):
        return _page([n for n in self.w.activity if n["type"] in types], limit, max_id, min_id)

    def markers(self, timelines=("home", "notifications")):
        return {t: {"last_read_id": v} for t, v in self.w.markers.items() if t in timelines}

    def set_markers(self, positions):
        self.w.markers.update(positions)
        return {}

    def relationship(self, acc_id):
        return {"id": acc_id, "following": acc_id in self.w.following,
                "followed_by": False, "requested": False,
                "note": self.w.notes.get(acc_id, "")}

    def follow(self, acc_id, on=True):
        (self.w.following.add if on else self.w.following.discard)(acc_id)
        return self.relationship(acc_id)

    def tag_timeline(self, tag, limit=40, max_id=None, min_id=None):
        tagged = [s for s in self.w.statuses.values() if f"#{tag}".lower() in
                  s["content"].lower()]
        return _page(tagged, limit, max_id, min_id)

    def search(self, q, kind=None, resolve=True, limit=5):
        ql = q.lower().lstrip("@#")
        if resolve and q in self.w.remote:  # my server fetches it from its home
            got = self.w.remote.pop(q)
            self.w.statuses[got["id"]] = got
        st = [s for s in self.w.statuses.values() if q in (s.get("url"), s.get("uri"))]
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
        if acc_id in self.w.list_refuse:  # just followed, not confirmed yet
            raise ApiError(404, "Record not found")
        self.w.lists[list_id]["members"].add(acc_id)

    def list_remove(self, list_id, acc_id):
        self.w.lists[list_id]["members"].discard(acc_id)

    def upload_media(self, path, description="", focus=None):
        self.w.uploads.append((path, description, focus))
        return {"id": "m1", "url": "https://example.test/m1.png"}

    def post_status(self, text, visibility="private", in_reply_to_id=None, spoiler_text="",
                    media_ids=(), markdown=False, language="", sensitive=False, poll=None,
                    quoted_status_id=None, quote_policy="", interaction_policy=None,
                    scheduled_at=None):
        if scheduled_at:
            item = {"id": f"s{len(self.w.scheduled) + 1}", "scheduled_at": scheduled_at,
                    "params": {"text": text, "visibility": visibility}}
            self.w.scheduled.append(item)
            return item
        self.w.languages.append(language)
        self.w.extras.append({"sensitive": sensitive, "poll": poll,
                              "quote": quoted_status_id, "quote_policy": quote_policy,
                              "interaction_policy": interaction_policy})
        self.w.seq += 1
        reply_acc = self.w.statuses[in_reply_to_id]["account"]["id"] if in_reply_to_id else None
        st = status(str(self.w.seq), ME, in_reply_to_id, reply_acc, minute=59, vis=visibility,
                    text=text)
        self.w.posted.append((text, visibility, in_reply_to_id, markdown))
        self.w.add(st, home=True)
        return st

    def edit_status(self, sid, text, spoiler_text="", media_ids=(), markdown=False):
        old = self.w.statuses[sid]
        self.w.history.setdefault(sid, []).append(old)
        st = dict(old, content=f"<p>{text}</p>", spoiler_text=spoiler_text,
                  edited_at="2099-10-14T12:00:00.000Z",
                  media_attachments=[m for m in old["media_attachments"]
                                     if m["id"] in media_ids])
        self.w.statuses[sid] = st
        return st

    def status_source(self, sid):
        st = self.w.statuses[sid]
        return {"id": sid, "text": st["content"][3:-4], "spoiler_text": st["spoiler_text"]}

    def status_history(self, sid):
        return self.w.history.get(sid, []) + [self.w.statuses[sid]]

    def delete_status(self, sid):
        self.w.statuses.pop(sid, None)
        self.w.home = [s for s in self.w.home if s["id"] != sid]

    def favourite(self, sid, on=True):
        st = dict(self.w.statuses[sid], favourited=on)
        self.w.statuses[sid] = st
        return st

    def mute(self, acc_id, on=True):
        (self.w.muted.add if on else self.w.muted.discard)(acc_id)
        return {"id": acc_id, "muting": on}

    def block(self, acc_id, on=True):
        (self.w.blocked.add if on else self.w.blocked.discard)(acc_id)
        return {"id": acc_id, "blocking": on}

    def mutes(self):
        return [{"id": i} for i in sorted(self.w.muted)]

    def blocks(self):
        return [{"id": i} for i in sorted(self.w.blocked)]

    def filters(self):
        return list(self.w.filters.values())

    def create_filter(self, title, keywords, action="warn", contexts=("home",)):
        self.w.seq += 1
        f = {"id": f"F{self.w.seq}", "title": title, "filter_action": action,
             "context": list(contexts), "keywords": [{"keyword": k} for k in keywords]}
        self.w.filters[f["id"]] = f
        return f

    def delete_filter(self, filter_id):
        self.w.filters.pop(filter_id, None)

    def _poll_owner(self, pid):
        return next(s for s in self.w.statuses.values() if (s.get("poll") or {}).get("id") == pid)

    def poll(self, pid):
        return self._poll_owner(pid)["poll"]

    def vote(self, pid, choices):
        st = self._poll_owner(pid)
        poll = st["poll"]
        if poll.get("expired"):
            raise ApiError(422, "poll has already ended")
        if poll.get("voted"):
            raise ApiError(422, "already voted")
        opts = [dict(o) for o in poll["options"]]
        for i in choices:
            opts[i]["votes_count"] = (opts[i].get("votes_count") or 0) + 1
        poll = dict(poll, options=opts, voted=True, own_votes=list(choices),
                    votes_count=poll.get("votes_count", 0) + len(choices),
                    voters_count=(poll.get("voters_count") or 0) + 1)
        self.w.statuses[st["id"]] = dict(st, poll=poll)
        return poll

    def bookmark(self, sid, on=True):
        st = dict(self.w.statuses[sid], bookmarked=on)
        self.w.statuses[sid] = st
        return st

    def bookmarks(self, limit=40, max_id=None, min_id=None):
        marked = [s for s in self.w.statuses.values() if s.get("bookmarked")]
        self.bookmarks_next = None
        return sorted(marked, key=_sid, reverse=True)[:limit]

    def favourites(self, limit=40, max_id=None, min_id=None):
        liked = [s for s in self.w.statuses.values() if s.get("favourited")]
        self.favourites_next = None
        return sorted(liked, key=_sid, reverse=True)[:limit]

    def follow_options(self, acc_id, reblogs=None, languages=None):
        opts = self.w.follow_opts.setdefault(acc_id, {"showing_reblogs": True,
                                                       "languages": None})
        if reblogs is not None:
            opts["showing_reblogs"] = reblogs
        if languages is not None:
            opts["languages"] = list(languages) or None
        return dict(self.relationship(acc_id), **opts)

    def notify_posts(self, acc_id, on=True):
        self.w.bells[acc_id] = on
        return {"id": acc_id, "following": True, "notifying": on}

    def reblog(self, sid, on=True):
        st = dict(self.w.statuses[sid], reblogged=on)
        self.w.statuses[sid] = st
        return {"id": "rb" + sid, "reblog": st, "account": ME}

    def authorize_follow(self, acc_id):
        self.w.requests = [a for a in self.w.requests if a["id"] != acc_id]

    reject_follow = authorize_follow

    # ---- 0.11 (core/social.py) ------------------------------------------------------
    def _need(self, feature):
        self.w.calls.append(feature)
        if feature in self.w.missing:  # a server without it (GoToSocial, say)
            raise ApiError(404, "Not Found")

    def favourited_by(self, sid, max_id=None):
        self._need("favourited_by")
        return list(self.w.reactions.get(sid, {}).get("favourited_by", [])), None

    def reblogged_by(self, sid, max_id=None):
        self._need("reblogged_by")
        return list(self.w.reactions.get(sid, {}).get("reblogged_by", [])), None

    def quotes(self, sid, max_id=None):
        self._need("quotes")
        return list(self.w.quotes.get(sid, [])), None

    def revoke_quote(self, sid, quoting_id):
        self._need("quotes")
        st = dict(self.w.statuses[quoting_id], quote={"state": "revoked", "quoted_status": None})
        self.w.statuses[quoting_id] = st
        self.w.quotes[sid] = [q for q in self.w.quotes.get(sid, []) if q["id"] != quoting_id]
        return st

    def mute_conversation(self, sid, on=True):
        self._need("mute_thread")
        st = dict(self.w.statuses[sid], muted=on)
        self.w.statuses[sid] = st
        return st

    def conversations(self, limit=40):
        self._need("conversations")
        return [dict(c) for c in self.w.conversations][:limit]

    def read_conversation(self, cid):
        self._need("conversations")
        for c in self.w.conversations:
            if c["id"] == cid:
                c["unread"] = False
        self.w.read_conversations.append(cid)
        return {}

    def dismiss_notification(self, nid):
        self._need("dismiss")
        self.w.activity = [n for n in self.w.activity if n["id"] != nid]

    def clear_notifications(self):
        self._need("dismiss")
        self.w.activity = []

    def interaction_requests(self, status_id=None):
        self._need("interactions")
        return list(self.w.interactions)

    def answer_interaction(self, req_id, approve):
        self.w.interactions = [r for r in self.w.interactions if r["id"] != req_id]
        self.w.answered.append((req_id, approve))
        return {"id": req_id}

    def notifications_unread(self):
        return {"count": len(self.w.activity)}

    def remove_from_followers(self, acc_id):
        self._need("remove_follower")
        self.w.followers.discard(acc_id)
        return {"id": acc_id, "followed_by": False, "following": acc_id in self.w.following}

    def endorse(self, acc_id, on=True):
        self._need("endorse")
        (self.w.endorsed.add if on else self.w.endorsed.discard)(acc_id)
        return {"id": acc_id, "endorsed": on}

    def my_featured_tags(self):
        self._need("featured_tags")
        return [{"id": "t" + n, "name": n} for n in sorted(self.w.my_tags)]

    def feature_tag(self, name):
        self._need("featured_tags")
        self.w.my_tags.add(name)
        return {"id": "t" + name, "name": name}

    def unfeature_tag(self, tag_id):
        self.w.my_tags.discard(tag_id[1:])

    def familiar_followers(self, ids):
        self._need("familiar")
        return [{"id": i, "accounts": self.w.familiar.get(i, [])} for i in ids]

    def suggestions(self, limit=40):
        self._need("suggestions")
        return [{"source": "global", "account": a} for a in self.w.suggested][:limit]

    def dismiss_suggestion(self, acc_id):
        self._need("suggestions")
        self.w.suggested = [a for a in self.w.suggested if a["id"] != acc_id]

    def directory(self, offset=0, local=False, limit=40):
        self._need("directory")
        return self.w.directory[offset:offset + limit]

    def trends(self, kind, offset=0, limit=20):
        self._need("trends_" + kind)
        return list(self.w.trends.get(kind, []))

    def instance_rules(self):
        return [{"id": "1", "text": "Be kind"}]

    def instance_page(self, which):
        return {"content": f"<p>{which} text</p>"}

    def preferences(self):
        self._need("preferences")
        return dict(self.w.prefs)

    def react_announcement(self, aid, name, on=True):
        self._need("announcement_reactions")
        self.w.reacted.append((aid, name, on))


class World:
    def __init__(self):
        self.statuses, self.home, self.local, self.notifications = {}, [], [], []
        self.requests = []
        self.posted = []
        self.announcements = []
        self.uploads = []  # (path, description, focus)
        self.emoji = []  # the server's custom emoji
        self.featured = {}  # account id -> {"tags": [...], "people": [...]}
        self.revoked = []  # tokens revoked through /oauth/revoke
        self.policy = None  # notification policy: None — the server has none (404)
        self.held, self.answered = [], []  # notification requests; answers to them
        self.me = ME
        self.remote = {}  # uri -> status my server hasn't got yet (search resolves it)
        self.languages = []  # the language of each post, "" — none given
        self.calls = []
        self.seq = 1000
        self.fail_auth = False
        self.profile = {}
        self.lists = {}
        self.list_refuse = set()
        self.interactions, self.answered = [], []
        self.follow_opts = {}
        self.activity = []
        self.following = set()
        self.followed_tags = set()
        self.muted, self.blocked, self.filters = set(), set(), {}
        self.history = {}
        self.profile_updates = []
        self.markers = {}  # timeline -> last_read_id, as another client left it
        self.extras = []  # sensitive / poll of each post
        self.reports = []
        self.blocked_domains = set()
        self.notes = {}
        self.scheduled = []
        self.bells = {}
        self.missing = set()  # features this server answers 404 for (social.py)
        self.reactions = {}  # sid -> {"favourited_by": [accounts], "reblogged_by": [...]}
        self.quotes = {}  # sid -> [statuses quoting it]
        self.conversations, self.read_conversations = [], []
        self.followers, self.endorsed, self.my_tags = set(), set(), set()
        self.familiar, self.suggested, self.directory = {}, [], []
        self.trends = {}
        self.prefs = {"posting:default:visibility": "public"}
        self.reacted = []

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

