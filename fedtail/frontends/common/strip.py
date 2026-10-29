"""The places of a list of cards, without a toolkit: which cards exist, where they stand,
which to build first (docs/en/dev/memory.md, step 5). Qt's FeedView and GTK's lane both
keep their cards on it, so both scroll the same way.

Every key of the list has a place — a top and a height: measured once its card was built
at this width, else the mean of those measured (an older width scales). The body is as
tall as every place together; only the cards within `ahead` screens of the screen exist,
placed by hand. The ones on screen are built at once, the rest a few at a time, nearest
first (below the screen before above at the same distance: reading goes on down).

Nothing here draws or measures: the toolkit builds a card, measures it and says so with
`measured()`; the strip says where it goes.
"""

from __future__ import annotations


class Strip:
    def __init__(self, gap=8, margin=10, first_guess=160):
        self.gap, self.margin, self.first_guess = gap, margin, first_guess
        self.keys = []        # every key, top to bottom
        self.index = {}       # key -> its place in keys
        self.hidden = set()   # keys folded away (no place)
        self.h = {}           # key -> (width, height) measured
        self.ys = {}          # key -> the top of its place
        self.width = 0        # the cards' width now
        self.total = 0        # the body's height
        self.head = (0, 0)    # (top, height) of what stands above the cards

    # ---- the keys -------------------------------------------------------------------
    def set_keys(self, keys):
        self.keys = list(keys)
        self.index = {k: i for i, k in enumerate(self.keys)}
        self.hidden &= set(self.index)
        for k in [k for k in self.h if k not in self.index]:
            del self.h[k]

    # ---- heights --------------------------------------------------------------------
    def guess(self):
        """A card not measured yet: the mean of those measured at this width."""
        hs = [h for w, h in self.h.values() if w == self.width]
        return int(sum(hs) / len(hs)) if hs else self.first_guess

    def height(self, key, guess=None):
        got = self.h.get(key)
        if got is None:
            return self.guess() if guess is None else guess
        w, h = got
        if w == self.width or not w:
            return h
        return max(20, int(h * w / max(1, self.width)))  # wider — shorter, about

    def measured(self, key, width, height, guess=None):
        """A card's height at width, as its toolkit measured it. → True when its place
        was another height (the places below move: lay out again)."""
        if self.h.get(key) == (width, height):
            return False
        placed = self.height(key, guess)
        self.h[key] = (width, height)
        return placed != height

    # ---- places ---------------------------------------------------------------------
    def lay_out(self, width, head=0, foot=0):
        """Every place again for cards `width` wide, with `head` above them and `foot`
        below (the lane's header, "Older"…). → the body's height."""
        self.width = width
        y = self.margin
        self.head = (y, head)
        if head:
            y += head + self.gap
        guess = self.guess()
        ys = {}
        for key in self.keys:
            ys[key] = y
            if key in self.hidden:
                continue
            y += self.height(key, guess) + self.gap
        self.ys = ys
        self.foot_top = y
        self.total = y + foot + self.margin
        return self.total

    def first_place(self, y, guess=None):
        """The index of the first place whose bottom is below y (a bisection)."""
        guess = self.guess() if guess is None else guess
        lo, hi = 0, len(self.keys)
        while lo < hi:
            mid = (lo + hi) // 2
            key = self.keys[mid]
            if self.ys.get(key, 0) + self.height(key, guess) <= y:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def wanted(self, top, view_h, ahead=1.0, held=()):
        """The keys whose places are within `ahead` screens of the screen, and the held
        ones (gone to by a link, find, j / k: built wherever the screen is)."""
        vh = max(1, view_h)
        lo, hi = top - ahead * vh, top + vh + ahead * vh
        guess = self.guess()
        keys = []
        for key in self.keys[self.first_place(lo, guess):]:
            if self.ys.get(key, 0) > hi:
                break
            if key not in self.hidden:
                keys.append(key)
        held = {k for k in held if k in self.index and k not in self.hidden}
        if held - set(keys):
            near = set(keys) | held
            keys = [k for k in self.keys if k in near]
        return keys

    def on_screen(self, keys, top, view_h, held=()):
        """Of keys, those whose places the screen shows now, and the held."""
        bottom = top + max(1, view_h)
        guess = self.guess()
        held = set(held)
        return [k for k in keys if k in held or (
            self.ys.get(k, 0) < bottom and self.ys.get(k, 0) + self.height(k, guess) > top)]

    def by_nearness(self, keys, top, view_h):
        """Nearest the screen first — below it first at the same distance."""
        bottom = top + max(1, view_h)

        def far(k):
            y = self.ys.get(k, 0)
            return (top - y) * 1.2 if y < top else y - bottom
        return sorted(keys, key=far)

    def anchor(self, top):
        """(key, its top less the screen's top) of the card on top of the screen — by
        the places, built or not — or None."""
        for key in self.keys[self.first_place(top):]:
            if key not in self.hidden and key in self.ys:
                return key, self.ys[key] - top
        return None

    def top_for(self, anchor):
        """The screen's top that puts anchor (key, offset) back where it was, or None."""
        if anchor is None or anchor[0] not in self.ys:
            return None
        return max(0, self.ys[anchor[0]] - anchor[1])
