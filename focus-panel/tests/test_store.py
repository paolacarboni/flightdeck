from focus_panel import store
from tests.helpers import NOW, TempHomeCase

DAY = 24 * 3600


class AddTest(TempHomeCase):
    def test_add_today_assigns_ids_and_day(self):
        state = store.load(NOW)
        first = store.add(state, "Scrivere indice slide", 45, "oggi", now=NOW)
        second = store.add(state, "Rispondere a review", 30, "domani", now=NOW)
        parked = store.add(state, "Leggere paper", 60, "dopo", now=NOW)
        self.assertEqual((first["id"], second["id"]), (1, 2))
        self.assertEqual(first["day"], "2026-10-17")
        self.assertEqual(second["day"], "2026-10-18")
        self.assertIsNone(parked["day"])

    def test_fourth_item_on_same_day_is_refused(self):
        state = store.load(NOW)
        for n in range(3):
            store.add(state, "Voce %d" % n, 15, "oggi", now=NOW)
        with self.assertRaises(store.FocusError):
            store.add(state, "Voce in più", 15, "oggi", now=NOW)
        store.add(state, "In parcheggio", 15, "dopo", now=NOW)

    def test_minutes_and_text_are_validated(self):
        state = store.load(NOW)
        for text, minutes in (("", 30), ("Fare", 0), ("Fare", 241)):
            with self.assertRaises(store.FocusError):
                store.add(state, text, minutes, "oggi", now=NOW)

    def test_due_date_is_validated(self):
        state = store.load(NOW)
        item = store.add(state, "Consegnare HLD", 60, "dopo", due="2026-10-20", now=NOW)
        self.assertEqual(item["due"], "2026-10-20")
        with self.assertRaises(store.FocusError):
            store.add(state, "Consegnare HLD", 60, "dopo", due="20/10", now=NOW)

    def test_state_survives_save_and_load(self):
        state = store.load(NOW)
        store.add(state, "Scrivere indice", 45, "oggi", now=NOW)
        store.save(state)
        self.assertEqual(store.load(NOW)["items"][0]["text"], "Scrivere indice")


class FrogTest(TempHomeCase):
    def test_one_frog_per_day(self):
        state = store.load(NOW)
        a = store.add(state, "A", 30, "oggi", frog=True, now=NOW)
        b = store.add(state, "B", 30, "oggi", now=NOW)
        tomorrow = store.add(state, "C", 30, "domani", frog=True, now=NOW)
        store.set_frog(state, b["id"], now=NOW)
        self.assertFalse(a["frog"])
        self.assertTrue(b["frog"])
        self.assertTrue(tomorrow["frog"])

    def test_parked_item_cannot_be_frog(self):
        state = store.load(NOW)
        item = store.add(state, "A", 30, "dopo", now=NOW)
        with self.assertRaises(store.FocusError):
            store.set_frog(state, item["id"], now=NOW)

    def test_move_to_parking_drops_frog_and_respects_limit(self):
        state = store.load(NOW)
        item = store.add(state, "A", 30, "oggi", frog=True, now=NOW)
        store.move(state, item["id"], "dopo", now=NOW)
        self.assertIsNone(item["day"])
        self.assertFalse(item["frog"])
        for n in range(3):
            store.add(state, "D%d" % n, 15, "domani", now=NOW)
        with self.assertRaises(store.FocusError):
            store.move(state, item["id"], "domani", now=NOW)

    def test_unknown_id(self):
        with self.assertRaises(store.FocusError):
            store.drop(store.load(NOW), 99)


class RolloverTest(TempHomeCase):
    def test_unfinished_past_items_go_to_parking(self):
        state = store.load(NOW - DAY)
        late = store.add(state, "Non fatta", 30, "oggi", frog=True, now=NOW - DAY)
        finished = store.add(state, "Fatta", 30, "oggi", now=NOW - DAY)
        finished["doneAt"] = NOW - DAY
        store.save(state)
        items = {i["text"]: i for i in store.load(NOW)["items"]}
        self.assertIsNone(items["Non fatta"]["day"])
        self.assertFalse(items["Non fatta"]["frog"])
        self.assertEqual(items["Fatta"]["day"], "2026-10-16")
        self.assertEqual(late["id"], 1)
