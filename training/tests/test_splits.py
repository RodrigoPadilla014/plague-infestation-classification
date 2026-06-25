import unittest

import pandas as pd

from splits import walk_forward_splits


class WalkForwardTests(unittest.TestCase):
    def test_expanding_windows(self):
        periods = pd.Series(["2019", "2019", "2020", "2021", "2022"])
        folds = walk_forward_splits(
            periods,
            ["2019", "2020", "2021", "2022"],
            min_train_periods=1,
        )
        self.assertEqual(len(folds), 3)
        self.assertEqual(folds[0].train_periods, ("2019",))
        self.assertEqual(folds[0].validation_period, "2020")
        self.assertEqual(folds[-1].train_periods, ("2019", "2020", "2021"))
        self.assertEqual(folds[-1].validation_period, "2022")


if __name__ == "__main__":
    unittest.main()

