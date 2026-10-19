from focus_panel import store
from tests.helpers import NOW, TempHomeCase

MIN = 60


class BoxTest(TempHomeCase):
    def setUp(self):
        super().setUp()
        self.state = store.load(NOW)
        self.item = store.add(self.state, "Scrivere indice", 45, "oggi", now=NOW)

    def test_start_uses_item_minutes_by_default(self):
        box = store.start(self.state, self.item["id"], now=NOW)
        self.assertEqual(box["minutes"], 45)
        status = store.box_status(self.state, NOW + 10 * MIN)
        self.assertEqual(status["phase"], "run")
        self.assertEqual(status["end"], NOW + 45 * MIN)
        self.assertEqual(status["remaining"], 35 * MIN)

    def test_last_five_minutes_warn_then_over(self):
        store.start(self.state, self.item["id"], 25, now=NOW)
        self.assertEqual(store.box_status(self.state, NOW + 21 * MIN)["phase"], "warn")
        self.assertEqual(store.box_status(self.state, NOW + 26 * MIN)["phase"], "over")

    def test_only_one_box_and_one_extension(self):
        other = store.add(self.state, "Altro", 15, "oggi", now=NOW)
        store.start(self.state, self.item["id"], 25, now=NOW)
        with self.assertRaises(store.FocusError):
            store.start(self.state, other["id"], now=NOW)
        store.extend(self.state, now=NOW)
        self.assertEqual(store.box_status(self.state, NOW)["end"], NOW + 35 * MIN)
        with self.assertRaises(store.FocusError):
            store.extend(self.state, now=NOW)

    def test_done_inside_the_box_is_on_time(self):
        store.start(self.state, self.item["id"], 25, now=NOW)
        store.done(self.state, now=NOW + 20 * MIN)
        self.assertIsNone(self.state["box"])
        self.assertEqual(self.item["doneAt"], NOW + 20 * MIN)
        self.assertEqual(store.over_today(self.state, NOW + 20 * MIN), 0)

    def test_late_or_extended_box_counts_as_over(self):
        store.start(self.state, self.item["id"], 25, now=NOW)
        store.stop(self.state, now=NOW + 30 * MIN)
        self.assertIsNone(self.item["doneAt"])
        other = store.add(self.state, "Altro", 15, "oggi", now=NOW)
        store.start(self.state, other["id"], 15, now=NOW + 40 * MIN)
        store.extend(self.state, now=NOW + 50 * MIN)
        store.done(self.state, now=NOW + 60 * MIN)
        self.assertEqual(store.over_today(self.state, NOW + 60 * MIN), 2)
        self.assertEqual(store.over_today(self.state, NOW + 24 * 3600), 0)

    def test_done_by_id_closes_its_box(self):
        store.start(self.state, self.item["id"], 25, now=NOW)
        store.done(self.state, self.item["id"], now=NOW + MIN)
        self.assertIsNone(self.state["box"])

    def test_cannot_box_done_or_parked_items(self):
        parked = store.add(self.state, "Dopo", 15, "dopo", now=NOW)
        with self.assertRaises(store.FocusError):
            store.start(self.state, parked["id"], now=NOW)
        store.done(self.state, self.item["id"], now=NOW)
        with self.assertRaises(store.FocusError):
            store.start(self.state, self.item["id"], now=NOW)

    def test_stop_without_box(self):
        with self.assertRaises(store.FocusError):
            store.stop(self.state, now=NOW)

    def test_dropping_boxed_item_closes_box(self):
        store.start(self.state, self.item["id"], 25, now=NOW)
        store.drop(self.state, self.item["id"])
        self.assertIsNone(self.state["box"])
