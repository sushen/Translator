import subprocess
import sys
import unittest
from pathlib import Path


class TestProviderLoading(unittest.TestCase):
    def test_cloud_startup_and_model_discovery_do_not_import_torch(self):
        code = (
            "import sys; from app.translation import BaseTranslator, ModelManager; "
            "from app.translation.openai_translator import OpenAITranslator; "
            "assert 'torch' not in sys.modules"
        )
        result = subprocess.run([sys.executable, "-c", code],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
