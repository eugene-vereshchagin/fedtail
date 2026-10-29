"""The Qt lane's places stay true while pictures come in and new posts arrive: no card
over another, no gap between them (a lane of pictures under warnings, 29.10)."""

import unittest

from . import test_qt_smoke as smoke
from .fakes import BOB, status

HAVE_QT = smoke.HAVE_QT


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class LanePlacesTest(unittest.TestCase):
    setUpClass = smoke.QtSmokeTest.__dict__["setUpClass"]
    setUp = smoke.QtSmokeTest.setUp
    tearDown = smoke.QtSmokeTest.tearDown
    pump = smoke.QtSmokeTest.pump

    @property
    def app(self):
        from PySide6.QtWidgets import QApplication
        return QApplication.instance()

    def _pictures(self, n, start):
        sizes = [(1200, 900), (800, 1400), (1600, 700), (600, 600), (1000, 1500)]
        for i in range(n):
            sid = f"{start + i:03d}"
            st = status(sid, BOB, minute=(start + i) % 60, vis="public",
                        text="Every angle " * (3 + i % 7))
            w, h = sizes[i % len(sizes)]
            st["media_attachments"] = [
                {"type": "image", "url": f"https://pics.test/{sid}-{k}.jpg",
                 "preview_url": f"https://pics.test/{sid}-{k}_s.jpg",
                 "meta": {"small": {"width": w // 4, "height": h // 4},
                          "original": {"width": w, "height": h}}}
                for k in range(1 + i % 3)]
            st["sensitive"] = True
            if i % 2:
                st["spoiler_text"] = "NSFW 18+"
            self.world.add(st, home=True)

    def _overlaps(self, view):
        stray = [c for c in view.body.children() if hasattr(c, "spec") and c.isVisible()
                 and view.rows.get(c.spec.key) is not c]
        bad = [("stray", c.spec.key, c.geometry().getRect()) for c in stray]
        keys = [k for k in view.order if k in view.rows]
        for a, b in zip(keys, keys[1:], strict=False):
            ra, rb = view.rows[a], view.rows[b]
            need = view._measure(ra, view._width)
            if ra.geometry().bottom() >= rb.geometry().top() or ra.height() < need:
                bad.append((a, ra.geometry().getRect(), need, b, rb.geometry().getRect()))
        for k in keys:  # a card made again shows one body: the old one is gone from sight
            row = view.rows[k]
            body = getattr(row, "body", None)
            if body is None:
                continue
            seen = [c for c in row.children() if isinstance(c, type(body)) and c.isVisible()
                    and c is not body and c.objectName() == body.objectName()]
            if seen:
                bad.append(("two bodies", k))
        return bad

    def test_pictures_and_new_posts_keep_the_places(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QColor, QPixmap

        self._pictures(30, 100)

        def get(url, cb, *a, **k):  # pictures come a little later, as from the network
            def give():
                pm = QPixmap(900, 700)
                pm.fill(QColor("#c08080"))
                try:
                    cb(pm)
                except RuntimeError:
                    pass
            if url.endswith("0.jpg") or url.endswith("_s.jpg") and hash(url) % 2:
                give()  # in the cache already: at once, inside the card's building
            else:
                QTimer.singleShot(30, give)
        self.win.images.get = get
        self.win.ctx.cfg["feed"]["sensitive_media"] = "show"
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("home")
        lane = self.win.lane_widgets["home"]
        view = lane.view
        self.pump(until=lambda: len(view.rows) > 3 and not view._pending)
        self.pump(0.5)
        self.assertEqual(self._overlaps(view), [])
        sb = view.verticalScrollBar()
        sb.setValue(sb.maximum() // 2)
        self.pump(0.5)
        self.assertEqual(self._overlaps(view), [])
        for n in range(3):  # new posts come in on top, again and again
            self._pictures(2, 200 + 2 * n)
            self.core.poll_once()
            lane.refresh()
            self.pump(0.6)
            self.assertEqual(self._overlaps(view), [], f"after new posts #{n}")
            sb.setValue(0 if n % 2 else sb.maximum())
            self.pump(0.4)
            self.assertEqual(self._overlaps(view), [], f"after a jump #{n}")

        # likes and boosts counted anew on a refresh: only the row of buttons is made
        # again, the card (its pictures) stays — and never shows two of itself
        bodies = {k: view.rows[k].body for k in view.order if hasattr(view.rows[k], "body")}
        for st in self.world.statuses.values():
            st["favourites_count"] = st.get("favourites_count", 0) + 5
        self.core.poll_once()
        lane.refresh()
        for _ in range(3):
            self.app.processEvents()
        self.assertEqual(self._overlaps(view), [])
        kept = [k for k in bodies if k in view.rows]
        self.assertTrue(kept)
        self.assertTrue(all(view.rows[k].body is bodies[k] for k in kept))
        from PySide6.QtWidgets import QToolButton
        texts = [b.text() for k in kept
                 for b in view.rows[k].actions_box.findChildren(QToolButton)]
        self.assertTrue(any(t.endswith("5") for t in texts), texts[:8])


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class LaneHoleTest(unittest.TestCase):
    setUpClass = smoke.QtSmokeTest.__dict__["setUpClass"]
    setUp = smoke.QtSmokeTest.setUp
    tearDown = smoke.QtSmokeTest.tearDown
    pump = smoke.QtSmokeTest.pump
    _pictures = LanePlacesTest._pictures

    def test_a_hole_is_mended(self):
        """The screen empty with cards to show there (a lane opened blank at its end, the
        read posts above, 29.10): the lane says so in the log and builds them."""
        self._pictures(30, 100)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("home")
        view = self.win.lane_widgets["home"].view
        self.pump(until=lambda: len(view.rows) > 3 and not view._pending)
        for key in list(view.rows):  # lost, as if never built
            view._let_go(key)
        with self.assertLogs("fedtail", "WARNING") as said:
            view._check_holes()
        self.assertIn("hole in a lane", said.output[0])
        self.assertTrue(view.rows)

    def test_one_cards_room_left_blank_is_mended(self):
        """Not only a screen mostly empty: one card's room left blank (the last post at
        the lane's end, then a post's height of nothing, 29.10) is a hole too; a lane
        whose places are true has none."""
        self._pictures(30, 100)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("home")
        view = self.win.lane_widgets["home"].view
        self.pump(until=lambda: len(view.rows) > 3 and not view._pending)
        self.pump(0.3)
        view._hole_said = 0
        with self.assertNoLogs("fedtail.frontends.qt.feedview", "WARNING"):
            view._check_holes()
        sb = view.verticalScrollBar()
        vt, vh = sb.value(), view.viewport().height()
        key = next(k for k in view.order if view._ys[k] > vt + 20
                   and view._ys[k] + view.rows[k].height() < vt + vh)
        view._let_go(key)  # its room on screen, nothing in it
        with self.assertLogs("fedtail.frontends.qt.feedview", "WARNING") as said:
            view._check_holes()
        self.assertIn("empty", said.output[0])
        self.assertIn(key, view.rows)  # built again where it stands


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class LaneStoodTest(unittest.TestCase):
    setUpClass = smoke.QtSmokeTest.__dict__["setUpClass"]
    setUp = smoke.QtSmokeTest.setUp
    tearDown = smoke.QtSmokeTest.tearDown
    pump = smoke.QtSmokeTest.pump
    _pictures = LanePlacesTest._pictures

    def test_opens_where_the_reader_stood_and_says_where_it_stands(self):
        """The lane opens on the card the reader stood at last, in whatever interface
        (LaneModel.stood) — not at its first unread; read on, the card on top goes back
        to the core."""
        self._pictures(20, 100)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.core.set_state("stood.home", "110")
        self.win.select_lane("home")
        view = self.win.lane_widgets["home"].view
        self.pump(until=lambda: "110" in view.rows and not view._pending)
        self.pump(0.5)
        top = view.verticalScrollBar().value()
        self.assertLessEqual(abs(view._ys["110"] - 6 - top), 2)
        view._touched_at = __import__("time").monotonic()  # read by hand, as a reader
        view._target = None
        view.verticalScrollBar().setValue(view._ys["115"] + 2)
        self.pump(0.1)
        view._emit_seen()
        self.assertEqual(self.core.get_state("stood.home"), "115")
        sb = view.verticalScrollBar()  # read to the end: no place kept, it opens as ever
        sb.setValue(sb.maximum())
        self.pump(0.1)
        view._target = None
        view._emit_seen()
        self.assertEqual(self.core.get_state("stood.home"), "")


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class LaneStrayTest(unittest.TestCase):
    setUpClass = smoke.QtSmokeTest.__dict__["setUpClass"]
    setUp = smoke.QtSmokeTest.setUp
    tearDown = smoke.QtSmokeTest.tearDown
    pump = smoke.QtSmokeTest.pump
    _pictures = LanePlacesTest._pictures

    def test_no_card_stands_unowned_and_no_key_twice(self):
        """A card on the lane that the lane doesn't own goes, said in the log (two posts
        drawn in one place, 29.10); the same card twice in the specs takes one place."""
        from fedtail.frontends.qt.card import row_class
        self._pictures(12, 100)
        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("home")
        view = self.win.lane_widgets["home"].view
        self.pump(until=lambda: len(view.rows) > 3 and not view._pending)
        key = view.order[0]
        spec = view.model[view._index[key]]
        stray = row_class(spec)(spec, view.ctx)
        stray.setParent(view.body)
        stray.show()
        with self.assertLogs("fedtail.frontends.qt.feedview", "WARNING") as said:
            self.assertEqual(view._strays(), 1)
        self.assertIn("no one owns", said.output[0])
        self.assertTrue(stray.isHidden())
        self.assertEqual(view._strays(), 0)  # the lane's own cards stay
        before = view._total
        view.set_specs(list(view.model) + [view.model[-1]])
        self.assertEqual(view._total, before)
        self.assertEqual(len(view.strip.keys), len(set(view.strip.keys)))


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class HoverTest(unittest.TestCase):
    setUpClass = smoke.QtSmokeTest.__dict__["setUpClass"]
    setUp = smoke.QtSmokeTest.setUp
    tearDown = smoke.QtSmokeTest.tearDown
    pump = smoke.QtSmokeTest.pump

    def test_the_post_under_the_mouse_is_lit(self):
        """shape.hover (point.im): the post under the mouse has its buttons lit and, on
        my own post, ✎ ✕ at the top right; off the mouse, gone; other posts have none."""
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QEnterEvent

        self.win.start()
        self.pump(until=lambda: self.core.me is not None)
        self.core.poll_once()
        self.win.select_lane("home")
        view = self.win.lane_widgets["home"].view
        self.pump(until=lambda: "010" in view.rows and "011" in view.rows)
        shape = view.ctx.theme.shape
        old = shape.get("hover")
        shape["hover"] = True
        self.addCleanup(lambda: shape.__setitem__("hover", old))
        view.rebuild_rows()
        self.pump(until=lambda: "010" in view.rows and "011" in view.rows)
        mine, theirs = view.rows["010"], view.rows["011"]
        p = QPointF(5, 5)
        theirs.enterEvent(QEnterEvent(p, p, p))
        self.assertIsNone(theirs.own_tools)
        mine.enterEvent(QEnterEvent(p, p, p))
        self.assertTrue(mine.own_tools.isVisible())
        self.assertEqual(mine.actions_box.property("hover"), "true")
        mine.leaveEvent(QEvent(QEvent.Type.Leave))
        self.assertFalse(mine.own_tools.isVisible())
        self.assertEqual(mine.actions_box.property("hover"), "false")
