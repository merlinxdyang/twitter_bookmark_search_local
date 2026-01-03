# Contributing / 贡献指南

This repository is intended to be small and easy to fork.  
本仓库目标是保持轻量、易于 Fork 和长期维护。

## Guidelines / 基本原则

- Keep dependencies minimal.  
  依赖尽量少。
- Avoid network calls that could leak user data.  
  不要加入会联网、可能泄露用户数据的功能。
- Prefer SQLite-only features and keep a safe fallback path.  
  优先使用 SQLite 自身能力，并保留可用的回退方案（例如没有 FTS5 时回退到 LIKE）。

## Ideas / 可能的改进方向

- Better adapters for other exporters  
  兼容更多导出工具的 JSON 结构
- Faster media file lookup (recursive scan with a cached index)  
  更快的媒体文件查找（递归扫描并缓存索引）
- UI refinements (filters, highlighting, pagination)  
  界面增强（更多筛选、高亮、分页等）
