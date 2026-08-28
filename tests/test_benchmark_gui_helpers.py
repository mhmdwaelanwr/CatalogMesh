import unittest

from ai_product_photo_sorter.benchmark_gui import _format_elapsed, _result_summary


class BenchmarkGuiHelperTests(unittest.TestCase):
    def test_elapsed_format_keeps_hours(self):
        self.assertEqual("01:01:01", _format_elapsed(3661.9))

    def test_failed_benchmark_is_not_presented_as_success(self):
        summary = _result_summary(
            {
                "return_code": 2,
                "photos_completed": 0,
                "photos_selected": 50,
                "logical_provider_calls": 0,
                "wall_seconds": 0.957,
            }
        )
        self.assertIn("failed before useful measurement", summary)
        self.assertIn("0/50 photos", summary)
        self.assertIn("0 provider calls", summary)

    def test_success_summary_includes_time_throughput_and_calls(self):
        summary = _result_summary(
            {
                "return_code": 0,
                "photos_completed": 50,
                "photos_selected": 50,
                "logical_provider_calls": 9,
                "wall_seconds": 125.4,
                "photos_per_second": 0.3987,
                "seconds_per_photo": 2.508,
            }
        )
        self.assertIn("Completed", summary)
        self.assertIn("00:02:05", summary)
        self.assertIn("0.3987 photos/s", summary)
        self.assertIn("2.508 s/photo", summary)
        self.assertIn("9 provider calls", summary)


if __name__ == "__main__":
    unittest.main()
