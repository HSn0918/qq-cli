from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from click.testing import CliRunner

from qq_cli.main import cli


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            return bytes(out)


def _field_varint(number: int, value: int) -> bytes:
    return _varint((number << 3) | 0) + _varint(value)


def _field_bytes(number: int, payload: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(payload)) + payload


def _field_str(number: int, value: str) -> bytes:
    return _field_bytes(number, value.encode("utf-8"))


def _message_blob(text: str | None = None, file_name: str | None = None, file_path: str | None = None) -> bytes:
    inner = bytearray()
    inner += _field_varint(45002, 1 if text else 3)
    if text:
        inner += _field_str(45101, text)
    if file_name:
        inner += _field_str(45402, file_name)
    if file_path:
        inner += _field_str(45403, file_path)
    return _field_bytes(48000, bytes(inner))


class QQCliSmokeTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.db_dir = self.root / "nt_db"
        self.db_dir.mkdir()
        self.config = self.root / "config.json"
        self.config.write_text(json.dumps({"db_dir": str(self.db_dir)}, ensure_ascii=False), encoding="utf-8")
        self._build_profile_db()
        self._build_group_db()
        self._build_nt_msg_db()
        self._build_files_db()
        self._build_rich_media_db()
        self._build_collection_db()
        self._build_emoji_db()
        self.runner = CliRunner()

    def tearDown(self):
        self.tmpdir.cleanup()

    @contextmanager
    def _connect(self, name: str):
        conn = sqlite3.connect(self.db_dir / name)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _build_profile_db(self):
        with self._connect("profile_info.db") as conn:
            conn.execute('CREATE TABLE buddy_list ("1000" TEXT, "1001" TEXT, "1002" INTEGER, "25007" INTEGER)')
            conn.execute(
                'CREATE TABLE profile_info_v6 ("1000" TEXT, "1001" TEXT, "1002" INTEGER, "20002" TEXT, "20009" TEXT, "20011" TEXT, "20004" TEXT, "20072" BLOB)'
            )
            conn.execute('INSERT INTO buddy_list VALUES ("u_100", "alice_qid", 10001, 0)')
            conn.execute(
                'INSERT INTO profile_info_v6 VALUES ("u_100", "alice_qid", 10001, "Alice", "Alice Remark", "hello", "https://img", X\'C2E60900\')'
            )

    def _build_group_db(self):
        with self._connect("group_info.db") as conn:
            conn.execute('CREATE TABLE group_list ("60001" INTEGER, "60007" TEXT)')
            conn.execute(
                'CREATE TABLE group_detail_info_ver1 ("60001" INTEGER, "60007" TEXT, "60026" TEXT, "60002" TEXT, "60004" INTEGER, "60005" INTEGER, "60006" INTEGER, "60340" INTEGER)'
            )
            conn.execute(
                'CREATE TABLE group_member3 ("60001" INTEGER, "1000" TEXT, "1002" INTEGER, "20002" TEXT, "64003" TEXT, "64010" INTEGER, "64016" INTEGER, "64023" TEXT, "64007" INTEGER)'
            )
            conn.execute('INSERT INTO group_list VALUES (8888, "AI Group")')
            conn.execute('INSERT INTO group_detail_info_ver1 VALUES (8888, "AI Group", "AI Team", "owner_uid", 1710000000, 500, 2, 0)')
            conn.execute('INSERT INTO group_member3 VALUES (8888, "u_100", 10001, "Alice", "Alice In Group", 1, 0, "Admin", 1710000001)')
            conn.execute('INSERT INTO group_member3 VALUES (8888, "u_200", 10002, "Bob", "Bob In Group", 0, 0, "", 1710000002)')

    def _build_nt_msg_db(self):
        with self._connect("nt_msg.db") as conn:
            conn.execute(
                'CREATE TABLE recent_contact_v3_table ("40010" INTEGER, "40021" TEXT, "40030" INTEGER, "40050" INTEGER, "40051" BLOB, "40093" TEXT, "40090" TEXT, "40095" TEXT, "40020" TEXT, "40033" INTEGER, "41135" TEXT, "41110" TEXT)'
            )
            conn.execute(
                'CREATE TABLE c2c_msg_table ("40001" INTEGER, "40002" INTEGER, "40003" INTEGER, "40011" INTEGER, "40012" INTEGER, "40013" INTEGER, "40020" TEXT, "40021" TEXT, "40030" INTEGER, "40033" INTEGER, "40050" INTEGER, "40090" TEXT, "40093" TEXT, "40800" BLOB)'
            )
            conn.execute(
                'CREATE TABLE group_msg_table ("40001" INTEGER, "40002" INTEGER, "40003" INTEGER, "40011" INTEGER, "40012" INTEGER, "40013" INTEGER, "40020" TEXT, "40021" TEXT, "40030" INTEGER, "40033" INTEGER, "40050" INTEGER, "40090" TEXT, "40093" TEXT, "40800" BLOB)'
            )
            conn.execute(
                'INSERT INTO recent_contact_v3_table VALUES (1, "u_100", 10001, 1710000100, ?, "Alice", "", "Alice Remark", "u_100", 10001, "", "")',
                (_message_blob(text="hello from alice"),),
            )
            conn.execute(
                'INSERT INTO recent_contact_v3_table VALUES (2, "8888", 8888, 1710000200, ?, "Bob", "Bob In Group", "", "u_200", 10002, "AI Team", "/tmp/group.png")',
                (_message_blob(text="group hello"),),
            )
            conn.execute(
                'INSERT INTO c2c_msg_table VALUES (1, 2, 3, 2, 0, 0, "u_100", "u_100", 10001, 10001, 1710000100, "", "Alice", ?)',
                (_message_blob(text="hello from alice"),),
            )
            conn.execute(
                'INSERT INTO group_msg_table VALUES (2, 5, 6, 3, 0, 0, "u_200", "8888", 8888, 10002, 1710000200, "Bob In Group", "Bob", ?)',
                (_message_blob(file_name="report.pdf", file_path="/tmp/report.pdf"),),
            )

    def _build_files_db(self):
        with self._connect("files_in_chat.db") as conn:
            conn.execute(
                'CREATE TABLE files_in_chat_table ("45001" INTEGER, "82300" INTEGER, "40001" INTEGER, "45403" TEXT, "45404" TEXT, "40020" TEXT, "40021" TEXT, "40010" INTEGER, "82301" INTEGER, "45002" INTEGER, "45003" INTEGER, "45402" TEXT, "45405" INTEGER, "40050" INTEGER, "82302" INTEGER)'
            )
            conn.execute(
                'INSERT INTO files_in_chat_table VALUES (10, 5, 2, "", "/tmp/report-thumb.png", "u_200", "8888", 2, 0, 3, 0, "report.pdf", 2048, 1710000200, 1)'
            )

    def _build_rich_media_db(self):
        with self._connect("rich_media.db") as conn:
            conn.execute(
                'CREATE TABLE file_table ("45401" INTEGER, "40001" INTEGER, "45001" INTEGER, "45402" TEXT, "45403" TEXT, "45405" INTEGER, "45985" INTEGER, "45503" TEXT, "40021" TEXT, "64914" INTEGER)'
            )
            conn.execute(
                'INSERT INTO file_table VALUES (0, 2, 10, "report.pdf", "/tmp/report.pdf", 2048, 0, "uuid-1", "8888", 0)'
            )

    def _build_collection_db(self):
        with self._connect("collection.db") as conn:
            conn.execute(
                'CREATE TABLE collection_list_info_table ("180001" TEXT, "180008" INTEGER, "180009" INTEGER, "180011" INTEGER, "180004" BLOB, "180015" BLOB)'
            )
            source = _field_varint(18504, 8888) + _field_str(18505, "AI Team") + _field_str(18506, "u_100") + _field_varint(18501, 10001) + _field_str(180503, "Alice Remark")
            summary = _field_str(181450, "收藏标题") + _field_str(181452, "收藏摘要") + _field_str(180610, "/tmp/note.md")
            conn.execute(
                'INSERT INTO collection_list_info_table VALUES ("sid-1", 1, 1710000000, 1710000300, ?, ?)',
                (source, summary),
            )

    def _build_emoji_db(self):
        with self._connect("emoji.db") as conn:
            conn.execute(
                'CREATE TABLE fav_emoji_info_storage_table ("80001" INTEGER, "80002" TEXT, "1002" INTEGER, "80010" TEXT, "80011" TEXT, "80012" TEXT, "80213" INTEGER, "80201" TEXT, "80202" INTEGER, "80223" TEXT, "80225" TEXT)'
            )
            conn.execute(
                'CREATE TABLE base_sys_emoji_table ("81211" TEXT, "81212" TEXT, "81226" INTEGER, "81221" INTEGER, "81229" TEXT, "81230" TEXT)'
            )
            conn.execute(
                'INSERT INTO fav_emoji_info_storage_table VALUES (0, "10001_0_0_0_MD5_0_0", 10001, "https://download", "ABCDEF", "/tmp/emoji.png", 0, "", 0, "备注", "")'
            )
            conn.execute(
                'INSERT INTO base_sys_emoji_table VALUES ("1", "[微笑]", 1, 0, "https://static", "https://apng")'
            )

    def _run_json(self, *args):
        result = self.runner.invoke(cli, ["--config", str(self.config), *args])
        self.assertEqual(result.exit_code, 0, msg=result.output)
        return json.loads(result.output)

    def test_contacts_sessions_history_files_collections_and_emojis(self):
        contacts = self._run_json("contacts")
        self.assertEqual(contacts[0]["display_name"], "Alice Remark")

        groups = self._run_json("contacts", "--groups")
        self.assertEqual(groups[0]["display_name"], "AI Team")

        sessions = self._run_json("sessions", "--limit", "2")
        self.assertEqual(sessions[0]["chat_name"], "AI Team")
        self.assertEqual(sessions[1]["chat_name"], "Alice Remark")

        history = self._run_json("history", "Alice", "--limit", "10")
        self.assertEqual(history["messages"][0]["text"], "hello from alice")

        members = self._run_json("members", "AI Team")
        self.assertEqual(members["count"], 2)

        files = self._run_json("files", "--chat", "AI Team")
        self.assertEqual(files[0]["file_path"], "/tmp/report.pdf")

        collections = self._run_json("collections")
        self.assertEqual(collections[0]["title"], "收藏标题")

        emojis = self._run_json("emojis")
        self.assertEqual(emojis[0]["local_path"], "/tmp/emoji.png")

        system_emojis = self._run_json("emojis", "--system")
        self.assertEqual(system_emojis[0]["description"], "[微笑]")


if __name__ == "__main__":
    unittest.main()
