#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st

# ------------------------
# DB helpers
# ------------------------

def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def has_fts(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tweets_fts'").fetchone()
        conn.execute("SELECT count(*) FROM tweets_fts").fetchone()
        return True
    except Exception:
        return False

def local_path(media_dir: Path | None, filename: str | None) -> Path | None:
    if not media_dir or not filename:
        return None
    p = media_dir / filename
    return p if p.exists() else None

def fmt_dt(s: str | None) -> str:
    if not s:
        return ""
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s

# ------------------------
# Search
# ------------------------

def search(conn: sqlite3.Connection, q: str, limit: int, only_media: bool, min_bookmark: int, min_fav: int):
    filters = []
    params = []

    if only_media:
        filters.append("t.has_media = 1")
    if min_bookmark > 0:
        filters.append("(t.bookmark_count IS NOT NULL AND t.bookmark_count >= ?)")
        params.append(min_bookmark)
    if min_fav > 0:
        filters.append("(t.favorite_count IS NOT NULL AND t.favorite_count >= ?)")
        params.append(min_fav)

    where_extra = (" AND " + " AND ".join(filters)) if filters else ""
    q = (q or "").strip()

    # FTS5 preferred
    if q and has_fts(conn):
        sql = f"""
        SELECT t.*
        FROM tweets t
        JOIN tweets_fts ON tweets_fts.rowid = t.rowid
        WHERE tweets_fts MATCH ? {where_extra}
        ORDER BY bm25(tweets_fts) ASC
        LIMIT ?
        """
        params2 = [q] + params + [limit]
        return conn.execute(sql, params2).fetchall(), "fts"

    # fallback: LIKE
    like = f"%{q}%" if q else "%"
    sql = f"""
    SELECT t.*
    FROM tweets t
    WHERE (t.full_text LIKE ? OR t.screen_name LIKE ? OR t.name LIKE ?) {where_extra}
    ORDER BY t.created_at_utc DESC
    LIMIT ?
    """
    params2 = [like, like, like] + params + [limit]
    return conn.execute(sql, params2).fetchall(), "like"

def fetch_media(conn: sqlite3.Connection, tweet_id: str):
    return conn.execute(
        "SELECT * FROM media WHERE tweet_id = ? ORDER BY idx ASC",
        (tweet_id,)
    ).fetchall()

# ------------------------
# UI i18n
# ------------------------

I18N = {
    "en": {
        "page_title": "Twitter Bookmark Search",
        "title": "Twitter Bookmark Search",
        "lang_label": "Language / 语言",
        "sidebar_search": "Search",
        "keyword": "Keyword",
        "max_results": "Max results",
        "only_media": "Only tweets with media",
        "min_bookmarks": "Min bookmarks",
        "min_likes": "Min likes",
        "status": "Status",
        "db": "DB",
        "fts": "FTS5",
        "fts_enabled": "enabled",
        "fts_fallback": "fallback to LIKE",
        "media_dir": "Media dir",
        "media_dir_not_set": "not set",
        "db_not_found_title": "Database not found",
        "db_not_found_help": "Run build_index.py first.",
        "hits": "Hits",
        "mode": "Mode",
        "open_tweet": "Open tweet",
        "media": "Media",
        "open_remote_media": "Open remote media",
        "bookmarks": "bookmarks",
        "likes": "likes",
        "retweets": "retweets",
        "local_file": "Local file",
    },
    "zh": {
        "page_title": "推特书签检索",
        "title": "推特书签检索",
        "lang_label": "Language / 语言",
        "sidebar_search": "检索设置",
        "keyword": "关键词 / 查询",
        "max_results": "最多返回条数",
        "only_media": "只看带媒体的推文",
        "min_bookmarks": "最少收藏数",
        "min_likes": "最少喜欢数",
        "status": "索引状态",
        "db": "数据库",
        "fts": "FTS5",
        "fts_enabled": "已启用",
        "fts_fallback": "不可用，回退到 LIKE",
        "media_dir": "媒体目录",
        "media_dir_not_set": "未设置",
        "db_not_found_title": "未找到数据库",
        "db_not_found_help": "请先运行 build_index.py 导入数据。",
        "hits": "命中",
        "mode": "模式",
        "open_tweet": "打开原推文",
        "media": "媒体",
        "open_remote_media": "打开远端媒体",
        "bookmarks": "收藏",
        "likes": "喜欢",
        "retweets": "转推",
        "local_file": "本地文件",
    }
}

def t(lang: str, key: str) -> str:
    lang = lang if lang in I18N else "en"
    return I18N[lang].get(key, I18N["en"].get(key, key))

# ------------------------
# Render
# ------------------------

def render_tweet(conn: sqlite3.Connection, row: sqlite3.Row, media_dir: Path | None, lang: str):
    col1, col2 = st.columns([1, 7])
    with col1:
        p = local_path(media_dir, row["profile_image_file"])
        if p:
            st.image(str(p), use_container_width=True)

    with col2:
        title = f'{row["name"] or ""}  @{row["screen_name"] or ""}'
        st.markdown(f"**{title}**")

        st.caption(
            f'{fmt_dt(row["created_at_utc"])}  |  '
            f'{t(lang, "bookmarks")} {row["bookmark_count"] or 0}  '
            f'{t(lang, "likes")} {row["favorite_count"] or 0}  '
            f'{t(lang, "retweets")} {row["retweet_count"] or 0}'
        )

        st.write(row["full_text"] or "")

        if row["tweet_url"]:
            st.link_button(t(lang, "open_tweet"), row["tweet_url"])

        media_rows = fetch_media(conn, row["id"])
        if media_rows:
            st.markdown(f"**{t(lang, 'media')}**")
            for m in media_rows:
                lf = local_path(media_dir, m["local_file"])
                mtype = (m["type"] or "").lower()

                if lf:
                    if mtype in ("photo", "image", "animated_gif"):
                        st.image(str(lf), use_container_width=True)
                    elif mtype in ("video",):
                        st.video(str(lf))
                    elif mtype in ("audio",):
                        st.audio(str(lf))
                    else:
                        st.caption(f'{t(lang, "local_file")}: {lf.name}')
                else:
                    if m["original_url"]:
                        st.link_button(f'{t(lang, "open_remote_media")} ({mtype or "media"})', m["original_url"])

    st.divider()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="bookmarks.db")
    ap.add_argument("--media_dir", default="")
    args, _ = ap.parse_known_args()

    db_path = Path(args.db).expanduser().resolve()
    media_dir = Path(args.media_dir).expanduser().resolve() if args.media_dir else None

    # Language selector is in sidebar, but page config needs a value early.
    # We set a neutral title and update visible UI later.
    st.set_page_config(page_title="Twitter Bookmark Search", layout="wide")

    with st.sidebar:
        lang_choice = st.selectbox(
            "Language / 语言",
            options=["English", "中文"],
            index=0
        )
    lang = "zh" if lang_choice == "中文" else "en"

    st.title(t(lang, "title"))

    if not db_path.exists():
        st.error(f'{t(lang, "db_not_found_title")}: {db_path}')
        st.info(t(lang, "db_not_found_help"))
        st.stop()

    conn = connect(db_path)
    fts_on = has_fts(conn)

    with st.sidebar:
        st.markdown(f"## {t(lang, 'sidebar_search')}")
        q = st.text_input(t(lang, "keyword"), value="")
        limit = st.slider(t(lang, "max_results"), min_value=10, max_value=200, value=50, step=10)
        only_media = st.checkbox(t(lang, "only_media"), value=False)
        min_bookmark = st.number_input(t(lang, "min_bookmarks"), min_value=0, value=0, step=10)
        min_fav = st.number_input(t(lang, "min_likes"), min_value=0, value=0, step=10)

        st.markdown(f"## {t(lang, 'status')}")
        st.write(f'{t(lang, "db")}: {db_path.name}')
        st.write(f'{t(lang, "fts")}: {t(lang, "fts_enabled") if fts_on else t(lang, "fts_fallback")}')
        if media_dir:
            st.write(f'{t(lang, "media_dir")}: {media_dir}')
        else:
            st.write(f'{t(lang, "media_dir")}: {t(lang, "media_dir_not_set")}')

    rows, mode = search(conn, q, limit, only_media, int(min_bookmark), int(min_fav))
    st.caption(f'{t(lang, "hits")}: {len(rows)}  |  {t(lang, "mode")}: {mode}')

    for r in rows:
        render_tweet(conn, r, media_dir, lang)

if __name__ == "__main__":
    main()
