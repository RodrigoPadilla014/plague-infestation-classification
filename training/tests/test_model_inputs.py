import unittest

import numpy as np
import pandas as pd

from feature_schema import FeatureSchema
from model_inputs import MISSING_CATEGORY, prepare_model_inputs


class ModelInputTests(unittest.TestCase):
    def test_native_category_alignment(self):
        schema = FeatureSchema(
            feature_columns=["numeric", "category"],
            categorical_columns=["category"],
            numeric_columns=["numeric"],
            metadata_columns=[],
            excluded_columns=[],
        )
        train = pd.DataFrame({"numeric": [1, np.inf], "category": ["A", None]})
        validation = pd.DataFrame({"numeric": [2], "category": ["B"]})
        prepared = prepare_model_inputs(train, validation, schema, "xgboost")
        self.assertIsInstance(prepared.train["category"].dtype, pd.CategoricalDtype)
        self.assertEqual(
            list(prepared.train["category"].cat.categories),
            list(prepared.validation["category"].cat.categories),
        )
        self.assertIn(MISSING_CATEGORY, prepared.train["category"].cat.categories)
        self.assertTrue(pd.isna(prepared.train.loc[1, "numeric"]))


if __name__ == "__main__":
    unittest.main()
