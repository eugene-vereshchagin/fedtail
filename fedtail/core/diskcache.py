"""The pictures' and videos' files on disk (paths.cache_dir) kept within ui.image_disk_mb
and ui.video_disk_mb: those not used the longest go first. The core does it, every
interface alike — only the windows' picture cache did, so the web page, the phone and
the terminal filled the folder without end (21.11)."""

import logging
import time

log = logging.getLogger(__name__)


def is_picture(p):
    """Our picture files: names of 40 hex digits (sha1 of the address)."""
    return len(p.name) == 40 and all(c in "0123456789abcdef" for c in p.name)


def is_video(p):
    return len(p.stem) == 40 and p.suffix != ".part"


def prune(folder, limit, ours, what):
    """Files of `folder` that `ours` says are ours, cut down to some 80 % of `limit`
    bytes when over it; the oldest used first. Returns how many went."""
    if limit <= 0:
        return 0
    files, total = [], 0
    try:
        for p in folder.iterdir():
            if not p.is_file() or not ours(p):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, p))
            total += st.st_size
    except OSError:
        return 0
    if total <= limit:
        return 0
    files.sort()  # oldest used first
    target = int(limit * 0.8)  # some room, so it isn't pruned again right away
    freed = gone = 0
    for _mtime, size, p in files:
        if total - freed <= target:
            break
        try:
            p.unlink()
            freed += size
            gone += 1
        except OSError:
            pass
    log.info("%s: %d files, %.0f MB let go (%.0f MB kept, limit %d MB)", what, gone,
             freed / 2**20, (total - freed) / 2**20, limit // 2**20)
    return gone


def prune_all(cfg, cache_dir):
    """Both caches within their budgets. → (pictures gone, videos gone)."""
    ui = cfg.get("ui") or {}
    t = time.monotonic()
    pics = prune(cache_dir, int(ui.get("image_disk_mb", 1000)) * 1024 * 1024, is_picture,
                 "image cache")
    vids = prune(cache_dir / "video", int(ui.get("video_disk_mb", 10000)) * 1024 * 1024,
                 is_video, "video cache")
    if pics or vids:
        log.debug("disk caches pruned in %.2f s", time.monotonic() - t)
    return pics, vids
