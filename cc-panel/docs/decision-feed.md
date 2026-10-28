# Decision feed

Un unico feed live di tutte le sessioni Claude Code: cosa stanno facendo, le decisioni importanti che
prendono, i punti da attenzionare e i concetti da approfondire. Tutto resta in
`~/.claude/cc-panel/events.jsonl`; nessun dato esce dalla macchina.

```bash
cc-panel feed --follow      # sessioni, ⚠ da attenzionare, decisioni (aggiorna ogni 5 s)
cc-panel feed --json        # modello per il pannello
cc-panel dive <id>          # fork della sessione che ti spiega la decisione o il concetto --learn
```

`dive` apre `claude --resume <sessione> --fork-session "<domanda>"`: la fork ha tutto il contesto
della sessione, che intanto continua senza interruzioni.

## 1. Hook in `~/.claude/settings.json`

Registrano inizio, prompt, attesa di input/permessi, fine turno e fine sessione. `|| true` garantisce
che un hook non blocchi mai la sessione.

```json
"hooks": {
  "SessionStart":     [{"hooks": [{"type": "command", "command": "cc-panel hook || true", "timeout": 5}]}],
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "cc-panel hook || true", "timeout": 5}]}],
  "Notification":     [{"hooks": [{"type": "command", "command": "cc-panel hook || true", "timeout": 5}]}],
  "Stop":             [{"hooks": [{"type": "command", "command": "cc-panel hook || true", "timeout": 5}]}],
  "SessionEnd":       [{"hooks": [{"type": "command", "command": "cc-panel hook || true", "timeout": 5}]}],
  "PostToolUse":      [{"matcher": "ExitPlanMode",
                        "hooks": [{"type": "command", "command": "cc-panel hook || true", "timeout": 5}]}]
}
```

L'hook su `ExitPlanMode` ricorda all'agente di registrare le decisioni del piano appena approvato.

## 2. Istruzione in `~/.claude/CLAUDE.md`

```markdown
# Registro decisioni (cc-panel)

Quando prendi una decisione IMPORTANTE registrala subito, prima di applicarla:
`cc-panel decide "<titolo>" --why "<motivo>" --alt "<alternativa scartata>" [--watch "<rischio>"] [--learn "<concetto>"]`

È importante se almeno uno: difficile da annullare; c'erano alternative reali; tocca interfacce, dati,
sicurezza o costi; devia dalla richiesta o dal piano; si regge su un'assunzione non verificata.
Massimo 3–5 per sessione, niente decisioni banali. `--watch` per ciò che l'utente deve controllare,
`--learn` per il concetto che vale la pena approfondire.
```
