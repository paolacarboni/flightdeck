"""Cartelle di lavoro per ticket: ricordate, dedotte dalla storia delle sessioni, repo locali."""
import os
from collections import Counter
from pathlib import Path

from cc_panel import config, history, paths, state

REPO_SEARCH_DEPTH = 3
RELOCATE_DEPTH = 5
SKIP_DIRS = {"node_modules", "__pycache__", "venv", "target", "dist", "build"}


def remember(key, folder):
    current = state.load()
    current.setdefault("folders", {})[key] = str(folder)
    state.save(current)


def remembered(key):
    folder = state.load().get("folders", {}).get(key)
    return Path(folder) if folder and Path(folder).is_dir() else None


def _project_dirs():
    """Cartelle sotto ~/Projects fino a RELOCATE_DEPTH livelli, senza nascoste e dipendenze."""
    projects = config.projects_dir()
    found = []
    for root, dirs, _ in os.walk(projects):
        depth = len(Path(root).relative_to(projects).parts)
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS] if depth < RELOCATE_DEPTH else []
        found.extend(Path(root) / d for d in dirs)
    return found


def _relocate(folder, project_dirs):
    """Ritrova sotto ~/Projects una cartella spostata, confrontando la parte finale del percorso."""
    projects = config.projects_dir()
    try:
        tail = folder.relative_to(projects).parts
    except ValueError:
        return None
    candidates = [p for p in project_dirs if p.parts[-len(tail):] == tail]
    return candidates[0] if len(candidates) == 1 else None


def from_history(key):
    """Cartelle da cui sono partite le sessioni che hanno citato la chiave, un voto per sessione."""
    return relocated(Counter(s["cwd"] for s in history.index() if key in s["keys"] and s["cwd"]))


def relocated(votes):
    return [folder for folder, _ in relocated_counts(votes)]


def relocated_counts(votes):
    """(cartella, voti) per cartelle esistenti, dalla più votata; quelle spostate ritrovate sotto
    ~/Projects; home esclusa; voti di cartelle che coincidono dopo la ricollocazione sommati."""
    home = paths.home()
    project_dirs = None
    totals = Counter()
    for cwd, count in votes.most_common():
        folder = Path(cwd)
        if not folder.is_dir():
            if project_dirs is None:
                project_dirs = _project_dirs()
            folder = _relocate(folder, project_dirs)
        if folder and folder != home:
            totals[folder] += count
    return totals.most_common()


def repos():
    found = []

    def walk(folder, depth):
        for child in sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")):
            if (child / ".git").exists():
                found.append(child)
            elif depth < REPO_SEARCH_DEPTH:
                walk(child, depth + 1)

    projects = config.projects_dir()
    if projects.is_dir():
        walk(projects, 1)
    return found


def suggest(key, epic):
    """Proposte in ordine: cartella ricordata, storia del ticket, storia dell'epica."""
    ordered = [remembered(key)] + from_history(key) + (from_history(epic) if epic else [])
    unique = []
    for folder in ordered:
        if folder and folder not in unique:
            unique.append(folder)
    return unique
