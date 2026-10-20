// fedtail in a browser: lanes, posts with what they answer, threads as trees, profiles,
// writing, the Point-style command line. Post HTML arrives cleaned on the server; the
// page puts post data into the document only through textContent and attributes —
// the one exception is that cleaned HTML (post text, bios), and it is marked where used.
"use strict";

const $ = (s) => document.querySelector(s);
const state = {
  me: null, words: {}, lane: null, lanes: [], posts: [], cursor: -1, version: -1,
  replyTo: null, readQueue: new Set(), side: null, older: false, busy: false,
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

function when(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const now = new Date();
  const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === now.toDateString()) return hm;
  const opts = { day: "numeric", month: "short" };
  if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
  return d.toLocaleDateString([], opts) + " " + hm;
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

function renderPost(p, inThread) {
  const card = el("article", "post" + (p.unread ? " unread" : "") + (p.own ? " own" : ""));
  card.dataset.id = p.id;
  if (inThread && p.depth) card.style.setProperty("--depth", String(Math.min(p.depth, 8)));
  if (p.shared_by) {
    const s = el("div", "shared", "♻ ");
    const by = el("a", "", p.shared_by.name || p.shared_by.handle);
    by.href = "#";
    by.onclick = (e) => { e.preventDefault(); openAccount(p.shared_by.id); };
    s.append(by);
    card.append(s);
  }
  const head = el("div", "head");
  head.append(avatar(p.account));
  const names = el("div", "names");
  const who = el("a", "who", p.account.name || p.account.handle);
  who.href = "#";
  who.onclick = (e) => { e.preventDefault(); openAccount(p.account.id); };
  names.append(who, el("span", "acct", "@" + p.account.handle));
  head.append(names);
  const meta = el("div", "meta");
  if (inThread) meta.append(el("span", "num", p.number ? "/" + p.number : "#"));
  if (p.alias) {
    const a = el("span", "alias", "#" + p.alias);
    a.title = w("web_cmd");
    a.onclick = () => { const c = $("#cmd"); c.value = "#" + p.alias + " "; c.focus(); };
    meta.append(a);
  }
  if (VIS_MARK[p.visibility]) {
    const v = el("span", "vis", VIS_MARK[p.visibility]);
    v.title = w(VIS[p.visibility]);
    meta.append(v);
  }
  const t = el("span", "time", when(p.created) + (p.edited ? " · " + w("web_edited") : ""));
  t.title = new Date(p.created).toLocaleString();
  meta.append(t);
  head.append(meta);
  card.append(head);
  if (p.context) {
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
  if (p.quote) content.append(renderQuote(p.quote));
  if (p.warning) {
    const d = el("details", "cw");
    d.open = !!state.me.expand_cw;
    d.append(el("summary", "", "⚠ " + p.warning), content);
    card.append(d);
  } else card.append(content);
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
    for (const m of p.media) box.append(renderOne(m));
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

function renderOne(m) {
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
      img.title = m.alt;
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      img.onclick = () => view(m);
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
  const box = el("div", "broken", "▣ " + w("web_media"));
  if (m.url) box.append(" ", link(w("web_original") + " ↗", m.url));
  return box;
}

function view(m) {  // a picture over the page; click or Esc — gone
  $("#viewer-img").src = m.url || m.preview;
  $("#viewer-img").alt = m.alt;
  $("#viewer-alt").textContent = m.alt;
  const o = $("#viewer-open");
  o.textContent = w("web_original") + " ↗";
  o.href = m.url || m.preview;
  o.hidden = !(m.url || m.preview);
  $("#viewer").hidden = false;
}

function closeViewer() {
  $("#viewer").hidden = true;
  $("#viewer-img").removeAttribute("src");
}

function renderPoll(p) {
  const poll = p.poll;
  const box = el("div", "poll");
  const open = !poll.expired && !poll.voted && !p.own;
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
      try { redraw(await api("/api/vote", { id: p.sid, choices: [...picked] })); toast(w("poll_voted")); }
      catch (e) { toast(e.message); b.disabled = false; }
    };
    foot.prepend(b, " ");
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

// ---- lanes ------------------------------------------------------------------------------
async function loadLanes() {
  const lanes = await api("/api/lanes");
  state.lanes = lanes;
  const nav = $("#lanes");
  nav.textContent = "";
  for (const l of lanes) {
    if (l.group) nav.append(el("div", "group", l.group));
    const a = el("a", l.name === state.lane ? "on" : "");
    a.href = "#" + encodeURIComponent(l.name);
    a.dataset.lane = l.name;
    a.append(el("span", "lt", l.title));
    if (l.unread) a.append(el("span", "n", String(l.unread)));
    a.onclick = (e) => { e.preventDefault(); closeNav(); selectLane(l.name); };
    nav.append(a);
  }
  return lanes;
}

async function selectLane(name, keep) {
  const changed = state.lane !== name;
  state.lane = name;
  if (location.hash.slice(1) !== encodeURIComponent(name))
    history.replaceState(null, "", "#" + encodeURIComponent(name));
  for (const a of document.querySelectorAll("#lanes a"))
    a.classList.toggle("on", a.dataset.lane === name);
  let data;
  try {
    data = await api("/api/lane?name=" + encodeURIComponent(name));
    if (changed) api("/api/active", { name: data.name }).catch(() => {});  // a POST: GET only reads
  } catch (e) { toast(w("web_load_error", { err: e.message })); return; }
  if (state.lane !== name) return;  // another lane was picked meanwhile
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
  for (const p of data.posts) box.append(renderPost(p, false));
  if (more && newestFirst) box.append(more);
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
  for (const c of document.querySelectorAll("#posts .post.unread")) c.classList.remove("unread");
  for (const p of state.posts) p.unread = false;
  countUnread();
  if (ids.length) await api("/api/read", { ids }).catch((e) => toast(e.message));
  loadLanes();
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
  try {
    const t = await api("/api/thread?id=" + encodeURIComponent(id));
    if (state.side !== token) return;  // something else was opened meanwhile
    const body = $("#side-body");
    body.textContent = "";
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

async function openAccount(id) {
  if (!id) return;
  const token = showSide(w("tui_profile"));
  try {
    const a = await api("/api/account?id=" + encodeURIComponent(id));
    if (state.side !== token) return;
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
    box.append(el("div", "muted", a.account.counts +
                  (a.relation.followed_by ? " · " + w("acc_follows_you") : "")));
    const row = el("div", "row");
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
    for (const p of a.posts) body.append(renderPost(p, false));
    if (!a.posts.length) body.append(el("div", "empty", w("web_empty")));
  } catch (e) { $("#side-body").textContent = w("web_load_error", { err: e.message }); }
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

// ---- doing things -----------------------------------------------------------------------
async function act(action, p) {
  try { redraw(await api("/api/act", { action, id: p.sid })); }
  catch (e) { toast(e.message); }
}

// ---- writing ------------------------------------------------------------------------------
function compose(replyTo) {
  const d = $("#compose");
  state.replyTo = replyTo || null;
  const t = $("#text");
  $("#compose-title").textContent = replyTo ? w("reply") : w("web_new_post");
  const line = $("#reply-line");
  line.hidden = !replyTo;
  line.textContent = "";
  if (replyTo) {
    line.append(el("b", "", w("web_reply_to", { who: "@" + replyTo.account.handle })),
                el("div", "muted", (replyTo.warning ? "⚠ " + replyTo.warning : "")
                  || (replyTo.html ? new DOMParser().parseFromString(replyTo.html, "text/html").body.textContent.slice(0, 200) : "")));
    const draft = store("draft." + replyTo.sid);
    t.value = draft || replyTo.reply_prefix || "";
    $("#vis").value = narrower(replyTo.visibility, state.me.visibility);
    if (replyTo.warning) { $("#cw").value = replyTo.warning; showCw(true); }
  } else {
    t.value = store("draft.new");
    $("#vis").value = state.me.visibility;
  }
  if (!replyTo || !replyTo.warning) { $("#cw").value = ""; showCw(false); }
  counter();
  if (!d.open) d.showModal();
  t.focus();
  t.setSelectionRange(t.value.length, t.value.length);
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
  $("#chars").textContent = n ? String(n) : "";
  const key = state.replyTo ? "draft." + state.replyTo.sid : "draft.new";
  store(key, $("#text").value);
}

function closeCompose() { $("#compose").close(); state.replyTo = null; $("#posts").focus(); }

async function send(e) {
  e.preventDefault();
  const text = $("#text").value.trim();
  if (!text || state.busy) return;
  state.busy = true;
  $("#send").disabled = true;
  try {
    await api("/api/post", { text, reply_to: state.replyTo ? state.replyTo.sid : null,
                             visibility: $("#vis").value, cw: $("#cw").hidden ? "" : $("#cw").value,
                             lang: $("#lang").value });
    store(state.replyTo ? "draft." + state.replyTo.sid : "draft.new", "");
    $("#text").value = "";
    toast(w("sent"));
    closeCompose();
  } catch (err) { toast(err.message); }
  finally { state.busy = false; $("#send").disabled = false; }
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
    else if (kind === "tag") {  // the tag's page on my server
      const server = state.me.server || "";
      if (/^https:\/\//i.test(server))
        window.open(server.replace(/\/$/, "") + "/tags/" + encodeURIComponent(arg),
                    "_blank", "noopener");
    } else if (kind === "resolve") {
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
  if (!$("#viewer").hidden) { if (e.key === "Escape") closeViewer(); return; }
  if (e.target.closest("textarea, input, select")) {
    if (e.key === "Escape" && e.target.id === "cmd") { e.target.value = ""; $("#posts").focus(); }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && e.target.closest("#compose")) send(e);
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

// ---- live: the server answers when something changed ---------------------------------
async function follow() {
  for (;;) {
    try {
      const r = await api("/api/wait?v=" + state.version);
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
  $("#compose-close").title = w("web_close");
  $("#compose").addEventListener("cancel", (e) => { e.preventDefault(); closeCompose(); });
  $("#compose-form").addEventListener("submit", send);
  $("#text").addEventListener("input", counter);
  $("#cw").addEventListener("input", counter);
  $("#cw").placeholder = w("cw_placeholder");
  $("#cw-toggle").textContent = "⚠";
  $("#cw-toggle").title = w("cw_add");
  $("#cw-toggle").onclick = () => showCw($("#cw").hidden);
  $("#lang").placeholder = "lang";
  $("#lang").title = w("lang_label");
  $("#text").placeholder = w("write");
  const vis = $("#vis");
  for (const v of ["public", "unlisted", "followers", "direct"]) {
    const o = el("option", "", w(VIS[v]));  // the words carry their own mark
    o.value = v;
    vis.append(o);
  }
  vis.value = me.visibility;
  vis.title = w("web_visibility");
  $("#viewer").onclick = (e) => { if (e.target.id !== "viewer-open") closeViewer(); };
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
