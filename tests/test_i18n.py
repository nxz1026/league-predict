"""Tests for i18n team-name translation (P6)."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import core.i18n as i18n
from core.i18n import to_cn, warm_translations


class TestI18N(unittest.TestCase):
    def setUp(self):
        # 用临时缓存文件，避免污染仓库 references/
        self._tmp = tempfile.TemporaryDirectory()
        self._cache_file = Path(self._tmp.name) / "team_translations.json"
        self._orig_file = i18n.TRANSLATION_CACHE_FILE
        i18n.TRANSLATION_CACHE_FILE = self._cache_file
        i18n._CACHE = None

    def tearDown(self):
        i18n.TRANSLATION_CACHE_FILE = self._orig_file
        i18n._CACHE = None
        self._tmp.cleanup()

    def test_country_still_mapped(self):
        # 国名走 COUNTRY_CN，不依赖 LLM
        self.assertEqual(to_cn("England"), "英格兰")

    def test_unknown_without_cache_returns_original(self):
        self.assertEqual(to_cn("SomeUnknownFC"), "SomeUnknownFC")

    def test_warm_translates_and_persists(self):
        fake = {"Arsenal": "阿森纳", "Manchester City": "曼城"}
        with patch("ai.llm_client.generate", return_value={"translations": fake}):
            warm_translations(["Arsenal", "Manchester City"])
        self.assertEqual(to_cn("Arsenal"), "阿森纳")
        self.assertEqual(to_cn("Manchester City"), "曼城")
        # 已持久化到缓存文件
        self.assertTrue(self._cache_file.exists())
        import json
        data = json.loads(self._cache_file.read_text(encoding="utf-8"))
        self.assertEqual(data["Arsenal"], "阿森纳")

    def test_warm_skips_already_cached(self):
        # 第一次预热写入
        with patch("ai.llm_client.generate", return_value={"translations": {"Chelsea": "切尔西"}}):
            warm_translations(["Chelsea"])
        # 仅传已缓存项时不应再调用 LLM
        with patch("ai.llm_client.generate") as mock_gen:
            warm_translations(["Chelsea"])
        mock_gen.assert_not_called()
        self.assertEqual(to_cn("Chelsea"), "切尔西")


if __name__ == "__main__":
    unittest.main()
