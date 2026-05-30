import curses
import unittest

from clipvault.app import collect_pending_keys


class InputDrainTests(unittest.TestCase):
    def test_collect_pending_keys_drains_burst_after_first_key(self):
        screen = FakeScreen([curses.KEY_DOWN, curses.KEY_DOWN, ord("j"), -1])

        keys = collect_pending_keys(screen, curses.KEY_DOWN)

        self.assertEqual(keys, [curses.KEY_DOWN, curses.KEY_DOWN, curses.KEY_DOWN, ord("j")])

    def test_collect_pending_keys_stops_at_frame_limit(self):
        screen = FakeScreen([ord("j")] * 100)

        keys = collect_pending_keys(screen, ord("j"), max_keys=8)

        self.assertEqual(keys, [ord("j")] * 8)


class FakeScreen:
    def __init__(self, keys):
        self.keys = list(keys)

    def getch(self):
        if self.keys:
            return self.keys.pop(0)
        return -1


if __name__ == "__main__":
    unittest.main()
