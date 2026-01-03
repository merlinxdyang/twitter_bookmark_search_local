 # Twitter Bookmark Search / 推特书签本地检索

A local search tool for X/Twitter bookmarks exported as JSON, with a lightweight web UI.
本项目用于把 X/Twitter 书签 JSON 导入本地数据库，并提供一个轻量网页界面用于关键词检索。

It is designed for continuous use: your exported JSON files will grow over time, so this project supports incremental imports into a persistent SQLite database.
它面向“持续增长”的真实使用场景：书签会不断增加，因此提供“增量导入”，把新内容追加进同一个 SQLite 数据库。

This project works well with JSON exported by `twitter-web-exporter`:
本项目对 `twitter-web-exporter` 的导出 JSON 兼容良好：

- GitHub: https://github.com/prinsss/twitter-web-exporter

---

## Features / 功能

- Keyword search (match by inclusion)  
  关键词检索（包含匹配）
- Fast full-text search when SQLite FTS5 is available, with automatic fallback to LIKE  
  SQLite 支持 FTS5 时启用全文检索（更快、排序更好），不支持时自动回退到 LIKE 模糊匹配
- Incremental import  
  增量导入  
  - Append only new tweets (dedup by tweet id)  
    只追加新推文（按 tweet id 去重）
  - Skip unchanged JSON files automatically (size + modified time)  
    自动跳过未变化的旧 JSON 文件（按文件大小与修改时间判断）
- Local media support  
  本地媒体展示  
  - If you download media into `tweet_back/` using the same filename as the URL basename, the UI will render images, audio, and video from your disk.  
    如果你把媒体文件下载到 `tweet_back/` 且文件名等于 URL 最后一段（basename），界面将直接显示本地图片、音频、视频。

---

## Quick start / 快速开始

### 1) Install / 安装依赖

```bash
pip install -r requirements.txt
```

### 2) Put your data under `data/` / 把数据放进 data/

Recommended layout / 推荐结构：

- Exported JSON: `data/bookmarks_json/*.json`  
  书签 JSON：`data/bookmarks_json/*.json`
- Media folder: `data/tweet_back/`  
  媒体目录：`data/tweet_back/`

Tip / 提示：  
This repo ignores `data/` by default via `.gitignore`, so you can open-source the tool without uploading your personal bookmarks.  
本仓库默认通过 `.gitignore` 忽略 `data/`，你可以开源工具而不泄露个人书签数据。

### 3) Incremental import / 增量导入（推荐）

```bash
python build_index.py --mode incremental --json_dir ./data/bookmarks_json --media_dir ./data/tweet_back --db ./data/bookmarks.db
```

Run it again any time you add new JSON files. Unchanged old JSON files are skipped.  
以后新增 JSON 文件后重复运行同一条命令即可，未变化的旧 JSON 会自动跳过。

### 4) Run the UI / 启动界面

```bash
streamlit run app.py -- --db ./data/bookmarks.db --media_dir ./data/tweet_back
```

---

## Import modes / 导入模式

- `--mode incremental` (default)  
  默认增量导入：追加新推文、跳过已有 id
- `--mode rebuild`  
  重建数据库：删除 db 后重新导入

Example rebuild / 重建示例：

```bash
python build_index.py --mode rebuild --json_dir ./data/bookmarks_json --media_dir ./data/tweet_back --db ./data/bookmarks.db
```

---

## Search behavior / 检索说明

- If FTS5 is available, the app uses full-text search and ranks by relevance (bm25).  
  如果 FTS5 可用，将使用全文检索并按相关度排序（bm25）。
- Otherwise it falls back to substring search (LIKE).  
  否则自动回退到 LIKE 子串匹配。
- Your requirement “contain the keyword” is supported in both modes.  
  你的“只要包含关键词即可”的需求，两种模式都支持。

---

## JSON schema assumption / JSON 格式假设

The importer expects the JSON to be a list of tweet-like dict objects. Typical keys include:  
导入器假设 JSON 顶层为 list，元素为推文对象 dict，常见字段包括：

- `id`, `created_at`, `full_text`, `screen_name`, `name`, `profile_image_url`, `url`
- `media`: list of items with `type`, and urls like `original` / `thumbnail`

If your exporter changes the schema, adjust the mapping in `build_index.py`.  
如果导出工具将来调整了字段名或结构，你只需要在 `build_index.py` 里改映射即可。

---

## Privacy / 隐私

Everything stays on your machine. No data is uploaded anywhere by this tool.  
所有数据都留在本机，本工具不会上传任何内容到外部服务器。
