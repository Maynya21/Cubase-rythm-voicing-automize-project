"""설치 마법사 테스트.

선물로 줄 물건이라 **기존 설정을 절대 망가뜨리지 않는 것** 이 가장 중요합니다.
그 부분을 집중적으로 확인합니다.
"""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cubase_mcp.setup_wizard import SERVER_KEY, claude_config_path, server_entry
from cubase_mcp.setup_wizard import install as _install
from cubase_mcp.setup_wizard import remove as _remove


def install(*args, **kwargs):
    """마법사는 사람이 읽을 안내를 출력합니다. 테스트에서는 조용히 실행합니다."""
    with contextlib.redirect_stdout(io.StringIO()):
        return _install(*args, **kwargs)


def remove(*args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return _remove(*args, **kwargs)

EXISTING = {
    "mcpServers": {
        "filesystem": {"command": "npx",
                       "args": ["-y", "@modelcontextprotocol/server-filesystem",
                                "C:\\Users\\me"]},
        "github": {"command": "npx", "args": ["-y", "server-github"]},
    },
    "globalShortcut": "Ctrl+Space",
    "한글키": "한글 값",
}


class TestSetupWizard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wizard-test-"))
        self.config = self.tmp / "claude_desktop_config.json"
        self.out = self.tmp / "out"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def read(self):
        return json.loads(self.config.read_text(encoding="utf-8"))

    def write(self, data):
        self.config.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def backups(self):
        return list(self.tmp.glob("*.backup-*"))

    # ---- 새로 설치 -------------------------------------------------------
    def test_creates_config_when_missing(self):
        self.assertEqual(install(self.config, self.out), 0)
        self.assertEqual(list(self.read()["mcpServers"]), [SERVER_KEY])

    def test_creates_output_folder_and_test_file(self):
        install(self.config, self.out)
        self.assertTrue(self.out.is_dir())
        self.assertTrue(list(self.out.glob("*.mid")))

    def test_entry_points_at_this_interpreter(self):
        entry = server_entry(self.out)
        self.assertEqual(entry["args"], ["-m", "cubase_mcp.server"])
        self.assertEqual(entry["env"]["CUBASE_MCP_OUTPUT_DIR"], str(self.out))

    # ---- 기존 설정 보존 ---------------------------------------------------
    def test_keeps_other_servers_and_top_level_keys(self):
        self.write(EXISTING)
        self.assertEqual(install(self.config, self.out), 0)
        data = self.read()
        self.assertEqual(set(data["mcpServers"]),
                         {"filesystem", "github", SERVER_KEY})
        self.assertEqual(data["mcpServers"]["filesystem"]["args"][2], "C:\\Users\\me")
        self.assertEqual(data["globalShortcut"], "Ctrl+Space")
        self.assertEqual(data["한글키"], "한글 값")

    def test_makes_a_backup_before_writing(self):
        self.write(EXISTING)
        install(self.config, self.out)
        self.assertEqual(len(self.backups()), 1)
        self.assertEqual(json.loads(self.backups()[0].read_text(encoding="utf-8")),
                         EXISTING)

    def test_running_twice_is_idempotent(self):
        self.write(EXISTING)
        install(self.config, self.out)
        first = self.read()
        install(self.config, self.out)
        self.assertEqual(self.read(), first)

    def test_handles_utf8_bom(self):
        self.config.write_text("\ufeff" + json.dumps(EXISTING, ensure_ascii=False),
                               encoding="utf-8")
        self.assertEqual(install(self.config, self.out), 0)
        self.assertIn("github", self.read()["mcpServers"])

    def test_handles_empty_file(self):
        self.config.write_text("", encoding="utf-8")
        self.assertEqual(install(self.config, self.out), 0)
        self.assertIn(SERVER_KEY, self.read()["mcpServers"])

    # ---- 망가진 설정은 건드리지 않음 ---------------------------------------
    def test_refuses_to_touch_invalid_json(self):
        broken = '{ "mcpServers": { "x": }'
        self.config.write_text(broken, encoding="utf-8")
        self.assertEqual(install(self.config, self.out), 1)
        self.assertEqual(self.config.read_text(encoding="utf-8"), broken)
        self.assertEqual(self.backups(), [], "실패했는데 백업을 만들면 안 됩니다")

    def test_refuses_when_mcp_servers_is_not_an_object(self):
        self.write({"mcpServers": ["oops"]})
        self.assertEqual(install(self.config, self.out), 1)
        self.assertEqual(self.read()["mcpServers"], ["oops"])

    def test_refuses_when_root_is_not_an_object(self):
        self.config.write_text('["not", "an", "object"]', encoding="utf-8")
        self.assertEqual(install(self.config, self.out), 1)

    # ---- 미리보기 / 해제 ---------------------------------------------------
    def test_dry_run_changes_nothing(self):
        self.write(EXISTING)
        self.assertEqual(install(self.config, self.out, dry_run=True), 0)
        self.assertEqual(self.read(), EXISTING)
        self.assertEqual(self.backups(), [])

    def test_remove_only_deletes_our_entry(self):
        self.write(EXISTING)
        install(self.config, self.out)
        self.assertEqual(remove(self.config), 0)
        self.assertEqual(set(self.read()["mcpServers"]), {"filesystem", "github"})
        self.assertEqual(self.read()["한글키"], "한글 값")

    def test_remove_is_safe_when_not_installed(self):
        self.write(EXISTING)
        self.assertEqual(remove(self.config), 0)
        self.assertEqual(self.read(), EXISTING)

    # ---- 경로 ------------------------------------------------------------
    def test_config_path_is_platform_appropriate(self):
        path = claude_config_path()
        self.assertEqual(path.name, "claude_desktop_config.json")
        self.assertIn("Claude", path.parts)


if __name__ == "__main__":
    unittest.main()
