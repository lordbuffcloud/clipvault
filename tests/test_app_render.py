import unittest

from clipvault.app import BRAND, COW_LOGO_LINES, HEADER_HEIGHT, TAGLINE, render_snapshot_ui


class AppRenderTests(unittest.TestCase):
    def test_snapshot_ui_contains_ck42x_brand_and_core_panels(self):
        snapshot = render_snapshot_ui(width=96)

        self.assertIn(BRAND, snapshot)
        for line in COW_LOGO_LINES:
            self.assertIn(line, snapshot)
        self.assertGreaterEqual(HEADER_HEIGHT, 6)
        self.assertIn(TAGLINE, snapshot)
        self.assertIn("HISTORY BUFFER", snapshot)
        self.assertIn("OPS", snapshot)
        self.assertIn("STATUS", snapshot)
        self.assertIn("q quit", snapshot)

    def test_cli_parser_supports_daemon_flags(self):
        from clipvault.app import build_parser

        args = build_parser().parse_args(["--daemon", "--once", "--interval", "0.2"])

        self.assertTrue(args.daemon)
        self.assertTrue(args.once)
        self.assertEqual(args.interval, 0.2)

    def test_snapshot_ui_respects_requested_width(self):
        snapshot = render_snapshot_ui(width=80)

        self.assertTrue(all(len(line) <= 80 for line in snapshot.splitlines()))


if __name__ == "__main__":
    unittest.main()
