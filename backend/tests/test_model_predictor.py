from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from services import model_predictor


SAMPLE_PARAMS = {
    "horizontal_depth": 500,
    "shading_type": 2,
    "material": 1,
    "spacing": 600,
    "h_rotation": 40,
    "v_rotation": -80,
    "blade_depth": 100,
    "window_distance": 100,
    "wwr": 40,
    "glass_type": 4,
}


class ConstantModel:
    def __init__(self, value: float):
        self.value = value
        self.inputs = None

    def predict(self, inputs):
        self.inputs = inputs
        return np.full(len(inputs), self.value)


class ModelPredictorTests(unittest.TestCase):
    def test_type_fix_feature_interface_and_unit_conversion(self):
        design = model_predictor._to_model_params(SAMPLE_PARAMS)
        row = model_predictor._build_feature_row(design)

        self.assertEqual(len(row), 22)
        self.assertEqual(row[:7], [5.0, 6.0, 1.0, 1.0, 4.0, 0.0, -8.0])
        self.assertAlmostEqual(row[7], 1.71)
        self.assertAlmostEqual(row[8], 0.0684)
        self.assertEqual(row[9:12], [-32.0, 24.0, 1.25])
        self.assertEqual(row[12:], [0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0])

    def test_energy_prediction_feeds_both_lifecycle_calculations(self):
        energy_model = ConstantModel(150.0)
        sda_model = ConstantModel(65.0)
        with patch.object(model_predictor, "_load_models", return_value=(energy_model, sda_model)):
            performance = model_predictor.predict_performance(SAMPLE_PARAMS, "南")

        self.assertEqual(performance, {"lcce": 2819.31, "lcc": 6703.48, "sda": 65.0})
        np.testing.assert_allclose(energy_model.inputs, sda_model.inputs)

    def test_batch_prediction_preserves_input_order(self):
        energy_model = ConstantModel(150.0)
        sda_model = ConstantModel(65.0)
        second = SAMPLE_PARAMS | {"wwr": 60}
        with patch.object(model_predictor, "_load_models", return_value=(energy_model, sda_model)):
            results = model_predictor.predict_performance_many([SAMPLE_PARAMS, second])

        self.assertEqual(len(results), 2)
        self.assertLess(results[0]["lcc"], results[1]["lcc"])
        self.assertEqual(energy_model.inputs.shape, (2, 22))


if __name__ == "__main__":
    unittest.main()
