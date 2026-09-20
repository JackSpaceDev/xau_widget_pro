from __future__ import annotations

import unittest

from main import WIN_H, WIN_W, center_in_bar, in_taskbar_y


class TaskbarPosTests(unittest.TestCase):
    def test_bottom_bar_centers_horizontally_and_vertically(self):
        x, y = center_in_bar((0, 1032, 1920, 1080), win_w=108, win_h=34)
        self.assertEqual(x, (1920 - 108) // 2)
        self.assertEqual(y, 1039)
        self.assertTrue(in_taskbar_y(y, (0, 1032, 1920, 1080), win_h=34))

    def test_window_above_bar_is_not_in_taskbar(self):
        self.assertFalse(in_taskbar_y(1000, (0, 1032, 1920, 1080), win_h=34))

    def test_side_bar_centers_horizontally(self):
        x, y = center_in_bar((0, 0, 48, 1080))
        self.assertEqual(x, 0)
        self.assertEqual(y, 1080 - WIN_H - 8)


if __name__ == "__main__":
    unittest.main()
