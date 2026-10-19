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
