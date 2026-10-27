"""What an open thread says while its replies come from its author's server
(threads.thread_progress): the same words in every interface."""

from ...i18n import _


def thread_words(step):
    """{"stage", "done", "total"} (Core.thread_progress) → a short line, "" — nothing."""
    if not step:
        return ""
    stage, done, total = step.get("stage"), int(step.get("done") or 0), \
        int(step.get("total") or 0)
    if stage == "asking":
        return "⇣ " + _("thread_fetch_asking")
    if stage == "fetching":
        return "⇣ " + (_("thread_fetch_n", done=done, total=total) if total
                       else _("thread_fetch_asking"))
    if stage == "done":
        if done:
            return "⇣ " + _("thread_fetch_done", n=done)
        return "⇣ " + (_("thread_fetch_zero", total=total) if total else
                       _("thread_fetch_none"))
    if stage == "failed":
        return "⇣ " + _("thread_fetch_failed")
    return ""


def bar(step, width=12):
    """▰▰▰▱▱▱ for "fetching" (a terminal, a phone's line); "" otherwise."""
    if not step or step.get("stage") != "fetching" or not step.get("total"):
        return ""
    full = round(width * int(step["done"]) / int(step["total"]))
    return "▰" * full + "▱" * (width - full)
