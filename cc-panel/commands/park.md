---
description: Salva una nota di ripresa sul ticket Jira prima di fermarti
argument-hint: "[KEY]"
allowed-tools: Bash(cc-panel park:*), Bash(git -C:*)
---

Salva una nota di ripresa per il ticket su cui stai lavorando, così la prossima sessione riparte da qui.

1. Chiave del ticket: usa `$ARGUMENTS` se è una chiave Jira (es. `OPS-369`); altrimenti la chiave della riga `Ticket: <KEY>` del primo messaggio della sessione; altrimenti chiedila all'utente e fermati finché non risponde.
2. Ricava cartella e branch correnti con `git -C "$PWD" branch --show-current` (se non è un repo git, scrivi solo la cartella).
3. Componi la nota in italiano, concreta e breve, con esattamente queste righe:
   - `**Dove:** <cartella> · branch <branch>`
   - `**Fatto:** <cosa è stato completato in questa sessione, 1-3 punti>`
   - `**Prossimo passo:** <la prima azione da fare alla ripresa, eseguibile senza altro contesto>`
   - `**Blocchi:** <cosa aspetta decisioni o altre persone, oppure "nessuno">`
   - `**File chiave:** <path rilevanti, separati da virgola>`
4. Salvala passando il testo via heredoc con delimitatore tra apici:

   ```bash
   cc-panel park <KEY> <<'NOTA'
   <nota>
   NOTA
   ```

5. Riporta all'utente il path scritto e il prossimo passo.
