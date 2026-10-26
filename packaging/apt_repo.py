"""fedtail's apt repository (CI's apt job, after a release): the `apt` branch holds
pool/main/*.deb and dists/stable/ — the release's .deb added, the indexes made anew with
apt-ftparchive, signed with the repository's key (APT_GPG_KEY), the public key beside
them (fedtail.asc, fedtail.gpg). GitHub Pages serves the branch; people add

    deb [signed-by=/usr/share/keyrings/fedtail.gpg] https://<owner>.github.io/<repo> stable main

Run in CI only: it pushes. Usage: apt_repo.py VERSION."""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ARCHES = ("all", "amd64", "arm64", "i386", "armhf")  # the package is "all": every one


def run(*cmd, cwd=None, inp=None):
    return subprocess.run(cmd, cwd=cwd, check=True, input=inp, capture_output=True,
                          text=True).stdout


def main(version):
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    work = Path(tempfile.mkdtemp())
    branch = work / "apt"
    url = f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{repo}.git"
    try:
        run("git", "clone", "--depth", "1", "--branch", "apt", url, str(branch))
    except subprocess.CalledProcessError:  # the first time: an empty branch of its own
        branch.mkdir()
        run("git", "init", "-q", "-b", "apt", cwd=branch)
        run("git", "remote", "add", "origin", url, cwd=branch)
    pool = branch / "pool" / "main"
    pool.mkdir(parents=True, exist_ok=True)
    run("gh", "release", "download", f"v{version}", "-p", "*.deb", "-D", str(pool),
        "--clobber", "-R", repo)
    gnupg = work / "gnupg"
    gnupg.mkdir(mode=0o700)
    env = dict(os.environ, GNUPGHOME=str(gnupg))
    subprocess.run(["gpg", "--batch", "--import"], input=os.environ["KEY"], text=True,
                   check=True, env=env, capture_output=True)
    dist = branch / "dists" / "stable"
    shutil.rmtree(dist, ignore_errors=True)
    packages = run("apt-ftparchive", "packages", "pool", cwd=branch)
    for arch in ARCHES:
        d = dist / "main" / f"binary-{arch}"
        d.mkdir(parents=True)
        (d / "Packages").write_text(packages)
        with gzip.open(d / "Packages.gz", "wt") as f:
            f.write(packages)
    release = run("apt-ftparchive",
                  "-o", "APT::FTPArchive::Release::Origin=fedtail",
                  "-o", "APT::FTPArchive::Release::Label=fedtail",
                  "-o", "APT::FTPArchive::Release::Suite=stable",
                  "-o", "APT::FTPArchive::Release::Codename=stable",
                  "-o", "APT::FTPArchive::Release::Architectures=" + " ".join(ARCHES),
                  "-o", "APT::FTPArchive::Release::Components=main",
                  "release", "dists/stable", cwd=branch)
    (dist / "Release").write_text(release)
    sign = ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback"]
    subprocess.run(sign + ["--clearsign", "-o", str(dist / "InRelease"), str(dist / "Release")],
                   check=True, env=env, capture_output=True)
    subprocess.run(sign + ["-abs", "-o", str(dist / "Release.gpg"), str(dist / "Release")],
                   check=True, env=env, capture_output=True)
    pub = subprocess.run(["gpg", "--batch", "--armor", "--export"], check=True, env=env,
                         capture_output=True, text=True).stdout
    (branch / "fedtail.asc").write_text(pub)
    subprocess.run(["gpg", "--batch", "--yes", "--dearmor", "-o", str(branch / "fedtail.gpg")],
                   input=pub.encode(), check=True, env=env, capture_output=True)
    (branch / ".nojekyll").write_text("")  # Pages: the files as they are
    run("git", "add", "-A", cwd=branch)
    run("git", "-c", "user.name=github-actions",
        "-c", "user.email=github-actions@users.noreply.github.com",
        "commit", "-q", "-m", f"apt: fedtail {version}", cwd=branch)
    run("git", "push", "-q", "origin", "apt", cwd=branch)
    print(f"apt: fedtail {version} published")


if __name__ == "__main__":
    try:
        main(sys.argv[1])
    except subprocess.CalledProcessError as e:  # what the tool said, never the key
        print(f"apt: {e.cmd[0]} {e.cmd[1] if len(e.cmd) > 1 else ''} failed ({e.returncode}):"
              f" {(e.stderr or '')[-2000:]}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:  # a tool missing on the runner (0.20.0: apt-ftparchive)
        print(f"apt: {e.filename} is missing — apt-utils, gnupg, gh", file=sys.stderr)
        sys.exit(1)
