from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qq_cli.core.live import LiveDBFiles


class LiveDBFilesTest(unittest.TestCase):
    @patch("qq_cli.core.live.require_sqlcipher", return_value="/opt/homebrew/bin/sqlcipher")
    @patch("qq_cli.core.live.decrypt_db_dir")
    def test_materializes_once_and_caches(self, mock_decrypt, _mock_sqlcipher):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "nt_db"
            raw_dir.mkdir()
            (raw_dir / "nt_msg.db").write_bytes(b"SQLite header 3\x00" + b"\x00" * 64)

            def fake_decrypt(db_dir: str, out_dir: str, key: str, names=None):
                out_path = Path(out_dir) / "nt_msg.db"
                out_path.write_text("plaintext", encoding="utf-8")
                return {
                    "db_dir": db_dir,
                    "out_dir": out_dir,
                    "decrypted": [{"name": "nt_msg", "source": str(Path(db_dir) / "nt_msg.db"), "output": str(out_path)}],
                    "failures": [],
                }

            mock_decrypt.side_effect = fake_decrypt

            live_files = LiveDBFiles(str(raw_dir), "secret")
            try:
                first = live_files["nt_msg"]
                second = live_files["nt_msg"]
            finally:
                live_files.close()

            self.assertEqual(first, second)
            self.assertEqual(mock_decrypt.call_count, 1)

    @patch("qq_cli.core.live.require_sqlcipher", return_value="/opt/homebrew/bin/sqlcipher")
    @patch("qq_cli.core.live.decrypt_db_dir")
    def test_reports_decrypt_failure(self, mock_decrypt, _mock_sqlcipher):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "nt_db"
            raw_dir.mkdir()
            (raw_dir / "nt_msg.db").write_bytes(b"SQLite header 3\x00" + b"\x00" * 64)
            mock_decrypt.return_value = {
                "db_dir": str(raw_dir),
                "out_dir": str(raw_dir),
                "decrypted": [],
                "failures": [{"name": "nt_msg", "source": str(raw_dir / "nt_msg.db"), "error": "database disk image is malformed"}],
            }

            live_files = LiveDBFiles(str(raw_dir), "secret")
            try:
                with self.assertRaises(RuntimeError) as ctx:
                    _ = live_files["nt_msg"]
            finally:
                live_files.close()

            self.assertIn("live 模式解密 nt_msg 失败", str(ctx.exception))
            self.assertIn("database disk image is malformed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
