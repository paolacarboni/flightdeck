import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from unittest import mock

from focus_panel import cli, store, view
from tests.helpers import NOW, TempHomeCase

EVENING = datetime(2026, 10, 17, 18, 0).timestamp()


class ViewTest(TempHomeCase):
    def test_frog_first_in_the_morning(self):
        state = store.load(NOW)
        store.add(state, "Rispondere mail", 15, "oggi", now=NOW)
        store.add(state, "Scrivere indice", 45, "oggi", frog=True, now=NOW)
        store.add(state, "Leggere paper", 30, "dopo", now=NOW)
        store.start(state, 1, 25, now=NOW)
        store.save(state)
        data = view.show(NOW + 60)
        self.assertEqual([i["text"] for i in data["today"]], ["Scrivere indice", "Rispondere mail"])
        self.assertTrue(data["frogFirst"])
        self.assertFalse(data["planMode"])
        self.assertEqual(data["box"]["text"], "Rispondere mail")
        self.assertEqual(data["box"]["phase"], "run")
        self.assertEqual(len(data["parked"]), 1)
        self.assertFalse(view.show(datetime(2026, 10, 17, 12, 30).timestamp())["frogFirst"])

    def test_evening_plan_mode_until_tomorrow_has_a_frog(self):
        data = view.show(EVENING)
        self.assertTrue(data["planMode"])
        self.assertFalse(data["tomorrowFrog"])
        state = store.load(EVENING)
        store.add(state, "Preparare demo", 60, "domani", frog=True, now=EVENING)
        store.save(state)
        data = view.show(EVENING)
        self.assertTrue(data["tomorrowFrog"])
        self.assertEqual(data["tomorrow"][0]["text"], "Preparare demo")

    def test_done_items_go_last_and_are_counted(self):
        state = store.load(NOW)
        store.add(state, "A", 15, "oggi", frog=True, now=NOW)
        store.add(state, "B", 15, "oggi", now=NOW)
        store.done(state, 1, now=NOW)
        store.save(state)
        data = view.show(NOW)
        self.assertEqual([i["text"] for i in data["today"]], ["B", "A"])
        self.assertEqual(data["doneToday"], 1)
        self.assertFalse(data["frogFirst"])


class CliTest(TempHomeCase):
    def run_cli(self, *args, now=NOW):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("focus_panel.cli._now", return_value=now), redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_add_start_done_round_trip(self):
        self.assertEqual(self.run_cli("add", "Scrivere", "indice", "-m", "45", "--frog")[0], 0)
        self.assertEqual(self.run_cli("start", "1", "-m", "25")[0], 0)
        self.assertEqual(self.run_cli("extend")[0], 0)
        code, out, _ = self.run_cli("done")
        self.assertEqual(code, 0)
        self.assertIn("Scrivere indice", out)
        data = json.loads(self.run_cli("show")[1])
        self.assertEqual(data["today"][0]["doneAt"], NOW)
        self.assertEqual(data["overToday"], 1)

    def test_errors_go_to_stderr_with_exit_one(self):
        code, _, err = self.run_cli("stop")
        self.assertEqual(code, 1)
        self.assertIn("Nessun box", err)

    def test_move_frog_drop(self):
        self.run_cli("add", "A", "-m", "15", "--when", "dopo", "--due", "2026-10-20")
        self.assertEqual(self.run_cli("move", "1", "domani")[0], 0)
        self.assertEqual(self.run_cli("frog", "1")[0], 0)
        data = json.loads(self.run_cli("show")[1])
        self.assertTrue(data["tomorrow"][0]["frog"])
        self.assertEqual(data["deadlines"][0]["days"], 3)
        self.assertEqual(self.run_cli("drop", "1")[0], 0)
        self.assertEqual(json.loads(self.run_cli("show")[1])["tomorrow"], [])
