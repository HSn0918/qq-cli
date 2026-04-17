from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from qq_cli.core.context import AppContext


class AppContextModesTest(unittest.TestCase):
    def test_explicit_decrypted_dir_works_without_detectable_raw_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decrypted_dir = root / "decrypted"
            decrypted_dir.mkdir()

            conn = sqlite3.connect(decrypted_dir / "nt_msg.db")
            conn.execute('CREATE TABLE recent_contact_v3_table ("40050" INTEGER)')
            conn.commit()
            conn.close()

            config_path = root / "config.json"
            config_path.write_text(json.dumps({"db_dir": "/nonexistent/raw"}, ensure_ascii=False), encoding="utf-8")

            app = AppContext(str(config_path), decrypted_dir=str(decrypted_dir))
            try:
                self.assertEqual(app.mode, "decrypted")
                self.assertEqual(app.db_dir, str(decrypted_dir))
                self.assertEqual(app.db_files["nt_msg"], str(decrypted_dir / "nt_msg.db"))
            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()
