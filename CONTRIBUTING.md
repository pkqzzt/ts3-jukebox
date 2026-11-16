# 参与贡献

感谢愿意一起改进这个项目 🙌 下面是最短路径。

## 开发环境

    git clone https://github.com/pkqzzt/ts3-jukebox.git
    cd ts3-jukebox
    cp config.example.toml config.toml      # 改端口/密码，指向你本地的 TS3AudioBot
    python3 -m jukebox -c config.toml

只依赖 Python 3.11+ 标准库，不需要装任何第三方包。

## 跑测试

    python3 -m unittest discover -s tests -v

`tests/test_web.py` 会起一个假的 TS3AudioBot（HTTP 服务）和真实的面板 HTTP 服务，
覆盖登录限流、点歌、切歌、排序、删除、搜索等路径，不需要 TeamSpeak 或任何外部账号。

## 代码风格

- 只用标准库；新增依赖需要在 PR 里说明理由
- 4 空格缩进，行宽尽量 ≤ 100
- 用户可见文案用中文，注释/日志中英均可
- 插件必须实现 `search()` 和 `prepare()`，失败时抛 `PluginError` 而不是返回空串

## 提交信息

用 Conventional Commits 风格，中文或英文都可以：

    feat(netease): 支持按专辑搜索
    fix(web): 修复机器人超时导致的队列卡死
    docs: 补充 Apple Music cookies 导出步骤

## 新增音源插件

1. 在 `jukebox/plugins/` 下新建 `yourplugin.py`，继承 `Plugin`
2. 定义 `id`、`title`，实现 `search()` 与 `prepare()`
3. 在 `config.toml` 的 `plugins.enabled` 里加上 id（自动发现，无需改注册表）
4. 参考 [docs/plugin-dev.md](docs/plugin-dev.md)，附带一个最小测试

## 提交 PR 前

- [ ] `python3 -m unittest discover -s tests` 全绿
- [ ] `python3 -m compileall -q jukebox scripts` 无报错
- [ ] 更新 `CHANGELOG.md` 的 Unreleased 段
- [ ] 没有把 cookies、密码、服务器地址提交进来
