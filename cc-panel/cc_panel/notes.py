"""Note di ripresa nella sezione `## Ripresa` della nota del ticket (`notes_dir/<KEY>.md`)."""
import re

SECTION = "## Ripresa"
_SECTION_LINE = re.compile(r"^## Ripresa[ \t]*$", re.M)
_NEXT_SECTION = re.compile(r"^## ", re.M)
_ENTRY_HEADING = re.compile(r"^### ", re.M)


def new_note(key):
    # Frontmatter minimo: altri strumenti (es. sync di Obsidian) possono completarlo.
    return "---\ntype: jira\nkey: %s\n---\n\n## Note\n\n" % key


def add_entry(text, entry, stamp):
    block = "### %s\n\n%s\n" % (stamp, entry.strip())
    match = _SECTION_LINE.search(text)
    if not match:
        separator = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return "%s%s%s\n\n%s" % (text, separator, SECTION, block)
    insert_at = match.end() + 1
    rest = text[insert_at:].lstrip("\n")
    return text[:insert_at] + "\n" + block + ("\n" + rest if rest else "")


def latest_entries(text, count):
    match = _SECTION_LINE.search(text)
    if not match:
        return []
    body = text[match.end():]
    following = _NEXT_SECTION.search(body)
    if following:
        body = body[:following.start()]
    starts = [m.start() for m in _ENTRY_HEADING.finditer(body)]
    entries = [body[a:b].strip() for a, b in zip(starts, starts[1:] + [len(body)])]
    return entries[:count]


_NEXT_STEP = re.compile(r"^[-*\s]*\*\*Prossimo passo:\*\*\s*(.+?)\s*$", re.M)


def next_step(text):
    """Testo della riga «Prossimo passo» nell'ultima voce di ripresa, se presente."""
    entries = latest_entries(text, 1)
    match = _NEXT_STEP.search(entries[0]) if entries else None
    return match.group(1) if match else None
