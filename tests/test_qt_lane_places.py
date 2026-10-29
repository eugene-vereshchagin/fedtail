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
