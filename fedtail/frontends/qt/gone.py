"""Taking widgets away. deleteLater() waits for the event loop, and till then the old
widget stays where it was, visible, over its successor: a card rebuilt on a refresh
showed both its bodies at once (the buttons drawn twice, an old picture over the next
card, 29.10), a profile rebuilt in a narrower window its last buttons sticking out. So
every widget that goes is hidden at once, out of its layout, and deleted after."""


def drop(widget, layout=None):
    """widget gone from sight now (and from `layout`, if given), deleted later."""
    if widget is None:
        return
    if layout is not None:
        layout.removeWidget(widget)
    widget.hide()
    widget.deleteLater()


def clear(layout):
    """Every widget of a layout (and of the layouts inside it) gone."""
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            drop(item.widget())
        elif item.layout() is not None:
            clear(item.layout())
