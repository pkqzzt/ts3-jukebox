# Changelog

本文件记录所有值得注意的变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [1.4.0] - 2026-11-17

### Added
- 公共歌单：歌单视图里「发布到服务器」，所有人共享（`GET/POST /api/public_playlists`、`POST /api/public_playlists/delete`）
- 公共歌单以带「公共」标记的胶囊展示，点击即可浏览并逐首点歌/插播
- 服务器端保存在 `data/public_playlists.json`，最多 50 个歌单、每个 300 首

## [1.3.1] - 2026-11-17

### Fixed
- 去掉右上角重复的「＋ 歌单」入口，只保留歌单胶囊里的「＋ 导入歌单」

## [1.3.0] - 2026-11-17

### Changed
- 歌单常驻前台：保存过的歌单以胶囊按钮显示在搜索框上方，点击即可在左侧列出全部曲目并逐首点歌/插播
- 导入歌单后自动跳转到该歌单视图，导入弹窗只保留「解析 + 管理」

### Fixed
- 删除歌单时左侧歌单视图会停留在已删除的内容上

## [1.2.1] - 2026-11-17

### Fixed
- 网易云歌单解析没带 MUSIC_U cookie，私密歌单（例如「我喜欢的音乐」）会报 401「该歌单已被创建者设置为隐私」
- 网易云接口报错时直接显示接口返回的中文原因，而不是 `HTTP Error 401: Unauthorized`
- 新增 `playlist_id()` 单元测试，覆盖带 `&uct2=` 等跟踪参数的分享链接

## [1.2.0] - 2026-11-17

### Added
- 歌单功能：粘贴网易云 / Apple Music 歌单链接，解析后保存在浏览器本地，可逐首点歌/插播或整单加入（`GET /api/playlist`、`POST /api/add_bulk`）
- 媒体服务可拆成独立进程（`python -m jukebox.media` + `ts3-jukebox-media.service`），面板重启不再中断正在播放的歌曲

### Changed
- `[media] embedded` 配置项，默认 true（面板内嵌），可切换为独立服务

## [1.1.2] - 2026-11-17

### Added
- 进度调节：点击/拖动进度条跳转，另有 −10s / +10s 按钮（`POST /api/seek`）

### Fixed
- 桌面端双栏布局下「正在播放」卡片被 flex 压缩、标题与控制按钮被裁掉
- 机器人命令返回 204 时被误判为失败（seek/pause 等无响应体的命令）

## [1.1.1] - 2026-11-17

### Changed
- 桌面端改为左右两栏独立滚动：搜索结果、正在播放/队列/历史各自滚动，滚右栏不再需要等左栏到底
- 移除音量滑杆（后端 /api/volume 保留）

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
