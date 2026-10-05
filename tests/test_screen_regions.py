import unittest

from parser.screen_regions import _contiguous_groups, align_batter_layout, load_batter_layout


class ScreenRegionTests(unittest.TestCase):
    def test_vertical_separator_fragments_are_merged_when_allowed(self) -> None:
        import numpy as np

        fragments = np.array([431, 432, 434, 435, 436, 437, 526, 527])

        self.assertEqual(_contiguous_groups(fragments), [(431, 432), (434, 437), (526, 527)])
        self.assertEqual(_contiguous_groups(fragments, max_gap=4), [(431, 437), (526, 527)])

    def test_batter_layout_keeps_calibrated_cell_interior_with_blue_headers(self) -> None:
        import numpy as np

        layout = load_batter_layout()
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        x = 300
        for width in (210,) + (90,) * 13:
            image[220:329, x:x + width] = (230, 135, 55)
            x += width + 8

        aligned = align_batter_layout(image, layout)

        self.assertEqual(aligned.first_row_y, layout.first_row_y)
        self.assertEqual(aligned.row_height, layout.row_height)
        self.assertEqual(aligned.row_stride, layout.row_stride)
        self.assertEqual(aligned.columns["name"], layout.columns["name"])
