import unittest

import pandas as pd

from calibration import temporal_postprocessing_split


class TemporalCalibrationTests(unittest.TestCase):
    def test_uses_earlier_periods_for_calibration_and_latest_for_threshold(self):
        oof = pd.DataFrame(
            {
                "zafra": ["2020", "2021", "2022"],
                "actual_target": [0, 1, 0],
                "predicted_probability": [0.2, 0.7, 0.4],
            }
        )
        split = temporal_postprocessing_split(
            oof, "zafra", ["2020", "2021", "2022"], "sigmoid"
        )
        self.assertEqual(split.calibration_periods, ("2020", "2021"))
        self.assertEqual(split.threshold_period, "2022")

    def test_rejects_calibration_with_only_one_oof_period(self):
        oof = pd.DataFrame(
            {
                "zafra": ["2022"],
                "actual_target": [1],
                "predicted_probability": [0.7],
            }
        )
        with self.assertRaisesRegex(ValueError, "at least two OOF"):
            temporal_postprocessing_split(oof, "zafra", ["2022"], "isotonic")

    def test_allows_no_calibration_with_one_oof_period(self):
        oof = pd.DataFrame(
            {
                "zafra": ["2022"],
                "actual_target": [1],
                "predicted_probability": [0.7],
            }
        )
        split = temporal_postprocessing_split(oof, "zafra", ["2022"], "none")
        self.assertEqual(split.calibration_periods, ())
        self.assertEqual(split.threshold_period, "2022")


if __name__ == "__main__":
    unittest.main()
