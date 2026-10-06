import unittest

from parser.screen_regions import _contiguous_groups, align_batter_layout, align_pitcher_layout, load_batter_layout, load_pitcher_layout


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

    def test_pitcher_uses_blue_headers_only_after_a_material_horizontal_shift(self) -> None:
        import numpy as np

        layout = load_pitcher_layout()
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        header_blue = (230, 135, 55)
        widths = [213, 131, 130, 82, 81, 81, 82, 82, 82, 82, 82]
        x = 308  # 45px right of the calibrated name-cell origin.
        for width in widths:
            image[235:344, x:x + width] = header_blue
            x += width + 8
        image[352:410, 240:296] = header_blue

        aligned = align_pitcher_layout(image, layout)

        self.assertEqual((aligned.first_row_y, aligned.row_height), (352, 58))
        self.assertEqual((aligned.columns["decision"].x, aligned.columns["decision"].width), (240, 56))
        self.assertEqual((aligned.columns["name"].x, aligned.columns["name"].width), (308, 213))
        self.assertEqual((aligned.columns["innings"].x, aligned.columns["innings"].width), (529, 131))

    def test_shifted_pitcher_rows_follow_their_actual_grid_separators(self) -> None:
        import numpy as np

        layout = load_pitcher_layout()
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        header_blue = (230, 135, 55)
        x = 308
        for width in [213, 131, 130, 82, 81, 81, 82, 82, 82, 82, 82]:
            image[235:344, x:x + width] = header_blue
            x += width + 8
        image[352:410, 240:296] = header_blue
        for start, end in ((345, 355), (408, 415), (469, 475), (529, 535), (589, 592)):
            image[start:end + 1, 529:1520] = 255

        aligned = align_pitcher_layout(image, layout)

        self.assertEqual(aligned.row_bounds, ((356, 52), (416, 53), (476, 53), (536, 53)))
        self.assertEqual((aligned.first_row_y, aligned.row_height, aligned.row_stride), (356, 53, 60))

    def test_pitcher_keeps_calibrated_layout_when_blue_headers_are_in_place(self) -> None:
        import numpy as np

        layout = load_pitcher_layout()
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        header_blue = (230, 135, 55)
        x = layout.columns["name"].x
        for width in (234, 141, 140, 88, 88, 88, 88, 88, 88, 88, 88):
            image[220:329, x:x + width] = header_blue
            x += width + 8

        aligned = align_pitcher_layout(image, layout)

        self.assertEqual(aligned.first_row_y, layout.first_row_y)
        self.assertEqual(aligned.row_height, layout.row_height)
        self.assertEqual(aligned.row_stride, layout.row_stride)
        self.assertEqual(aligned.columns, layout.columns)
