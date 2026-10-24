// fedtail in a browser: lanes, posts with what they answer, threads as trees, profiles,
// writing, the Point-style command line. Post HTML arrives cleaned on the server; the
// page puts post data into the document only through textContent and attributes —
// the one exception is that cleaned HTML (post text, bios), and it is marked where used.
"use strict";

const $ = (s) => document.querySelector(s);
const state = {
  me: null, words: {}, lane: null, lanes: [], posts: [], cursor: -1, version: -1,
  soundSeq: -1, played: [], noteSeq: -1, shown: [],
  replyTo: null, readQueue: new Set(), side: null, older: false, busy: false,
  edit: null, quote: null,  // the editor correcting my post / quoting one
  media: [], poll: null, sensitive: false,  // the editor's pictures, poll, "sensitive"
};

// ---- small things ------------------------------------------------------------------
function w(key, vars) {
  let s = state.words[key] || key;
  for (const [k, v] of Object.entries(vars || {})) s = s.split("{" + k + "}").join(v);
  return s;
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-Fedtail": "1" },
    body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || String(r.status));
  return data;
}

function toast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 5000);
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function link(text, url, cls) {
  const a = el("a", cls || "", text);
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function locale() {  // the interface's language, else the browser's
  return document.documentElement.lang || [];
}

function when(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const now = new Date();
  const hm = d.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === now.toDateString()) return hm;
  const opts = { day: "numeric", month: "short" };
  if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
  return d.toLocaleDateString(locale(), opts) + " " + hm;
}

function store(key, value) {  // a remembered draft: a convenience, never needed
  try {
    if (value === undefined) return localStorage.getItem("fedtail." + key) || "";
    if (value) localStorage.setItem("fedtail." + key, value);
    else localStorage.removeItem("fedtail." + key);
  } catch (e) { /* private mode: no drafts kept */ }
  return "";
}

const VIS = { public: "vis_public", unlisted: "vis_unlisted", followers: "vis_private",
              direct: "vis_direct" };
const VIS_MARK = { followers: "🔒", direct: "✉", unlisted: "🔓" };

// ---- one post -------------------------------------------------------------------------
function avatar(acc, cls) {
  if (!acc.avatar) return el("span", (cls || "ava") + " blank");
  const img = el("img", cls || "ava");
  img.src = acc.avatar;
  img.alt = "";
  img.loading = "lazy";
  img.referrerPolicy = "no-referrer";
  return img;
}

function bitEl(b, cls) {  // a piece of the card's words: plain, or a fedtail: link
  if (!b) return null;
  const x = b.link ? el("a", cls || "", b.text) : el("span", cls || "", b.text);
  if (b.link) x.href = b.link;
  if (b.tip) x.title = b.tip;
  return x;
}

function renderPost(p, inThread) {
  const card = el("article", "post" + (p.unread ? " unread" : "") + (p.own ? " own" : ""));
  card.dataset.id = p.id;
  if (inThread && p.depth) card.style.setProperty("--depth", String(Math.min(p.depth, 8)));
  const wd = p.words;  // the windows' words around the card (common/cardtext.py)
  if (wd && wd.boosted) {
    const s = el("div", "shared");
    s.append(bitEl(wd.boosted));
    card.append(s);
  } else if (p.shared_by) {
    const s = el("div", "shared", "♻ ");
    const by = el("a", "", p.shared_by.name || p.shared_by.handle);
    by.href = "#";
    by.onclick = (e) => { e.preventDefault(); openAccount(p.shared_by.id); };
    s.append(by);
    card.append(s);
  }
  const head = el("div", "head");
  const face = el("a", "face");  // the windows' avatar: a click opens the profile
  face.href = "#";
  face.title = w("a11y_avatar", { acct: p.account.handle });
  face.setAttribute("aria-label", face.title);
  face.onclick = (e) => { e.preventDefault(); openAccount(p.account.id); };
  face.append(avatar(p.account));
  head.append(face);
  const names = el("div", "names");
  const who = el("a", "who", p.account.name || p.account.handle);
  who.href = "#";
  who.onclick = (e) => { e.preventDefault(); openAccount(p.account.id); };
  names.append(who, el("span", "acct", "@" + p.account.handle));
  head.append(names);
  const meta = el("div", "meta");
  if (inThread) meta.append(el("span", "num", p.number ? "/" + p.number : "#"));
  if (p.unread) {  // the windows' mark of the new, its word on hover
    const dot = el("span", "dot", "●");
    dot.title = w("unread_tip");
    meta.append(dot);
  }
  if (p.via) {  // all accounts in one window: which of mine got it
    const v = el("span", "via", p.via.text);
    v.title = p.via.tip;
    meta.append(v);
  }
  if (p.came_from) meta.append(el("span", "came-from", p.came_from));
  if (p.alias) {
    const a = el("span", "alias", "#" + p.alias);
    a.title = w("short_id_tip");
    a.onclick = () => { const c = $("#cmd"); c.value = "#" + p.alias + " "; c.focus(); };
    meta.append(a);
  }
  if (VIS_MARK[p.visibility]) {
    const v = el("span", "vis", VIS_MARK[p.visibility]);
    v.title = w(VIS[p.visibility]);
    meta.append(v);
  }
  if (wd) {  // who sees it: the mark above (🔒 ✉ 🔓), the word in its tip
    wd.meta.filter((b) => b.kind !== "vis").forEach((b, i) => {
      if (i) meta.append(" · ");
      meta.append(bitEl(b, b.kind === "time" ? "time" : "mark"));
    });
  } else {
    const t = el("span", "time", when(p.created) + (p.edited ? " · " + w("web_edited") : ""));
    t.title = new Date(p.created).toLocaleString(locale());
    meta.append(t);
  }
  head.append(meta);
  card.append(head);
  if (wd && !inThread) {
    if (wd.context) card.append(bitEl(wd.context, "ctx"));
  } else if (p.context) {
    const c = el("div", "ctx", p.context.missing ? "↳ " + w("web_parent_gone")
      : "↳ @" + p.context.handle + ": " + p.context.text);
    if (p.context.id) c.onclick = () => openThread(p.context.id);
    card.append(c);
  }
  const content = el("div", "content");
  const body = el("div", "body");
  body.innerHTML = p.html;  // cleaned on the server: allowed tags, safe links, https pictures
  if (p.lang) body.lang = p.lang;
  content.append(body);
  if (p.poll) content.append(renderPoll(p));
  if (p.media.length) content.append(renderMedia(p));
  if (p.card && !p.media.length) content.append(renderCard(p.card));
  if (p.quote && !p.quote.note) content.append(renderQuote(p.quote));
  else if (wd && wd.quote) content.append(bitEl(wd.quote, "quote-line"));
  else if (p.quote) content.append(renderQuote(p.quote));
  if (wd && wd.reactions) {
    const r = el("div", "muted reactions", wd.reactions);
    r.title = w("reactions_tip");
    content.append(r);
  }
  const warning = wd ? wd.warning : (p.warning ? "⚠ " + p.warning : "");
  if (warning) {
    const d = el("details", "cw");
    d.open = !!state.me.expand_cw && !(wd && wd.folded);
    d.append(el("summary", "", warning), content);
    card.append(d);
  } else card.append(content);
  if (wd) {
    for (const b of wd.my_replies) card.append(bitEl(b, "myreply"));
    if (wd.conversation) card.append(bitEl(wd.conversation, "ctx conv"));
  }
  card.append(renderActions(p, inThread));
  card._post = p;
  card._inThread = !!inThread;
  card.addEventListener("click", (e) => {
    if (e.target.closest("a, button, summary, img, video, audio, input, label, .alias, .ctx"))
      return;
    const list = card.closest("#posts");
    if (list) setCursor(state.posts.findIndex((x) => x.id === p.id), true);
  });
  return card;
}

function renderMedia(p) {
  const box = el("div", "media n" + Math.min(p.media.length, 4));
  const veiled = p.sensitive && !p.warning && state.me.sensitive_media === "hide";
  const show = () => {
    box.textContent = "";
    for (const m of p.media) box.append(renderOne(m, p.media));
  };
  if (veiled) {
    const v = el("button", "veil", "⚠ " + w("web_sensitive"));
    v.type = "button";
    v.onclick = show;
    box.append(v);
  } else show();
  return box;
}

const LATER = [60, 300, 1800];  // s: a picture that didn't come is asked again by itself

function renderOne(m, all) {
  const cell = el("figure", "cell");
  const caption = m.alt ? el("figcaption", "alt", m.alt) : null;
  const fail = (again) => {  // a box that says so (with a link), and a try later
    const box = broken(m);
    cell.replaceChildren(box);
    if (caption) cell.append(caption);
    const n = (cell._tries = (cell._tries || 0) + 1);
    if (again && n <= LATER.length + 3)
      setTimeout(() => { if (cell.isConnected) again(); }, LATER[Math.min(n - 1, LATER.length - 1)] * 1000);
  };
  if (m.kind === "image" && (m.preview || m.url)) {
    const put = () => {
      const img = el("img");
      img.alt = m.alt;
      img.title = m.alt || w("image_loading");  // the windows' "loading…" till it comes
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      img.onload = () => { img.title = m.alt; };
      img.onclick = () => view(m, all);
      // a preview the server couldn't make: the original; neither — say so, try later
      img.onerror = () => {
        if (m.url && img.getAttribute("src") !== m.url) img.src = m.url;
        else fail(put);
      };
      img.src = m.preview || m.url;
      cell.replaceChildren(img);
      if (caption) cell.append(caption);
    };
    put();
    return cell;
  }
  if ((m.kind === "video" || m.kind === "gifv") && m.url) {
    const v = el("video");
    v.src = m.url;
    if (m.preview) v.poster = m.preview;
    v.preload = "none";
    v.playsInline = true;
    if (m.kind === "gifv") { v.loop = true; v.muted = true; v.autoplay = true; v.preload = "auto"; }
    else v.controls = true;
    v.title = m.alt;
    v.onerror = () => fail(null);
    cell.append(v);
  } else if (m.kind === "audio" && m.url) {
    const a = el("audio");
    a.src = m.url;
    a.controls = true;
    a.preload = "none";
    cell.append(a);
  } else cell.append(broken(m));
  if (caption) cell.append(caption);
  return cell;
}

function broken(m) {  // nothing to show here: still a way to the file
  const box = el("div", "broken", "▣ " + (m.kind === "image" ? w("image_failed") : w("web_media")));
  if (m.url) box.append(" ", link(w("web_original") + " ↗", m.url));
  return box;
}

function view(m, all) {  // a picture over the page; ←/→ through the post's; click or Esc — gone
  const list = (all || [m]).filter((x) => x.kind === "image" && (x.url || x.preview));
  state.viewer = { list, at: Math.max(0, list.indexOf(m)) };
  $("#viewer-prev").hidden = $("#viewer-next").hidden = list.length < 2;
  $("#viewer-img").src = m.url || m.preview;
  $("#viewer-img").alt = m.alt;
  $("#viewer-alt").textContent = m.alt;
  const o = $("#viewer-open");
  o.textContent = w("web_original") + " ↗";
  o.href = m.url || m.preview;
  o.hidden = !(m.url || m.preview);
  state.viewer.url = m.url || m.preview;
  $("#viewer").classList.remove("full");
  $("#viewer-note").textContent = w("viewer_keys");
  // the original that didn't come: say so (the windows' words), the link still there
  $("#viewer-img").onerror = () => {
    $("#viewer-note").textContent = w("viewer_unreachable", { err: "HTTP" });
  };
  $("#viewer").hidden = false;
}

async function saveViewed() {  // "Save": the original into ui.save_dir on this machine
  const v = state.viewer;
  if (!v || !v.url) return;
  toast(w("saving"));
  try { toast((await api("/api/save", { url: v.url })).message); }
  catch (e) { toast(e.message); }
}

function stepViewer(d) {
  const v = state.viewer;
  if (!v || v.list.length < 2) return;
  v.at = (v.at + d + v.list.length) % v.list.length;
  view(v.list[v.at], v.list);
}

function closeViewer() {
  $("#viewer").hidden = true;
  $("#viewer-img").removeAttribute("src");
}

function renderPoll(p, peek) {
  const poll = p.poll;
  const box = el("div", "poll");
  const open = !poll.expired && !poll.voted && !p.own && !peek;  // peek: the results first
  const picked = new Set();
  poll.options.forEach((o, i) => {
    const row = el(open ? "label" : "div", "opt" + (poll.mine.includes(i) ? " mine" : ""));
    if (open) {
      const inp = el("input");
      inp.type = poll.multiple ? "checkbox" : "radio";
      inp.name = "poll-" + p.id;
      inp.onchange = () => {
        if (!poll.multiple) picked.clear();
        if (inp.checked) picked.add(i); else picked.delete(i);
      };
      row.append(inp, el("span", "", o.title));
    } else {
      const bar = el("span", "bar");
      bar.style.setProperty("--share", o.share + "%");
      row.append(bar, el("span", "pct", o.share + "%"), el("span", "", o.title));
    }
    box.append(row);
  });
  const foot = el("div", "poll-foot", poll.summary);
  if (open) {
    const b = el("button", "primary small", w("poll_vote"));
    b.type = "button";
    b.onclick = async () => {
      if (!picked.size) return;
      b.disabled = true;
      b.textContent = w("poll_sending");
      try { redraw(await api("/api/vote", { id: p.sid, choices: [...picked] })); toast(w("poll_voted")); }
      catch (e) { toast(e.message); b.disabled = false; b.textContent = w("poll_vote"); }
    };
    // the results before voting (the windows' "Results"): the same poll, as bars
    const look = el("button", "tool small", w("poll_results"));
    look.type = "button";
    look.onclick = () => box.replaceWith(renderPoll(p, true));
    foot.prepend(b, " ", look, " ");
  }
  if (!poll.expired) {  // fresh counts from the server
    const again = el("a", "", w("poll_refresh"));
    again.href = "#";
    again.onclick = async (e) => {
      e.preventDefault();
      try { redraw(await api("/api/poll_refresh", { id: p.sid })); }
      catch (err) { toast(err.message); }
    };
    foot.append(" · ", again);
  }
  box.append(foot);
  return box;
}

function renderCard(c) {
  const a = link("", c.url, "card");
  if (c.image) {
    const img = el("img");
    img.src = c.image;
    img.alt = "";
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer";
    img.onerror = () => img.remove();
    a.append(img);
  }
  const t = el("div", "card-text");
  if (c.provider) t.append(el("div", "card-provider", c.provider));
  t.append(el("div", "card-title", c.title || c.url));
  if (c.description) t.append(el("div", "card-desc", c.description));
  a.append(t);
  return a;
}

function renderQuote(q) {
  const box = el("div", "quote");
  if (q.note) { box.append(el("span", "muted", "❝ " + q.note)); return box; }
  const head = el("div", "quote-head");
  head.append(avatar(q.account, "ava small"), el("b", "", q.account.name || q.account.handle),
              el("span", "acct", " @" + q.account.handle), el("span", "time", " · " + when(q.created)));
  box.append(head, el("div", "", q.text));
  if (q.id) box.onclick = () => openThread(q.id);
  return box;
}

function renderActions(p, inThread) {
  const row = el("div", "acts");
  const btn = (label, title, on, fn) => {
    const b = el("button", on ? "on" : "", label);
    b.type = "button";
    b.title = title;
    b.onclick = fn;
    row.append(b);
    return b;
  };
  const n = (x) => (x ? " " + x : "");
  btn("↩" + n(p.counts.replies), w("reply"), false, () => compose(p));
  btn((p.mine.liked ? "★" : "☆") + n(p.counts.likes), p.mine.liked ? w("faved") : w("fav"),
      p.mine.liked, () => act("like", p));
  if (p.visibility === "public" || p.visibility === "unlisted")
    btn("♻" + n(p.counts.shares), p.mine.shared ? w("boosted") : w("boost"), p.mine.shared,
        () => act("share", p));
  btn("🔖", p.mine.bookmarked ? w("unbookmark") : w("bookmark"), p.mine.bookmarked,
      () => act("bookmark", p));
  if (!inThread) btn("⤷", w("thread"), false, () => openThread(p.sid));
  if (p.url) {
    const a = link("↗", p.url);
    a.title = w("open_browser");
    row.append(a);
  }
  const more = btn("⋯", w("web_more"), false, null);
  more.onclick = (e) => { e.stopPropagation(); postMenu(p, more); };
  return row;
}

function redraw(p) {  // a post came back changed: every card of it, here and in the side
  const fresh = { mine: p.mine, counts: p.counts, poll: p.poll };
  state.posts = state.posts.map((x) => (x.sid === p.sid ? Object.assign({}, x, fresh) : x));
  for (const card of document.querySelectorAll(".post")) {
    const old = card._post;
    if (!old || old.sid !== p.sid) continue;
    const next = renderPost(Object.assign({}, old, fresh), card._inThread);
    next.className = card.className;
    card.replaceWith(next);
  }
}

// ---- menus: a post's ⋯ and the window's ≡ (one at a time; items [label, fn] or "-") ----
function popup(anchor, items) {
  const pop = $("#pop");
  pop.textContent = "";
  for (const it of items) {
    if (it === "-") { pop.append(el("hr")); continue; }
    const b = el("button", "", it[0]);
    b.type = "button";
    b.setAttribute("role", "menuitem");
    if (it[2]) b.title = it[2];  // a tooltip, as the windows' menus have
    b.onclick = () => { closePopup(); it[1](); };
    pop.append(b);
  }
  pop.hidden = false;
  const r = anchor.getBoundingClientRect();
  const pw = pop.offsetWidth, ph = pop.offsetHeight;
  pop.style.left = Math.max(4, Math.min(r.right - pw, innerWidth - pw - 4)) + "px";
  pop.style.top = (r.bottom + ph + 4 < innerHeight ? r.bottom + 4
    : Math.max(4, r.top - ph - 4)) + "px";
  const first = pop.querySelector("button");
  if (first) first.focus();
}

function closePopup() { $("#pop").hidden = true; }

async function postMenu(p, anchor) {
  let info = { subscribed: false, muted: false, own: p.own };
  try { info = await api("/api/post_menu?id=" + encodeURIComponent(p.sid)); }
  catch (e) { /* the rest of the menu still works */ }
  const items = [];
  if (info.items) {
    // the same items as the Qt and GTK windows' ⋯, in the same order (common/actions)
    for (const it of info.items) {
      if (it.kind === "separator") items.push("-");
      else if (it.kind === "open") items.push([it.label, () => window.open(it.url, "_blank", "noopener")]);
      else if (it.kind === "copy") items.push([it.label, () => copyText(it.text)]);
      else if (it.kind === "quote_reply") items.push(["❝ " + it.label, () => quoteReply(p)]);
      else if (it.kind === "link") items.push([it.label, () => linkAct(it.url, p)]);
      else if (it.page) items.push([it.label + " …", () => openThing(it.page)]);
    }
    items.push("-");
  }
  items.push([w("tui_profile") + " @" + p.account.handle, () => openAccount(p.account.id)]);
  popup(anchor, items);
}

// one of a few answers, and maybe a box to tick (the server's choose(): how long a mute
// lasts…): resolves with {key, ticked}, or null when closed
function chooseDlg(c) {
  return new Promise((resolve) => {
    const d = el("dialog", "choose-dlg");
    const f = el("form");
    f.method = "dialog";
    f.append(el("h3", "", c.title));
    if (c.text) f.append(el("p", "", c.text));
    let tick = null;
    const list = el("div", "choose-options");
    let done = false;
    const finish = (v) => { if (done) return; done = true; d.close(); d.remove(); resolve(v); };
    for (const o of c.options) {
      const b = el("button", "", o.label);
      b.type = "button";
      b.onclick = () => finish({ key: o.key, ticked: !!(tick && tick.checked) });
      list.append(b);
    }
    f.append(list);
    if (c.check) {
      const lab = el("label", "choose-check");
      tick = el("input");
      tick.type = "checkbox";
      lab.append(tick, document.createTextNode(" " + c.check));
      f.append(lab);
    }
    const cancel = el("button", "", w("web_cancel"));
    cancel.type = "button";
    cancel.onclick = () => finish(null);
    f.append(cancel);
    d.append(f);
    d.addEventListener("close", () => finish(null));
    document.body.append(d);
    d.showModal();
    const first = list.querySelector("button");
    if (first) first.focus();
  });
}

// a fedtail: link from the ⋯ menu: the server does it as every window does, and says
// what is left for the page — a question first, a place to open, the editor, a copy
async function linkAct(url, p, confirmed, chosen) {
  let r;
  try { r = await api("/api/link", { url, confirmed: !!confirmed, chosen: chosen || null }); }
  catch (e) { toast(e.message); return; }
  if (r.confirm) {
    if (window.confirm(r.confirm)) await linkAct(url, p, true, chosen);
    return;
  }
  if (r.choose) {
    const got = await chooseDlg(r.choose);
    if (got) await linkAct(url, p, confirmed, got);
    return;
  }
  if (r.copy) copyText(r.copy);
  if (r.alias) { const c = $("#cmd"); c.value = "#" + r.alias + " "; c.focus(); }
  if (r.open) openThing(r.open);
  if (r.compose) composeFrom(r.compose, p);
  if (r.read_up_to) readUpTo(r.read_up_to);
  if (r.message) toast(r.message);
  if (r.refresh) await refresh();
}

function composeFrom(c, p) {  // the editor as the link asked: edit, quote, invite, redraft
  const parent = c.reply_to ? (state.posts.find((x) => x.sid === c.reply_to || x.id === c.reply_to)
                               || (p && p.sid === c.reply_to ? p : null)) : null;
  compose(parent);
  state.edit = c.edit || null;
  state.quote = c.quote || null;
  if (c.edit) {  // an edit changes words: pictures and who sees it stay (as the windows say)
    $("#compose-title").textContent = w("edit");
    $("#attach").disabled = $("#vis").disabled = $("#poll-toggle").disabled = true;
    $("#attach").title = $("#vis").title = w("edit_media_kept");
    state.editNote = w("edit_media_kept");
    hint("");
  }
  if (c.quote) {
    $("#compose-title").textContent = w("quote");
    const line = $("#reply-line");
    line.hidden = false;
    line.textContent = "❝ " + (c.quote_of || "");
  }
  if (c.text !== undefined) $("#text").value = c.text;
  if (c.cw) { $("#cw").value = c.cw; showCw(true); }
  if (c.visibility) $("#vis").value = c.visibility === "private" ? "followers" : c.visibility;
  if (c.lang) $("#lang").value = c.lang;
  counter();
}

function readUpTo(sid) {  // this post and everything older in the lane: read
  const at = state.posts.findIndex((x) => x.sid === sid || x.id === sid);
  if (at < 0) return;
  const older = state.me.order === "oldest_first" ? state.posts.slice(0, at + 1)
                                                  : state.posts.slice(at);
  for (const x of older) {
    if (!x.unread) continue;
    const card = document.querySelector(`.post[data-id="${CSS.escape(x.id)}"]`);
    if (card) read(card);
    else { x.unread = false; state.readQueue.add(x.id); }
  }
  countUnread();
  flushRead();
}

async function threadAct(action, p) {
  try { toast((await api("/api/thread_act", { action, id: p.sid })).message); await refresh(); }
  catch (e) { toast(e.message); }
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast(w("web_copied")); }
  catch (e) { window.prompt("", text); }  // no clipboard over plain http (the LAN): by hand
}

function mainMenu() {
  const places = (state.me.places || []).filter((x) => !["help", "news", "about"].includes(x.name))
    .map((x) => [x.title + " …", () => openPlace(x.name)]);
  popup($("#more"), [
    ["✎ " + w("write"), () => compose(null)],
    [w("my_profile"), () => state.me.me && openAccount(state.me.me.id)],
    [w("refresh"), refresh],
    [w("web_mark_read"), markAllRead],
    "-",
    ...places,
    "-",
    ...(canNotify() && Notification.permission !== "granted"
      ? [[w("web_notify"), askNotify]] : []),
    [w("help_title"), () => openPlace("help")],
    [w("help_news"), () => openPlace("news")],
    [w("web_keys"), () => info(w("web_keys_text"))],
    [w("try_theme") + " …", tryTheme, w("try_theme_tip")],
    "-",
    [w("debug_notify"), testNotify],
    [(state.me.merged ? "☑ " : "☐ ") + w("accounts_merge"), toggleMerge, w("accounts_merge_tip")],
    [w("about"), () => openPlace("about")],
  ]);
}

// ≡ → Try a theme: the windows' themes (their colours and font), for this run of
// fedtail; ui.theme in the config is what the next start brings
async function tryTheme() {
  let t;
  try { t = await api("/api/themes"); } catch (e) { toast(e.message); return; }
  const got = await chooseDlg({ title: t.title, text: t.tip,
                                options: t.themes.map((x) => ({ key: x.name,
                                  label: (x.on ? "● " : "") + x.label })) });
  if (!got || got.key === t.current) return;
  try {
    const r = await api("/api/theme", { name: got.key });
    const link = $("#theme-css");
    if (link) link.href = "/theme.css?v=" + encodeURIComponent(got.key) + "." + Date.now();
    toast(r.message);
  } catch (e) { toast(e.message); }
}

function info(text, links) {
  $("#info-text").textContent = text;
  const box = $("#info-links");
  box.textContent = "";
  for (const [label, url] of links || []) box.append(link(label, url));
  $("#info").showModal();
}

// ---- quoting: answer a post piece by piece ------------------------------------------------
const LEADING_MENTIONS = /^(?:@[\w.-]+(?:@[\w.-]+)?[\s,]*)+/u;

function quoteLines(text, whole) {  // the same as fedtail/model/text.py quote_lines
  const prefix = state.me.quote_prefix || "> ";
  text = (text || "").replace(/\r\n/g, "\n").trim();
  if (whole) text = text.replace(LEADING_MENTIONS, "").trim();
  if (!text) return "";
  const bare = prefix.trimEnd();
  return text.split("\n").map((l) => (l.trim() ? prefix + l : bare)).join("\n") + "\n\n";
}

function joinQuote(before) {  // fedtail/model/text.py join_quote
  const t = before.trim();
  if (!t) return "";
  if (!t.includes("\n") && (t + " ").replace(LEADING_MENTIONS, "") === "")
    return before.endsWith("\n") ? "" : "\n";
  const tail = before.length - before.replace(/\n+$/, "").length;
  return "\n".repeat(Math.max(0, 2 - tail));
}

function plainOf(p) {  // the post's text as the reader sees it
  // an inert document: nothing in it loads or runs, and it never joins the page
  const box = new DOMParser().parseFromString(p.html, "text/html").body;
  for (const br of box.querySelectorAll("br")) br.replaceWith("\n");
  for (const para of box.querySelectorAll("p")) para.append("\n\n");
  return box.textContent.replace(/\n{3,}/g, "\n\n").trim();
}

// put a quote into the reply at its cursor, the cursor after it
function insertQuote(text, whole) {
  const q = quoteLines(text, whole);
  if (!q) return;
  const t = $("#text");
  const at = t.selectionStart, end = t.selectionEnd;
  const before = t.value.slice(0, at);
  const ins = joinQuote(before) + q;
  t.value = before + ins + t.value.slice(end);
  t.focus();
  t.selectionStart = t.selectionEnd = at + ins.length;
  counter();
}

function quoteReply(p) {  // ⋯ → reply with quote: the whole post, or into the open reply
  if (!($("#compose").open && state.replyTo && state.replyTo.sid === p.sid)) compose(p);
  const t = $("#text");
  t.selectionStart = t.selectionEnd = t.value.length;
  insertQuote(plainOf(p), true);
}

// ---- lanes ------------------------------------------------------------------------------
async function loadLanes() {
  const lanes = await api("/api/lanes");
  state.lanes = lanes;
  const nav = $("#lanes");
  nav.textContent = "";
  let head = null;  // the section the lanes below belong to: its heading folds them
  for (const l of lanes) {
    if (l.group) {  // a section heading, as the windows': a click folds or unfolds it
      head = el("button", "group" + (l.folded ? " folded" : ""), (l.folded ? "▸ " : "▾ ") + l.group);
      head.type = "button";
      head.title = w("group_fold_tip");
      head.dataset.section = l.section || "";
      head._n = 0;
      const section = l.section;
      head.onclick = async () => {
        try { await api("/api/fold", { group: section }); } catch (e) { toast(e.message); }
        loadLanes();
      };
      nav.append(head);
    }
    const a = el("a", l.name === state.lane ? "on" : "");
    a.href = "#" + encodeURIComponent(l.name);
    a.dataset.lane = l.name;
    if (l.tip) a.title = l.tip;
    a.append(el("span", "lt", l.title));
    if (l.unread) a.append(el("span", "n", String(l.unread)));
    a.onclick = (e) => { e.preventDefault(); closeNav(); selectLane(l.name); };
    // a folded section: its lanes hidden, their new posts a number on the heading
    // (the lane on screen stays, as the windows keep it)
    if (l.folded && l.name !== state.lane) {
      a.hidden = true;
      if (head) head._n += l.unread || 0;
    }
    nav.append(a);
  }
  for (const h of nav.querySelectorAll("button.group.folded"))
    if (h._n) h.append(el("span", "n", String(h._n)));
  return lanes;
}

function laneBar(data) {  // the lane's choices, as the windows' header has them
  const bar = $("#lanebar");
  bar.textContent = "";
  const seg = (items, pick) => {
    const box = el("span", "seg");
    for (const [label, tip, on, fn] of items) {
      const b = el("button", on ? "on" : "", label);
      b.type = "button";
      b.title = tip || "";
      b.onclick = fn;
      box.append(b);
    }
    bar.append(box);
  };
  const set = async (body) => {
    await api("/api/lane_set", Object.assign({ name: data.name }, body)).catch((e) => toast(e.message));
    selectLane(data.name, false);
  };
  if (data.filters && data.filters.length)
    seg(data.filters.map(([f, label, tip]) => [label, tip, f === data.filter, () => set({ filter: f })]));
  const c = data.conversations;
  if (c && c.offered)
    seg([[c.words[0], c.tips[0], !c.on, () => set({ conversations: false })],
         [c.words[1], c.tips[1], c.on, () => set({ conversations: true })]]);
  const m = data.media;
  if (m) {
    const b = el("button", "tool" + (m.active ? " on" : ""), "▾ " + m.label);
    b.type = "button";
    b.title = m.tip;
    b.onclick = (e) => {
      e.stopPropagation();
      popup(b, m.kinds.map(([k, label, on]) => [(on ? "☑ " : "☐ ") + label,
                                                () => set({ media: k, on: !on })])
                 .concat(["-", [m.all, () => set({ media: "reset" })]]));
    };
    bar.append(b);
  }
  if (data.posts.some((x) => x.unread)) {
    const b = el("button", "tool", "↓ " + w("to_new"));
    b.type = "button";
    b.title = w("to_new_tip");
    b.onclick = () => setCursor(state.posts.findIndex((x) => x.unread), false, "start");
    bar.append(b);
  } else if (data.posts.length) {  // nothing new: the same button takes you to the freshest
    const b = el("button", "tool", "⤓");
    b.type = "button";
    b.title = w("to_end_tip");
    b.onclick = () => setCursor(state.me.order === "newest_first" ? 0 : state.posts.length - 1);
    bar.append(b);
  }
  if (data.info) bar.append(el("span", "muted", data.info));
  bar.hidden = !bar.childElementCount;
}

async function selectLane(name, keep) {
  const changed = state.lane !== name;
  // another lane: the find bar goes — unless it is looking in every lane, which leads here
  if (changed && $("#find") && !$("#find").hidden && !finder.hits) closeFind();
  state.lane = name;
  if (location.hash.slice(1) !== encodeURIComponent(name))
    history.replaceState(null, "", "#" + encodeURIComponent(name));
  for (const a of document.querySelectorAll("#lanes a"))
    a.classList.toggle("on", a.dataset.lane === name);
  let data;
  try {
    data = await api("/api/lane?name=" + encodeURIComponent(name) + (keep ? "&keep=1" : ""));
    if (changed) api("/api/active", { name: data.name }).catch(() => {});  // a POST: GET only reads
  } catch (e) { toast(w("web_load_error", { err: e.message })); return; }
  if (state.lane !== name) return;  // another lane was picked meanwhile
  if (data.place) {  // Activity, Requests: not posts — the place, in the lane's stead
    $("#lanebar").hidden = true;
    $("#title").textContent = data.title;
    document.title = data.title + " — fedtail";
    state.posts = [];
    return openPlace(data.place, "", "", "", "main");
  }
  const newestFirst = state.me.order === "newest_first";
  if (newestFirst) data.posts.reverse();
  const box = $("#posts");
  const anchor = keep ? firstVisible() : null;
  const oldTop = anchor ? anchor.getBoundingClientRect().top : 0;
  const cursorId = keep && state.posts[state.cursor] ? state.posts[state.cursor].id : null;
  state.posts = data.posts;
  state.older = data.older;
  $("#title").textContent = data.title;
  document.title = data.title + " — fedtail";
  countUnread();
  box.textContent = "";
  const more = olderButton();
  if (!data.posts.length) box.append(el("div", "empty", w("web_empty")));
  if (more && !newestFirst) box.append(more);
  for (const p of data.posts) {
    const card = renderPost(p, false);
    if (data.divider && data.divider.before === p.id) {  // "new below", fixed where reading stood
      const d = el("div", "divider", data.divider.text);
      if (newestFirst) box.append(card, d); else box.append(d, card);
      continue;
    }
    box.append(card);
  }
  if (more && newestFirst) box.append(more);
  laneBar(data);
  if (data.empty_browse && !data.posts.length) box.textContent = w("browse_empty");
  watchRead(box);
  const again = anchor && box.querySelector(`.post[data-id="${CSS.escape(anchor.dataset.id)}"]`);
  if (again) {
    box.scrollTop += again.getBoundingClientRect().top - oldTop;
    const ci = state.posts.findIndex((x) => x.id === cursorId);
    if (ci >= 0) markCursor(ci);
  } else {
    const firstUnread = data.posts.findIndex((p) => p.unread);
    const lastUnread = data.posts.map((p) => p.unread).lastIndexOf(true);
    const newest = newestFirst ? 0 : data.posts.length - 1;
    const oldestUnread = newestFirst ? lastUnread : firstUnread;
    const start = state.me.start_at === "newest" || oldestUnread < 0 ? newest : oldestUnread;
    setCursor(start, false, "start");
  }
  if (state.me.mark_read === "on_open" && !keep) {  // the lane is read once it is open;
    const ids = data.posts.filter((p) => p.unread).map((p) => p.id);  // the marks stay
    if (ids.length) api("/api/read", { ids }).catch(() => {});        // till next time
  }
}

function olderButton() {
  if (!state.older) return null;
  const b = el("button", "older", w("more"));
  b.type = "button";
  b.onclick = async () => {
    b.disabled = true;
    try {
      const r = await api("/api/older", { name: state.lane });
      if (!r.n) { b.textContent = w("no_older"); return; }
      await selectLane(state.lane, true);
    } catch (e) { toast(e.message); b.disabled = false; }
  };
  return b;
}

function countUnread() {
  const unread = state.posts.filter((p) => p.unread).length;
  $("#count").textContent = unread ? "· " + unread : "";
  const a = document.querySelector(`#lanes a[data-lane="${CSS.escape(state.lane || "")}"] .n`);
  if (a) { if (unread) a.textContent = String(unread); else a.remove(); }
}

function firstVisible() {
  const box = $("#posts").getBoundingClientRect();
  for (const c of document.querySelectorAll("#posts .post")) {
    const r = c.getBoundingClientRect();
    if (r.bottom > box.top + 4) return c;
  }
  return null;
}

// ---- read marks: a post seen whole is read (read.mark_read = on_scroll) ---------------
let observer = null;
function watchRead(box) {
  if (observer) observer.disconnect();
  if (state.me.mark_read !== "on_scroll") return;
  observer = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      read(e.target);
      observer.unobserve(e.target);
    }
  }, { root: box, threshold: 0.9 });
  for (const c of box.querySelectorAll(".post.unread")) observer.observe(c);
}

function read(card) {
  if (!card.classList.contains("unread")) return;
  card.classList.remove("unread");
  const dot = card.querySelector(".head .dot");
  if (dot) dot.remove();
  state.readQueue.add(card.dataset.id);
  const p = state.posts.find((x) => x.id === card.dataset.id);
  if (p) p.unread = false;
  countUnread();
  clearTimeout(read.timer);
  read.timer = setTimeout(flushRead, 600);
}

async function flushRead() {
  if (!state.readQueue.size) return;
  const ids = [...state.readQueue];
  state.readQueue.clear();
  try { await api("/api/read", { ids }); } catch (e) { /* the next look marks them */ }
}

async function markAllRead() {
  const ids = state.posts.filter((p) => p.unread).map((p) => p.id);
  for (const c of document.querySelectorAll("#posts .post.unread")) {
    c.classList.remove("unread");
    const dot = c.querySelector(".head .dot");
    if (dot) dot.remove();
  }
  for (const p of state.posts) p.unread = false;
  countUnread();
  if (ids.length) await api("/api/read", { ids }).catch((e) => toast(e.message));
  loadLanes();
}

// ---- Ctrl+F: find in the lane (the server matches as the windows do) -------------------
const finder = { ids: [], at: -1, timer: null };
function findBar() {
  let bar = $("#find");
  if (bar) return bar;
  bar = el("form", "");
  bar.id = "find";
  const inp = el("input");
  inp.id = "find-q";
  inp.placeholder = w("find_placeholder");
  const count = el("span", "muted");
  count.id = "find-count";
  const b = (label, title, fn) => {
    const x = el("button", "tool", label);
    x.type = "button";
    x.title = title;
    x.onclick = fn;
    return x;
  };
  // "deeper": everything stored for the lane; "in every lane": all of them (the windows')
  const deeper = b(w("find_deeper"), w("find_deeper_tip"), findDeeper);
  deeper.id = "find-deeper";
  deeper.hidden = true;
  const every = el("label", "check");
  every.title = w("find_everywhere_tip");
  const box = el("input");
  box.type = "checkbox";
  box.id = "find-every";
  box.onchange = () => findNow();
  every.append(box, " ", w("find_everywhere"));
  bar.append(inp, count, deeper, every, b("↑", w("find_prev"), () => findStep(-1)),
             b("↓", w("find_next"), () => findStep(1)), b("×", w("find_close"), closeFind));
  bar.onsubmit = (e) => { e.preventDefault(); findStep(1); };
  inp.oninput = () => { clearTimeout(finder.timer); finder.timer = setTimeout(findNow, 250); };
  inp.onkeydown = (e) => {
    if (e.key === "Escape") { e.preventDefault(); closeFind(); }
    else if (e.key === "Enter" && e.shiftKey) { e.preventDefault(); findStep(-1); }
  };
  $("#posts").before(bar);
  return bar;
}

function openFind() { findBar().hidden = false; $("#find-q").focus(); $("#find-q").select(); }
function closeFind() {
  const bar = $("#find");
  if (bar) bar.hidden = true;
  for (const c of document.querySelectorAll("#posts .post.found")) c.classList.remove("found");
  finder.ids = [];
  finder.hits = null;
  $("#posts").focus();
}

async function findNow() {
  const q = $("#find-q").value;
  finder.hits = null;
  if ($("#find-every") && $("#find-every").checked) return findEverywhere(q);
  let r = { ids: [], text: "" };
  try { if (q.trim()) r = await api("/api/find?" + new URLSearchParams({ lane: state.lane, q })); }
  catch (e) { toast(e.message); }
  finder.ids = r.ids;
  finder.at = -1;
  for (const c of document.querySelectorAll("#posts .post"))
    c.classList.toggle("found", r.ids.includes(c.dataset.id));
  $("#find-count").textContent = r.text;
  $("#find-deeper").hidden = !q.trim();  // further back than the lane shows, on asking
  if (r.ids.length) findStep(1);
}

async function findDeeper() {
  const q = $("#find-q").value;
  const b = $("#find-deeper");
  b.disabled = true;
  $("#find-count").textContent = w("find_searching");
  try {
    const r = await api("/api/find_deeper?" + new URLSearchParams({ lane: state.lane, q }));
    if (r.more) { await selectLane(state.lane, true); await findNow(); }
    else $("#find-count").textContent = r.text || w("find_count", { i: finder.at + 1, n: finder.ids.length });
  } catch (e) { toast(e.message); }
  finally { b.disabled = false; }
}

async function findEverywhere(q) {  // every lane's store, in the sidebar's order
  $("#find-deeper").hidden = true;
  if (!q.trim()) { $("#find-count").textContent = ""; finder.hits = []; return; }
  $("#find-count").textContent = w("find_searching");
  try {
    const r = await api("/api/find_everywhere?" + new URLSearchParams({ q }));
    finder.hits = r.hits;
    finder.at = -1;
    $("#find-count").textContent = r.text;
    if (r.hits.length) findStep(1);
  } catch (e) { toast(e.message); }
}

async function findStep(d) {
  if (finder.hits) {  // in every lane: to the match's lane, loaded down to it
    const n = finder.hits.length;
    if (!n) return;
    finder.at = finder.at < 0 ? (d > 0 ? 0 : n - 1) : (finder.at + d + n) % n;
    const h = finder.hits[finder.at];
    await api("/api/reveal", { lane: h.lane, index: h.index }).catch(() => {});
    await selectLane(h.lane, state.lane === h.lane);
    const i = state.posts.findIndex((x) => x.item === h.item || x.id === h.id || x.sid === h.id);
    if (i >= 0) setCursor(i);
    for (const c of document.querySelectorAll("#posts .post"))
      c.classList.toggle("found", c.dataset.id === h.id || c.dataset.id === h.item);
    $("#find-count").textContent = w("find_count", { i: finder.at + 1, n }) + " · " + h.title;
    return;
  }
  const n = finder.ids.length;
  if (!n) return;
  finder.at = finder.at < 0 ? (d > 0 ? 0 : n - 1) : (finder.at + d + n) % n;
  const i = state.posts.findIndex((x) => x.id === finder.ids[finder.at]);
  if (i >= 0) setCursor(i);
  $("#find-count").textContent = w("find_count", { i: finder.at + 1, n });
}

// ---- the cursor (j / k) ---------------------------------------------------------------
function markCursor(i) {
  const cards = document.querySelectorAll("#posts .post");
  for (const c of cards) c.classList.remove("cursor");
  state.cursor = i;
  if (cards[i]) cards[i].classList.add("cursor");
  return cards[i];
}

function setCursor(i, quiet, how) {
  const cards = document.querySelectorAll("#posts .post");
  if (!cards.length) return;
  i = Math.max(0, Math.min(i, cards.length - 1));
  const card = markCursor(i);
  if (how === "start") card.scrollIntoView({ block: state.me.start_at === "newest" ? "end" : "start" });
  else if (!quiet) card.scrollIntoView({ block: "nearest" });
}

function current() { return state.posts[state.cursor]; }

// ---- the side panel: a thread or a profile --------------------------------------------
async function openThread(id) {
  const token = showSide(w("web_thread"));
  $("#side-body").textContent = w("thread_loading");
  try {
    const t = await api("/api/thread?id=" + encodeURIComponent(id));
    if (state.side !== token) return;  // something else was opened meanwhile
    const body = $("#side-body");
    body.textContent = "";
    if (t.head) body.append(threadHead(t.head, id));
    let focus = null;
    for (const p of t.posts) {
      const card = renderPost(p, true);
      if (p.sid === t.focus || p.id === t.focus) { card.classList.add("cursor"); focus = card; }
      body.append(card);
    }
    if (t.posts.length) $("#side-title").textContent = w("web_thread") + " · @" + t.posts[0].account.handle;
    if (focus) focus.scrollIntoView({ block: "center" });
    if (state.me.mark_read !== "manual") {
      const ids = t.posts.filter((p) => p.unread).map((p) => p.id);
      if (ids.length) api("/api/read", { ids }).catch(() => {});
      for (const card of document.querySelectorAll("#posts .post.unread"))
        if (ids.includes(card.dataset.id)) read(card);
    }
  } catch (e) { $("#side-body").textContent = w("web_load_error", { err: e.message }); }
}

// a thread's head, as the windows': its first words, how many answers and #id (and why
// it reaches me without following it), Follow, every warning opened or closed at once
function threadHead(h, openedFrom) {
  const box = el("div", "thread-head");
  box.append(el("div", "th-title", h.title));
  const info = el("div", "muted th-info", h.info + (h.via ? " · " + h.via : ""));
  if (h.via_tip) info.title = h.via_tip;
  box.append(info);
  const row = el("div", "row");
  const sub = el("button", "tool" + (h.subscribed ? " on" : ""), h.sub);
  sub.type = "button";
  sub.title = h.sub_tip;
  sub.onclick = async () => {
    sub.disabled = true;
    try {
      const r = await api("/api/thread_act", { action: h.subscribed ? "unsub" : "sub", id: h.sid });
      toast(r.message);
      openThread(openedFrom);
    } catch (e) { toast(e.message); sub.disabled = false; }
  };
  row.append(sub);
  if (h.cw) {
    let open = !!state.me.expand_cw;
    const cw = el("button", "tool", open ? h.cw_hide : h.cw_show);
    cw.type = "button";
    cw.title = h.cw_tip;
    cw.onclick = () => {
      open = !open;
      cw.textContent = open ? h.cw_hide : h.cw_show;
      for (const d of $("#side-body").querySelectorAll("details.cw")) d.open = open;
    };
    row.append(cw);
  }
  box.append(row);
  return box;
}

// which of their posts the profile shows: posts, posts and replies, media (the server
// says which and in which words); a press shows the profile again with that
function profileShows(a, id) {
  const bar = el("div", "row profile-shows");
  bar.setAttribute("role", "group");
  if (a.show_tip) bar.title = a.show_tip;
  for (const s of a.shows || []) {
    const b = el("button", s.on ? "primary" : "tool", s.label);
    b.type = "button";
    b.setAttribute("aria-pressed", s.on ? "true" : "false");
    b.onclick = () => { if (!s.on) openAccount(id, s.key); };
    bar.append(b);
  }
  return bar;
}

async function openAccount(id, show) {
  if (!id) return;
  const token = showSide(w("tui_profile"));
  try {
    const a = await api("/api/account?id=" + encodeURIComponent(id)
                        + (show ? "&show=" + encodeURIComponent(show) : ""));
    if (state.side !== token) return;
    const on = (a.shows || []).find((s) => s.on);
    state.profileShow = on ? {id: id, show: on.key} : null;  // a button press keeps it
    const body = $("#side-body");
    body.textContent = "";
    const box = el("section", "profile");
    if (a.account.header) {
      const h = el("img", "header");
      h.src = a.account.header;
      h.alt = "";
      h.referrerPolicy = "no-referrer";
      h.onerror = () => h.remove();
      box.append(h);
    }
    const head = el("div", "head");
    head.append(avatar(a.account, "ava big"));
    const names = el("div", "names");
    names.append(el("b", "", a.account.name), el("span", "acct", "@" + a.account.handle));
    head.append(names);
    box.append(head);
    const note = el("div", "body");
    note.innerHTML = a.account.note;  // cleaned on the server
    box.append(note);
    if (a.account.fields.length) {
      const fields = el("dl", "fields");
      for (const f of a.account.fields) {
        fields.append(el("dt", "", f.name));
        const v = el("dd", f.verified ? "verified" : "");
        v.innerHTML = f.value;  // cleaned on the server
        fields.append(v);
      }
      box.append(fields);
    }
    box.append(el("div", "muted", [a.account.counts].concat(a.meta || []).join(" · ")));
    const row = el("div", "row");
    if (a.actions) {
      // the same buttons as the windows' profile (common/profile.py)
      for (const act of a.actions) {
        const b = el("button", act.primary ? "primary" : "tool", act.label);
        b.type = "button";
        if (act.tip) b.title = act.tip;
        b.onclick = () => profileAct(id, act.key);
        row.append(b);
      }
      box.append(row);
      if (a.note_line) box.append(el("div", "muted", a.note_line));
      body.append(box);
      body.append(profileShows(a, id));
      for (const p of a.posts) body.append(renderPost(p, false));
      if (!a.posts.length) body.append(el("div", "empty", w("web_empty")));
      return;
    }
    if (!a.account.own) {
      const label = () => (a.relation.requested ? w("web_requested")
        : a.relation.following ? w("unfollow") : w("follow"));
      const f = el("button", "primary", label());
      f.type = "button";
      f.onclick = async () => {
        f.disabled = true;
        try {
          const r = await api("/api/follow", { id, on: !(a.relation.following || a.relation.requested) });
          a.relation.following = r.following && !r.requested;
          a.relation.requested = r.requested;
          f.textContent = label();
        } catch (e) { toast(e.message); }
        f.disabled = false;
      };
      row.append(f);
    }
    if (a.account.url) row.append(link(w("open_browser") + " ↗", a.account.url, "tool"));
    box.append(row);
    body.append(box);
    body.append(profileShows(a, id));
    for (const p of a.posts) body.append(renderPost(p, false));
    if (!a.posts.length) body.append(el("div", "empty", w("web_empty")));
  } catch (e) { $("#side-body").textContent = w("web_load_error", { err: e.message }); }
}

async function profileAct(id, key, answer, confirmed, chosen) {
  let r;
  try { r = await api("/api/profile_act", { id, key, answer: answer === undefined ? null : answer,
                                             confirmed: !!confirmed, chosen: chosen || null }); }
  catch (e) { toast(e.message); return; }
  if (r.confirm) {
    if (window.confirm(r.confirm)) await profileAct(id, key, answer, true, chosen);
    return;
  }
  if (r.choose) {
    const got = await chooseDlg(r.choose);
    if (got) await profileAct(id, key, answer, confirmed, got);
    return;
  }
  if (r.ask) {
    const got = window.prompt(r.ask.title + "\n\n" + r.ask.question, r.ask.text || "");
    if (got !== null) await profileAct(id, key, got, confirmed);
    return;
  }
  if (r.copy) copyText(r.copy);
  if (r.compose) composeFrom(r.compose, null);
  if (r.message) toast(r.message);
  if (r.open) { openThing(r.open); return; }
  if (r.refresh) {
    const kept = state.profileShow && state.profileShow.id === id ? state.profileShow.show : "";
    await openAccount(id, kept);
  }
}

let sideN = 0;
function showSide(title) {
  state.side = ++sideN;
  $("#side").hidden = false;
  $("#side-title").textContent = title;
  $("#side-body").textContent = "…";
  $("#side-body").scrollTop = 0;
  return state.side;
}

function closeSide() { $("#side").hidden = true; state.side = null; $("#posts").focus(); }

// ---- places: silence, lists, search, a tag, the help… as the server lays them out
// (common/places.py: the same place, the same buttons in the terminal) ------------------
function openThing(o) {  // where an action leads
  if (!o) return;
  if (o.thread) openThread(o.thread);
  else if (o.account) openAccount(o.account);
  else if (o.url) window.open(o.url, "_blank", "noopener");
  else if (o.file) copyText(o.file);  // on the machine fedtail runs on: its path
  else if (o.page) openPlace(o.page, o.arg, o.tab, o.cursor,
                             state.place && state.place.into === "main" && o.page === state.place.name
                               ? "main" : "side", o.anchor);
  else if (o.back) { if (state.place && state.place.into === "side") closeSide(); }
}

// the help's pages, as the windows' ← and →: where I was, where I came back from
const helpHist = { back: [], fwd: [] };

function helpGo(step) {
  const from = step < 0 ? helpHist.back : helpHist.fwd;
  const to = step < 0 ? helpHist.fwd : helpHist.back;
  if (!from.length || !state.place || state.place.name !== "help") return;
  to.push(state.place.arg);
  openPlace("help", from.pop(), "", "", state.place.into, "", true);
}

async function openPlace(name, arg, tab, cursor, into, anchor, byHistory) {
  into = into || "side";
  if (name === "help" && !byHistory) {
    if (state.place && state.place.name === "help" && state.place.arg !== (arg || "")) {
      helpHist.back.push(state.place.arg);
      helpHist.fwd.length = 0;
    } else if (!state.place || state.place.name !== "help") {
      helpHist.back.length = 0;
      helpHist.fwd.length = 0;
    }
  }
  const box = into === "side" ? $("#side-body") : $("#posts");
  const token = into === "side" ? showSide("…") : (state.side_main = (state.side_main || 0) + 1);
  const q = new URLSearchParams({ name, arg: arg || "", tab: tab || "", cursor: cursor || "" });
  let pg;
  try { pg = await api("/api/page?" + q); }
  catch (e) { box.textContent = w("web_load_error", { err: e.message }); return; }
  if (into === "side" ? state.side !== token : state.side_main !== token) return;
  if (into === "main" && state.lane && !["activity", "requests"].includes(state.lane)
      && name !== state.lane) return;
  state.place = { name, arg: arg || "", tab: pg.tab, into };
  if (into === "side") $("#side-title").textContent = pg.title;
  renderPlace(pg, box);
  if (anchor) {
    const at = document.getElementById(anchor);
    if (at) at.scrollIntoView({ block: "start" });
  } else box.scrollTop = 0;
}

function renderPlace(pg, box) {
  box.textContent = "";
  const page = el("section", "place place-" + pg.name);
  if (pg.name === "help") {
    const nav = el("div", "row help-nav");
    for (const [label, tip, step, list] of [["←", w("help_back"), -1, helpHist.back],
                                            ["→", w("help_forward"), 1, helpHist.fwd]]) {
      const b = el("button", "tool", label);
      b.type = "button";
      b.title = tip;
      b.setAttribute("aria-label", tip);
      b.disabled = !list.length;
      b.onclick = () => helpGo(step);
      nav.append(b);
    }
    page.append(nav);
  }
  if (pg.hint) page.append(el("div", "muted hint", pg.hint));
  if (pg.tabs.length) {
    const tabs = el("div", "tabs");
    for (const [key, label] of pg.tabs) {
      const b = el("button", key === pg.tab ? "on" : "", label);
      b.type = "button";
      b.onclick = () => openPlace(pg.name, pg.arg, key, "", state.place.into);
      tabs.append(b);
    }
    page.append(tabs);
  }
  const form = pg.form.length ? renderForm(pg.form) : null;
  if (form && pg.name === "search") page.append(form.box);  // the box first, then the finds
  for (const r of pg.rows) page.append(renderRow(r));
  if (!pg.rows.length && pg.empty) page.append(el("div", "empty", pg.empty));
  if (form && pg.name !== "search") page.append(form.box);
  if (pg.submit || pg.more) {
    const row = el("div", "row");
    if (pg.submit) row.append(placeButton(pg.submit, form && form.values));
    if (pg.more) row.append(placeButton(pg.more));
    (form ? form.box : page).append(row);
    if (form) form.box.onsubmit = (e) => { e.preventDefault(); placeAct(pg.submit.act, form.values()); };
  }
  box.append(page);
  watchRead(box);
}

function renderRow(r) {
  if (r.kind === "post") return renderPost(r.post, false);
  if (r.kind === "heading") return el("h3", "place-head", r.title);
  if (r.kind === "html") {
    const d = el("div", "body html");
    d.innerHTML = r.html;  // cleaned on the server (the help: made there from our Markdown)
    return d;
  }
  const row = el("div", "item" + (r.kind === "account" ? " person" : ""));
  if (r.account) {
    const a = avatar(r.account, "ava small");
    a.onclick = () => openAccount(r.account.id);
    row.append(a);
  }
  const t = el("div", "item-text");
  t.append(el("b", "", r.title));
  if (r.line) t.append(el("div", "muted", r.line));
  row.append(t);
  if (r.buttons.length) {
    const bs = el("div", "item-btns");
    for (const b of r.buttons) bs.append(placeButton(b));
    row.append(bs);
  }
  return row;
}

function placeButton(b, values) {
  const x = el("button", b.primary ? "primary small" : "tool small", b.label);
  x.type = "button";
  if (b.tip) x.title = b.tip;
  x.onclick = () => placeAct(b.act, values ? values() : null);
  return x;
}

function renderForm(fields) {
  const box = el("form", "place-form");
  const get = {};
  for (const f of fields) {
    const lab = el("label", "field field-" + f.kind);
    if (f.kind === "check") {
      const c = el("input");
      c.type = "checkbox";
      c.checked = !!f.value;
      lab.append(c, " ", f.label);
      get[f.name] = () => c.checked;
    } else if (f.kind === "checks") {
      if (f.label) lab.append(el("span", "", f.label));
      const boxes = f.choices.map(([v, words]) => {
        const c = el("input");
        c.type = "checkbox";
        c.checked = (f.value || []).includes(v);
        const l = el("label", "check");
        l.append(c, " ", words);
        lab.append(l);
        return [v, c];
      });
      get[f.name] = () => boxes.filter(([, c]) => c.checked).map(([v]) => v);
    } else if (f.kind === "file") {  // a picture to upload: read here, sent as base64
      lab.append(el("span", "", f.label));
      const inp = el("input");
      inp.type = "file";
      inp.accept = "image/*";
      let picked = null;
      inp.onchange = async () => {  // uploaded as the editor's pictures are; its token goes
        const file = inp.files && inp.files[0];
        picked = null;
        if (!file) return;
        try {
          const r = await fetch("/api/upload", { method: "POST", body: file, headers: {
            "X-Fedtail": "1", "X-Name": encodeURIComponent(file.name),
            "Content-Type": "application/octet-stream" } });
          const got = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(got.error || String(r.status));
          picked = { upload: got.token };
        } catch (e) { toast(e.message); }
      };
      lab.append(inp);
      get[f.name] = () => picked;
    } else if (f.kind === "choice") {
      lab.append(el("span", "", f.label));
      const sel = el("select");
      for (const [v, words] of f.choices) {
        const o = el("option", "", words);
        o.value = v;
        sel.append(o);
      }
      sel.value = f.value;
      lab.append(sel);
      get[f.name] = () => sel.value;
    } else {
      lab.append(el("span", "", f.label));
      const inp = el(f.kind === "text" ? "textarea" : "input");
      inp.value = f.value || "";
      if (f.kind === "text") inp.rows = 4;
      lab.append(inp);
      get[f.name] = () => inp.value;
    }
    if (f.tip) {  // the whole explanation on hover, its last line (the option's name) under it
      lab.title = f.tip;
      lab.append(el("small", "field-tip", f.tip.split("\n").slice(-1)[0]));
    }
    box.append(lab);
  }
  const values = () => Object.fromEntries(Object.entries(get).map(([k, f]) => [k, f()]));
  return { box, values };
}

async function placeAct(act, values, confirmed, answer) {
  let r;
  try {
    r = await api("/api/place", { act, values: values || {}, confirmed: !!confirmed,
                                  answer: answer === undefined ? null : answer });
  } catch (e) { toast(e.message); return; }
  if (r.confirm) { if (window.confirm(r.confirm)) await placeAct(act, values, true, answer); return; }
  if (r.ask) {
    const got = window.prompt(r.ask.title + "\n\n" + r.ask.question, r.ask.text || "");
    if (got !== null) await placeAct(act, values, confirmed, got);
    return;
  }
  if (r.copy) await copyText(r.copy);
  if (r.message) toast(r.message);
  if (r.compose) composeFrom(r.compose, null);
  if (r.open) { openThing(r.open); return; }
  if (r.refresh && state.place) {
    const pl = state.place;
    await openPlace(pl.name, pl.arg, pl.tab, "", pl.into);
    if (pl.into === "main") loadLanes();
  }
}

// ---- doing things -----------------------------------------------------------------------
async function act(action, p) {
  try { redraw(await api("/api/act", { action, id: p.sid })); }
  catch (e) { toast(e.message); }
}

// ---- writing ------------------------------------------------------------------------------
function compose(replyTo) {
  const d = $("#compose");
  state.replyTo = replyTo || null;
  state.edit = state.quote = null;
  state.media = [];
  state.poll = null;
  state.sensitive = false;
  drawAttached();
  drawPoll();
  $("#schedbox").hidden = true;
  $("#sched-at").value = "";
  $("#lang").value = (state.me.editor || {}).language || "";
  fillFrom(replyTo);
  const t = $("#text");
  $("#compose-title").textContent = replyTo ? w("reply") : w("web_new_post");
  const line = $("#reply-line");
  line.hidden = !replyTo;
  line.textContent = "";
  if (replyTo) {
    line.append(el("b", "", w("web_reply_to", { who: "@" + replyTo.account.handle })));
    if (replyTo.warning) line.append(el("div", "muted", "⚠ " + replyTo.warning));
    // the whole post, to select a piece of it and quote it with ❝ (post.quote_prefix)
    if (replyTo.html) line.append(el("div", "whole", plainOf(replyTo)));
    const draft = store("draft." + replyTo.sid);
    t.value = draft || replyTo.reply_prefix || "";
    $("#vis").value = narrower(replyTo.visibility, state.me.visibility);
    if (replyTo.warning) { $("#cw").value = replyTo.warning; showCw(true); }
  } else {
    t.value = store("draft.new");
    $("#vis").value = state.me.visibility;
  }
  if (!replyTo || !replyTo.warning) { $("#cw").value = ""; showCw(false); }
  $("#quote-sel").hidden = !(replyTo && replyTo.html && state.me.quote_prefix);
  $("#vis").disabled = false;  // an edit before locked these (composeFrom)
  $("#attach").title = w("attach");
  $("#vis").title = w("web_visibility");
  state.editNote = "";
  hint("");
  counter();
  if (!d.open) d.showModal();
  t.focus();
  t.setSelectionRange(t.value.length, t.value.length);
}

// all accounts in one window: whom it goes from — the account that got the post replied
// to (its id says: "work~…"), the main one for a new post; whole @name@server each
function fillFrom(replyTo) {
  const sel = $("#from");
  const accounts = (state.me.editor || {}).accounts || [];
  sel.hidden = accounts.length < 2 || !!state.edit;
  if (sel.hidden) return;
  sel.textContent = "";
  for (const [key, label] of accounts) {
    const o = el("option", "", label);
    o.value = key;
    sel.append(o);
  }
  const sid = replyTo ? String(replyTo.sid || "") : "";
  const tag = sid.includes("~") ? sid.split("~")[0] : "";
  sel.value = accounts.some(([k]) => k === tag) ? tag : "";
  sel.dataset.first = sel.value;
  sel.title = w("post_from_tip");
}

const VIS_ORDER = ["public", "unlisted", "followers", "direct"];
function narrower(a, b) {  // a reply goes no wider than what it answers
  return VIS_ORDER[Math.max(VIS_ORDER.indexOf(a), VIS_ORDER.indexOf(b), 0)];
}

function showCw(on) {
  $("#cw").hidden = !on;
  $("#cw-toggle").classList.toggle("on", on);
  if (on) $("#cw").focus();
}

function counter() {
  const n = [...$("#text").value].length + [...$("#cw").value].length;
  const limit = (state.me.editor || {}).limit || 500;
  $("#chars").textContent = n ? n + " / " + limit : "";
  $("#chars").classList.toggle("over", n > limit);
  const key = state.replyTo ? "draft." + state.replyTo.sid : "draft.new";
  store(key, $("#text").value);
  clearTimeout(state.checkTimer);  // the chain and the #CamelCase hint, as the windows count
  state.checkTimer = setTimeout(checkText, 400);
}

// the line under the text: an edit's note, how many posts a chain makes, #CamelCase
function hint(extra) {
  const line = [state.editNote, extra].filter(Boolean).join(" · ");
  $("#compose-hint").textContent = line;
  $("#compose-hint").hidden = !line;
}

async function checkText() {
  const text = $("#text").value;
  if (!$("#compose").open) return;
  if (!text.trim()) { hint(""); return; }
  try {
    const r = await api("/api/compose_check", { text, cw: $("#cw").hidden ? "" : $("#cw").value });
    hint([r.chain, r.camel].filter(Boolean).join(" · "));
  } catch (e) { /* the local counter stands */ }
}

function closeCompose() {
  $("#compose").close();
  state.replyTo = state.edit = state.quote = null;
  $("#posts").focus();
}

// "Discard": the text and its draft gone, after a question (as the windows ask)
function discard() {
  if ($("#text").value.trim() && !window.confirm(w("discard_q"))) return;
  store(state.replyTo ? "draft." + state.replyTo.sid : "draft.new", "");
  $("#text").value = "";
  state.media = [];
  state.poll = null;
  closeCompose();
}

function postBody(extra) {
  return Object.assign({
    text: $("#text").value.trim(), reply_to: state.replyTo ? state.replyTo.sid : null,
    visibility: $("#vis").value, cw: $("#cw").hidden ? "" : $("#cw").value,
    lang: $("#lang").value, edit: state.edit, quote: state.quote,
    media: state.media.map((m) => ({ token: m.token, alt: m.alt, focus: m.focus || null })),
    sensitive: state.sensitive && state.media.length > 0,
    poll: state.poll && !state.media.length ? {
      options: state.poll.options, expires_in: state.poll.expires_in,
      multiple: state.poll.multiple } : null,
    scheduled_at: $("#schedbox").hidden ? null : ($("#sched-at").value || null),
    account: $("#from").hidden ? null : $("#from").value }, extra || {});
}

async function send(e, extra) {
  if (e) e.preventDefault();
  const body = postBody(extra);
  if (!body.text || state.busy) return;
  state.busy = true;
  $("#send").disabled = true;
  try {
    const r = await api("/api/post", body);
    if (r.ask_alt) {  // a picture without a description: ask first (post.alt_reminder)
      state.busy = false;
      if (window.confirm(r.ask_alt.text + "\n\n" + r.ask_alt.send + "?")) {
        return await send(null, Object.assign({}, extra, { alt_ok: true }));
      }
      const bare = [...$("#attached").querySelectorAll("input")].find((i) => !i.value.trim());
      if (bare) bare.focus();
      return;
    }
    store(state.replyTo ? "draft." + state.replyTo.sid : "draft.new", "");
    $("#text").value = "";
    toast(r.message || w("sent"));
    closeCompose();
  } catch (err) { toast(err.message); }
  finally { state.busy = false; $("#send").disabled = false; }
}

// "Preview": the post as it will read, Markdown or plain, a chain in its parts
async function preview() {
  const text = $("#text").value.trim();
  if (!text) return;
  const lang = $("#lang");
  try {
    const r = await api("/api/preview", {
      text, cw: $("#cw").hidden ? "" : $("#cw").value, media: state.media.length,
      visibility_words: $("#vis").selectedOptions[0] ? $("#vis").selectedOptions[0].textContent : "",
      lang_words: lang.value && lang.selectedOptions[0] ? lang.selectedOptions[0].textContent : "" });
    $("#preview-title").textContent = r.title;
    $("#preview-head").textContent = r.head;
    const body = $("#preview-body");
    body.textContent = "";
    if (r.cw) body.append(el("div", "warning", "⚠ " + r.cw));
    r.parts.forEach((html, i) => {
      const part = el("div", "pv-part");
      if (r.parts.length > 1) part.append(el("div", "muted", (i + 1) + "/" + r.parts.length));
      const inner = el("div", "content");
      inner.innerHTML = html;  // the server's own safe HTML (mdhtml / escaped)
      part.append(inner);
      body.append(part);
    });
    $("#preview-back").textContent = r.back;
    $("#preview-send").textContent = r.send;
    $("#preview-dlg").showModal();
  } catch (e) { toast(e.message); }
}

// "Another language…": a code asked for, kept in the list from then on
async function otherLanguage() {
  const sel = $("#lang");
  const was = sel.dataset.was || "";
  const code = window.prompt(w("lang_other_title") + "\n" + w("lang_other_ask"), "");
  if (!code) { sel.value = was; return; }
  try {
    const r = await api("/api/add_language", { code });
    if (![...sel.options].some((o) => o.value === r.code)) {
      const o = el("option", "", r.label);
      o.value = r.code;
      sel.insertBefore(o, sel.lastElementChild);  // before "Another language…"
    }
    sel.value = r.code;
  } catch (e) { toast(e.message); sel.value = was; }
  sel.dataset.was = sel.value;
}

// a click on an attached picture: where the main thing is (focus, -1…1, y up)
function aimFocus(m, img, e) {
  const box = img.getBoundingClientRect();
  const x = ((e.clientX - box.left) / box.width) * 2 - 1;
  const y = 1 - ((e.clientY - box.top) / box.height) * 2;
  m.focus = [Math.round(x * 100) / 100, Math.round(y * 100) / 100];
  drawAttached();
}

function focusWords(m) {
  const sign = (v) => (v >= 0 ? "+" : "") + v.toFixed(2);
  return m.focus ? w("focus_at", { x: sign(m.focus[0]), y: sign(m.focus[1]) }) : w("focus_none");
}

// ---- the editor's extras: pictures with descriptions, a poll, later ---------------------
async function attachFiles(files) {
  const max = (state.me.editor || {}).max_media || 4;
  for (const f of files) {
    if (state.media.length >= max) { toast(w("media_limit", { n: max })); break; }
    try {
      const r = await fetch("/api/upload", { method: "POST", body: f, headers: {
        "X-Fedtail": "1", "X-Name": encodeURIComponent(f.name), "Content-Type": "application/octet-stream" } });
      const got = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(got.error || String(r.status));
      state.media.push({ token: got.token, alt: "", name: f.name,
                         url: f.type.startsWith("image/") ? URL.createObjectURL(f) : "" });
    } catch (e) { toast(e.message); }
  }
  if (state.media.length) { state.poll = null; drawPoll(); }
  drawAttached();
}

function drawAttached() {
  const box = $("#attached");
  box.textContent = "";
  box.hidden = !state.media.length;
  $("#sensitive").hidden = !state.media.length;
  $("#sensitive").classList.toggle("on", state.sensitive);
  $("#poll-toggle").disabled = state.media.length > 0;  // pictures or a poll
  state.media.forEach((m, i) => {
    const cell = el("div", "att");
    if (m.url) {
      const pic = el("div", "aim");
      const img = el("img");
      img.src = m.url;
      img.alt = m.alt;
      img.title = w("focus_tip");
      img.onclick = (e) => aimFocus(m, img, e);
      pic.append(img);
      if (m.focus) {  // the mark where the crop will centre
        const dot = el("span", "focus-mark");
        dot.style.left = ((m.focus[0] + 1) * 50) + "%";
        dot.style.top = ((1 - m.focus[1]) * 50) + "%";
        pic.append(dot);
      }
      const where = el("button", "tool small", focusWords(m));
      where.type = "button";
      where.title = w("focus_centre");
      where.onclick = () => { m.focus = null; drawAttached(); };
      cell.append(pic, where);
    } else cell.append(el("span", "muted", "▣ " + m.name));
    const alt = el("input");
    alt.placeholder = w("alt_prompt");
    alt.value = m.alt;
    alt.oninput = () => { m.alt = alt.value; };
    const x = el("button", "tool", "✕");
    x.type = "button";
    x.title = w("detach");
    x.onclick = () => { state.media.splice(i, 1); drawAttached(); };
    cell.append(alt, x);
    box.append(cell);
  });
}

function drawPoll() {
  const box = $("#pollbox");
  box.textContent = "";
  box.hidden = !state.poll;
  $("#attach").disabled = !!state.poll;
  if (!state.poll) return;
  const ed = state.me.editor || {};
  state.poll.options.forEach((o, i) => {
    const inp = el("input");
    inp.placeholder = w("poll_option", { n: i + 1 });
    inp.value = o;
    inp.oninput = () => { state.poll.options[i] = inp.value; };
    box.append(inp);
  });
  const row = el("div", "row");
  if (state.poll.options.length < (ed.max_options || 4)) {
    const more = el("button", "tool", "+");
    more.type = "button";
    more.onclick = () => { state.poll.options.push(""); drawPoll(); };
    row.append(more);
  }
  const len = el("select");
  for (const [secs, label] of ed.poll_lengths || []) {
    const o = el("option", "", label);
    o.value = secs;
    len.append(o);
  }
  len.value = state.poll.expires_in;
  len.onchange = () => { state.poll.expires_in = Number(len.value); };
  const multi = el("label", "check");
  const c = el("input");
  c.type = "checkbox";
  c.checked = state.poll.multiple;
  c.onchange = () => { state.poll.multiple = c.checked; };
  multi.append(c, " ", w("poll_several"));
  row.append(len, multi);
  box.append(row);
}

// ---- the command line (Point) ----------------------------------------------------------
async function runCommand(e) {
  e.preventDefault();
  const c = $("#cmd");
  const line = c.value.trim();
  if (!line) { $("#posts").focus(); return; }
  c.disabled = true;
  try {
    let r = await api("/api/command", { line });
    if (r.confirm) {  // D #id: deleted only when asked twice
      if (!window.confirm(r.confirm)) return;
      r = await api("/api/command", { line, confirm: true });
    }
    if (r.message) toast(r.message);
    if (!r.ok) return;
    c.value = "";
    if (r.open && r.open.thread) openThread(r.open.thread);
    if (r.open && r.open.account) openAccount(r.open.account);
  } catch (err) { toast(err.message); }
  finally { c.disabled = false; if (!c.value) $("#posts").focus(); else c.focus(); }
}

// ---- links inside posts: fedtail:account/ID, :thread/ID, :tag/x, :resolve/URL -----------
document.addEventListener("click", async (e) => {
  const a = e.target.closest("a[href]");
  if (!a) return;
  const href = a.getAttribute("href");
  if (href.startsWith("fedtail:")) {
    e.preventDefault();
    const [kind, ...rest] = href.slice(8).split("/");
    const arg = decodeURIComponent(rest.join("/"));
    if (kind === "account") openAccount(arg);
    else if (kind === "thread") openThread(arg);
    else if (kind === "tag") openPlace("tag", arg);
    else if (kind === "help") {  // a page of the help, and a place on it
      const [page, anchor] = arg.split("#");
      openPlace("help", page, "", "", state.place && state.place.into === "main" ? "main" : "side",
                anchor);
    } else if (!["resolve"].includes(kind)) {  // history, a post action…: the windows' way
      linkAct(href, null);
    }
    if (kind === "resolve") {
      // not found here: to the browser — a web address only, never file:, javascript:…
      const web = /^https?:\/\//i.test(arg);
      try {
        const r = await api("/api/resolve", { url: arg });  // my server fetches it: a POST
        if (r.found === "thread") openThread(r.id);
        else if (r.found === "account") openAccount(r.id);
        else if (web) window.open(arg, "_blank", "noopener");
      } catch (err) { if (web) window.open(arg, "_blank", "noopener"); }
    }
    return;
  }
  if (/^https?:/.test(href) && !a.target) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
});

// ---- keys --------------------------------------------------------------------------------
document.addEventListener("keydown", (e) => {
  if (!$("#viewer").hidden) {
    if (e.key === "Escape") closeViewer();
    else if (e.key === "ArrowLeft") stepViewer(-1);
    else if (e.key === "ArrowRight") stepViewer(1);
    else if (e.key === "s" || e.key === "S") saveViewed();
    else if (e.key === "o" || e.key === "O") window.open($("#viewer-open").href, "_blank", "noopener");
    else if (e.key === "z" || e.key === "Z") $("#viewer").classList.toggle("full");
    else if ((e.key === "r" || e.key === "R") && state.viewer) {  // the original, asked again
      $("#viewer-img").removeAttribute("src");
      $("#viewer-note").textContent = w("viewer_keys");
      $("#viewer-img").src = state.viewer.url;
    }
    return;
  }
  if (!$("#pop").hidden && e.key === "Escape") { e.preventDefault(); closePopup(); return; }
  if (e.target.closest("textarea, input, select")) {
    if (e.key === "Escape" && e.target.id === "cmd") { e.target.value = ""; $("#posts").focus(); }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && e.target.closest("#compose")) send(e);
    return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "f" && !$("#compose").open) {
    e.preventDefault();
    openFind();
    return;
  }
  if ($("#compose").open || e.ctrlKey || e.metaKey || e.altKey) return;
  const p = current();
  const keys = {
    j: () => setCursor(state.cursor + 1), k: () => setCursor(state.cursor - 1),
    ArrowDown: () => setCursor(state.cursor + 1), ArrowUp: () => setCursor(state.cursor - 1),
    r: () => p && compose(p), f: () => p && act("like", p), b: () => p && act("share", p),
    m: () => p && act("bookmark", p), o: () => p && openThread(p.sid),
    Enter: () => p && openThread(p.sid), n: () => compose(null),
    p: () => p && openAccount(p.account.id), x: markAllRead, R: refresh,
    q: () => p && quoteReply(p), "/": () => openPlace("search"),
    ":": () => $("#cmd").focus(), Escape: () => (isNavOpen() ? closeNav() : closeSide()),
  };
  if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
});

// ---- navigation on a phone -------------------------------------------------------------
function isNavOpen() { return $("#nav").classList.contains("open"); }
function openNav() { $("#nav").classList.add("open"); $("#scrim").hidden = false; }
function closeNav() { $("#nav").classList.remove("open"); $("#scrim").hidden = true; }

async function refresh() {
  await flushRead();
  await loadLanes().catch((e) => toast(e.message));
  if (state.lane) await selectLane(state.lane, true);
}

// ---- sounds: the theme's, sent by the server with the news (fedtail sound.*) -----------
let audioCtx = null;
function beep() {
  try {
    audioCtx = audioCtx || new AudioContext();
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.frequency.value = 880;
    g.gain.value = 0.12 * (state.me.sound.volume / 100);
    o.connect(g).connect(audioCtx.destination);
    o.start();
    o.stop(audioCtx.currentTime + 0.12);
  } catch (e) { /* no audio here: silence */ }
}

function playSound(snd) {
  const s = state.me && state.me.sound;
  if (!s || (!s.when_focused && document.hasFocus())) return;
  state.played.push(snd.event);
  if (snd.kind === "bell") return beep();
  const a = new Audio("/sound/" + encodeURIComponent(snd.event));
  a.volume = Math.max(0, Math.min(1, s.volume / 100));
  a.play().catch(() => { /* the browser wants a click on the page first */ });
}

// ---- notifications: the windows' words (notify.*), shown by the browser ----------------
function canNotify() { return "Notification" in window && window.isSecureContext; }

// ≡ → Send a test notification: the browser's, as the windows' test
async function testNotify() {
  if (!canNotify()) { toast(w("web_notify_off")); return; }
  if (Notification.permission !== "granted"
      && await Notification.requestPermission() !== "granted") {
    toast(w("web_notify_off"));
    return;
  }
  try {
    new Notification("fedtail", { body: w("notify_test_body"), tag: "fedtail-test" });
    toast(w("debug_notify_sent", { backend: "browser" }));
  } catch (e) { toast(w("notify_failed", { err: e.message })); }
}

// ≡ → All accounts in one window: from the next start of fedtail, as in the windows
async function toggleMerge() {
  try {
    const r = await api("/api/merge", {});
    state.me.merged = r.merged;
    toast(r.message);
  } catch (e) { toast(e.message); }
}

async function askNotify() {
  if (!canNotify()) return;
  const got = await Notification.requestPermission();
  toast(w(got === "granted" ? "web_notify_on" : "web_notify_off"));
}

function showNote(note) {
  state.shown.push(note.title);
  if (!canNotify() || Notification.permission !== "granted") return;
  const looking = document.hasFocus() && !document.hidden;
  if (looking && (!state.me.notify.when_focused || note.lane === state.lane)) return;
  const n = new Notification(note.title, { body: note.body, tag: "fedtail-" + note.lane });
  n.onclick = () => {
    window.focus();
    if (note.thread) openThread(note.thread); else selectLane(note.lane);
    n.close();
  };
}

// ---- live: the server answers when something changed ---------------------------------
async function follow() {
  for (;;) {
    try {
      const r = await api("/api/wait?v=" + state.version + "&s=" + state.soundSeq +
                          "&n=" + state.noteSeq);
      state.soundSeq = r.s;
      state.noteSeq = r.n;
      for (const snd of r.sounds || []) playSound(snd);
      for (const note of r.notes || []) showNote(note);
      if (r.v !== state.version) {
        const first = state.version < 0;
        state.version = r.v;
        if (!first && !$("#compose").open) await refresh();
      }
    } catch (e) {
      await new Promise((ok) => setTimeout(ok, 5000));
    }
  }
}

// ---- start --------------------------------------------------------------------------------
async function start() {
  const me = await api("/api/me");
  state.me = me;
  state.words = me.words;
  try { me.places = await api("/api/places"); } catch (e) { me.places = []; }
  // dates and times as fedtail's language writes them, not the browser's (a Russian
  // window said "10:25 PM")
  if (me.lang) document.documentElement.lang = me.lang;
  const who = $("#who");
  who.append(avatar(me.me, "ava small"), el("span", "", "@" + me.handle));
  who.title = me.server || "";
  who.onclick = () => openAccount(me.me.id);
  $("#write").textContent = "✎ " + w("write");
  $("#write").onclick = () => { closeNav(); compose(null); };
  $("#write2").onclick = () => compose(null);
  $("#write2").title = w("write");
  $("#allread").textContent = "✓";
  $("#allread").title = w("web_mark_read");
  $("#allread").onclick = markAllRead;
  $("#refresh").title = w("refresh");
  $("#refresh").onclick = refresh;
  $("#back").textContent = "← " + w("tui_back");
  $("#back").onclick = closeSide;
  $("#menu").onclick = () => (isNavOpen() ? closeNav() : openNav());
  $("#menu").title = w("web_lanes");
  $("#scrim").onclick = closeNav;
  $("#cmd").placeholder = ": " + w("web_cmd");
  $("#cmdline").addEventListener("submit", runCommand);
  $("#send").textContent = w("send");
  $("#compose-close").onclick = closeCompose;
  $("#compose-close").title = w("close_tip");
  $("#discard").textContent = w("discard");
  $("#discard").onclick = discard;
  $("#preview").textContent = "👁";
  $("#preview").title = w("preview") + ": " + w("preview_tip");
  $("#preview").hidden = (me.editor || {}).preview === false;
  $("#preview").onclick = preview;
  $("#preview-back").onclick = () => $("#preview-dlg").close();
  $("#preview-send").onclick = () => { $("#preview-dlg").close(); send(null); };
  $("#lang").addEventListener("change", () => {
    if ($("#lang").value === "\x00other") otherLanguage();
    else $("#lang").dataset.was = $("#lang").value;
  });
  $("#compose").addEventListener("cancel", (e) => { e.preventDefault(); closeCompose(); });
  $("#compose-form").addEventListener("submit", send);
  $("#text").addEventListener("input", counter);
  $("#cw").addEventListener("input", counter);
  $("#cw").placeholder = w("cw_placeholder");
  $("#cw-toggle").textContent = "⚠";
  $("#cw-toggle").title = w("cw_add_tip");
  $("#cw-toggle").onclick = () => showCw($("#cw").hidden);
  $("#lang").title = w("lang_tip");
  for (const [code, label] of (me.editor || {}).languages || [["", ""]]) {
    const o = el("option", "", label);
    o.value = code;
    $("#lang").append(o);
  }
  $("#attach").title = w("attach");
  $("#attach").onclick = () => $("#files").click();
  $("#files").onchange = () => { attachFiles([...$("#files").files]); $("#files").value = ""; };
  $("#text").addEventListener("paste", (e) => {  // a screenshot pasted: a picture of the post
    const files = [...(e.clipboardData || {}).files || []];
    if (files.length) { e.preventDefault(); attachFiles(files); }
  });
  $("#poll-toggle").title = w("poll_add_tip");
  $("#poll-toggle").onclick = () => {
    state.poll = state.poll ? null : { options: ["", ""], expires_in: 86400, multiple: false };
    drawPoll();
  };
  $("#sensitive").title = w("sensitive_mark_tip");
  $("#sensitive").onclick = () => { state.sensitive = !state.sensitive; drawAttached(); };
  $("#sched-toggle").title = w("schedule_tip");
  $("#sched-label").textContent = w("schedule_when");
  $("#sched-toggle").onclick = () => { $("#schedbox").hidden = !$("#schedbox").hidden; };
  $("#text").placeholder = w("write");
  const vis = $("#vis");
  for (const v of ["public", "unlisted", "followers", "direct"]) {
    const o = el("option", "", w(VIS[v]));  // the words carry their own mark
    o.value = v;
    vis.append(o);
  }
  vis.value = me.visibility;
  vis.title = w("web_visibility");
  $("#viewer").onclick = (e) => {
    if (e.target.id !== "viewer-open" && e.target.id !== "viewer-save" &&
        e.target.id !== "viewer-img" && !e.target.closest(".nav-btn")) closeViewer();
  };
  $("#viewer-img").ondblclick = (e) => { e.stopPropagation(); $("#viewer").classList.toggle("full"); };
  $("#viewer").addEventListener("wheel", (e) => {  // the wheel leafs through, as the windows'
    if ($("#viewer").classList.contains("full")) return;
    e.preventDefault();
    stepViewer(e.deltaY > 0 ? 1 : -1);
  }, { passive: false });
  $("#viewer-save").textContent = "⤓ " + w("viewer_save");
  $("#viewer-save").title = w("viewer_save_tip");
  $("#viewer-save").onclick = (e) => { e.stopPropagation(); saveViewed(); };
  $("#viewer-prev").onclick = () => stepViewer(-1);
  $("#viewer-next").onclick = () => stepViewer(1);
  $("#more").title = w("web_menu");
  $("#more").onclick = (e) => { e.stopPropagation(); mainMenu(); };
  document.addEventListener("mousedown", (e) => {
    if (!$("#pop").hidden && !e.target.closest("#pop")) closePopup();
  });
  $("#info-close").textContent = w("web_close");
  const qs = $("#quote-sel");
  qs.textContent = "❝ " + w("quote_in_reply");
  qs.onmousedown = (e) => e.preventDefault();  // keep the selection in the post
  qs.onclick = () => {
    const sel = window.getSelection();
    const whole = $("#reply-line .whole");
    const picked = sel && !sel.isCollapsed && whole && whole.contains(sel.anchorNode)
      ? sel.toString() : "";
    insertQuote(picked || (whole ? whole.textContent : ""), !picked);
  };
  const lanes = await loadLanes();
  const want = decodeURIComponent(location.hash.slice(1));
  const names = lanes.map((l) => l.name);
  const first = lanes.find((l) => l.start);
  if (names.includes(want)) await selectLane(want);
  else if (first) await selectLane(first.name);
  follow();
  window.addEventListener("hashchange", () => {
    const name = decodeURIComponent(location.hash.slice(1));
    if (name && name !== state.lane && names.includes(name)) selectLane(name);
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) flushRead(); });
}

start().catch((e) => toast(e.message));
