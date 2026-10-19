# focus-panel

**Keep the focus on few things: the frog of the day, one tight time box, at most three items per day,
tomorrow planned tonight, and the deadlines of the next seven days.**

<p align="center"><img src="../docs/screenshots/focus-panel.png" alt="focus-panel" width="520"></p>

## Rules

| Rule | On the panel |
|---|---|
| Eat the frog | One frog per day (◆ magenta). Until it is done, before noon, the other items are dimmed. |
| Time boxing | One active box on one of today's items, length chosen up front (15/30/60/90′ or the estimate). |
| Parkinson's law | Green bar, amber in the last 5′, blinking red after. One single 10′ extension. Boxes extended or closed late count as *FUORI TEMPO*. |
| Plan the day before | After 17:30 *DOMANI* appears and new items go to tomorrow; amber until tomorrow has a frog. |
| Next concrete action | Every item is *verb + object* with an estimate (5-240′). |

At most three items per day, frog included. Unfinished items from past days go back to the parking lot.

## Use

From the panel: *+ AGGIUNGI* opens the input (Enter adds, Esc closes); hovering an item shows ▶ BOX, FROG,
→ DOM., PARK, ✓ and ✕. On the box: ✓ FATTO, +10′, ■ STOP. Click a Jira deadline to open it.
The same actions are in the [menu bar](../harlock-bar/).

```bash
focus-panel add Write the release notes -m 45 --frog       # today
focus-panel add Prepare the demo -m 60 --when domani --due 2026-10-21
focus-panel start 1 -m 25 | extend | stop | done [ID]
focus-panel frog ID | move ID oggi|domani|dopo | drop ID
focus-panel sync                                            # Jira deadlines now
focus-panel show                                            # JSON for the panel
```

The panel reloads every 15 seconds. Jira deadlines (assigned to you, open, due within 7 days, overdue
included) refresh in background every 30 minutes, reusing cc-panel's client, configuration and token
(cc-panel is expected next to this folder; `FOCUS_PANEL_CC_PANEL` points elsewhere).

## Files

| Path | Content |
|---|---|
| `~/.claude/focus-panel/focus.json` | items, active box, box log |
| `~/.claude/focus-panel/deadlines.json` | cached Jira deadlines |

## Tests

```bash
/usr/bin/python3 -m unittest discover -s tests -t .
```
