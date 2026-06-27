from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from routers import lab


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_new_user_gets_default_lab(self):
        result = lab.get_lab(user_id="lab-user-a")

        self.assertEqual(result["params"], lab.LAB_DEFAULT_PARAMS)
        self.assertIsNone(result["performance"])
        self.assertIn("lcce", result["reference_ranges"])

    @patch("routers.lab.predict_performance", return_value={"lcce": 2800.0, "lcc": 6700.0, "sda": 78.0})
    def test_evaluate_persists_only_current_user_lab(self, _predict):
        result = lab.evaluate_lab(
            lab.LabEvaluateRequest(params=lab.LabParams()),
            user_id="lab-user-a",
        )

        self.assertEqual(result["evaluations"]["overall"]["grade"], "优")
        saved = lab.get_lab(user_id="lab-user-a")
        other = lab.get_lab(user_id="lab-user-b")
        self.assertEqual(saved["performance"]["sda"], 78.0)
        self.assertIsNone(other["performance"])


if __name__ == "__main__":
    unittest.main()
