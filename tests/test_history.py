import tempfile
import unittest
from pathlib import Path

from clipvault.history import ClipboardHistory


class ClipboardHistoryTests(unittest.TestCase):
    def test_add_ignores_empty_and_whitespace_text(self):
        history = ClipboardHistory(max_items=5)

        self.assertIsNone(history.add(""))
        self.assertIsNone(history.add("   \n\t  "))

        self.assertEqual(history.items, [])

    def test_add_puts_new_text_at_top_with_preview_fields(self):
        history = ClipboardHistory(max_items=5)

        item = history.add("first copied value")

        self.assertIsNotNone(item)
        self.assertEqual(history.items[0].text, "first copied value")
        self.assertFalse(history.items[0].pinned)
        self.assertTrue(history.items[0].id)
        self.assertTrue(history.items[0].created_at)
        self.assertTrue(history.items[0].updated_at)

    def test_duplicate_text_moves_existing_item_to_top_without_duplication(self):
        history = ClipboardHistory(max_items=5)
        first = history.add("alpha")
        history.add("bravo")

        duplicate = history.add("alpha")

        self.assertEqual(duplicate.id, first.id)
        self.assertEqual([item.text for item in history.items], ["alpha", "bravo"])
        self.assertEqual(len(history.items), 2)

    def test_max_items_prunes_oldest_unpinned_entries_but_keeps_pinned(self):
        history = ClipboardHistory(max_items=3)
        alpha = history.add("alpha")
        history.pin(alpha.id, True)
        history.add("bravo")
        history.add("charlie")
        history.add("delta")

        texts = [item.text for item in history.items]
        self.assertEqual(len(texts), 3)
        self.assertIn("alpha", texts)
        self.assertIn("delta", texts)
        self.assertNotIn("bravo", texts)

    def test_search_matches_text_case_insensitively_and_keeps_order(self):
        history = ClipboardHistory(max_items=5)
        history.add("Alpha token")
        history.add("bravo")
        history.add("another ALPHA value")

        results = history.search("alpha")

        self.assertEqual([item.text for item in results], ["another ALPHA value", "Alpha token"])

    def test_delete_pin_and_clear_unpinned(self):
        history = ClipboardHistory(max_items=5)
        keep = history.add("keep")
        remove = history.add("remove")

        self.assertTrue(history.pin(keep.id, True))
        self.assertTrue(history.delete(remove.id))
        self.assertFalse(history.delete("missing"))
        history.add("temporary")
        history.clear(include_pinned=False)

        self.assertEqual([item.text for item in history.items], ["keep"])
        self.assertTrue(history.items[0].pinned)

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            history = ClipboardHistory(path=path, max_items=5)
            pinned = history.add("persistent secret-free note")
            history.pin(pinned.id, True)
            history.add("second")
            history.save()

            loaded = ClipboardHistory.load(path=path, max_items=5)

            self.assertEqual([item.text for item in loaded.items], ["second", "persistent secret-free note"])
            self.assertFalse(loaded.items[0].pinned)
            self.assertTrue(loaded.items[1].pinned)


if __name__ == "__main__":
    unittest.main()
