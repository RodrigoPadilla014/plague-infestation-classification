import unittest

import pandas as pd

from config import RunConfig
from data import validate_dataset


def config():
    return RunConfig(
        stage="diagnostics",
        dataset="unused.csv",
        output_dir="out",
        model_dir="model",
        train_periods=["2019", "2020"],
        evaluation_periods=["2021"],
        categorical_columns=["category"],
        min_train_periods=1,
    )


class ValidationTests(unittest.TestCase):
    def test_rejects_duplicate_prediction_rows(self):
        df = pd.DataFrame(
            {
                "record_id": ["a", "a", "b"],
                "zafra": ["2019", "2020", "2021"],
                "target": [0, 1, 0],
                "category": ["x", "y", "z"],
            }
        )
        with self.assertRaisesRegex(ValueError, "uniquely identify"):
            validate_dataset(df, config())

    def test_accepts_binary_dataset(self):
        df = pd.DataFrame(
            {
                "record_id": ["a", "b", "c"],
                "zafra": ["2019", "2020", "2021"],
                "target": [0, 1, 0],
                "category": ["x", "y", "z"],
            }
        )
        self.assertEqual(len(validate_dataset(df, config())), 3)


if __name__ == "__main__":
    unittest.main()

