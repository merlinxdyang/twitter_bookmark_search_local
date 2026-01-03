#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

def parse_dt(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return dt_str
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.astimezone(timezone.utc).isoformat()

def url_to_candidates(url: str) -> list[str]:
    if not url:
        return []
    u = urlparse(url)
    base = os.path.basename(u.path).strip()
    if not base:
        return []

    candidates = [base]

    if "." not in base:
        qs = parse_qs(u.query)
        fmt = (qs.get("format", [""])[0] or "").lower()
        if fmt:
            candidates.append(f"{base}.{fmt}")

        for ext in ("jpg", "jpeg", "png", "gif", "webp", "mp4", "mov", "m4a", "mp3"):
            candidates.append(f"{base}.{ext}")

    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            out.append(c)
            seen.add(c)
    return out

def choose_existing(media_dir: Path, candidates: list[str]) -> str | None:
    for c in candidates:
        p = media_dir / c
        if p.exists():
            return c
    return None

def ensure_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_test USING fts5(x);")
        conn.execute("DROP TABLE IF EXISTS _fts_test;")
        return True
    except sqlite3.OperationalError:
        return False

def get_int(x):
    try:
        return int(x)
    except Exception:
        return None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tweets (
    id TEXT PRIMARY KEY,
    created_at_utc TEXT,
    created_at_raw TEXT,
    full_text TEXT,
    screen_name TEXT,
    name TEXT,
    profile_image_url TEXT,
    profile_image_file TEXT,
    tweet_url TEXT,
    favorite_count INTEGER,
    retweet_count INTEGER,
    bookmark_count INTEGER,
    quote_count INTEGER,
    reply_count INTEGER,
    views_count INTEGER,
    in_reply_to TEXT,
    has_media INTEGER
);

CREATE TABLE IF NOT EXISTS media (
    tweet_id TEXT,
    idx INTEGER,
    type TEXT,
    url TEXT,
    thumbnail_url TEXT,
    original_url TEXT,
    local_file TEXT,
    PRIMARY KEY (tweet_id, idx)
);

CREATE TABLE IF NOT EXISTS imports (
    file_path TEXT PRIMARY KEY,
    file_size INTEGER,
    file_mtime REAL,
    imported_at_utc TEXT
);
"""

def ensure_fts_tables(conn: sqlite3.Connection) -> bool:
    if not ensure_fts5(conn):
        return False

    conn.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS tweets_fts
    USING fts5(full_text, screen_name, name, content='tweets', content_rowid='rowid');
    """)

    conn.executescript("""
    CREATE TRIGGER IF NOT EXISTS tweets_ai AFTER INSERT ON tweets BEGIN
        INSERT INTO tweets_fts(rowid, full_text, screen_name, name)
        VALUES (new.rowid, new.full_text, new.screen_name, new.name);
    END;

    CREATE TRIGGER IF NOT EXISTS tweets_ad AFTER DELETE ON tweets BEGIN
        INSERT INTO tweets_fts(tweets_fts, rowid, full_text, screen_name, name)
        VALUES ('delete', old.rowid, old.full_text, old.screen_name, old.name);
    END;

    CREATE TRIGGER IF NOT EXISTS tweets_au AFTER UPDATE ON tweets BEGIN
        INSERT INTO tweets_fts(tweets_fts, rowid, full_text, screen_name, name)
        VALUES ('delete', old.rowid, old.full_text, old.screen_name, old.name);
        INSERT INTO tweets_fts(rowid, full_text, screen_name, name)
        VALUES (new.rowid, new.full_text, new.screen_name, new.name);
    END;
    """)

    return True

def should_skip_file(conn: sqlite3.Connection, file_path: Path) -> bool:
    st = file_path.stat()
    row = conn.execute(
        "SELECT file_size, file_mtime FROM imports WHERE file_path = ?",
        (str(file_path),)
    ).fetchone()
    if not row:
        return False
    return (row[0] == st.st_size) and (abs(row[1] - st.st_mtime) < 1e-6)

def mark_file_imported(conn: sqlite3.Connection, file_path: Path):
    st = file_path.stat()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO imports(file_path, file_size, file_mtime, imported_at_utc) VALUES (?,?,?,?)",
        (str(file_path), int(st.st_size), float(st.st_mtime), now)
    )

def import_one_json(conn: sqlite3.Connection, json_path: Path, media_dir: Path | None) -> tuple[int, int]:
    with json_path.open("r", encoding="utf-8") as f:
        tweets = json.load(f)

    if not isinstance(tweets, list):
        raise ValueError(f"JSON root must be list[dict]. File: {json_path}")

    inserted = 0
    total = 0

    for tw in tweets:
        total += 1
        tid = str(tw.get("id", "")).strip()
        if not tid:
            continue

        # Dedup by tweet id
        cur = conn.execute("SELECT 1 FROM tweets WHERE id = ? LIMIT 1", (tid,)).fetchone()
        if cur:
            continue

        created_raw = tw.get("created_at") or ""
        created_utc = parse_dt(created_raw) if created_raw else None

        full_text = tw.get("full_text") or ""
        screen_name = tw.get("screen_name") or ""
        name = tw.get("name") or ""
        profile_image_url = tw.get("profile_image_url") or ""
        tweet_url = tw.get("url") or ""

        in_reply_to = tw.get("in_reply_to")
        in_reply_to = str(in_reply_to) if in_reply_to is not None else None

        media_list = tw.get("media") or []
        has_media = 1 if media_list else 0

        profile_file = None
        if media_dir and profile_image_url:
            cand = url_to_candidates(profile_image_url)
            profile_file = choose_existing(media_dir, cand)

        conn.execute(
            """INSERT INTO tweets (
                id, created_at_utc, created_at_raw, full_text, screen_name, name,
                profile_image_url, profile_image_file, tweet_url,
                favorite_count, retweet_count, bookmark_count, quote_count, reply_count, views_count,
                in_reply_to, has_media
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                tid, created_utc, created_raw, full_text, screen_name, name,
                profile_image_url, profile_file, tweet_url,
                get_int(tw.get("favorite_count")),
                get_int(tw.get("retweet_count")),
                get_int(tw.get("bookmark_count")),
                get_int(tw.get("quote_count")),
                get_int(tw.get("reply_count")),
                get_int(tw.get("views_count")),
                in_reply_to, has_media
            )
        )
        inserted += 1

        for i, m in enumerate(media_list):
            mtype = m.get("type") or ""
            url = m.get("url") or ""
            thumb = m.get("thumbnail") or ""
            orig = m.get("original") or ""

            local_file = None
            if media_dir:
                for candidate_url in (orig, thumb, url):
                    if not candidate_url:
                        continue
                    cand = url_to_candidates(candidate_url)
                    local_file = choose_existing(media_dir, cand)
                    if local_file:
                        break

            conn.execute(
                """INSERT OR REPLACE INTO media
                (tweet_id, idx, type, url, thumbnail_url, original_url, local_file)
                VALUES (?,?,?,?,?,?,?)""",
                (tid, i, mtype, url, thumb, orig, local_file)
            )

    return inserted, total

def collect_json_files(json_path: str, json_dir: str) -> list[Path]:
    files: list[Path] = []
    if json_path:
        files.append(Path(json_path).expanduser().resolve())
    if json_dir:
        d = Path(json_dir).expanduser().resolve()
        if not d.exists():
            raise FileNotFoundError(f"json_dir not found: {d}")
        for p in sorted(d.glob("*.json")):
            files.append(p.resolve())

    seen = set()
    out = []
    for f in files:
        if str(f) not in seen:
            out.append(f)
            seen.add(str(f))
    if not out:
        raise ValueError("Please provide --json or --json_dir")
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["incremental", "rebuild"], default="incremental")
    ap.add_argument("--json", default="", help="single JSON path")
    ap.add_argument("--json_dir", default="", help="directory containing *.json")
    ap.add_argument("--db", default="bookmarks.db", help="output SQLite db path")
    ap.add_argument("--media_dir", default="", help="tweet_back directory (optional)")
    args = ap.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    media_dir = Path(args.media_dir).expanduser().resolve() if args.media_dir else None
    if media_dir and not media_dir.exists():
        raise FileNotFoundError(f"media_dir not found: {media_dir}")

    json_files = collect_json_files(args.json, args.json_dir)

    if args.mode == "rebuild" and db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.executescript(SCHEMA_SQL)

    fts_ok = ensure_fts_tables(conn)

    new_total = 0
    processed_total = 0
    skipped_files = 0

    for jf in json_files:
        if not jf.exists():
            raise FileNotFoundError(f"JSON not found: {jf}")

        if args.mode == "incremental" and should_skip_file(conn, jf):
            skipped_files += 1
            continue

        inserted, total = import_one_json(conn, jf, media_dir)
        new_total += inserted
        processed_total += total
        mark_file_imported(conn, jf)
        conn.commit()

    conn.close()

    print(f"DB: {db_path}")
    print(f"JSON files: {len(json_files)} (skipped unchanged: {skipped_files})")
    print(f"Read tweets: {processed_total}, newly inserted: {new_total}")
    print(f"FTS5: {'enabled' if fts_ok else 'not available, UI will fallback to LIKE'}")

if __name__ == "__main__":
    main()
