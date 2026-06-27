from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from services import image_client


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b'{"output":{"task_id":"task-123"}}'


class ImageClientTests(unittest.TestCase):
    @patch("services.image_client.urllib.request.urlopen", return_value=_FakeResponse())
    @patch("services.image_client.dashscope_image_model", return_value="wanx2.1-t2i-turbo")
    def test_wanxiang_v2_uses_text_to_image_contract(self, _model, urlopen):
        result = image_client._submit_text_to_image_task("test-key", "facade prompt")

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertTrue(request.full_url.endswith("/services/aigc/text2image/image-synthesis"))
        self.assertEqual(payload["input"]["prompt"], "facade prompt")
        self.assertIn("negative_prompt", payload["input"])
        self.assertNotIn("messages", payload["input"])
        self.assertEqual(payload["parameters"]["size"], "1024*1024")
        self.assertEqual(result["output"]["task_id"], "task-123")


if __name__ == "__main__":
    unittest.main()
