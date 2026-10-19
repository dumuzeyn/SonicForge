import unittest

from ui.windowing import centered_outer_position


class CenteredOuterPositionTests(unittest.TestCase):
    def test_common_primary_monitor_work_areas(self):
        cases = (
            ((0, 0, 1920, 1032), (910, 699)),
            ((0, 0, 2560, 1392), (910, 699)),
            ((0, 0, 1366, 728), (910, 699)),
        )
        for work_area, outer_size in cases:
            with self.subTest(work_area=work_area):
                x, y = centered_outer_position(work_area, outer_size)
                window_center = (x + outer_size[0] / 2, y + outer_size[1] / 2)
                work_center = (
                    (work_area[0] + work_area[2]) / 2,
                    (work_area[1] + work_area[3]) / 2,
                )
                self.assertLessEqual(abs(window_center[0] - work_center[0]), 0.5)
                self.assertLessEqual(abs(window_center[1] - work_center[1]), 0.5)

    def test_negative_monitor_coordinates(self):
        work_area = (-1920, 0, 0, 1032)
        outer_size = (910, 699)
        self.assertEqual(centered_outer_position(work_area, outer_size), (-1415, 166))


if __name__ == "__main__":
    unittest.main()
