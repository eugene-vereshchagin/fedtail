"""The lane editor as a place (common/laneedit.py does the work): "lanes" — every lane, in
its order, shown or not, with ↑ ↓, show / hide, edit, "back to the set's", delete; "lane" —
one lane as a form: its title, picture, section, sources, how it is read, and over the form
its conditions in words; "cond" — one condition, key by key (what it asks, what else it may
ask), its quick filter, the whole of it as a line; "condpart" — one key's values to tick
(or words to type). No syntax needed: the words of every key and value are in i18n
(lk_*, lv_*, lt_*). A change is written into
config.toml at once and the lanes follow; every interface draws it (Qt's and GTK's
place windows, the web page, the terminal)."""

from __future__ import annotations

from ...core import atoms
from ...i18n import _, current_language
from . import laneedit

NEW = "new"  # the form's name of the empty line that adds a condition


class LanePlaces:
    """The places "lanes" and "lane" (mixed into common/places.py Places)."""

    def _editor(self):
        return laneedit.Editor.load(self.view)

    def _lane_out(self, ed, message="", open_=None):
        from .places import Out
        from .settings import SaveError
        try:
            said = ed.save(self.view)
        except (SaveError, ValueError) as e:
            return Out(error=str(e))
        return Out(message=message or said, refresh=open_ is None, open=open_)

    # ---- every lane ----------------------------------------------------------------------
    def _p_lanes(self, _arg, _tab, _cur):
        from ...core import presets
        from .places import Page, Row
        ed = self._editor()
        page = Page("lanes", _("le_title"), hint=_("le_hint", preset=ed.preset))
        # the set first: "as in fedtail / Mastodon / Tusky / Phanpy", then one's own on top
        own = bool(ed.own) or ed.cfg["lanes"].get("enabled")
        page.rows.append(Row("heading", _("le_sets")))
        for name in presets.names():
            on = name == ed.preset
            words = _("le_set_" + name) if _("le_set_" + name) != "le_set_" + name else name
            line = (_("le_set_now_own") if own else _("le_set_now")) if on else ""
            page.rows.append(Row("item", ("● " if on else "○ ") + name, words + (
                " · " + line if line else ""), key="set:" + name, buttons=() if on else (
                self._btn(_("le_set_take"), "lanes", "preset", name, primary=True,
                          tip=_("le_set_take_tip")),)))
        if own:
            page.rows.append(Row("item", _("le_own_title"), _("le_own_line", n=len(ed.own)),
                                 key="_own", buttons=(self._btn(
                                     _("le_own_drop"), "lanes", "clean", "",
                                     tip=_("le_own_drop_tip")),)))
        page.rows.append(Row("heading", _("le_lanes_now")))
        page.rows.append(Row("item", _("le_new"), _("le_new_tip"), key="_new", buttons=(
            self._btn(_("le_new"), "lanes", "new", "", primary=True),)))
        shown = [n for n in ed.order if n in ed.shown]
        for n in ed.order:
            on = n in ed.shown
            kind = ed.kind(n)
            words = [n]
            if kind != "rule":
                words.append(_("le_kind_" + kind) if _("le_kind_" + kind) != "le_kind_" + kind
                             else kind)
            if ed.changed(n):
                words.append(_("le_changed"))
            elif ed.is_own(n):
                words.append(_("le_own"))
            if not on:
                words.append(_("le_hidden"))
            if kind == "rule":  # a typo, a key not known, "never filled": said here too
                bad = laneedit.problems(ed.tables.get(n) or {})
                if bad:
                    words.append("⚠ " + "; ".join(bad))
            buttons = []
            if on:
                if shown.index(n) > 0:
                    buttons.append(self._btn("↑", "lanes", "up", n, tip=_("le_up")))
                if shown.index(n) < len(shown) - 1:
                    buttons.append(self._btn("↓", "lanes", "down", n, tip=_("le_down")))
            if n != "tags":
                buttons.append(self._btn(_("le_hide") if on else _("le_show"), "lanes",
                                         "toggle", n))
            if kind == "rule":
                buttons.append(self._btn(_("le_edit"), "lanes", "edit", n, primary=True))
            if ed.changed(n):
                buttons.append(self._btn(_("le_reset"), "lanes", "reset", n,
                                         tip=_("le_reset_tip")))
            elif ed.is_own(n):
                buttons.append(self._btn(_("le_delete"), "lanes", "delete", n))
            page.rows.append(Row("item", ("" if on else "· ") + ed.title(n), " · ".join(words),
                                 key=n, buttons=tuple(buttons)))
        return page

    def _a_lanes_preset(self, name, _v, confirmed, _ans):
        """Another set: its lanes, in its order (lanes.enabled back to the set's);
        one's own lanes stay, after them."""
        from ...core import config_edit, presets
        from .places import Out
        from .settings import SaveError, config_file
        if name not in presets.names():
            return Out(error=name)
        if not confirmed:
            return Out(confirm=_("le_set_q", name=name))
        try:
            cfg, _w = config_edit.save(config_file(self.view),
                                       {("lanes", "preset"): name,
                                        ("lanes", "enabled"): config_edit.UNSET})
        except SaveError as e:
            return Out(error=str(e))
        saved = getattr(self.view, "lanes_saved", None)
        if saved is not None:
            saved(cfg)
        return Out(message=_("le_set_done", name=name), refresh=True)

    def _a_lanes_clean(self, _d, _v, confirmed, _ans):
        """One's own changes all gone: the set as it is."""
        from ...core import config_edit
        from .places import Out
        from .settings import SaveError, config_file
        if not confirmed:
            return Out(confirm=_("le_own_drop_q"))
        try:
            cfg, _w = config_edit.save(config_file(self.view),
                                       {("lanes", "custom"): [],
                                        ("lanes", "enabled"): config_edit.UNSET})
        except SaveError as e:
            return Out(error=str(e))
        saved = getattr(self.view, "lanes_saved", None)
        if saved is not None:
            saved(cfg)
        return Out(message=_("le_own_dropped"), refresh=True)

    def _a_lanes_up(self, name, _v, _c, _ans):
        ed = self._editor()
        ed.move(name, -1)
        return self._lane_out(ed)

    def _a_lanes_down(self, name, _v, _c, _ans):
        ed = self._editor()
        ed.move(name, +1)
        return self._lane_out(ed)

    def _a_lanes_toggle(self, name, _v, _c, _ans):
        ed = self._editor()
        ed.toggle(name)
        return self._lane_out(ed)

    def _a_lanes_edit(self, name, _v, _c, _ans):
        from .places import Out
        return Out(open={"page": "lane", "arg": name})

    def _a_lanes_reset(self, name, _v, confirmed, _ans):
        from .places import Out
        if not confirmed:
            return Out(confirm=_("le_reset_q", name=name))
        ed = self._editor()
        ed.reset(name)
        return self._lane_out(ed)

    def _a_lanes_delete(self, name, _v, confirmed, _ans):
        from .places import Out
        if not confirmed:
            return Out(confirm=_("le_delete_q", name=name))
        ed = self._editor()
        ed.delete(name)
        return self._lane_out(ed)

    def _a_lanes_new(self, _d, _v, _c, answer):
        from .places import Out
        if answer is None:
            return Out(ask=(_("le_new"), _("le_new_q"), ""))
        ed = self._editor()
        try:
            name = ed.new(answer)
        except ValueError as e:
            return Out(error=str(e))
        return self._lane_out(ed, open_={"page": "lane", "arg": name})

    # ---- why a post is (or isn't) in each lane ----------------------------------------------
    def _p_why(self, sid, _tab, _cur):
        """"Why is it here?": for each lane of rules shown — whether it shows the post, by
        which condition, or what kept it out (common to every interface)."""
        from .places import Page, Row
        got = self.view.explain_post(sid) if hasattr(self.view, "explain_post") else []
        page = Page("why", _("why_here"), arg=sid, hint=_("why_hint"),
                    empty=_("why_none"))
        for g in got:
            title = g["title"] or _("lane_" + g["lane"])
            if title == "lane_" + g["lane"]:
                title = g["lane"]
            lines = []
            if g["quiet"] == "silenced":
                lines.append(_("why_silenced"))
            elif g["quiet"] == "before_rules":
                lines.append(_("why_before_rules"))
            if g["taken"]:
                raw = next(c for w, i, c, _r in g["conds"] if w == "any" and i == g["by"])
                lines.append(_("why_taken", n=g["by"] + 1, line=laneedit.cond_line(raw)))
            elif g["out"] is not None:
                raw = next(c for w, i, c, _r in g["conds"] if w == "none" and i == g["out"])
                lines.append(_("why_kept_out", n=g["out"] + 1, line=laneedit.cond_line(raw)))
            elif not g.get("source_ok", True):
                lines.append(_("why_source"))
            else:
                for w, i, raw, reason in g["conds"]:
                    if w == "any" and reason:
                        lines.append(_("why_not_cond", n=i + 1, what=reason,
                                       line=laneedit.cond_line(raw)))
            mark = "✓ " if g["in_lane"] else "· "
            page.rows.append(Row("item", mark + title, "\n".join(lines), key=g["lane"],
                                 buttons=(self._btn(_("le_edit"), "lanes", "edit", g["lane"]),)))
        return page

    # ---- one lane ------------------------------------------------------------------------
    def _p_lane(self, name, _tab, _cur):
        from .places import Field, Page, Row
        ed = self._editor()
        t = ed.tables.get(name)
        if t is None or ed.kind(name) != "rule":
            raise KeyError(name)
        page = Page("lane", _("le_lane_title", title=ed.title(name)), arg=name)
        tools = [self._btn(_("le_back"), "lane", "back", name)]
        if ed.changed(name):
            tools.append(self._btn(_("le_reset"), "lanes", "reset", name,
                                   tip=_("le_reset_tip")))
        page.rows.append(Row("item", name, _("le_set_lane") if ed.from_set(name)
                             else _("le_own"), key="_tools", buttons=tuple(tools)))
        for w in laneedit.problems(t):
            page.rows.append(Row("text", "⚠ " + w))
        for part in ("any", "none"):  # the conditions: each a row, edited on a page of its own
            page.rows.append(Row("heading", _("le_conds_" + part)))
            for i, c in enumerate(_conds(t, part)):
                line = laneedit.cond_line(c)
                if c.get("switch"):
                    line += " · ⇄ " + str(c["switch"]) + (" (" + _("le_f_hidden") + ")"
                                                          if c.get("shown") is False else "")
                arg = _cond_arg(name, part, i)
                page.rows.append(Row("item", f"{i + 1}. " + laneedit.cond_words(c), line,
                                     key=f"{part}.{i}", buttons=(
                                         self._btn(_("le_edit"), "lane", "cond", arg,
                                                   primary=True),
                                         self._btn(_("le_cond_drop"), "lane", "conddrop",
                                                   arg))))
            page.rows.append(Row("item", _("le_cond_add"), _("le_cond_add_tip"),
                                 key=f"{part}.new", buttons=(self._btn(
                                     _("le_cond_add"), "lane", "cond",
                                     _cond_arg(name, part, NEW)),)))
        title = ed.title(name)  # its own, or the built-in word it shows
        icons = (("", _("le_f_icon_none")),) + tuple(sorted(
            ((i, _("pic_" + i)) for i in atoms.LANE_ICONS), key=lambda c: c[1].casefold()))
        sources = sorted(set(laneedit.SOURCES) | set(_words(t.get("source"))))
        form = [
            Field("title", _("le_f_title"), str(title or ""), tip=_("le_f_title_tip")),
            Field("icon", _("le_f_icon"), str(t.get("icon") or ""), "choice", icons,
                  pictures=True),
            Field("group", _("le_f_group"), str(t.get("group") or "personal"), "choice",
                  tuple((g, _("grp_" + g)) for g in laneedit.GROUPS)),
            Field("source", _("le_f_source"), _words(t.get("source")), "checks",
                  tuple((s, s) for s in sources), tip=_("le_f_source_tip")),
            Field("read", _("le_f_read"), str(t.get("read") or "through"), "choice",
                  tuple((r, _("le_read_" + r)) for r in laneedit.READS)),
            Field("sort", _("le_f_sort"), str(t.get("sort") or "arrival"), "choice",
                  tuple((s, _("le_sort_" + s)) for s in laneedit.SORTS)),
            Field("mode", _("le_f_mode"), str(t.get("mode") or "lane"), "choice",
                  (("lane", _("le_mode_lane")), ("catch_up", _("le_mode_catch_up")))),
            Field("window", _("le_f_window"), str(t.get("window") or ""),
                  tip=_("le_f_window_tip")),
            Field("filter_context", _("le_f_filters"), str(t.get("filter_context") or ""),
                  "choice", (("", "—"),) + tuple((c, _("le_fctx_" + c))
                                                 for c in laneedit.FILTER_CONTEXTS)),
            Field("per_author", _("le_f_per_author"), str(t.get("per_author") or ""),
                  tip=_("le_f_per_author_tip")),
            Field("bundle", _("le_f_bundle"), str(t.get("bundle") or ""), "choice",
                  (("", "—"), ("author", _("le_bundle_author")))),
            Field("view", _("le_f_view"), str(t.get("view") or ""), "choice",
                  (("", _("le_view_posts")), ("threads", _("le_view_threads"))),
                  tip=_("le_f_view_tip")),
            Field("threads_shown", _("le_f_threads_shown"), str(t.get("threads_shown") or ""),
                  "choice", (("", _("le_threads_new")), ("all", _("le_threads_all"))),
                  tip=_("le_f_threads_shown_tip")),
            Field("open_at", _("le_f_open_at"), str(t.get("open_at") or ""), "choice",
                  (("", _("le_open_at_setting")), ("post", _("le_open_at_post")),
                   ("first_unread", _("le_open_at_first_unread"))),
                  tip=_("le_f_open_at_tip")),
            # the lane's own switches over what it holds (atoms.SWITCHES): its rule says
            Field("switches", _("le_f_switches"), list(t.get("switches") or ()), "checks",
                  tuple((s, _(s)) for s in atoms.SWITCHES), tip=_("le_f_switches_tip")),
        ]
        page.form = tuple(form)
        page.submit = self._btn(_("save"), "lane", "save", name, primary=True)
        return page

    # ---- one condition, and one part of it ---------------------------------------------
    def _a_lane_cond(self, arg, _v, _c, _ans):
        from .places import Out
        return Out(open={"page": "cond", "arg": arg})

    def _a_lane_conddrop(self, arg, _v, confirmed, _ans):
        from .places import Out
        name, part, i = _cond_of(arg)
        ed = self._editor()
        conds = _conds(ed.tables.get(name) or {}, part)
        if not isinstance(i, int) or i >= len(conds):
            return Out(error=arg)
        if not confirmed:
            return Out(confirm=_("le_cond_drop_q", line=laneedit.cond_line(conds[i])))
        del conds[i]
        return self._cond_put(ed, name, part, conds)

    def _cond_put(self, ed, name, part, conds, open_=None):
        """The lane with these conditions of `part`, saved; open_: where to go after."""
        from .places import Out
        t = dict(ed.tables.get(name) or {})
        if conds or part == "any":
            t[part] = conds
        else:
            t.pop(part, None)
        bad = laneedit.problems(t)
        if bad:
            return Out(error="; ".join(bad))
        ed.put(name, t)
        return self._lane_out(ed, open_=open_)

    def _p_cond(self, arg, _tab, _cur):
        """One condition: what it asks, key by key (each its own page to tick the values
        on), what else it may ask, its quick filter — and the whole of it as a line."""
        from .places import Field, Page, Row
        name, part, i = _cond_of(arg)
        ed = self._editor()
        t = ed.tables.get(name)
        if t is None or ed.kind(name) != "rule":
            raise KeyError(name)
        conds = _conds(t, part)
        if isinstance(i, int) and i >= len(conds):
            raise KeyError(arg)
        c = conds[i] if isinstance(i, int) else {}
        title = _("le_cond_title", n=i + 1, title=ed.title(name)) if isinstance(i, int) \
            else _("le_cond_new_title", title=ed.title(name))
        page = Page("cond", title, arg=arg, hint=_("le_cond_hint2"))
        tools = [self._btn(_("le_cond_back"), "cond", "back", name)]
        if isinstance(i, int):
            tools.append(self._btn(_("le_cond_drop"), "lane", "conddrop", arg))
        page.rows.append(Row("item", laneedit.cond_words(c), laneedit.cond_line(c),
                             key="_tools", buttons=tuple(tools)))
        asked = [k for k in c if k in laneedit.KEYS]
        if asked:
            page.rows.append(Row("heading", _("le_cond_parts")))
        for k in asked:
            words = laneedit.cond_words({k: c[k]}).partition(": ")[2]
            page.rows.append(Row("item", laneedit.key_words(k), words, key="k:" + k,
                                 buttons=(self._btn(_("le_edit"), "cond", "part",
                                                    arg + SEP + k, primary=True),
                                          self._btn(_("le_cond_drop"), "cond", "unask",
                                                    arg + SEP + k))))
        rest = [k for k in laneedit.KEYS if k not in c]
        if rest:
            page.rows.append(Row("heading", _("le_cond_more_parts")))
        for k in rest:
            page.rows.append(Row("item", laneedit.key_words(k), k, key="k:" + k,
                                 buttons=(self._btn(_("le_cond_ask"), "cond", "part",
                                                    arg + SEP + k),)))
        form = [Field("line", _("le_cond_line"), laneedit.cond_line(c) if c else "",
                      tip=_("le_cond_line_tip"))]
        if part == "any":
            form.append(Field("switch", _("le_f_switch"), str(c.get("switch") or ""),
                              tip=_("le_f_switch_tip")))
            form.append(Field("hidden", _("le_f_hidden"), c.get("shown") is False, "check",
                              tip=_("le_f_hidden_tip")))
        page.form = tuple(form)
        page.submit = self._btn(_("save"), "cond", "save", arg, primary=True)
        return page

    def _a_cond_back(self, name, _v, _c, _ans):
        from .places import Out
        return Out(open={"page": "lane", "arg": name})

    def _a_cond_part(self, data, _v, _c, _ans):
        from .places import Out
        return Out(open={"page": "condpart", "arg": data})

    def _a_cond_unask(self, data, _v, _c, _ans):
        arg, _s, key = data.rpartition(SEP)
        return self._cond_change(arg, lambda c: c.pop(key, None))

    def _a_cond_save(self, arg, values, _c, _ans):
        from .places import Out
        line = str((values or {}).get("line") or "").strip()
        try:
            new = laneedit.parse_line(line) if line else {}
        except ValueError as e:
            return Out(error=str(e))
        switch = str((values or {}).get("switch") or "").strip()
        hidden = bool((values or {}).get("hidden"))

        def change(c):
            c.clear()
            c.update(new)
            if switch:
                c["switch"] = switch
                if hidden:
                    c["shown"] = False
        return self._cond_change(arg, change, back=True)

    def _cond_change(self, arg, change, back=False):
        """One condition changed by `change(cond)` (a new one made first) and saved; then
        the condition's page again — or the lane's (back)."""
        from .places import Out
        name, part, i = _cond_of(arg)
        ed = self._editor()
        t = ed.tables.get(name)
        if t is None:
            return Out(error=name)
        conds = _conds(t, part)
        if isinstance(i, int):
            if i >= len(conds):
                return Out(error=arg)
            c = dict(conds[i])
        else:
            c = {}
        try:
            change(c)
        except ValueError as e:
            return Out(error=str(e))
        if isinstance(i, int):
            conds[i] = c
        else:
            conds.append(c)
            i = len(conds) - 1
        where = {"page": "lane", "arg": name} if back else \
            {"page": "cond", "arg": _cond_arg(name, part, i)}
        return self._cond_put(ed, name, part, conds, open_=where)

    def _p_condpart(self, data, _tab, _cur):
        """One key of a condition: its values to tick (or the words to type), what the
        list hasn't typed beside them."""
        from .places import Field, Page
        arg, _s, key = data.rpartition(SEP)
        name, part, i = _cond_of(arg)
        if key not in laneedit.KEYS:
            raise KeyError(key)
        ed = self._editor()
        t = ed.tables.get(name)
        if t is None:
            raise KeyError(name)
        conds = _conds(t, part)
        c = conds[i] if isinstance(i, int) and i < len(conds) else {}
        now = laneedit.part_words(c, key)
        choices = laneedit.KEYS[key]
        page = Page("condpart", _("le_part_title", what=laneedit.key_words(key),
                                  title=ed.title(name)), arg=data,
                    hint=_("le_part_empty"))
        tip = _("lt_" + key) if _("lt_" + key) != "lt_" + key else _("le_part_more_tip")
        if key == "text":
            form = [Field("typed", _("le_part_typed"), laneedit.cond_line(
                {"text": c["text"]}).partition(": ")[2] if "text" in c else "", tip=tip)]
        elif choices and key in laneedit.SINGLE:
            form = [Field("one", _("le_part_one"), now[0] if now else "", "choice",
                          (("", "—"),) + tuple((v, laneedit.value_words(key, v))
                                               for v in choices))]
        elif choices:
            known = [v for v in now if v in choices]
            other = [v for v in now if v not in choices]
            form = [Field("ticked", _("le_part_words"), known, "checks",
                          tuple((v, laneedit.value_words(key, v)) for v in choices)),
                    Field("typed", _("le_part_more"), ", ".join(other), tip=tip)]
        else:
            form = [Field("typed", _("le_part_typed"), ", ".join(now), tip=tip)]
        page.form = tuple(form)
        page.submit = self._btn(_("save"), "condpart", "save", data, primary=True)
        return page

    def _a_condpart_save(self, data, values, _c, _ans):
        arg, _s, key = data.rpartition(SEP)
        values = values or {}
        ticked = values.get("ticked") or ([values["one"]] if values.get("one") else [])

        def change(c):
            got = laneedit.part_value(key, [x for x in ticked if isinstance(x, str)],
                                      values.get("typed") or "")
            if got is None:
                c.pop(key, None)
            else:
                c[key] = got
        return self._cond_change(arg, change)

    def _a_lane_back(self, _name, _v, _c, _ans):
        from .places import Out
        return Out(open={"page": "lanes"})

    def _a_lane_save(self, name, values, _c, _ans):
        from .places import Out
        ed = self._editor()
        old = ed.tables.get(name)
        if old is None:
            return Out(error=name)
        try:
            table = _table_of(name, old, values)
        except ValueError as e:
            return Out(error=str(e))
        bad = laneedit.problems(table)
        if bad:
            return Out(error="; ".join(bad))
        if table == old:
            return Out(message=_("le_same"), refresh=True)
        ed.put(name, table)
        return self._lane_out(ed)


SEP = "|"  # in a condition's place argument: lane|part|index (index "new": one to make)


def _cond_arg(name, part, i):
    return f"{name}{SEP}{part}{SEP}{i}"


def _cond_of(arg):
    """"lane|any|2" → ("lane", "any", 2); the index NEW stays a word."""
    name, part, i = (str(arg or "").split(SEP) + ["", "", ""])[:3]
    if part not in ("any", "none"):
        raise KeyError(arg)
    return name, part, int(i) if i.isdigit() else NEW


def _conds(table, part):
    """A lane's conditions of `part` as a new list of tables (a lone table: one)."""
    got = table.get(part) or []
    return [dict(c) for c in ([got] if isinstance(got, dict) else got) if isinstance(c, dict)]


def _words(v):
    if not v:
        return []
    return [v] if isinstance(v, str) else [str(x) for x in v]


def _table_of(name, old, values):
    """The form's values → the lane's new table (what the form doesn't show stays)."""
    t = {k: v for k, v in old.items() if k not in ("title", "icon", "group", "source", "read",
                                                    "sort", "mode", "window", "filter_context",
                                                    "per_author", "bundle", "view",
                                                    "threads_shown", "open_at",
                                                    "any", "none", "switches")}
    t["name"] = name
    title = str(values.get("title") or "").strip()
    was = old.get("title")
    builtin = _("lane_" + name)
    if title and not was and title in (name, builtin):
        title = ""  # the word it shows anyway: nothing of its own
    if title:
        if isinstance(was, dict):
            t["title"] = dict(was, **{current_language(): title})
        else:
            t["title"] = title
    for key, default in (("icon", ""), ("group", "personal"), ("read", "through"),
                         ("sort", "arrival"), ("mode", "lane"), ("window", ""),
                         ("filter_context", ""), ("bundle", ""), ("view", ""),
                         ("threads_shown", ""), ("open_at", "")):
        v = str(values.get(key) or "")
        if v and (v != default or key in old):
            t[key] = v
    n = str(values.get("per_author") or "").strip()
    if n:
        if not n.isdigit():
            raise ValueError(_("le_f_per_author_tip"))
        if int(n) or "per_author" in old:
            t["per_author"] = int(n)
    switches = [s for s in values.get("switches") or () if s in atoms.SWITCHES]
    if switches or "switches" in old:
        t["switches"] = switches
    src = [s for s in values.get("source") or () if isinstance(s, str)]
    if src:
        t["source"] = src[0] if len(src) == 1 else src
    for part in ("any", "none"):  # the conditions: their own pages (cond, condpart)
        if part in old:
            t[part] = old[part]
    return t


__all__ = ["LanePlaces"]
