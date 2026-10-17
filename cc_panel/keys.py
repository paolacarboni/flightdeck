"""Chiavi dei ticket Jira."""
import re

KEY_PATTERN = r"[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,6}"
_FULL_KEY = re.compile(r"^%s$" % KEY_PATTERN)


def is_key(text):
    return bool(_FULL_KEY.match(text))


def mention_pattern(key):
    """Regex per la chiave citata nel testo: AI-34 non combacia con AI-340 né con XAI-34."""
    return re.compile(r"(?<![A-Z0-9-])%s(?![0-9])" % re.escape(key))

# Nome di sessione o titolo che inizia con una chiave ticket («PROJ-369 titolo»).
TICKET_NAME = re.compile(r"^%s(\s|$)" % KEY_PATTERN)
