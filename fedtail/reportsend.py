"""A bug report (or a self-check's archive) pushed straight into a private git
repository over ssh, with the user's own ssh keys: debug.report_repo = "user/repo"
(GitHub) or any git address ("git@host:user/repo.git", "ssh://…").

No working copy: the file is put on top of the remote branch with git's plumbing
(hash-object, read-tree, commit-tree, push) in a bare cache repository fetched
with --filter=blob:none, so the reports already there are never downloaded — only
the trees. Two machines pushing at once: the one that loses fetches again and
retries. ssh never asks anything (BatchMode): no key, no access — an error in words.

    where = send(archive, "me/fedtail-reports", cache_dir)   # "reports/2026-10/…"
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_HOST = "git@github.com:"
TRIES = 3
_SPEC = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class SendError(Exception):
    """Why the report didn't go, in words for the person."""


def remote_url(spec):
    """"user/repo" → GitHub over ssh; a git address as it is; "" → None."""
    spec = (spec or "").strip()
    if not spec:
        return None
    if _SPEC.match(spec):
        name = spec if spec.endswith(".git") else spec + ".git"
        return DEFAULT_HOST + name
    if spec.startswith(("ssh://", "git@", "https://", "file://", "/")) or \
            re.match(r"^[\w.-]+@[\w.-]+:", spec) or re.match(r"^[A-Za-z]:[\\/]", spec) or \
            spec.startswith("\\\\"):
        return spec  # (a folder on this machine or a share: C:\…, \\server\…)
    raise SendError(f"debug.report_repo = {spec!r}: not user/repo nor a git address")


def _env():
    from . import sysenv
    env = dict(sysenv.child_env() or os.environ)
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=20")
    env["GIT_TERMINAL_PROMPT"] = "0"  # never a password prompt nobody sees
    who = {"GIT_AUTHOR_NAME": "fedtail", "GIT_AUTHOR_EMAIL": "fedtail@localhost"}
    env.update(who)
    env.update({"GIT_COMMITTER_NAME": who["GIT_AUTHOR_NAME"],
                "GIT_COMMITTER_EMAIL": who["GIT_AUTHOR_EMAIL"]})
    return env


def _git(repo, *args, env=None, timeout=120, check=True):
    exe = shutil.which("git")
    if exe is None:
        raise SendError("git is not installed")
    try:
        r = subprocess.run([exe, "-C", str(repo), *args], capture_output=True, text=True,
                           env=env, timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise SendError(f"git {args[0]}: no answer in {timeout} s") from None
    if check and r.returncode != 0:
        raise SendError(_said(r.stderr) or f"git {args[0]} failed ({r.returncode})")
    return r


def _said(stderr):
    """git's last meaningful line (ssh's "Permission denied (publickey)" and the like)."""
    lines = [x.strip() for x in (stderr or "").splitlines()
             if x.strip() and not x.startswith(("hint:", "warning:"))]
    return lines[-1][:300] if lines else ""


def default_branch(repo, env):
    """The remote's HEAD branch; "main" for an empty repository."""
    r = _git(repo, "ls-remote", "--symref", "origin", "HEAD", env=env)
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", r.stdout, re.M)
    return m.group(1) if m else "main"


def _cache(cache_dir, url, env):
    repo = Path(cache_dir)
    if not (repo / "HEAD").exists():
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, "init", "-q", "--bare", env=env)
    have = _git(repo, "remote", "get-url", "origin", env=env, check=False)
    if have.returncode != 0:
        _git(repo, "remote", "add", "origin", url, env=env)
    elif have.stdout.strip() != url:
        _git(repo, "remote", "set-url", "origin", url, env=env)
    return repo


def send(path, spec, cache_dir, folder="reports", message=None):
    """Push the file at path into the repository spec names, as
    <folder>/<YYYY-MM>/<its name>. Returns that path in the repository; SendError
    when it couldn't."""
    url = remote_url(spec)
    if url is None:
        raise SendError("debug.report_repo is empty")
    path = Path(path)
    env = _env()
    repo = _cache(cache_dir, url, env)
    branch = default_branch(repo, env)
    where = f"{folder}/{time.strftime('%Y-%m')}/{path.name}"
    blob = _git(repo, "hash-object", "-w", str(path), env=env).stdout.strip()
    index = repo / "fedtail-index"
    last = None
    for _attempt in range(TRIES):
        got = _git(repo, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin",
                   f"refs/heads/{branch}", env=env, check=False)
        parent = None
        if got.returncode == 0:
            parent = _git(repo, "rev-parse", "FETCH_HEAD", env=env).stdout.strip()
        elif "couldn't find remote ref" not in got.stderr:
            raise SendError(_said(got.stderr) or "git fetch failed")
        idx_env = dict(env, GIT_INDEX_FILE=str(index))
        index.unlink(missing_ok=True)
        if parent:
            _git(repo, "read-tree", parent, env=idx_env)
        _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{where}",
             env=idx_env)
        # --missing-ok: the others' reports are only known of, never fetched (it would)
        tree = _git(repo, "write-tree", "--missing-ok", env=idx_env).stdout.strip()
        args = ["commit-tree", tree, "-m", message or f"report: {path.name}"]
        if parent:
            args[2:2] = ["-p", parent]
        commit = _git(repo, *args, env=env).stdout.strip()
        pushed = _git(repo, "push", "-q", "origin", f"{commit}:refs/heads/{branch}",
                      env=env, check=False, timeout=600)
        if pushed.returncode == 0:
            index.unlink(missing_ok=True)
            return where
        last = _said(pushed.stderr)
        if "rejected" not in pushed.stderr and "non-fast-forward" not in pushed.stderr \
                and "fetch first" not in pushed.stderr:
            break  # not a race: access, network — retrying won't help
    index.unlink(missing_ok=True)
    raise SendError(last or "git push failed")


def send_report(path, cfg, data_dir):
    """The bug report at path to debug.report_repo, if set. Words to show, or None
    when no repository is set; SendError when it is set and the push failed."""
    spec = ((cfg or {}).get("debug") or {}).get("report_repo", "")
    if not spec:
        return None
    from . import version
    where = send(path, spec, Path(data_dir) / "report-repo",
                 message=f"report: {Path(path).name} (fedtail {version.full()})")
    return f"{spec}: {where}"


__all__ = ["SendError", "default_branch", "remote_url", "send", "send_report"]
