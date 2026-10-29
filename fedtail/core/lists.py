"""Lists and lanes of tags: the server's lists (made, renamed, ordered, who is in them —
asked again later when the server isn't ready) and the saved lanes of several hashtags;
their lanes' titles and pictures."""

import logging
import threading
import time

from . import custom, lanes, presets, sources, taggroups
from .model import real
from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class ListsMixin:
    """A part of Core (core/app.py): see the module's words."""

    def _refresh_lists(self):
        """Lists and who is in them, from the server; lanes follow."""
        self._retry_list_pending()
        got = [{"id": x["id"], "title": x.get("title", ""), "exclusive": bool(x.get("exclusive")),
                "replies_policy": x.get("replies_policy") or ""}
               for x in self.api.lists()]
        members = {x["id"]: {a["id"] for a in self.api.list_accounts(x["id"])} for x in got}
        for list_id, acc_id, _since in self._list_pending():  # still waiting: in, here
            members.setdefault(list_id, set()).add(acc_id)
        self._lists_checked = time.monotonic()
        if got == self.lists and members == self.list_members:
            return
        self._apply_lists(got, members)

    def _apply_lists(self, got, members):
        got = self._ordered_lists(got)
        self.lists, self.list_members = got, members
        for x in got:
            name = f"list:{x['id']}"
            if name not in self.sources:
                self.sources[name] = sources.list_source(self.api, x["id"])
        self.tag_groups = self._tag_groups()
        for g in self.tag_groups:
            name = taggroups.lane_name(g)
            if name not in self.sources:
                # lanes.tags_one_request: where the server takes any[]/all[]/none[]
                # (Mastodon) the group is one request, not one per tag
                once = bool(self.cfg["lanes"].get("tags_one_request")) and \
                    getattr(self.caps, "software", "") == "mastodon"
                self.sources[name] = sources.tag_group_source(self.api, g, once)
        self.customs = custom.load(self.cfg)[0]  # the rules anew (the config may have changed)
        new_lanes = self._shown_lanes(lanes.enabled(self.cfg, got, self.tag_groups))
        self.lane_by_name = {lane.name: lane for lane in new_lanes}
        self.lanes = new_lanes
        self._lists_version += 1
        if threading.current_thread() is not threading.main_thread():
            self._warm_lanes()  # every lane anew (lists change what Home shows)
        self.emit("lists_changed", list(got))
        self.poll_now()

    def _ordered_lists(self, got):
        """Lists in my order (moved up and down in the sidebar, kept here: servers have
        no order of lists); the ones not placed yet keep the server's order, at the end."""
        order = self.store.kv_get("list_order", []) or []
        rank = {lid: i for i, lid in enumerate(order)}
        return sorted(got, key=lambda x: rank.get(x["id"], len(order) + got.index(x)))

    def move_list(self, list_id, step):
        """A list one place up (step -1) or down (+1) in the sidebar."""
        ids = [x["id"] for x in self.lists]
        if list_id not in ids:
            return
        i = ids.index(list_id)
        j = max(0, min(len(ids) - 1, i + step))
        if i == j:
            return
        ids.insert(j, ids.pop(i))
        self.store.kv_set("list_order", ids)
        if self.sync:
            self.sync.record_setting("list_order")
        self._apply_lists(list(self.lists), self.list_members)

    def list_people(self, list_id):
        """Who is in a list (and who waits to go in), for a tab of people: a future of
        ({accounts, relations}, None)."""
        def job():
            accounts = self.api.list_accounts(list_id)
            waiting = [p[1] for p in self._list_pending() if p[0] == list_id]
            log.info("list %s: %d on the server, %d waiting to go in", list_id,
                     len(accounts), len(waiting))
            have = {a["id"] for a in accounts}
            for acc_id in waiting:
                if acc_id not in have:
                    try:
                        accounts.append(self.api.account(acc_id))
                    except ApiError:
                        pass
            return self._with_relations(accounts), None
        return self.submit(job)

    def _tag_groups(self):
        """Lanes of several tags: the config's ([[lanes.tag_groups]]) and the ones saved
        from a search (kept here). Each {"any", "all", "none", "name", "saved"}."""
        out = []
        for g in self.cfg["lanes"].get("tag_groups") or []:
            out.append(dict(taggroups.normal(g), name=g.get("name") or "", saved=False,
                            not_in_home=bool(g.get("not_in_home"))))
        for g in self.store.kv_get("tag_groups", []) or []:
            out.append(dict(taggroups.normal(g), name=g.get("name") or "", saved=True,
                            not_in_home=bool(g.get("not_in_home"))))
        return out

    def set_tag_group_in_home(self, lane_name, in_home):
        """A saved lane of tags: its posts in Home too (True), or only in it (False)."""
        def job():
            saved = self.store.kv_get("tag_groups", []) or []
            for g in saved:
                if taggroups.lane_name(g) == lane_name:
                    g["not_in_home"] = not in_home
            self.store.kv_set("tag_groups", saved)
            if self.sync:
                self.sync.record_setting("tag_groups")
            self._apply_lists(list(self.lists), self.list_members)
        return self.submit(job)

    def tag_group_timeline(self, spec, max_id=None):
        """A page of several tags at once, for a search tab."""
        def job():
            page = taggroups.fetch(self.api.tag_timeline, spec,
                                   limit=self.cfg["feed"]["page_size"], max_id=max_id)
            self.store.put_statuses(page)
            return page
        return self.submit(job)

    def save_tag_group(self, spec, name="", in_home=True):
        """A search of several tags kept as a lane in the sidebar (group "Теги"); in_home
        False: its posts leave Home (like a list's "hide members")."""
        def job():
            saved = [g for g in self.store.kv_get("tag_groups", []) or []
                     if taggroups.key(g) != taggroups.key(spec)]
            saved.append(dict(taggroups.normal(spec), name=name, not_in_home=not in_home))
            self.store.kv_set("tag_groups", saved)
            if self.sync:
                self.sync.record_setting("tag_groups")
            self._apply_lists(list(self.lists), self.list_members)
            return taggroups.lane_name(spec)
        return self.submit(job)

    def add_tag_to_group(self, lane_name, tag):
        """A tag into a saved lane of tags (one more of its "any"). Its lane is called
        by what it holds, so it gets a new name: returned."""
        tag = tag.lstrip("#").lower()

        def job():
            saved = self.store.kv_get("tag_groups", []) or []
            out, new = [], lane_name
            for g in saved:
                if taggroups.lane_name(g) == lane_name:
                    g = dict(taggroups.normal(g), name=g.get("name") or "")
                    if tag not in g["any"] + g["all"]:
                        g["any"] = sorted(set(g["any"]) | {tag})
                    new = taggroups.lane_name(g)
                out.append(g)
            self.store.kv_set("tag_groups", out)
            if self.sync:
                self.sync.record_setting("tag_groups")
            self._apply_lists(list(self.lists), self.list_members)
            return new
        return self.submit(job)

    def drop_tag_group(self, lane_name):
        def job():
            saved = [g for g in self.store.kv_get("tag_groups", []) or []
                     if taggroups.lane_name(g) != lane_name]
            self.store.kv_set("tag_groups", saved)
            if self.sync:
                self.sync.record_setting("tag_groups")
            self._apply_lists(list(self.lists), self.list_members)
        return self.submit(job)

    def lane_title(self, name):
        """A list's title; None for the built-in lanes (their names are translated)."""
        c = next((c for c in self.customs if c.name == name), None)
        if c is not None:
            return c.title  # its own, or None: the built-in word
        if taggroups.is_tags(name):
            g = next((g for g in self.tag_groups if taggroups.lane_name(g) == name), None)
            return (g or {}).get("name") or taggroups.title(taggroups.spec_of(name) or {})
        if lanes.is_list(name):
            lid = name[len(lanes.LIST_PREFIX):]
            return next((x["title"] for x in self.lists if x["id"] == lid), "?")
        return None

    def lane_icon(self, name):
        """The picture of a lane: a lane of rules' `icon`; else the one its name has
        (frontends/iconpack.py LANE); a lane of one's own without one — a list's."""
        c = next((c for c in self.customs if c.name == name), None)
        if c is not None and c.rule.icon:
            return c.rule.icon
        if c is not None and name not in presets.known_names():
            return "list"
        return None

    def lists_of(self, acc_id):
        return {lid for lid, m in self.list_members.items() if acc_id in m}

    def create_list(self, title, exclusive=False, add=None, replies_policy=None):
        """replies_policy: whose replies the list shows — "followed", "list", "none"."""
        def job():
            x = self.api.create_list(title, exclusive, replies_policy=replies_policy) \
                if replies_policy else self.api.create_list(title, exclusive)
            try:
                if add:  # refused (not followed yet): waits, as with an existing list
                    self._list_add_or_wait(x["id"], add)
            finally:
                self._refresh_lists()  # the new list shows whatever happened to the add
            return x
        return self.submit(job)

    def update_list(self, list_id, title, exclusive, replies_policy=None):
        def job():
            if replies_policy:
                self.api.update_list(list_id, title, exclusive, replies_policy=replies_policy)
            else:
                self.api.update_list(list_id, title, exclusive)
            self._refresh_lists()
        return self.submit(job)

    def delete_list(self, list_id):
        def job():
            self.api.delete_list(list_id)
            self._refresh_lists()
        return self.submit(job)

    LIST_PENDING_DAYS = 30

    def set_in_list(self, list_id, acc_id, on):
        """Into a list or out. A server takes only people I follow into lists; someone
        just followed (a locked account that hasn't approved yet, or a server slow to
        record it) is refused — then fedtail remembers it and puts them in by itself
        once it can. Returns "pending" in that case."""
        def job():
            if on:
                result = self._list_add_or_wait(list_id, acc_id)
            else:
                self.store.kv_set("list_pending", [p for p in self._list_pending()
                                                   if (p[0], p[1]) != (list_id, acc_id)])
                try:
                    self.api.list_remove(list_id, acc_id)
                except ApiError as e:  # it was only waiting here, never on the server
                    if e.status != 404:
                        raise
                result = "done"
            if result == "pending":  # in the list here at once: lanes treat them so
                members = {k: set(v) for k, v in self.list_members.items()}
                members.setdefault(list_id, set()).add(acc_id)
                self._apply_lists(list(self.lists), members)
            else:
                self._refresh_lists()
            # who is hidden where changed: every lane may look different now
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
            return result
        return self.submit(job)

    def _ask_prefetch(self, statuses):
        """The pictures of posts just come, for the frontend to fetch ahead
        (feed.prefetch): "previews" — previews and avatars; "all" — the originals, the
        videos and gifs too; "off" — nothing ahead, as before."""
        mode = self.cfg["feed"].get("prefetch", "previews")
        if mode == "off" or not statuses:
            return
        urls = []
        for st in statuses:
            for s in (st, real(st)):
                acc = s.get("account") or {}
                urls.append(acc.get("avatar_static") or acc.get("avatar"))
            for m in real(st).get("media_attachments") or []:
                urls.append(m.get("preview_url"))
                if mode == "all" and m.get("type") == "image":
                    urls.append(m.get("url"))
            card = real(st).get("card") or {}
            urls.append(card.get("image"))
        urls = [u for u in dict.fromkeys(urls) if u]
        if urls:
            self.emit("prefetch", urls)
        if mode == "all":  # videos, gifs, sounds: to their own cache (ui.video_disk_mb)
            videos = [m.get("url") for st in statuses
                      for m in real(st).get("media_attachments") or []
                      if m.get("type") in ("video", "gifv", "audio") and m.get("url")]
            if videos:
                self.emit("prefetch_video", list(dict.fromkeys(videos)))

    def _list_add_or_wait(self, list_id, acc_id):
        """Into the list on the server, or — refused for someone not followed (yet) —
        remembered and tried again on each lists refresh. "done" or "pending"."""
        pending = [p for p in self._list_pending() if (p[0], p[1]) != (list_id, acc_id)]
        try:
            self.api.list_add(list_id, acc_id)
            result = "done"
        except ApiError as e:
            if e.status not in (403, 404, 422):
                raise
            pending.append([list_id, acc_id, time.time()])
            log.info("list %s: %s not followed yet (%s), will add later", list_id, acc_id,
                     e.status)
            result = "pending"
        self.store.kv_set("list_pending", pending)
        return result

    def _list_pending(self):
        return [p for p in self.store.kv_get("list_pending", []) or []
                if time.time() - p[2] < self.LIST_PENDING_DAYS * 86400]

    def _retry_list_pending(self):
        """People waiting to go into lists: try again (on every lists refresh)."""
        pending = self._list_pending()
        if not pending:
            return
        # who is followed now: only they can go in; a request still waiting stays
        # waiting without asking the server; one refused or withdrawn is let go (it was
        # tried, and refused with a 404, every ten minutes for a month)
        try:
            rel = {r["id"]: r for r in self.api.relationships(
                list(dict.fromkeys(p[1] for p in pending)))}
        except Exception as e:  # noqa: BLE001 — can't tell now: try them all
            log.debug("list pending: relationships: %s", e)
            rel = None
        left = []
        for list_id, acc_id, since in pending:
            r = rel.get(acc_id) if rel is not None else None
            if r is not None and not r.get("following"):
                if r.get("requested"):
                    left.append([list_id, acc_id, since])
                else:
                    log.info("list %s: %s is not followed (the request refused or "
                             "withdrawn): not waiting to add them any more", list_id, acc_id)
                continue
            try:
                self.api.list_add(list_id, acc_id)
                log.info("list %s: %s added after all", list_id, acc_id)
            except ApiError as e:
                if r is not None and r.get("following") and e.status == 422:
                    # followed, and still "can't": in the list already (GoToSocial: "is
                    # already in list" — it was asked again every round, 29.10), or never
                    log.info("list %s: %s followed and refused (%s): in it already, not "
                             "waiting any more", list_id, acc_id, e.status)
                    continue
                log.debug("list %s pending %s: %s", list_id, acc_id, e)
                left.append([list_id, acc_id, since])
            except Exception as e:  # noqa: BLE001 — slow, or down: next time
                log.debug("list %s pending %s: %s", list_id, acc_id, e)
                left.append([list_id, acc_id, since])
        self.store.kv_set("list_pending", left)
