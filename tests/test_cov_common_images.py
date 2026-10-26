"""The picture cache every window shares (frontends/common/images.py), with a stand-in
toolkit (decode: the bytes as they are) and a stand-in network: memory and disk cache,
one download per address, the second and later tries of a picture a server was slow
on, previews asked again when their original comes, prefetching, videos to disk,
saving originals, and the disk kept within its size."""

import hashlib
import os
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import requests

from fedtail.core import remote
from fedtail.frontends.common import images


class Answer:
    def __init__(self, data=b"", status=200, kind="image/png", length=None, chunks=None):
        self.data, self.status = data, status
        self.headers = {"Content-Type": kind}
        if length is not None:
            self.headers["Content-Length"] = str(length)
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            e = requests.HTTPError(f"{self.status}")
            e.response = types.SimpleNamespace(status_code=self.status)
            raise e

    def iter_content(self, _n):
        if self.chunks is not None:
            yield from self.chunks
        elif self.data:
            yield self.data


class Bridge:
    """Hands a worker's result back at once (the test's thread is the 'main loop')."""

    def call(self, fut, ok=None, fail=None):
        try:
            res = fut.result(timeout=10)
        except Exception as e:  # noqa: BLE001
            if fail:
                fail(str(e))
            return
        if ok:
            ok(res)


class Cache(images.Cache):
    def __init__(self, core, net):
        self.net = net  # url -> Answer | Exception | callable(url) -> either
        self.opened = []
        self.timers = []
        super().__init__(core, Bridge())

    def decode(self, data, max_side):
        return None if data.startswith(b"bad") else ("pic", data, max_side)

    def size(self, picture):
        return (10, 10)

    def to_screen(self, picture):
        return ("screen",) + picture[1:]

    def later(self, ms, fn):
        self.timers.append((ms, fn))

    def _open(self, url, timeout):
        self.opened.append((url, timeout))
        a = self.net.get(url, requests.ConnectionError("nowhere"))
        if callable(a) and not isinstance(a, Answer):
            a = a(url)
        if isinstance(a, BaseException):
            raise a
        return a


def file_of(cache, url):
    return cache.cache_dir / hashlib.sha1(url.encode()).hexdigest()


class ImagesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        (tmp / "cache").mkdir()
        self.core = types.SimpleNamespace(
            paths=types.SimpleNamespace(cache_dir=tmp / "cache"),
            cfg={"ui": {"image_cache_mb": 1, "image_disk_mb": 1000, "video_disk_mb": 1000}},
            _own_hosts=lambda: ())
        self.net = {}
        self.c = Cache(self.core, self.net)
        self.addCleanup(self.close)

    def close(self):
        self.c.shutdown()
        for pool in (self.c.pre_pool, self.c.video_pool):
            pool.shutdown(wait=True)
        self.c.big_pool.shutdown(wait=True)
        self.c.pool.shutdown(wait=True)

    def get(self, url, **kw):
        got, failed = [], []
        self.c.get(url, got.append, failed=lambda: failed.append(url), **kw)
        return got, failed

    # ---- getting a picture ---------------------------------------------------------------
    def test_an_owner_keeps_the_callbacks_the_cache_doesnt(self):
        """A card thrown away is not kept alive by a picture that failed and is waited
        for (gave_up) — the cache holds its callbacks weakly once it names an owner."""
        import gc
        import weakref

        class Card:  # a widget: it has a __dict__, as Qt's and GTK's do
            def __init__(self):
                self.got = []

            def show(self, pic):
                self.got.append(pic)
        alive = Card()
        self.net["https://a/ok.png"] = Answer(b"PNG")
        self.c.get("https://a/ok.png", alive.show, owner=alive)
        self.assertEqual(len(alive.got), 1)  # while it lives: as before
        gone = Card()
        url = "https://a/broken.png"  # not on the net: fails, then waited for
        failed = []
        self.c.get(url, gone.show, failed=lambda: failed.append(1), owner=gone)
        self.c.get(url, gone.show, owner=gone)  # just failed: kept to try again later
        self.assertTrue(self.c.gave_up.get(url) or self.c.waiting or self.c.timers)
        ref = weakref.ref(gone)
        del gone
        gc.collect()
        self.assertIsNone(ref())  # not held by the cache
        for _side, cb, _f in self.c.gave_up.get(url, ()):
            cb(("late",))  # the picture comes after all: nobody to hand it to, no error

    def test_downloaded_once_then_from_memory_and_disk(self):
        self.net["https://a/1.png"] = Answer(b"PNG1")
        got, failed = self.get("https://a/1.png")
        self.assertEqual(got, [("screen", b"PNG1", images.FEED_SIDE)])
        self.assertEqual(failed, [])
        self.assertEqual(file_of(self.c, "https://a/1.png").read_bytes(), b"PNG1")
        self.assertEqual(self.c.local("https://a/1.png"), str(file_of(self.c, "https://a/1.png")))
        self.assertIsNone(self.c.local(""))
        self.assertIsNone(self.c.local("https://a/none"))
        got2, _f = self.get("https://a/1.png")
        self.assertEqual(got2, got)  # from memory: no second request
        self.assertEqual(len(self.c.opened), 1)
        got3, _f = self.get("https://a/1.png", max_side=400)  # another size: from disk
        self.assertEqual(got3, [("screen", b"PNG1", 400)])
        self.assertEqual(len(self.c.opened), 1)
        counts = self.c.counts()
        self.assertEqual((counts["done"], counts["from_disk"]), (2, 1))
        self.assertEqual(self.c.counts()["done"], 0)  # counted since the last time

    def test_no_address(self):
        got, failed = self.get("")
        self.assertEqual((got, failed), ([], [""]))
        self.c.get("", lambda _p: None)  # nobody to tell: nothing happens

    def test_a_broken_file_on_disk_is_fetched_again(self):
        url = "https://a/2.png"
        file_of(self.c, url).write_bytes(b"bad old")
        self.net[url] = Answer(b"PNG2")
        got, _f = self.get(url)
        self.assertEqual(got[0][1], b"PNG2")

    def test_a_format_that_cant_be_shown(self):
        url = "https://a/3.avif"
        self.net[url] = Answer(b"bad avif", kind="image/avif")
        got, failed = self.get(url)
        self.assertEqual((got, failed), ([], [url]))
        self.assertEqual(self.c.why[url], ("format", "image/avif"))
        self.assertFalse(file_of(self.c, url).exists())  # not kept
        self.assertEqual(self.c.timers, [])  # no point asking again
        # failed just now: not asked again, the card is told at once
        got, failed = self.get(url)
        self.assertEqual(failed, [url])
        self.assertEqual(len(self.c.opened), 1)
        self.net[url] = Answer(b"PNG", kind="image/png")
        got, _f = self.get(url, retry=True)  # asked for again on purpose
        self.assertTrue(got)

    def test_network_failure_second_try_then_later_tries(self):
        url = "https://a/4.png"
        self.net[url] = Answer(status=503)
        got, failed = self.get(url)
        self.assertEqual((got, failed), ([], []))  # still waiting: a second try is due
        (ms, again), = self.c.timers
        self.assertEqual(ms, self.c.SECOND_TRY_AFTER)
        self.assertEqual(self.c.why[url], ("network", "HTTP 503"))
        self.c.timers.clear()
        again()  # the patient try fails too: the card is told; a later try is planned
        self.assertEqual(failed, [url])
        self.assertEqual(self.c.opened[-1][1], (6, 60))  # with patience
        (ms, later), = self.c.timers
        self.assertEqual(ms, self.c.LATER_TRIES[0] * 1000)
        self.c.timers.clear()
        self.net[url] = Answer(b"PNG4")
        later()  # it came: the card that gave up gets it after all
        self.assertEqual(got, [("screen", b"PNG4", images.FEED_SIDE)])
        self.assertNotIn(url, self.c.broken)
        self.c._again(url)  # nobody waits any more: nothing

    def test_later_tries_end(self):
        url = "https://a/5.png"
        self.c.tries[url] = len(self.c.LATER_TRIES) + 3
        self.c._try_later(url)
        self.assertEqual(self.c.timers, [])
        for i in range(2001):
            self.c.tries[f"u{i}"] = 1
        before = len(self.c.tries)
        self.c._try_later(url + "?x")
        self.assertEqual(len(self.c.tries), before)  # the oldest went for the new one
        self.assertIn(url + "?x", self.c.tries)

    def test_a_server_that_says_too_many_is_left_alone_a_while(self):
        """HTTP 429 for a picture: nothing more asked of that server until its window is
        over (Retry-After); another server's pictures still come."""
        e = requests.HTTPError("429")
        e.response = types.SimpleNamespace(status_code=429, headers={"Retry-After": "30"})
        self.net["https://busy/1.png"] = e
        self.net["https://busy/2.png"] = Answer(b"PNG")
        self.net["https://calm/1.png"] = Answer(b"PNG")
        self.get("https://busy/1.png")
        self.assertEqual(self.c.why["https://busy/1.png"], ("network", "HTTP 429"))
        before = len(self.c.opened)
        self.get("https://busy/2.png")
        self.assertEqual(len(self.c.opened), before)  # not asked at all
        self.assertEqual(self.c.why["https://busy/2.png"], ("network", "HTTP 429"))
        self.get("https://calm/1.png")
        self.assertEqual(self.c.opened[-1][0], "https://calm/1.png")
        self.assertEqual(images._retry_after({"Retry-After": "x"}), 60.0)
        self.assertEqual(images._retry_after({"Retry-After": "99999"}), 900.0)

    def test_refused_and_connection_errors(self):
        self.net["https://a/6.png"] = remote.Refused("private address")
        self.net["https://a/7.png"] = requests.ConnectTimeout("slow")
        self.get("https://a/6.png")
        self.assertIn("refused", self.c.why["https://a/6.png"][1])
        self.get("https://a/7.png")
        self.assertEqual(self.c.why["https://a/7.png"], ("network", "ConnectTimeout"))

    def test_originals_go_to_their_own_workers_and_bring_back_their_previews(self):
        prev, orig = "https://a/p.png", "https://a/o.png"
        self.net[prev] = Answer(b"bad preview")  # a format the toolkit can't read
        got, failed = self.get(prev, original=orig)
        self.assertEqual(failed, [prev])
        self.net[prev] = Answer(b"PNGp")
        self.net[orig] = Answer(b"PNGo")
        big, _f = self.get(orig, big=True)
        self.assertEqual(big, [("screen", b"PNGo", images.FEED_SIDE)])
        self.assertIn((orig, images.FEED_SIDE), self.c.big)
        self.assertEqual(got, [("screen", b"PNGp", images.FEED_SIDE)])  # asked again
        self.assertEqual(self.c.opened[-1][1], (6, 12))
        self.assertTrue(any(t == (6, 120) for _u, t in self.c.opened))  # an original waits

    def test_a_request_with_no_answer_is_asked_again(self):
        url = "https://a/8.png"
        key = (url, images.FEED_SIDE)
        self.c.waiting[key] = [(lambda _p: None, None)]
        self.c.asked[key] = time.monotonic() - self.c.STUCK_AFTER - 1
        self.net[url] = Answer(b"PNG8")
        got, _f = self.get(url)
        self.assertTrue(got)
        self.c.waiting[key] = [(lambda _p: None, None)]
        self.c.asked[key] = time.monotonic()
        got, _f = self.get(url + "")  # in memory now
        self.assertTrue(got)

    def test_waiting_for_one_already_asked(self):
        url = "https://a/9.png"
        key = (url, images.FEED_SIDE)
        self.c.waiting[key] = [(lambda _p: None, None)]
        self.c.asked[key] = time.monotonic()
        got, _f = self.get(url)
        self.assertEqual(got, [])
        self.assertEqual(len(self.c.waiting[key]), 2)  # joined the queue, no new request

    def test_handlers_that_fail(self):
        url = "https://a/h.png"
        self.net[url] = Answer(b"PNGh")
        key = (url, images.FEED_SIDE)

        def gone(_p):
            raise RuntimeError("widget deleted")

        def bug(_p):
            raise ValueError("bug")
        seen = []
        self.c.waiting[key] = [(gone, None), (bug, None), (seen.append, None)]
        with self.assertLogs("fedtail.frontends.common.images", "ERROR"):
            self.c._ready(key, ("pic", b"x", 1))
        self.assertEqual(len(seen), 1)  # the others still got theirs
        url2 = "https://a/f.png"
        key2 = (url2, images.FEED_SIDE)

        def fail_gone():
            raise RuntimeError

        def fail_bug():
            raise ValueError
        self.c.waiting[key2] = [(None, fail_gone), (None, fail_bug)]
        with self.assertLogs("fedtail.frontends.common.images", "ERROR"):
            self.c._failed(key2)
        self.c._ready(key2, None)  # nothing came: as a failure

    def test_slow_window_and_memory_budget(self):
        self.c.mem_budget = 10 * 10 * 4 * 2  # two pictures
        for i in range(4):
            self.c._remember((f"u{i}", 1), ("p",))
        self.assertEqual(len(self.c.mem), 2)
        clock = iter([0.0, 1.0] + [1.0] * 10)
        with mock.patch.object(images.time, "monotonic", lambda: next(clock)):
            self.c._ready(("https://a/s", 1), ("pic", b"s", 1))

    def test_the_newest_waits_least_but_nobody_starves(self):
        now = time.monotonic()
        self.c._stacks[False][:] = [("https://a/old", 1, now - 60), ("https://a/new", 1, now)]
        self.net["https://a/old"] = Answer(b"PNGold")
        key, img = self.c._next(False)
        self.assertEqual(key[0], "https://a/old")  # starving: goes first
        self.c._stacks[False][:] = [("https://a/x", 1, now), ("https://a/y", 1, now)]
        key, img = self.c._next(False)
        self.assertEqual((key[0], img), ("https://a/y", None))  # newest; it failed

    def test_two_workers_one_download(self):
        url = "https://a/same.png"
        gate = threading.Event()

        def slow(_u):
            gate.wait(5)
            return Answer(b"PNGs")
        self.net[url] = slow
        out = []
        t = threading.Thread(target=lambda: out.append(self.c._download(url, 100)))
        t.start()
        for _ in range(200):
            if url in self.c._fetching:
                break
            time.sleep(0.005)
        t2 = threading.Thread(target=lambda: out.append(self.c._download(url, 50)))
        t2.start()
        time.sleep(0.05)
        gate.set()
        t.join()
        t2.join()
        self.assertEqual(sorted(x[2] for x in out), [50, 100])
        self.assertEqual(len(self.c.opened), 1)  # the second used the first one's file
        # the first one failed: so does the one that waited for it
        url2 = "https://a/fails.png"
        ev = threading.Event()
        ev.set()
        self.c._fetching[url2] = ev
        with self.assertRaises(requests.ConnectionError):
            self.c._download(url2, 50)

    def test_a_cached_file_that_cant_be_touched(self):
        url = "https://a/t.png"
        file_of(self.c, url).write_bytes(b"PNGt")
        with mock.patch.object(images.os, "utime", side_effect=OSError):
            self.assertEqual(self.c._download(url, 10)[1], b"PNGt")

    def test_closed_and_bookkeeping_limits(self):
        for i in range(4001):
            self.c.big.add((f"b{i}", 1))
        for i in range(2001):
            self.c.related[f"o{i}"] = {"p"}
        for i in range(501):
            self.c.gave_up[f"g{i}"] = []
        self.net["https://a/z.png"] = Answer(b"PNGz")
        self.get("https://a/z.png", big=True, original="https://a/zo.png")
        self.assertLessEqual(len(self.c.big), 2)
        self.assertLessEqual(len(self.c.related), 2001)
        for _ in range(10):
            self.c._give_up("https://a/w", 1, None, None)
        self.assertEqual(len(self.c.gave_up["https://a/w"]), 8)
        self.c.closed = True
        self.c._ask(("https://a/late", 1))  # a timer after the window went: nothing
        self.assertNotIn(("https://a/late", 1), self.c.asked)

    # ---- ahead of time, videos, saving --------------------------------------------------
    def test_prefetch(self):
        self.net["https://a/pre.png"] = Answer(b"PNGpre")
        self.net["https://a/page"] = Answer(b"<html>", kind="text/html")
        self.net["https://a/empty.png"] = Answer(b"")
        self.net["https://a/err.png"] = Answer(status=404)
        file_of(self.c, "https://a/have.png").write_bytes(b"x")
        urls = ["https://a/pre.png", "https://a/page", "https://a/empty.png",
                "https://a/err.png", "https://a/have.png", "", "https://a/pre.png"]
        self.c.prefetch(urls)
        self.c.pre_pool.shutdown(wait=True)
        self.assertEqual(file_of(self.c, "https://a/pre.png").read_bytes(), b"PNGpre")
        for u in ("https://a/page", "https://a/empty.png", "https://a/err.png"):
            self.assertFalse(file_of(self.c, u).exists(), u)
        self.assertEqual(sum(1 for u, _t in self.c.opened if u == "https://a/pre.png"), 1)
        self.c._pre_seen.update(str(i) for i in range(20001))
        self.c.prefetch([])
        self.assertEqual(self.c._pre_seen, set())

    def test_videos(self):
        url = "https://a/v/clip.MP4"
        self.net[url] = Answer(chunks=[b"vid", b"eo"], kind="video/mp4")
        self.assertIsNone(self.c.video_local(url))
        self.c.prefetch_video([url, url, ""])
        self.c.video_pool.shutdown(wait=True)
        local = self.c.video_local(url)
        self.assertTrue(local.endswith(".mp4"))
        self.assertEqual(Path(local).read_bytes(), b"video")
        self.c._fetch_video(url)  # there already: nothing
        self.assertEqual(sum(1 for u, _t in self.c.opened if u == url), 1)
        with mock.patch.object(images.os, "utime", side_effect=OSError):
            self.assertEqual(self.c.video_local(url), local)
        self.assertTrue(str(self.c._video_path("https://a/x.weird")).endswith(".bin"))

    def test_videos_too_big_or_failing_leave_nothing(self):
        for url, ans in (("https://a/big1.mp4", Answer(length=images.VIDEO_MAX + 1)),
                         ("https://a/big2.mp4", Answer(chunks=[b"x"] * 3)),
                         ("https://a/err.mp4", Answer(status=500))):
            self.net[url] = ans
            with mock.patch.object(images, "VIDEO_MAX", 2) if url.endswith("2.mp4") else \
                    mock.patch.object(images, "_short", images._short):
                self.c._fetch_video(url)
            self.assertIsNone(self.c.video_local(url), url)
            self.assertEqual(list(self.c.video_dir.glob("*.part")), [])

    def test_every_tenth_video_prunes(self):
        self.c._videos_written = 9
        self.net["https://a/t.mp4"] = Answer(b"v")
        with mock.patch.object(self.c, "prune_videos") as prune:
            self.c._fetch_video("https://a/t.mp4")
        prune.assert_called_once()
        self.core.cfg["ui"]["video_disk_mb"] = 0
        self.c.prefetch_video(["https://a/off.mp4"])  # videos to disk are off
        self.assertNotIn("https://a/off.mp4", self.c._video_seen)

    def test_save(self):
        folder = Path(self._tmp.name) / "saved"
        cached = "https://a/c/cat.png"
        file_of(self.c, cached).write_bytes(b"CAT")
        path = self.c.save(cached, folder).result(timeout=10)
        self.assertEqual(path.read_bytes(), b"CAT")
        self.net["https://a/d/dog"] = Answer(chunks=[b"DO", b"G"], kind="image/jpeg")
        path = self.c.save("https://a/d/dog", folder).result(timeout=10)
        self.assertEqual(path.read_bytes(), b"DOG")
        self.assertEqual(path.suffix, ".jpg")
        self.net["https://a/huge.bin"] = Answer(chunks=[b"x"] * 3, kind="video/mp4")
        with mock.patch.object(images, "SAVE_MAX", 2):
            with self.assertRaises(remote.Refused):
                self.c.save("https://a/huge.bin", folder).result(timeout=10)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), sorted(
            [path.name, "cat.png"]))  # no half file left

    # ---- the disk within its size -----------------------------------------------------
    def test_prune_keeps_what_was_used_last(self):
        d = self.c.cache_dir
        names = [hashlib.sha1(str(i).encode()).hexdigest() for i in range(10)]
        for i, n in enumerate(names):
            (d / n).write_bytes(b"x" * 1000)
            os.utime(d / n, (1000 + i, 1000 + i))
        (d / "not-ours.txt").write_bytes(b"x" * 100000)
        self.core.cfg["ui"]["image_disk_mb"] = 0
        self.assertEqual(self.c.prune_disk(), 0)  # no limit
        with mock.patch.object(images.Cache, "_prune", wraps=self.c._prune):
            gone = self.c._prune(d, 5000, lambda p: len(p.name) == 40, "test")
        self.assertEqual(gone, 6)  # down to 80 % of the limit, the oldest first
        self.assertEqual(sorted(p.name for p in d.iterdir() if len(p.name) == 40),
                         sorted(names[6:]))
        self.assertTrue((d / "not-ours.txt").exists())
        self.assertEqual(self.c._prune(d, 10**9, lambda p: True, "test"), 0)
        self.assertEqual(self.c._prune(d / "missing", 10, lambda p: True, "test"), 0)

    def test_prune_survives_files_going_away(self):
        d = self.c.cache_dir
        a = d / ("a" * 40)
        a.write_bytes(b"x" * 100)
        real_stat, real_unlink = Path.stat, Path.unlink

        def stat(p, *args, **kw):
            if p.name == "b" * 40 and not kw:  # there for is_file, gone a moment later
                raise OSError("gone")
            return real_stat(p, *args, **kw)
        (d / ("b" * 40)).write_bytes(b"x")
        with mock.patch.object(Path, "stat", stat), \
                mock.patch.object(Path, "unlink", side_effect=OSError("busy")):
            self.assertEqual(self.c._prune(d, 10, lambda p: len(p.name) == 40, "t"), 0)
        self.assertTrue(a.exists())
        del real_unlink

    def test_every_few_hundred_writes_prune(self):
        self.c._since_prune = 299
        with mock.patch.object(self.c.big_pool, "submit") as submit:
            self.c._count_write()
        submit.assert_called_once()
        self.assertEqual(self.c._since_prune, 0)

    def test_where_and_short(self):
        self.assertEqual(images._short("x" * 10), "x" * 10)
        self.assertTrue(images._short("x" * 100).startswith("…"))
        self.assertTrue(images._where("https://h.test/a?sig=1").startswith("h.test/"))
        self.assertTrue(images._where("nonsense").startswith("?/"))

    def test_the_toolkit_must_give_its_four_things(self):
        base = images.Cache.__new__(images.Cache)
        for name, args in (("decode", (b"", 1)), ("size", (None,)), ("later", (1, None))):
            with self.assertRaises(NotImplementedError):
                getattr(base, name)(*args)
        self.assertEqual(base.to_screen("p"), "p")

    def test_open_goes_through_remote(self):
        plain = images.Cache.__new__(images.Cache)
        plain.http = object()
        plain.core = self.core
        with mock.patch.object(images.remote, "open_url", return_value="R") as op:
            self.assertEqual(plain._open("https://x/1", 5), "R")
        self.assertEqual(op.call_args[1]["schemes"], images.MEDIA_SCHEMES)


if __name__ == "__main__":
    unittest.main()
