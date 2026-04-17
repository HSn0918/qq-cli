"""Message, session and attachment decoding."""

from __future__ import annotations

from datetime import datetime

from .contacts import ChatTarget
from .db import connect, quote_ident, table_columns, table_exists
from .protobuf import (
    collect_strings,
    field_first_int,
    field_first_string,
    field_ints,
    walk_messages,
)

CHAT_TYPE_NAMES = {
    1: "c2c",
    2: "group",
    4: "channel",
    100: "temp",
    102: "enterprise",
    103: "official",
}

MSG_TYPE_NAMES = {
    0: "unknown",
    1: "blank",
    2: "text",
    3: "file",
    5: "image",
    6: "voice",
    7: "video",
    8: "system",
    9: "reply",
    10: "card",
    11: "emoji",
    16: "xml",
}


def format_timestamp(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _shorten(text: str, limit: int = 140) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _human_size(value: int | None) -> str:
    if not value:
        return ""
    units = ["B", "KB", "MB", "GB"]
    size = float(value)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)}{units[index]}"
    return f"{size:.1f}{units[index]}"


def _render_element(message) -> tuple[str | None, dict | None]:
    fields = message.fields
    element_type = field_first_int(fields, 45002)
    file_name = field_first_string(fields, 45402)
    file_path = field_first_string(fields, 45403)
    thumb_path = field_first_string(fields, 45954) or field_first_string(fields, 45422)
    size = field_first_int(fields, 45405)
    text = field_first_string(fields, 45101)
    transcript = field_first_string(fields, 45923) or field_first_string(fields, 45102)
    face_text = field_first_string(fields, 47602)
    reply_text = field_first_string(fields, 47413)
    reply_name = field_first_string(fields, 47421)
    xml_text = field_first_string(fields, 48602) or field_first_string(fields, 47901)

    attachment = None
    if file_name or file_path or thumb_path:
        attachment = {
            "element_type": element_type,
            "file_name": file_name,
            "file_path": file_path,
            "thumb_path": thumb_path,
            "size": size,
            "size_text": _human_size(size),
        }

    if element_type == 1:
        return text, attachment
    if element_type == 2:
        label = "[图片]"
        if file_path:
            label += f" {file_path}"
        return label, attachment
    if element_type == 3:
        label = "[文件]"
        if file_name:
            label += f" {file_name}"
        if size:
            label += f" ({_human_size(size)})"
        return label, attachment
    if element_type == 4:
        label = "[语音]"
        if transcript:
            label += f" {transcript}"
        return label, attachment
    if element_type == 5:
        label = "[视频]"
        if file_name:
            label += f" {file_name}"
        elif file_path:
            label += f" {file_path}"
        return label, attachment
    if element_type == 6:
        return face_text or "[表情]", attachment
    if element_type == 7:
        if reply_text and reply_name:
            return f"[引用] {reply_name}: {reply_text}", attachment
        if reply_text:
            return f"[引用] {reply_text}", attachment
        return "[引用]", attachment
    if element_type == 8:
        return text or field_first_string(fields, 47713) or "[系统消息]", attachment
    if element_type in (10, 16):
        return f"[卡片] {_shorten(xml_text)}" if xml_text else "[卡片]", attachment
    if element_type == 11:
        return face_text or "[商城表情]", attachment
    if text:
        return text, attachment
    if xml_text:
        return f"[消息] {_shorten(xml_text)}", attachment
    return None, attachment


def decode_message_blob(blob: bytes | None) -> dict:
    if not blob:
        return {"text": "", "attachments": [], "element_types": []}

    rendered_parts: list[str] = []
    attachments: list[dict] = []
    element_types: list[int] = []
    for message in walk_messages(blob):
        element_type = field_first_int(message.fields, 45002)
        if element_type is None:
            continue
        element_types.append(element_type)
        text, attachment = _render_element(message)
        if text:
            rendered_parts.append(text)
        if attachment:
            attachments.append(attachment)

    if not rendered_parts:
        fallback_fields = {45101, 45102, 45402, 45403, 45923, 47413, 47602, 47901, 48602}
        rendered_parts = collect_strings(blob, interesting_fields=fallback_fields)

    rendered_parts = _dedupe_keep_order(rendered_parts)
    text = " ".join(rendered_parts) if rendered_parts else ""
    if not text and blob:
        text = f"[binary:{len(blob)}B]"

    return {
        "text": _shorten(text, limit=500),
        "attachments": attachments,
        "element_types": _dedupe_keep_order([str(v) for v in element_types]),
    }


def _buddy_lookup(buddies: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_uid = {str(item["nt_uid"]): item for item in buddies if item.get("nt_uid")}
    by_uin = {str(item["uin"]): item for item in buddies if item.get("uin") is not None}
    return by_uid, by_uin


def _group_lookup(groups: list[dict]) -> dict[str, dict]:
    return {str(item["group_uin"]): item for item in groups if item.get("group_uin") is not None}


def resolve_chat_name(
    chat_type: int | None,
    peer_uid,
    peer_uin,
    fallback_name,
    buddies: list[dict],
    groups: list[dict],
) -> str:
    by_uid, by_uin = _buddy_lookup(buddies)
    by_group = _group_lookup(groups)
    if chat_type == 2 and peer_uin is not None:
        group = by_group.get(str(peer_uin))
        if group:
            return group["display_name"]
    if chat_type != 2:
        buddy = by_uid.get(str(peer_uid)) if peer_uid else None
        if buddy is None and peer_uin is not None:
            buddy = by_uin.get(str(peer_uin))
        if buddy:
            return buddy["display_name"]
    return fallback_name or str(peer_uin or peer_uid or "")


def resolve_sender_name(sender_uid, sender_uin, nickname, member_name, buddies: list[dict]) -> str:
    by_uid, by_uin = _buddy_lookup(buddies)
    buddy = by_uid.get(str(sender_uid)) if sender_uid else None
    if buddy is None and sender_uin is not None:
        buddy = by_uin.get(str(sender_uin))
    if buddy:
        return buddy["display_name"]
    return member_name or nickname or str(sender_uin or sender_uid or "")


def load_recent_sessions(db_files: dict[str, str], buddies: list[dict], groups: list[dict], limit: int) -> list[dict]:
    path = db_files["nt_msg"]
    with connect(path) as conn:
        if not table_exists(conn, "recent_contact_v3_table"):
            return []
        cols = table_columns(conn, "recent_contact_v3_table")
        select_parts = [
            f'{quote_ident("40010")} AS chat_type' if "40010" in cols else "NULL AS chat_type",
            f'{quote_ident("40021")} AS peer_uid' if "40021" in cols else "NULL AS peer_uid",
            f'{quote_ident("40030")} AS peer_uin' if "40030" in cols else "NULL AS peer_uin",
            f'{quote_ident("40050")} AS last_time' if "40050" in cols else "NULL AS last_time",
            f'{quote_ident("40051")} AS last_message_blob' if "40051" in cols else "NULL AS last_message_blob",
            f'{quote_ident("40093")} AS send_nickname' if "40093" in cols else "NULL AS send_nickname",
            f'{quote_ident("40090")} AS send_member_name' if "40090" in cols else "NULL AS send_member_name",
            f'{quote_ident("40095")} AS remark_name' if "40095" in cols else "NULL AS remark_name",
            f'{quote_ident("40020")} AS sender_uid' if "40020" in cols else "NULL AS sender_uid",
            f'{quote_ident("40033")} AS sender_uin' if "40033" in cols else "NULL AS sender_uin",
            f'{quote_ident("41135")} AS group_name' if "41135" in cols else "NULL AS group_name",
            f'{quote_ident("41110")} AS group_avatar' if "41110" in cols else "NULL AS group_avatar",
        ]
        sql = f"""
            SELECT {", ".join(select_parts)}
            FROM recent_contact_v3_table
            ORDER BY COALESCE({quote_ident("40050")}, 0) DESC
            LIMIT ?
        """
        rows = conn.execute(sql, (limit,)).fetchall()

    results: list[dict] = []
    for row in rows:
        chat_type = row["chat_type"] or 0
        message = decode_message_blob(row["last_message_blob"])
        chat_name = resolve_chat_name(
            chat_type,
            row["peer_uid"],
            row["peer_uin"],
            row["group_name"] or row["remark_name"] or row["send_member_name"] or row["send_nickname"],
            buddies,
            groups,
        )
        sender_name = resolve_sender_name(
            row["sender_uid"],
            row["sender_uin"],
            row["send_nickname"],
            row["send_member_name"],
            buddies,
        )
        results.append(
            {
                "chat_type": chat_type,
                "chat_type_name": CHAT_TYPE_NAMES.get(chat_type, f"unknown:{chat_type}"),
                "chat_name": chat_name,
                "peer_uid": row["peer_uid"],
                "peer_uin": row["peer_uin"],
                "last_time": row["last_time"],
                "time": format_timestamp(row["last_time"]),
                "last_message": message["text"],
                "sender": sender_name,
                "group_avatar": row["group_avatar"] or "",
            }
        )
    return results


def _history_filters(columns: set[str], target: ChatTarget) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if target.kind == "group":
        if target.group_uin is not None and "40030" in columns:
            clauses.append(f"{quote_ident('40030')} = ?")
            params.append(target.group_uin)
        if target.group_uin is not None and "40021" in columns:
            clauses.append(f"{quote_ident('40021')} = ?")
            params.append(str(target.group_uin))
    else:
        if target.uin is not None and "40030" in columns:
            clauses.append(f"{quote_ident('40030')} = ?")
            params.append(target.uin)
        if target.nt_uid and "40021" in columns:
            clauses.append(f"{quote_ident('40021')} = ?")
            params.append(target.nt_uid)
        if target.nt_uid and "40020" in columns:
            clauses.append(f"{quote_ident('40020')} = ?")
            params.append(target.nt_uid)
    if not clauses:
        raise ValueError("当前数据库版本缺少可用于定位聊天对象的字段")
    return "(" + " OR ".join(clauses) + ")", params


def _time_filters(start_ts: int | None, end_ts: int | None, columns: set[str]) -> tuple[list[str], list]:
    if "40050" not in columns:
        return [], []
    clauses: list[str] = []
    params: list = []
    if start_ts is not None:
        clauses.append(f"{quote_ident('40050')} >= ?")
        params.append(start_ts)
    if end_ts is not None:
        clauses.append(f"{quote_ident('40050')} <= ?")
        params.append(end_ts)
    return clauses, params


def parse_time_input(value: str | None) -> int | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return int(datetime.strptime(value, fmt).timestamp())
        except ValueError:
            continue
    raise ValueError(f"无法解析时间: {value}")


def load_history(
    db_files: dict[str, str],
    target: ChatTarget,
    buddies: list[dict],
    limit: int,
    offset: int,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> list[dict]:
    table = "group_msg_table" if target.kind == "group" else "c2c_msg_table"
    path = db_files["nt_msg"]
    with connect(path) as conn:
        if not table_exists(conn, table):
            return []
        cols = table_columns(conn, table)
        where_chat, params = _history_filters(cols, target)
        time_clauses, time_params = _time_filters(start_ts, end_ts, cols)
        where_parts = [where_chat, *time_clauses]
        params.extend(time_params)
        select_parts = [
            f'{quote_ident("40001")} AS msg_id' if "40001" in cols else "NULL AS msg_id",
            f'{quote_ident("40002")} AS msg_random' if "40002" in cols else "NULL AS msg_random",
            f'{quote_ident("40003")} AS msg_seq' if "40003" in cols else "NULL AS msg_seq",
            f'{quote_ident("40011")} AS msg_type' if "40011" in cols else "NULL AS msg_type",
            f'{quote_ident("40012")} AS sub_msg_type' if "40012" in cols else "NULL AS sub_msg_type",
            f'{quote_ident("40013")} AS send_type' if "40013" in cols else "NULL AS send_type",
            f'{quote_ident("40020")} AS sender_uid' if "40020" in cols else "NULL AS sender_uid",
            f'{quote_ident("40021")} AS peer_uid' if "40021" in cols else "NULL AS peer_uid",
            f'{quote_ident("40030")} AS peer_uin' if "40030" in cols else "NULL AS peer_uin",
            f'{quote_ident("40033")} AS sender_uin' if "40033" in cols else "NULL AS sender_uin",
            f'{quote_ident("40050")} AS msg_time' if "40050" in cols else "NULL AS msg_time",
            f'{quote_ident("40090")} AS sender_member_name' if "40090" in cols else "NULL AS sender_member_name",
            f'{quote_ident("40093")} AS sender_nickname' if "40093" in cols else "NULL AS sender_nickname",
            f'{quote_ident("40800")} AS body' if "40800" in cols else "NULL AS body",
        ]
        sql = f"""
            SELECT {", ".join(select_parts)}
            FROM {quote_ident(table)}
            WHERE {" AND ".join(where_parts)}
            ORDER BY COALESCE({quote_ident("40050")}, 0) DESC, COALESCE({quote_ident("40003")}, 0) DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(sql, (*params, limit, offset)).fetchall()

    results: list[dict] = []
    for row in rows:
        decoded = decode_message_blob(row["body"])
        sender = resolve_sender_name(
            row["sender_uid"],
            row["sender_uin"],
            row["sender_nickname"],
            row["sender_member_name"],
            buddies,
        )
        msg_type = row["msg_type"]
        results.append(
            {
                "msg_id": row["msg_id"],
                "msg_random": row["msg_random"],
                "msg_seq": row["msg_seq"],
                "msg_type": msg_type,
                "msg_type_name": MSG_TYPE_NAMES.get(msg_type, f"unknown:{msg_type}") if msg_type is not None else None,
                "sub_msg_type": row["sub_msg_type"],
                "send_type": row["send_type"],
                "sender": sender,
                "sender_uid": row["sender_uid"],
                "sender_uin": row["sender_uin"],
                "timestamp": row["msg_time"],
                "time": format_timestamp(row["msg_time"]),
                "text": decoded["text"],
                "attachments": decoded["attachments"],
                "element_types": decoded["element_types"],
            }
        )
    return results


def load_files(
    db_files: dict[str, str],
    buddies: list[dict],
    groups: list[dict],
    limit: int,
    target: ChatTarget | None = None,
) -> list[dict]:
    results: list[dict] = []
    files_path = db_files.get("files_in_chat")
    if files_path:
        with connect(files_path) as conn:
            if table_exists(conn, "files_in_chat_table"):
                cols = table_columns(conn, "files_in_chat_table")
                clauses: list[str] = []
                params: list = []
                if target:
                    where_chat, where_params = _history_filters(cols, target)
                    clauses.append(where_chat)
                    params.extend(where_params)
                where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
                sql = f"""
                    SELECT
                        {quote_ident("45001")} AS client_seq,
                        {quote_ident("82300")} AS msg_random,
                        {quote_ident("40001")} AS msg_id,
                        {quote_ident("45402")} AS file_name,
                        {quote_ident("45403")} AS file_path,
                        {quote_ident("45404")} AS thumb_path,
                        {quote_ident("45405")} AS file_size,
                        {quote_ident("40020")} AS sender_uid,
                        {quote_ident("40021")} AS peer_uid,
                        {quote_ident("40010")} AS chat_type,
                        {quote_ident("45002")} AS element_type,
                        {quote_ident("45003")} AS sub_element_type,
                        {quote_ident("40050")} AS msg_time,
                        {quote_ident("82302")} AS original_flag
                    FROM files_in_chat_table
                    {where_sql}
                    ORDER BY COALESCE({quote_ident("40050")}, 0) DESC
                    LIMIT ?
                """
                rows = conn.execute(sql, (*params, limit)).fetchall()
                for row in rows:
                    chat_name = resolve_chat_name(
                        row["chat_type"],
                        row["peer_uid"],
                        int(row["peer_uid"]) if row["chat_type"] == 2 and str(row["peer_uid"]).isdigit() else None,
                        None,
                        buddies,
                        groups,
                    )
                    sender = resolve_sender_name(row["sender_uid"], None, None, None, buddies)
                    results.append(
                        {
                            "source": "files_in_chat",
                            "msg_id": row["msg_id"],
                            "msg_random": row["msg_random"],
                            "client_seq": row["client_seq"],
                            "chat_type": row["chat_type"],
                            "chat_name": chat_name,
                            "sender": sender,
                            "peer_uid": row["peer_uid"],
                            "file_name": row["file_name"] or "",
                            "file_path": row["file_path"] or "",
                            "thumb_path": row["thumb_path"] or "",
                            "file_size": row["file_size"],
                            "file_size_text": _human_size(row["file_size"]),
                            "element_type": row["element_type"],
                            "sub_element_type": row["sub_element_type"],
                            "is_original": row["original_flag"] == 1,
                            "timestamp": row["msg_time"],
                            "time": format_timestamp(row["msg_time"]),
                        }
                    )

    rich_path = db_files.get("rich_media")
    rich_by_key: dict[tuple, dict] = {}
    if rich_path:
        with connect(rich_path) as conn:
            if table_exists(conn, "file_table"):
                rows = conn.execute(
                    f"""
                    SELECT
                        {quote_ident("40001")} AS msg_id,
                        {quote_ident("45001")} AS element_id,
                        {quote_ident("45402")} AS file_name,
                        {quote_ident("45403")} AS file_path,
                        {quote_ident("45405")} AS file_size,
                        {quote_ident("45503")} AS file_uuid,
                        {quote_ident("40021")} AS peer_uid
                    FROM file_table
                    """
                ).fetchall()
                for row in rows:
                    rich_by_key[(row["msg_id"], row["file_name"])] = {
                        "file_path": row["file_path"] or "",
                        "file_uuid": row["file_uuid"] or "",
                        "file_size": row["file_size"],
                        "peer_uid": row["peer_uid"],
                        "element_id": row["element_id"],
                    }

    for item in results:
        rich = rich_by_key.get((item["msg_id"], item["file_name"]))
        if not rich:
            continue
        if not item["file_path"]:
            item["file_path"] = rich["file_path"]
        if not item["file_size"] and rich["file_size"]:
            item["file_size"] = rich["file_size"]
            item["file_size_text"] = _human_size(rich["file_size"])
        item["file_uuid"] = rich["file_uuid"]
        item["rich_element_id"] = rich["element_id"]

    return results


def load_collections(db_files: dict[str, str], limit: int) -> list[dict]:
    path = db_files.get("collection")
    if not path:
        return []
    with connect(path) as conn:
        if not table_exists(conn, "collection_list_info_table"):
            return []
        rows = conn.execute(
            f"""
            SELECT
                {quote_ident("180001")} AS sid,
                {quote_ident("180008")} AS collection_type,
                {quote_ident("180009")} AS created_at,
                {quote_ident("180011")} AS updated_at,
                {quote_ident("180004")} AS source_blob,
                {quote_ident("180015")} AS summary_blob
            FROM collection_list_info_table
            ORDER BY COALESCE({quote_ident("180011")}, 0) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    type_names = {
        1: "chat_text",
        2: "note",
        9: "chat_link",
    }
    results: list[dict] = []
    for row in rows:
        source_map = _decode_scalar_map(row["source_blob"])
        summary_map = _decode_scalar_map(row["summary_blob"])
        results.append(
            {
                "sid": row["sid"],
                "type": row["collection_type"],
                "type_name": type_names.get(row["collection_type"], f"unknown:{row['collection_type']}"),
                "created_at": row["created_at"],
                "created_time": format_timestamp(row["created_at"]),
                "updated_at": row["updated_at"],
                "updated_time": format_timestamp(row["updated_at"]),
                "title": _first(summary_map, 181450),
                "summary": _first(summary_map, 181452),
                "image_url": _first(summary_map, 180550),
                "image_name": _first(summary_map, 180553),
                "image_path": _first(summary_map, 180561),
                "file_path": _first(summary_map, 180610),
                "source_group_uin": _first(source_map, 18504),
                "source_group_name": _first(source_map, 18505),
                "source_sender_uid": _first(source_map, 18506),
                "source_sender_uin": _first(source_map, 18501),
                "source_sender_name": _first(source_map, 180503),
            }
        )
    return results


def load_emojis(db_files: dict[str, str], limit: int, system: bool = False) -> list[dict]:
    path = db_files.get("emoji")
    if not path:
        return []
    with connect(path) as conn:
        if system:
            if not table_exists(conn, "base_sys_emoji_table"):
                return []
            rows = conn.execute(
                f"""
                SELECT
                    {quote_ident("81211")} AS emoji_id,
                    {quote_ident("81212")} AS description,
                    {quote_ident("81226")} AS emoji_type,
                    {quote_ident("81221")} AS special_flag,
                    {quote_ident("81229")} AS static_url,
                    {quote_ident("81230")} AS apng_url
                FROM base_sys_emoji_table
                ORDER BY {quote_ident("81211")}
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [
                {
                    "emoji_id": row["emoji_id"],
                    "description": row["description"] or "",
                    "emoji_type": row["emoji_type"],
                    "is_special": row["special_flag"] == 1,
                    "static_url": row["static_url"] or "",
                    "apng_url": row["apng_url"] or "",
                }
                for row in rows
            ]

        if not table_exists(conn, "fav_emoji_info_storage_table"):
            return []
        rows = conn.execute(
            f"""
            SELECT
                {quote_ident("80001")} AS sort_order,
                {quote_ident("80002")} AS file_name,
                {quote_ident("1002")} AS owner_uin,
                {quote_ident("80010")} AS download_url,
                {quote_ident("80011")} AS emoji_md5,
                {quote_ident("80012")} AS local_path,
                {quote_ident("80213")} AS is_market,
                {quote_ident("80201")} AS market_key,
                {quote_ident("80202")} AS market_package_id,
                {quote_ident("80223")} AS note_a,
                {quote_ident("80225")} AS note_b
            FROM fav_emoji_info_storage_table
            ORDER BY COALESCE({quote_ident("80001")}, 0) ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "sort_order": row["sort_order"],
                "file_name": row["file_name"] or "",
                "owner_uin": row["owner_uin"],
                "download_url": row["download_url"] or "",
                "emoji_md5": row["emoji_md5"] or "",
                "local_path": row["local_path"] or "",
                "is_market": row["is_market"] == 1,
                "market_key": row["market_key"] or "",
                "market_package_id": row["market_package_id"],
                "note": row["note_a"] or row["note_b"] or "",
            }
            for row in rows
        ]


def _decode_scalar_map(blob: bytes | None) -> dict[int, list]:
    values: dict[int, list] = {}
    if not blob:
        return values
    for message in walk_messages(blob):
        for field in message.fields:
            if field.number not in values:
                values[field.number] = []
            if isinstance(field.value, int):
                values[field.number].append(field.value)
            else:
                decoded = collect_strings(field.value, max_depth=2)
                if decoded:
                    values[field.number].extend(decoded)
                else:
                    text = field.value.decode("utf-8", errors="ignore").strip()
                    if text:
                        values[field.number].append(text)
    return values


def _first(value_map: dict[int, list], key: int):
    values = value_map.get(key, [])
    return values[0] if values else None
