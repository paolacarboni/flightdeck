"""Primo messaggio della sessione: ticket, ultime note di ripresa, istruzioni."""

DESCRIPTION_LIMIT = 4000
COMMENT_LIMIT = 800
CLOSING = ('Riprendi dal "Prossimo passo" dell\'ultima ripresa, se presente; altrimenti '
           "proponi come iniziare. Prima di fermarti usa /park.")


def _truncate(text, limit):
    return text if len(text) <= limit else text[:limit] + " [troncato]"


def compose(issue, resume_entries):
    lines = ["Ticket: %s — %s" % (issue["key"], issue["summary"]), "", "## Ticket", "",
             "- Stato: %s · Tipo: %s" % (issue["status"], issue["type"])]
    if issue.get("epic"):
        lines.append("- Epica: %s %s" % (issue["epic"], issue.get("epic_summary") or ""))
    lines.append("- Link: %s" % issue["url"])
    if issue.get("description"):
        lines += ["", "## Descrizione", "", _truncate(issue["description"], DESCRIPTION_LIMIT)]
    if issue.get("comments"):
        lines += ["", "## Commenti recenti", ""]
        for comment in issue["comments"]:
            lines.append("- %s, %s: %s" % (comment["author"], comment["created"][:10],
                                           _truncate(comment["body"], COMMENT_LIMIT)))
    if resume_entries:
        lines += ["", "## Ultima ripresa", ""] + ["\n\n".join(resume_entries)]
    lines += ["", CLOSING]
    return "\n".join(lines) + "\n"
