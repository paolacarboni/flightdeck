"""Stato locale dei repo git, in sola lettura e senza rete."""
import subprocess
import time
from pathlib import Path

TIMEOUT_SECONDS = 3
_DIRTY_PREFIXES = ("1 ", "2 ", "u ", "? ")


def _git(folder, *args):
    try:
        result = subprocess.run(["git", "-C", str(folder)] + list(args), capture_output=True, text=True,
                                timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def root(folder):
    out = _git(folder, "rev-parse", "--show-toplevel")
    return Path(out.strip()) if out else None


def status(repo):
    """Branch, file modificati o non tracciati, commit non pubblicati, giorni dall'ultimo commit."""
    out = _git(repo, "status", "--porcelain=v2", "--branch")
    if out is None:
        return None
    branch, ahead, dirty = None, 0, 0
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            branch = line.split(" ", 2)[2]
        elif line.startswith("# branch.ab "):
            ahead = int(line.split()[2].lstrip("+"))
        elif line.startswith(_DIRTY_PREFIXES):
            dirty += 1
    last = _git(repo, "log", "-1", "--format=%ct")
    days = int((time.time() - int(last)) // 86400) if last and last.strip() else None
    return {"branch": branch, "dirty": dirty, "ahead": ahead, "lastCommitDays": days}
