"""Contact and group lookups."""

from __future__ import annotations

from dataclasses import dataclass

from .db import connect, quote_ident, table_columns, table_exists


@dataclass
class ChatTarget:
    kind: str
    display_name: str
    nt_uid: str | None = None
    uin: int | None = None
    qid: str | None = None
    group_uin: int | None = None
    nickname: str | None = None
    remark: str | None = None


def _normalize(value) -> str:
    return str(value or "").strip().lower()


def _value_present(columns: set[str], name: str) -> bool:
    return name in columns


def load_buddies(db_files: dict[str, str]) -> list[dict]:
    path = db_files.get("profile_info")
    if not path:
        return []

    with connect(path) as conn:
        if not table_exists(conn, "buddy_list"):
            return []
        buddy_cols = table_columns(conn, "buddy_list")
        profile_cols = table_columns(conn, "profile_info_v6") if table_exists(conn, "profile_info_v6") else set()

        select_parts = [
            f'b.{quote_ident("1000")} AS nt_uid' if _value_present(buddy_cols, "1000") else "NULL AS nt_uid",
            f'b.{quote_ident("1001")} AS qid_from_buddy' if _value_present(buddy_cols, "1001") else "NULL AS qid_from_buddy",
            f'b.{quote_ident("1002")} AS uin_from_buddy' if _value_present(buddy_cols, "1002") else "NULL AS uin_from_buddy",
            f'b.{quote_ident("25007")} AS category_id' if _value_present(buddy_cols, "25007") else "NULL AS category_id",
            f'p.{quote_ident("1001")} AS qid' if _value_present(profile_cols, "1001") else "NULL AS qid",
            f'p.{quote_ident("1002")} AS uin' if _value_present(profile_cols, "1002") else "NULL AS uin",
            f'p.{quote_ident("20002")} AS nickname' if _value_present(profile_cols, "20002") else "NULL AS nickname",
            f'p.{quote_ident("20009")} AS remark' if _value_present(profile_cols, "20009") else "NULL AS remark",
            f'p.{quote_ident("20011")} AS signature' if _value_present(profile_cols, "20011") else "NULL AS signature",
            f'p.{quote_ident("20004")} AS avatar_url' if _value_present(profile_cols, "20004") else "NULL AS avatar_url",
            f'hex(p.{quote_ident("20072")}) AS friend_flag' if _value_present(profile_cols, "20072") else "NULL AS friend_flag",
        ]

        sql = f"""
            SELECT {", ".join(select_parts)}
            FROM buddy_list b
            LEFT JOIN profile_info_v6 p ON p.{quote_ident("1000")} = b.{quote_ident("1000")}
            ORDER BY COALESCE(p.{quote_ident("20009")}, p.{quote_ident("20002")}, b.{quote_ident("1001")}, b.{quote_ident("1000")})
        """
        rows = conn.execute(sql).fetchall()

    results: list[dict] = []
    for row in rows:
        nt_uid = row["nt_uid"]
        qid = row["qid"] or row["qid_from_buddy"]
        uin = row["uin"] or row["uin_from_buddy"]
        nickname = row["nickname"] or ""
        remark = row["remark"] or ""
        display_name = remark or nickname or qid or str(uin or "") or nt_uid
        results.append(
            {
                "kind": "c2c",
                "display_name": display_name,
                "nt_uid": nt_uid,
                "qid": qid,
                "uin": uin,
                "nickname": nickname,
                "remark": remark,
                "signature": row["signature"] or "",
                "avatar_url": row["avatar_url"] or "",
                "category_id": row["category_id"],
                "is_friend": (row["friend_flag"] or "").upper() == "C2E60900",
            }
        )
    return results


def load_groups(db_files: dict[str, str]) -> list[dict]:
    path = db_files.get("group_info")
    if not path:
        return []

    with connect(path) as conn:
        if not table_exists(conn, "group_list"):
            return []
        group_cols = table_columns(conn, "group_list")
        detail_cols = table_columns(conn, "group_detail_info_ver1") if table_exists(conn, "group_detail_info_ver1") else set()

        select_parts = [
            f'g.{quote_ident("60001")} AS group_uin' if "60001" in group_cols else "NULL AS group_uin",
            f'g.{quote_ident("60007")} AS group_name' if "60007" in group_cols else "NULL AS group_name",
            f'd.{quote_ident("60007")} AS detail_name' if "60007" in detail_cols else "NULL AS detail_name",
            f'd.{quote_ident("60026")} AS group_remark' if "60026" in detail_cols else "NULL AS group_remark",
            f'd.{quote_ident("60002")} AS owner_uid' if "60002" in detail_cols else "NULL AS owner_uid",
            f'd.{quote_ident("60004")} AS created_at' if "60004" in detail_cols else "NULL AS created_at",
            f'd.{quote_ident("60005")} AS max_members' if "60005" in detail_cols else "NULL AS max_members",
            f'd.{quote_ident("60006")} AS member_count' if "60006" in detail_cols else "NULL AS member_count",
            f'd.{quote_ident("60340")} AS exited_flag' if "60340" in detail_cols else "NULL AS exited_flag",
        ]

        sql = f"""
            SELECT {", ".join(select_parts)}
            FROM group_list g
            LEFT JOIN group_detail_info_ver1 d ON d.{quote_ident("60001")} = g.{quote_ident("60001")}
            ORDER BY COALESCE(d.{quote_ident("60026")}, d.{quote_ident("60007")}, g.{quote_ident("60007")}, g.{quote_ident("60001")})
        """
        rows = conn.execute(sql).fetchall()

    results: list[dict] = []
    for row in rows:
        display_name = row["group_remark"] or row["detail_name"] or row["group_name"] or str(row["group_uin"])
        results.append(
            {
                "kind": "group",
                "display_name": display_name,
                "group_uin": row["group_uin"],
                "group_name": row["detail_name"] or row["group_name"] or "",
                "group_remark": row["group_remark"] or "",
                "owner_uid": row["owner_uid"] or "",
                "created_at": row["created_at"],
                "max_members": row["max_members"],
                "member_count": row["member_count"],
                "is_exited": row["exited_flag"] == 1,
            }
        )
    return results


def load_group_members(db_files: dict[str, str], group_uin: int) -> list[dict]:
    path = db_files.get("group_info")
    if not path:
        return []

    with connect(path) as conn:
        if not table_exists(conn, "group_member3"):
            return []
        cols = table_columns(conn, "group_member3")
        select_parts = [
            f'{quote_ident("1000")} AS nt_uid' if "1000" in cols else "NULL AS nt_uid",
            f'{quote_ident("1002")} AS uin' if "1002" in cols else "NULL AS uin",
            f'{quote_ident("20002")} AS nickname' if "20002" in cols else "NULL AS nickname",
            f'{quote_ident("64003")} AS group_nick' if "64003" in cols else "NULL AS group_nick",
            f'{quote_ident("64010")} AS is_admin' if "64010" in cols else "NULL AS is_admin",
            f'{quote_ident("64016")} AS exited_flag' if "64016" in cols else "NULL AS exited_flag",
            f'{quote_ident("64023")} AS title' if "64023" in cols else "NULL AS title",
            f'{quote_ident("64007")} AS joined_at' if "64007" in cols else "NULL AS joined_at",
        ]
        sql = f"""
            SELECT {", ".join(select_parts)}
            FROM group_member3
            WHERE {quote_ident("60001")} = ?
            ORDER BY COALESCE({quote_ident("64003")}, {quote_ident("20002")}, {quote_ident("1000")})
        """
        rows = conn.execute(sql, (group_uin,)).fetchall()

    results: list[dict] = []
    for row in rows:
        display_name = row["group_nick"] or row["nickname"] or row["nt_uid"]
        results.append(
            {
                "display_name": display_name,
                "nt_uid": row["nt_uid"],
                "uin": row["uin"],
                "nickname": row["nickname"] or "",
                "group_nick": row["group_nick"] or "",
                "title": row["title"] or "",
                "is_admin": row["is_admin"] == 1,
                "is_exited": row["exited_flag"] == 1,
                "joined_at": row["joined_at"],
            }
        )
    return results


def merge_recent_contacts(
    items: list[dict],
    recent_sessions: list[dict],
    *,
    groups: bool = False,
) -> list[dict]:
    """Merge recent-session targets that are not present in contacts/group tables."""

    merged = list(items)
    seen: set[tuple] = set()

    if groups:
        for item in items:
            seen.add(("group_name", _normalize(item.get("display_name"))))
            if item.get("group_uin") is not None:
                seen.add(("group_uin", str(item["group_uin"])))

        for session in recent_sessions:
            if session.get("chat_type") != 2:
                continue
            display_name = session.get("chat_name") or ""
            peer_uin = session.get("peer_uin")
            keys = {("group_name", _normalize(display_name))}
            if peer_uin not in (None, 0, ""):
                keys.add(("group_uin", str(peer_uin)))
            if any(key in seen for key in keys):
                continue
            merged.append(
                {
                    "kind": "group",
                    "display_name": display_name,
                    "group_uin": peer_uin,
                    "group_name": display_name,
                    "group_remark": "",
                    "owner_uid": "",
                    "created_at": None,
                    "max_members": None,
                    "member_count": None,
                    "is_exited": False,
                    "source": "recent_session",
                }
            )
            seen.update(keys)
        return merged

    for item in items:
        seen.add(("display_name", _normalize(item.get("display_name"))))
        if item.get("nt_uid"):
            seen.add(("nt_uid", str(item["nt_uid"])))
        if item.get("uin") not in (None, 0, ""):
            seen.add(("uin", str(item["uin"])))
        if item.get("qid"):
            seen.add(("qid", _normalize(item["qid"])))

    for session in recent_sessions:
        if session.get("chat_type") == 2:
            continue
        display_name = session.get("chat_name") or ""
        peer_uid = session.get("peer_uid")
        peer_uin = session.get("peer_uin")
        keys = {("display_name", _normalize(display_name))}
        if peer_uid:
            keys.add(("nt_uid", str(peer_uid)))
        if peer_uin not in (None, 0, ""):
            keys.add(("uin", str(peer_uin)))
        if any(key in seen for key in keys):
            continue
        merged.append(
            {
                "kind": "c2c",
                "display_name": display_name,
                "nt_uid": peer_uid,
                "qid": None,
                "uin": peer_uin,
                "nickname": display_name,
                "remark": "",
                "signature": "",
                "avatar_url": "",
                "category_id": None,
                "is_friend": False,
                "source": "recent_session",
            }
        )
        seen.update(keys)
    return merged


def resolve_chat_target(
    chat_name: str,
    buddies: list[dict],
    groups: list[dict],
    recent_sessions: list[dict] | None = None,
) -> ChatTarget | None:
    exact: list[ChatTarget] = []
    fuzzy: list[ChatTarget] = []
    needle = _normalize(chat_name)

    def _add_candidate(target: ChatTarget, haystacks: list[str]) -> None:
        if any(_normalize(value) == needle for value in haystacks if value):
            exact.append(target)
        elif any(needle in _normalize(value) for value in haystacks if value):
            fuzzy.append(target)

    for buddy in buddies:
        target = ChatTarget(
            kind="c2c",
            display_name=buddy["display_name"],
            nt_uid=buddy["nt_uid"],
            uin=buddy["uin"],
            qid=buddy["qid"],
            nickname=buddy["nickname"],
            remark=buddy["remark"],
        )
        haystacks = [
            buddy["display_name"],
            buddy["nt_uid"],
            buddy["qid"],
            buddy["nickname"],
            buddy["remark"],
            str(buddy["uin"] or ""),
        ]
        _add_candidate(target, haystacks)

    for group in groups:
        target = ChatTarget(
            kind="group",
            display_name=group["display_name"],
            group_uin=group["group_uin"],
            nickname=group["group_name"],
            remark=group["group_remark"],
        )
        haystacks = [
            group["display_name"],
            group["group_name"],
            group["group_remark"],
            str(group["group_uin"] or ""),
        ]
        _add_candidate(target, haystacks)

    if recent_sessions:
        for session in recent_sessions:
            target = ChatTarget(
                kind="group" if session["chat_type"] == 2 else "c2c",
                display_name=session["chat_name"],
                nt_uid=session.get("peer_uid"),
                uin=session.get("peer_uin"),
                group_uin=session.get("peer_uin") if session["chat_type"] == 2 else None,
            )
            haystacks = [
                session["chat_name"],
                session.get("peer_uid"),
                str(session.get("peer_uin") or ""),
            ]
            _add_candidate(target, haystacks)

    if exact:
        return exact[0]
    if fuzzy:
        return fuzzy[0]
    return None
