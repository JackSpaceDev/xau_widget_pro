from __future__ import annotations

import unittest
from unittest.mock import patch

from price_feed import Feed, Quote, mark_mt5_gone


class FeedFallbackTests(unittest.TestCase):
    def test_no_mt5_process_uses_web(self):
        feed = Feed()
        feed.mt5_ok = True
        feed._jin10 = None
        web = Quote(price=2610.25, source="TV", symbol="XAUUSD")
        with patch("price_feed.mt5_running", return_value=False), patch.object(
            feed, "_fetch_web_cached", return_value=web
        ):
            quote = feed.fetch()
        self.assertEqual(quote.source, "TV")
        self.assertEqual(quote.price, 2610.25)
        self.assertFalse(feed.mt5_ok)

    def test_web_fail_keeps_last_quote(self):
        feed = Feed()
        feed._jin10 = None
        feed._last_quote = Quote(price=2601.5, source="MT5", symbol="XAUUSDm")
        with patch("price_feed.mt5_running", return_value=False), patch.object(
            feed, "_fetch_web_cached", side_effect=RuntimeError("down")
        ):
            quote = feed.fetch()
        self.assertEqual(quote.price, 2601.5)
        self.assertEqual(quote.source, "MT5")

    def test_mark_mt5_gone_clears_cache(self):
        mark_mt5_gone()
        with patch("price_feed._scan_terminal", return_value=True) as scan:
            from price_feed import mt5_running

            self.assertFalse(mt5_running())
            self.assertFalse(scan.called)
            self.assertTrue(mt5_running(force=True))
            self.assertTrue(scan.called)


if __name__ == "__main__":
    unittest.main()
