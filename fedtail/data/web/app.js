// fedtail in a browser: lanes, posts with what they answer, threads as trees, the
// command line. Server HTML arrives cleaned already; the page adds no HTML of its own
// from post data except through textContent.
"use strict";

const $ = (s) => document.querySelector(s);
const state = { me: null, words: {}, lane: null, posts: [], cursor: -1, version: -1,
                replyTo: null, readQueue: new Set(), side: null };

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
  if (!r.ok) throw new Error(data.error || r.status);
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
  if (text !== undefined) e.textContent = text;
  return e;
}

function when(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const now = new Date();
  const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === now.toDateString() ? hm
    : d.toLocaleDateString([], { day: "numeric", month: "short" }) + " " + hm;
}

// ---- one post -------------------------------------------------------------------
function renderPost(p, inThread) {
  const card = el("article", "post" + (p.unread ? " unread" : ""));
  card.dataset.id = p.id;
  if (inThread && p.depth) card.style.marginLeft = Math.min(p.depth, 8) * 18 + "px";
  const head = el("div", "head");
  if (p.account.avatar) {
    const img = el("img", "ava");
    img.src = p.account.avatar;
    img.alt = "";
    img.loading = "lazy";
    head.append(img);
  }
  if (inThread) head.append(el("span", "num", p.number ? "/" + p.number : "#"));
  const who = el("a", "who", p.account.name || p.account.acct);
  who.href = "#";
  who.onclick = (e) => { e.preventDefault(); openAccount(p.account.id); };
  head.append(who, el("span", "acct", "@" + p.account.acct), el("span", "time", when(p.created_at)));
  if (p.alias) {
    const a = el("span", "alias", "#" + p.alias);
    a.title = "→ " + w("web_cmd");
    a.onclick = () => { const t = $("#text"); t.value = "#" + p.alias + " " + t.value; t.focus(); };
    head.append(a);
  }
  if (p.boosted_by) head.append(el("span", "meta", "♻ @" + p.boosted_by.acct));
  if (p.visibility === "direct") head.append(el("span", "meta", "✉"));
  if (p.visibility === "private") head.append(el("span", "meta", "🔒"));
  card.append(head);
  if (p.context) {
    const c = el("div", "ctx", p.context.missing ? "↳ " + w("web_parent_gone")
      : "↳ @" + p.context.acct + ": " + p.context.text);
    if (p.context.id) c.onclick = () => openThread(p.context.id);
    card.append(c);
  }
  const body = el("div", "body");
  body.innerHTML = p.html;  // cleaned on the server: allowed tags, safe links only
  if (p.spoiler && !state.me.expand_cw) {
    const d = el("details");
    d.append(el("summary", "", "⚠ " + p.spoiler), body);
    card.append(d);
  } else {
    if (p.spoiler) card.append(el("div", "meta", "⚠ " + p.spoiler));
    card.append(body);
  }
  if (p.media.length) card.append(renderMedia(p));
  if (p.poll) card.append(el("div", "meta", "📊 …"));
  card.append(renderActions(p, inThread));
  card.addEventListener("click", (e) => {
    if (e.target.closest("a, button, summary, img, .alias, .ctx")) return;
    setCursor(state.posts.findIndex((x) => x.id === p.id));
  });
  return card;
}

function renderMedia(p) {
  const box = el("div", "media");
  const veiled = p.sensitive && !p.spoiler && state.me.sensitive_media === "hide";
  const show = () => {
    box.textContent = "";
    for (const m of p.media) {
      if ((m.type === "image" || m.type === "gifv" || m.type === "video") && m.preview) {
        const img = el("img");
        img.src = m.preview;
        img.alt = m.desc;
        img.title = m.desc;
        img.loading = "lazy";
        img.onclick = () => m.url && window.open(m.url, "_blank", "noopener");
        box.append(img);
      } else if (m.url) {
        const a = el("a", "", "[" + w("web_media") + "]");
        a.href = m.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        box.append(a);
      }
      if (m.desc) box.append(el("div", "alt", m.desc));
    }
  };
  if (veiled) {
    const v = el("div", "veil", "⚠ " + w("web_sensitive"));
    v.onclick = show;
    box.append(v);
  } else show();
  return box;
}

function renderActions(p, inThread) {
  const row = el("div", "acts");
  const btn = (label, on, fn) => {
    const b = el("button", on ? "on" : "", label);
    b.type = "button";
    b.onclick = fn;
    row.append(b);
  };
  btn("↩ " + w("reply") + (p.replies ? " · " + p.replies : ""), false, () => startReply(p));
  btn((p.favourited ? "★ " + w("faved") : "☆ " + w("fav")) + (p.favs ? " · " + p.favs : ""),
      p.favourited, () => act("fav", p));
  if (p.visibility === "public" || p.visibility === "unlisted")
    btn("♻ " + (p.reblogged ? w("boosted") : w("boost")) + (p.boosts ? " · " + p.boosts : ""),
        p.reblogged, () => act("boost", p));
  btn(p.bookmarked ? "🔖 " + w("unbookmark") : "🔖", p.bookmarked, () => act("bookmark", p));
  if (!inThread) btn("⤷ " + w("thread"), false, () => openThread(p.sid));
  if (p.url) {
    const a = el("a", "", "↗");
    a.href = p.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.title = w("open_browser");
    row.append(a);
  }
  return row;
}

// ---- lanes ----------------------------------------------------------------------
async function loadLanes() {
  const lanes = await api("/api/lanes");
  const nav = $("#lanes");
  nav.textContent = "";
  for (const l of lanes) {
    if (l.group) nav.append(el("div", "group", l.group));
    const a = el("a", l.name === state.lane ? "on" : "");
    a.href = "#" + encodeURIComponent(l.name);
    a.append(el("span", "", l.title));
    if (l.unread) a.append(el("span", "n", String(l.unread)));
    a.onclick = (e) => { e.preventDefault(); nav.classList.remove("open"); selectLane(l.name); };
    nav.append(a);
  }
  return lanes;
}

async function selectLane(name, keep) {
  state.lane = name;
  location.hash = encodeURIComponent(name);
  for (const a of document.querySelectorAll("#lanes a"))
    a.classList.toggle("on", decodeURIComponent(a.hash.slice(1)) === name);
  let data;
  try { data = await api("/api/lane?name=" + encodeURIComponent(name)); }
  catch (e) { toast(w("web_load_error", { err: e.message })); return; }
  if (state.me.order === "newest_first") data.posts.reverse();
  const box = $("#posts");
  const anchor = keep ? firstVisible() : null;
  const oldTop = anchor ? anchor.getBoundingClientRect().top : 0;
  state.posts = data.posts;
  $("#title").textContent = data.title;
  const unread = data.posts.filter((p) => p.unread).length;
  $("#count").textContent = unread ? String(unread) : "";
  box.textContent = "";
  if (!data.posts.length) box.append(el("div", "empty", w("web_empty")));
  for (const p of data.posts) box.append(renderPost(p, false));
  watchRead(box);
  if (anchor && box.querySelector(`[data-id="${CSS.escape(anchor.dataset.id)}"]`)) {
    const again = box.querySelector(`[data-id="${CSS.escape(anchor.dataset.id)}"]`);
    box.scrollTop += again.getBoundingClientRect().top - oldTop;
  } else {
    const firstUnread = data.posts.findIndex((p) => p.unread);
    const newest = state.me.order === "newest_first" ? 0 : data.posts.length - 1;
    const start = state.me.start_at === "newest" || firstUnread < 0 ? newest : firstUnread;
    setCursor(start, true);
  }
}

function firstVisible() {
  const box = $("#posts").getBoundingClientRect();
  for (const c of document.querySelectorAll("#posts .post")) {
    const r = c.getBoundingClientRect();
    if (r.bottom > box.top + 4) return c;
  }
  return null;
}

// ---- read marks: a post seen whole is read (read.mark_read = on_scroll) ------------
let observer = null;
function watchRead(box) {
  if (observer) observer.disconnect();
  if (state.me.mark_read !== "on_scroll") return;
  observer = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      const card = e.target;
      if (!card.classList.contains("unread")) continue;
      card.classList.remove("unread");
      state.readQueue.add(card.dataset.id);
      observer.unobserve(card);
    }
    clearTimeout(watchRead.timer);
    watchRead.timer = setTimeout(flushRead, 600);
  }, { root: box, threshold: 0.9 });
  for (const c of box.querySelectorAll(".post.unread")) observer.observe(c);
}

async function flushRead() {
  if (!state.readQueue.size) return;
  const ids = [...state.readQueue];
  state.readQueue.clear();
  try { await api("/api/read", { ids }); } catch (e) { /* the next look marks them */ }
}

// ---- the cursor (j / k) ---------------------------------------------------------
function setCursor(i, quiet) {
  const cards = document.querySelectorAll("#posts .post");
  if (!cards.length) return;
  i = Math.max(0, Math.min(i, cards.length - 1));
  for (const c of cards) c.classList.remove("cursor");
  state.cursor = i;
  cards[i].classList.add("cursor");
  cards[i].scrollIntoView({ block: quiet ? "center" : "nearest" });
}

function current() { return state.posts[state.cursor]; }

// ---- side panel: a thread or a profile -------------------------------------------
async function openThread(id) {
  showSide(w("web_thread"));
  try {
    const t = await api("/api/thread?id=" + encodeURIComponent(id));
    const body = $("#side-body");
    body.textContent = "";
    let focus = null;
    for (const p of t.posts) {
      const card = renderPost(p, true);
      if (p.sid === t.focus || p.id === t.focus) { card.classList.add("cursor"); focus = card; }
      body.append(card);
    }
    if (t.posts.length) $("#side-title").textContent = w("web_thread") + " · @" + t.posts[0].account.acct;
    if (focus) focus.scrollIntoView({ block: "center" });
    if (state.me.mark_read !== "manual")
      api("/api/read", { ids: t.posts.filter((p) => p.unread).map((p) => p.id) }).catch(() => {});
  } catch (e) { toast(w("web_load_error", { err: e.message })); }
}

async function openAccount(id) {
  showSide(w("tui_profile"));
  try {
    const a = await api("/api/account?id=" + encodeURIComponent(id));
    const body = $("#side-body");
    body.textContent = "";
    const box = el("div", "profile");
    const head = el("div", "head");
    if (a.account.avatar) { const i = el("img", "ava"); i.src = a.account.avatar; i.alt = ""; head.append(i); }
    head.append(el("b", "", a.account.name), el("span", "acct", " @" + a.account.acct));
    box.append(head);
    const note = el("div", "body");
    note.innerHTML = a.account.note;  // cleaned on the server
    box.append(note);
    const fields = el("div", "fields");
    for (const f of a.account.fields) {
      const d = el("div");
      d.append(el("b", "", f.name + ": "));
      const v = el("span");
      v.innerHTML = f.value;  // cleaned on the server
      d.append(v);
      fields.append(d);
    }
    box.append(fields);
    const meta = [a.account.posts, a.account.followers, a.account.following].join(" · ");
    box.append(el("div", "meta", meta + (a.relation.followed_by ? " · " + w("acc_follows_you") : "")));
    const f = el("button", "primary", a.relation.following ? w("unfollow") : w("follow"));
    f.onclick = async () => {
      try {
        const r = await api("/api/follow", { id, on: !a.relation.following });
        a.relation.following = r.following;
        f.textContent = r.following ? w("unfollow") : w("follow");
      } catch (e) { toast(e.message); }
    };
    box.append(f);
    body.append(box);
    for (const p of a.posts) body.append(renderPost(p, false));
  } catch (e) { toast(w("web_load_error", { err: e.message })); }
}

function showSide(title) {
  state.side = title;
  $("#side").hidden = false;
  $("#side-title").textContent = title;
  $("#side-body").textContent = "…";
}

function closeSide() { $("#side").hidden = true; state.side = null; }

// ---- doing things ------------------------------------------------------------------
async function act(action, p) {
  try {
    const got = await api("/api/act", { action, id: p.id });
    Object.assign(p, { favourited: got.favourited, reblogged: got.reblogged,
                       bookmarked: got.bookmarked, favs: got.favs, boosts: got.boosts });
    for (const card of document.querySelectorAll(`.post[data-id="${CSS.escape(p.id)}"]`))
      card.replaceWith(renderPost(p, card.querySelector(".num") !== null));
    setCursor(state.cursor, true);
  } catch (e) { toast(e.message); }
}

function startReply(p) {
  state.replyTo = p;
  $("#reply-line").hidden = false;
  $("#reply-to").textContent = w("web_reply_to", { who: "@" + p.account.acct });
  const t = $("#text");
  const at = "@" + p.account.acct + " ";
  if (!p.mine && !t.value.startsWith(at)) t.value = at + t.value;
  $("#vis").value = p.visibility === "direct" ? "direct" : (p.visibility === "private" ? "private" : state.me.visibility);
  t.focus();
}

function cancelReply() {
  state.replyTo = null;
  $("#reply-line").hidden = true;
}

async function send(e) {
  e.preventDefault();
  const text = $("#text").value.trim();
  if (!text) return;
  $("#send").disabled = true;
  try {
    if (!state.replyTo && /^([#@!~?]|[SUD] [#@])/.test(text)) {
      const r = await api("/api/command", { line: text });
      if (r.message) toast(r.message);
      if (!r.ok) return;
      if (r.open && r.open.thread) openThread(r.open.thread);
      if (r.open && r.open.account) openAccount(r.open.account);
    } else {
      await api("/api/post", { text, reply_to: state.replyTo ? state.replyTo.id : null,
                               visibility: $("#vis").value, cw: $("#cw").value });
      toast(w("sent"));
    }
    $("#text").value = "";
    $("#cw").value = "";
    cancelReply();
  } catch (err) { toast(err.message); }
  finally { $("#send").disabled = false; }
}

// in-app links: fedtail:account/ID, fedtail:thread/ID, fedtail:tag/x, fedtail:resolve/URL
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
    else if (kind === "resolve") {
      // not found here: to the browser — a web address only, never file:, javascript:…
      const web = /^https?:\/\//i.test(arg);
      try {
        const r = await api("/api/resolve?url=" + encodeURIComponent(arg));
        if (r.found === "thread") openThread(r.id);
        else if (r.found === "account") openAccount(r.id);
        else if (web) window.open(arg, "_blank", "noopener");
      } catch (err) { if (web) window.open(arg, "_blank", "noopener"); }
    }
    return;
  }
  if (/^https?:/.test(href) && !a.target) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
});

// ---- keys ----------------------------------------------------------------------------
document.addEventListener("keydown", (e) => {
  if (e.target.closest("textarea, input, select")) {
    if (e.key === "Escape") { e.target.blur(); cancelReply(); }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && e.target.id === "text") send(e);
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const p = current();
  const keys = {
    j: () => setCursor(state.cursor + 1), k: () => setCursor(state.cursor - 1),
    r: () => p && startReply(p), f: () => p && act("fav", p), b: () => p && act("boost", p),
    m: () => p && act("bookmark", p), o: () => p && openThread(p.sid), Enter: () => p && openThread(p.sid),
    n: () => { cancelReply(); $("#text").focus(); }, Escape: closeSide,
    p: () => p && openAccount(p.account.id), x: markAllRead,
  };
  if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
});

async function markAllRead() {
  const ids = state.posts.filter((p) => p.unread).map((p) => p.id);
  if (ids.length) await api("/api/read", { ids }).catch(() => {});
  for (const c of document.querySelectorAll("#posts .post.unread")) c.classList.remove("unread");
  for (const p of state.posts) p.unread = false;
  $("#count").textContent = "";
  loadLanes();
}

// ---- live: the server answers when something changed -----------------------------
async function follow() {
  for (;;) {
    try {
      const r = await api("/api/wait?v=" + state.version);
      if (r.v !== state.version) {
        const first = state.version < 0;
        state.version = r.v;
        if (!first) {
          await flushRead();
          await loadLanes();
          if (state.lane) await selectLane(state.lane, true);
        }
      }
    } catch (e) {
      await new Promise((ok) => setTimeout(ok, 5000));
    }
  }
}

async function start() {
  const me = await api("/api/me");
  state.me = me;
  state.words = me.words;
  document.title = "fedtail — @" + me.acct;
  $("#send").textContent = w("send");
  $("#allread").textContent = w("web_mark_read");
  $("#allread").onclick = markAllRead;
  $("#back").textContent = "← " + w("tui_back");
  $("#back").onclick = closeSide;
  $("#reply-cancel").textContent = w("web_cancel");
  $("#reply-cancel").onclick = cancelReply;
  $("#text").placeholder = w("write") + " · " + w("web_cmd");
  $("#menu").onclick = () => $("#lanes").classList.toggle("open");
  const vis = $("#vis");
  for (const v of ["public", "unlisted", "private", "direct"]) {
    const o = el("option", "", w("vis_" + v));
    o.value = v;
    vis.append(o);
  }
  vis.value = me.visibility;
  vis.title = w("web_visibility");
  $("#compose").addEventListener("submit", send);
  const lanes = await loadLanes();
  const want = decodeURIComponent(location.hash.slice(1));
  const names = lanes.map((l) => l.name);
  const first = lanes.find((l) => l.start);
  if (names.includes(want)) await selectLane(want);
  else if (first) await selectLane(first.name);
  follow();
}

start().catch((e) => toast(e.message));
