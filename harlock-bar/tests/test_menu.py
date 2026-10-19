import unittest
from datetime import datetime

from harlock_bar import menu

# Lunedì 19 ottobre 2026, ore 15.
NOW = datetime(2026, 10, 19, 15, 0).timestamp()
CTX = {"icon": "ICON", "cmd": "/bin/harlock-bar", "day_end": (18, 30)}


def item(id_, text, minutes=30, frog=False, done=False):
    return {"id": id_, "text": text, "minutes": minutes, "day": "2026-10-19", "frog": frog,
            "doneAt": NOW - 60 if done else None}


def focus(today=(), box=None, **extra):
    state = {"now": NOW, "today": list(today), "tomorrow": [], "parked": [], "frogFirst": False,
             "planMode": False, "tomorrowFrog": False, "box": box, "overToday": 0, "doneToday": 0,
             "maxPerDay": 3, "deadlines": [], "jiraError": None, "syncing": False}
    state.update(extra)
    return state


def ticket(key, summary, session=None, category="indeterminate", next_step=None):
    return {"key": key, "summary": summary, "type": "Task", "status": "IN LAVORAZIONE",
            "statusCategory": category, "session": session or {"state": "none"}, "nextStep": next_step}


def board(items=(), no_epic=()):
    return {"baseUrl": "https://jira.example", "updatedAt": NOW - 120,
            "summary": {"inProgress": 0, "waitingSessions": 0, "staleSessions": 0},
            "epics": [{"key": "OPS-1", "summary": "Epica uno", "items": list(items)}],
            "noEpic": list(no_epic), "proposals": []}


def lines_of(**kwargs):
    args = {"focus": focus(), "board": board(), "now": NOW, "ctx": CTX}
    args.update(kwargs)
    return menu.build(**args)


class TitleTest(unittest.TestCase):
    def test_solo_icona_senza_box(self):
        self.assertEqual(lines_of()[0], " | image=ICON")

    def test_countdown_del_box_in_minuti(self):
        box = {"itemId": 1, "text": "Scrivere", "remaining": 11 * 60 + 5, "phase": "run", "extended": False}
        self.assertEqual(lines_of(focus=focus([item(1, "Scrivere")], box=box))[0], "12′ | image=ICON")

    def test_box_scaduto_in_rosso(self):
        box = {"itemId": 1, "text": "Scrivere", "remaining": -200, "phase": "over", "extended": True}
        self.assertEqual(lines_of(focus=focus([item(1, "Scrivere")], box=box))[0], "+3′ | image=ICON color=#ff6b5e")

    def test_sessioni_in_attesa_nel_titolo(self):
        waiting = ticket("OPS-2", "Due", {"state": "open", "status": "waiting"})
        self.assertEqual(lines_of(board=board([waiting]))[0], "⏸1 | image=ICON")


class DayTest(unittest.TestCase):
    def test_in_linea_se_il_lavoro_restante_sta_nella_giornata(self):
        lines = lines_of(focus=focus([item(1, "Uno", 60), item(2, "Due", 30, done=True)]))
        self.assertIn("Main task di oggi · 1/2 fatti | size=12", lines)
        self.assertIn("In linea: 60′ di lavoro, 210′ alla fine della giornata | color=#49f07c", lines)

    def test_sotto_se_il_lavoro_non_sta_nella_giornata(self):
        lines = lines_of(focus=focus([item(1, "Uno", 240)]))
        self.assertIn("In ritardo di 30′: 240′ di lavoro, 210′ alla fine della giornata | color=#ffb84a", lines)

    def test_voce_da_fare_ha_le_durate_del_countdown(self):
        lines = lines_of(focus=focus([item(7, "Preparare demo", 45, frog=True)]))
        self.assertIn("◆ Preparare demo · 45′ | color=#ff5ef0", lines)
        self.assertIn("--▶ Avvia countdown 45′ (stima) | shell=/bin/harlock-bar param1=focus param2=start "
                      "param3=7 param4=-m param5=45 terminal=false refresh=true", lines)
        self.assertIn("--▶ 15′ | shell=/bin/harlock-bar param1=focus param2=start param3=7 param4=-m param5=15 "
                      "terminal=false refresh=true", lines)
        self.assertIn("--✓ Segna fatto | shell=/bin/harlock-bar param1=focus param2=done param3=7 "
                      "terminal=false refresh=true", lines)

    def test_box_attivo_mostra_i_comandi_del_countdown(self):
        box = {"itemId": 1, "text": "Uno", "remaining": 300, "phase": "warn", "extended": False}
        lines = lines_of(focus=focus([item(1, "Uno")], box=box))
        self.assertIn("⏱ 5′ rimasti · Uno | color=#ffb84a", lines)
        self.assertIn("--+10′ (una volta sola) | shell=/bin/harlock-bar param1=focus param2=extend "
                      "terminal=false refresh=true", lines)
        # Con un box attivo non se ne avvia un altro.
        self.assertFalse(any("Avvia countdown" in line for line in lines))

    def test_voce_fatta_attenuata(self):
        lines = lines_of(focus=focus([item(1, "Uno", done=True)]))
        self.assertIn("✓ Uno | color=#7d8799", lines)


class TicketTest(unittest.TestCase):
    def two_epics(self):
        b = board([ticket("OPS-3", "Tre", {"state": "open", "status": "busy"}),
                   ticket("OPS-4", "Quattro", category="new"),
                   ticket("OPS-5", "Cinque", {"state": "open", "status": "waiting"}, next_step="provare | il fix"),
                   ticket("OPS-7", "Sette")],
                  [ticket("OPS-6", "Sei")])
        b["epics"].append({"key": "OPS-2", "summary": "Epica due", "items": [ticket("OPS-8", "Otto")]})
        return b

    def test_in_alto_solo_i_ticket_con_sessione_aperta_prima_quelli_in_attesa(self):
        lines = lines_of(board=self.two_epics())
        top = [l for l in lines if l.startswith(("⏸ OPS", "▶ OPS", "⚠ OPS"))]
        self.assertEqual([l.split(" ")[1] for l in top], ["OPS-5", "OPS-3"])
        self.assertIn("--La sessione Claude ti sta aspettando | color=#ffb84a", lines)
        self.assertIn("--Prossimo passo: provare ¦ il fix | size=12", lines)
        self.assertIn("--Riprendi la sessione | shell=/bin/harlock-bar param1=start param2=OPS-5 "
                      "terminal=false", lines)

    def test_una_riga_per_epica_con_colore_diverso_e_ticket_nel_sottomenu(self):
        lines = lines_of(board=self.two_epics())
        epics = [l for l in lines if l.startswith("● ")]
        self.assertEqual([l.split(" | ")[0] for l in epics], ["● Epica uno · 3", "● Epica due · 1", "● Senza epica · 1"])
        colors = [l.split("color=")[1] for l in epics]
        self.assertEqual(len(set(colors)), 3)
        self.assertIn("--OPS-7 Sette | color=%s" % colors[0], lines)
        self.assertIn("----Apri su Jira | href=https://jira.example/browse/OPS-7", lines)
        # I ticket non in lavorazione non compaiono.
        self.assertFalse(any("OPS-4" in l for l in lines))

    def test_ticket_attivo_con_il_colore_della_sua_epica(self):
        lines = lines_of(board=self.two_epics())
        epic_color = [l for l in lines if l.startswith("● Epica uno")][0].split("color=")[1]
        self.assertIn("▶ OPS-3 Tre | color=%s" % epic_color, lines)

    def test_senza_board(self):
        self.assertIn("Ticket: dati non ancora disponibili | color=#7d8799", lines_of(board=None))


class DeadlineTest(unittest.TestCase):
    def test_scadenze_in_una_riga_con_il_dettaglio_nel_sottomenu(self):
        deadlines = [{"source": "jira", "key": "OPS-9", "title": "Nove", "url": "https://j/OPS-9", "days": -3},
                     {"source": "local", "key": None, "title": "Locale", "url": None, "days": 0}]
        lines = lines_of(focus=focus(deadlines=deadlines))
        self.assertIn("Scadenze · 2, 1 scadute | color=#ff6b5e", lines)
        self.assertIn("--OPS-9 Nove · scaduta da 3 g | href=https://j/OPS-9 color=#ff6b5e", lines)
        self.assertIn("--Locale · oggi | color=#ffb84a", lines)


if __name__ == "__main__":
    unittest.main()
