# Changelog

本文件记录所有值得注意的变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.1.0] - 2026-11-17

### Added
- 登录失败限流：默认同一 IP 5 次/5 分钟内失败后锁定，登录成功即清零（`server.login_limit` / `server.login_window`）
- 播放历史（最近 50 首），网页右侧可直接「再点一次」
- 音量滑杆（0–100，记在浏览器本地）
- 队列拖动排序（`POST /api/reorder`）
- 歌词：网易云音源接入 `/lyric`，弹窗按播放进度高亮
- 搜索防抖（380ms）+「显示更多」（最多 50 条）
- 插件自动发现：把文件丢进 `jukebox/plugins/` 即注册，不再需要改代码登记
- Docker 支持：`Dockerfile`（含 `apple` 构建目标）与 `docker-compose.yml`
- `tests/test_web.py`：用假 TS3AudioBot 跑真实 HTTP 层，覆盖登录限流、点歌、切歌、排序、删除、搜索

### Changed
- Apple Music 搜索改为并行请求 hk/tw/us 三个商店，搜索结果上限提高到 50
- `/api/state` 增加 1.5 秒缓存 + 3 秒超时，机器人卡住时不再拖垮网页轮询
- 队列预取改为单工作线程 + 任务队列，点歌再多也不会堆线程

### Fixed
- worker 持锁调用机器人接口，机器响应慢时会阻塞整个面板
- 重启后面板可能残留 `downloading` 状态

## [1.0.0] - 2026-11-16

### Added
- 首个公开版本：插件式音源（网易云 / Apple Music）、Web 面板、队列状态机、内置媒体服务、systemd 部署
