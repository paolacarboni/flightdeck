import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harlock_bar import cli


class TempHomeCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        patcher = mock.patch.dict(os.environ, {"HARLOCK_BAR_HOME": str(self.home / "bar"),
                                               "HARLOCK_BAR_BOARD": str(self.home / "board.json")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        # Nessun test deve mostrare notifiche o avviare processi veri.
        self.notify = mock.patch("harlock_bar.cli.notify").start()
        self.spawn = mock.patch("harlock_bar.cli.spawn").start()
        self.addCleanup(mock.patch.stopall)


class BoxAlertTest(TempHomeCase):
    def box(self, phase, start=100.0):
        return {"box": {"itemId": 1, "start": start, "text": "Scrivere", "remaining": -10 if phase == "over" else 200,
                        "phase": phase}}

    def test_avvisa_una_sola_volta_a_fine_box(self):
        cli.alert_box(self.box("over"))
        cli.alert_box(self.box("over"))
        self.assertEqual(self.notify.call_count, 1)
        self.assertIn("Tempo scaduto", self.notify.call_args[0][0])

    def test_avvisa_cinque_minuti_prima_e_poi_alla_fine(self):
        cli.alert_box(self.box("warn"))
        cli.alert_box(self.box("over"))
        self.assertEqual(self.notify.call_count, 2)

    def test_box_nuovo_avvisa_di_nuovo(self):
        cli.alert_box(self.box("over", start=100.0))
        cli.alert_box(self.box("over", start=200.0))
        self.assertEqual(self.notify.call_count, 2)

    def test_nessun_box_nessun_avviso(self):
        cli.alert_box({"box": None})
        cli.alert_box(None)
        self.notify.assert_not_called()


class BoardTest(TempHomeCase):
    def write_board(self, updated):
        Path(os.environ["HARLOCK_BAR_BOARD"]).write_text(json.dumps({"updatedAt": updated}), encoding="utf-8")

    def test_board_recente_non_si_aggiorna(self):
        self.write_board(1000.0)
        self.assertEqual(cli.load_board(now=1000.0 + 60)["updatedAt"], 1000.0)
        self.spawn.assert_not_called()

    def test_board_vecchia_si_aggiorna_in_background_una_volta(self):
        self.write_board(1000.0)
        later = 1000.0 + cli.BOARD_MAX_AGE + 1
        cli.load_board(now=later)
        cli.load_board(now=later + 30)
        self.assertEqual(self.spawn.call_count, 1)

    def test_board_illeggibile_usa_l_ultima_copia_buona(self):
        # cc-panel riscrive board.json sul posto: durante la scrittura il file è vuoto o a metà.
        self.write_board(1000.0)
        cli.load_board(now=1000.0 + 60)
        Path(os.environ["HARLOCK_BAR_BOARD"]).write_text('{"updat', encoding="utf-8")
        self.assertEqual(cli.load_board(now=1000.0 + 90)["updatedAt"], 1000.0)

    def test_board_mancante(self):
        self.assertIsNone(cli.load_board(now=1000.0))
        self.spawn.assert_called_once()

    def test_aggiornamento_in_background_annota_l_esito(self):
        # Il processo staccato è `harlock-bar sync`, non cc-panel: così l'errore Jira resta nello stato.
        cli.load_board(now=1000.0)
        self.assertEqual(self.spawn.call_args[0][0][1:], ["sync"])


class SyncTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.refresh = mock.patch("harlock_bar.cli.refresh_xbar").start()

    def model(self, error=None):
        ticket = {"key": "OPS-1", "statusCategory": "indeterminate"}
        model = {"updatedAt": 1000, "epics": [{"key": "OPS-0", "items": [ticket, dict(ticket, key="OPS-2")]}],
                 "noEpic": []}
        if error:
            model.update(error=error, stale=True)
        return json.dumps(model)

    def test_aggiorna_aspetta_jira_avvisa_e_ridisegna_il_menu(self):
        with mock.patch("harlock_bar.cli.run", return_value=(0, self.model(), "")) as run:
            self.assertEqual(cli.main(["board"]), 0)
        self.assertEqual(run.call_args[0][0][1:], ["board", "--json"])
        self.spawn.assert_not_called()
        self.notify.assert_called_once_with("Ticket aggiornati da Jira: 2 in lavorazione")
        self.refresh.assert_called_once()
        self.assertIsNone(cli.load_state().get("boardError"))

    def test_errore_jira_notificato_e_conservato_per_il_menu(self):
        with mock.patch("harlock_bar.cli.run", return_value=(0, self.model("token scaduto o non valido"), "")):
            self.assertEqual(cli.main(["board"]), 1)
        self.notify.assert_called_once_with("Jira non aggiornato: token scaduto o non valido")
        self.refresh.assert_called_once()
        self.assertEqual(cli.load_state()["boardError"], "token scaduto o non valido")

    def test_cc_panel_che_non_risponde(self):
        with mock.patch("harlock_bar.cli.run", return_value=(1, "", "Traceback\nOSError: boom")):
            self.assertEqual(cli.main(["sync"]), 1)
        self.assertEqual(cli.load_state()["boardError"], "OSError: boom")
        self.notify.assert_not_called()

    def test_lettura_riuscita_cancella_l_errore_precedente(self):
        cli.save_state({"boardError": "vecchio"})
        with mock.patch("harlock_bar.cli.run", return_value=(0, self.model(), "")):
            self.assertEqual(cli.main(["sync"]), 0)
        self.assertIsNone(cli.load_state()["boardError"])
        self.refresh.assert_called_once()


class ActionTest(TempHomeCase):
    def test_azione_focus_riuscita(self):
        with mock.patch("harlock_bar.cli.run", return_value=(0, "Box di 30′: Scrivere", "")) as run:
            self.assertEqual(cli.main(["focus", "start", "3", "-m", "30"]), 0)
        self.assertEqual(run.call_args[0][0][1:], ["start", "3", "-m", "30"])
        self.notify.assert_called_once_with("Box di 30′: Scrivere")

    def test_azione_focus_fallita_mostra_l_errore(self):
        with mock.patch("harlock_bar.cli.run", return_value=(1, "", "C'è già un box attivo")):
            self.assertEqual(cli.main(["focus", "start", "3"]), 1)
        self.notify.assert_called_once_with("C'è già un box attivo")

    def test_chiave_non_valida_non_avvia_nulla(self):
        self.assertEqual(cli.main(["start", "rm -rf"]), 1)
        self.spawn.assert_not_called()

    def test_aggiungi_chiede_testo_e_durata(self):
        with mock.patch("harlock_bar.cli.ask", side_effect=["Preparare demo", "45"]), \
                mock.patch("harlock_bar.cli.run", return_value=(0, "Aggiunta 4: Preparare demo", "")) as run:
            self.assertEqual(cli.main(["add", "domani"]), 0)
        self.assertEqual(run.call_args[0][0][1:], ["add", "Preparare", "demo", "-m", "45", "--when", "domani"])

    def test_aggiungi_annullato(self):
        with mock.patch("harlock_bar.cli.ask", return_value=None), mock.patch("harlock_bar.cli.run") as run:
            self.assertEqual(cli.main(["add", "oggi"]), 0)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
