"""The point map's view fitting and scale bar (no Tk)."""

import unittest

from ui.core.pointmap import fit_view, nice_length

BED = (235.0, 235.0)


class FitViewTest(unittest.TestCase):
    def assert_inside_with_margin(self, view, points, margin_px):
        for x, y in points:
            px, py = view.to_px(x, y)
            self.assertGreaterEqual(px, margin_px)
            self.assertLessEqual(px, view.width - margin_px)
            self.assertGreaterEqual(py, margin_px)
            self.assertLessEqual(py, view.height - margin_px)

    def test_fits_points_with_margin(self):
        points = [(130, 140), (150, 140), (150, 150), (130, 150)]
        view = fit_view(points, 400, 300, BED)
        self.assert_inside_with_margin(view, points, 10)
        # Zoomed in: the view is a few times the points' extent, not the bed.
        self.assertLess(view.span[0], 60)
        # Same scale on both axes, +X right, +Y up.
        (ax, ay), (bx, by) = view.to_px(130, 140), view.to_px(150, 160)
        self.assertAlmostEqual(bx - ax, ay - by)
        self.assertGreater(bx, ax)
        self.assertLess(by, ay)

    def test_inverted_axes(self):
        points = [(130, 140), (150, 160)]
        view = fit_view(points, 400, 300, BED, invert_x=True, invert_y=True)
        self.assert_inside_with_margin(view, points, 10)
        (ax, ay), (bx, by) = view.to_px(130, 140), view.to_px(150, 160)
        self.assertLess(bx, ax)
        self.assertGreater(by, ay)

    def test_wide_row_fits_width(self):
        points = [(10, 100), (200, 100)]
        view = fit_view(points, 400, 300, BED)
        self.assert_inside_with_margin(view, points, 10)
        self.assertLess(view.span[0], 260)

    def test_single_point_uses_min_span(self):
        view = fit_view([(100, 100)], 400, 300, BED, min_span=10)
        self.assertEqual(view.to_px(100, 100), (200, 150))
        self.assertGreater(min(view.span), 10)
        self.assertLess(min(view.span), 20)

    def test_no_points_shows_the_bed(self):
        view = fit_view([], 400, 300, BED)
        self.assert_inside_with_margin(view, [(0, 0), BED], 1)

    def test_contains(self):
        view = fit_view([(100, 100)], 400, 300, BED)
        self.assertTrue(view.contains(101, 101))
        self.assertFalse(view.contains(0, 0))


class NiceLengthTest(unittest.TestCase):
    def test_values(self):
        for limit, expected in ((7, 5), (5, 5), (4.9, 2), (1.5, 1), (63, 50), (0.3, 0.2), (250, 200)):
            self.assertAlmostEqual(nice_length(limit), expected, msg=limit)

    def test_degenerate(self):
        self.assertEqual(nice_length(0), 0)
        self.assertEqual(nice_length(float("inf")), 0)


if __name__ == "__main__":
    unittest.main()
