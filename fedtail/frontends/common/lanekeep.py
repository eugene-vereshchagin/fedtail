"""Which lanes keep their cards while out of sight (docs/en/dev/memory.md, step 5).

A lane drawn is its cards — a score of widgets each, and the pictures: some 18 MB a lane
in the bench's window (28.10), and every lane opened stayed so for `unload_hidden_minutes`.
Reading through a dozen lanes held them all: half a gigabyte. Now the `keep` lanes shown
last (ui.keep_hidden_lanes) stay drawn for coming back at once; one shown before them
lets its cards go at the moment another comes to the front — and every hidden lane still
after `unload_hidden_minutes`. A lane let go is drawn anew when it is opened, at the
first unread. One rule for every window that keeps cards (Qt, GTK).
"""

from __future__ import annotations


class KeptLanes:
    def __init__(self, keep):
        self.keep = max(0, int(keep))
        self.recent = []  # names, the one shown last first

    def shown(self, name, unload):
        """`name` came to the front. unload(other) lets another's cards go — False when
        it can't (it is on screen too: a column, a tab beside). → the names let go."""
        if name in self.recent:
            self.recent.remove(name)
        self.recent.insert(0, name)
        gone = []
        for other in self.recent[1 + self.keep:]:
            if unload(other):
                gone.append(other)
        self.recent = [n for n in self.recent if n not in gone]
        return gone

    def forget(self, name):
        """A lane gone (a list deleted, the lanes rebuilt)."""
        if name in self.recent:
            self.recent.remove(name)
