# 插件开发

音源是插件：一个类，两个方法。核心不关心你从哪拿歌、怎么播放。

## 接口

    from .base import Plugin, PluginError

    class Plugin:
        id = ""        # 唯一 id，出现在 config 与前端
        title = ""     # 显示名，出现在网页标签上

        def __init__(self, conf, app_dir): ...
        def ready(self) -> tuple[bool, str]: ...        # (可用, 不可用原因)
        def describe(self) -> dict: ...                 # 默认实现即可
        def search(self, query: str, limit: int = 20) -> list[dict]: ...
        def lyrics(self, track_id: str) -> list[dict]: ...   # 可选，[{"t": 12.3, "text": "..."}]
        def prepare(self, track: dict, media) -> str: ...
        def prefetch(self, track, media) -> None: ...   # 可选
        def validate(self, track) -> str | None: ...    # 可选

## Track 字典

<code>search()</code> 返回的曲目会原样存进队列、原样回传给 <code>prepare()</code>，字段约定：

| 字段 | 必填 | 说明 |
|---|---|---|
| source | 是 | 插件 id，核心用它找插件 |
| id | 是 | 插件内部唯一，Apple 插件用它作缓存文件名 |
| name | 是 | 歌名 |
| artist / album | 否 | 展示用 |
| cover | 否 | 封面 URL |
| duration | 否 | 毫秒；机器人上报不了时长时用它兜底判断结束 |
| 其它 | 否 | 插件私有字段（Apple 用 url/storefront） |

## prepare 的返回值

- **远程地址**：返回 http(s) URL 即可，机器人自己拉流（网易云插件就是这样）
- **本地文件**：把文件写进任意目录，调 <code>media.add_root(目录)</code> 注册，再 <code>return media.url("文件名")</code>
  - 内置媒体服务支持 Range，ffmpeg 可以正常 seek
- 拿不到可播放地址时抛 <code>PluginError("原因")</code>，前端会提示、队列自动跳过

<code>prepare()</code> 在后台线程执行，可以慢（下载几十秒都行），不会卡住网页。

## prefetch

点歌时核心会立刻另起线程调用 <code>prefetch(track, media)</code>。
Apple 插件用它提前下载：等轮到这首歌时文件已经在本地，用户几乎感觉不到等待。
不是必需的，默认空实现。

## validate

<code>POST /api/add</code> 时调用，返回字符串表示拒绝（会作为 409 返回给前端）。
用来做「未登录不让点」「id 非法」这类前置检查。

## 注册

插件是**自动发现**的：把文件放进 <code>jukebox/plugins/</code>，类继承 <code>Plugin</code> 且 <code>id</code> 非空即可，
不需要改任何注册表。然后在 <code>config.toml</code> 的 <code>plugins.enabled</code> 里加上 id，
并提供 <code>[plugins.&lt;id&gt;]</code> 配置段（构造函数会收到这个字典）。

## 例子：本地音乐目录

    import os
    from .base import Plugin, PluginError

    class LocalPlugin(Plugin):
        id = "local"
        title = "本地曲库"

        def __init__(self, conf, app_dir):
            super().__init__(conf, app_dir)
            self.dir = conf.get("dir") or os.path.join(app_dir, "data/music")

        def search(self, query):
            out = []
            for name in os.listdir(self.dir):
                if query.lower() in name.lower():
                    out.append({"source": self.id, "id": name, "name": name})
            return out

        def prepare(self, track, media):
            path = os.path.join(self.dir, track["id"])
            if not os.path.exists(path):
                raise PluginError("文件不存在")
            media.add_root(self.dir)
            return media.url(track["id"])

配置：

    [plugins]
    enabled = ["local", "netease"]

    [plugins.local]
    dir = "/srv/music"

## 调试建议

- 面板日志：<code>journalctl -u ts3-jukebox -f</code>，<code>prepare</code> 抛错会打印 <code>prepare failed for ...</code>
- 单独测插件：

      python3 - <<'EOF'
      from jukebox.config import Config
      from jukebox.media import MediaServer
      from jukebox.plugins import create
      cfg = Config.load("config.toml")
      media = MediaServer(cfg.path(cfg.get("media", "dir"), "data/media"), port=8099).start()
      p = create("netease", cfg.plugin("netease"), cfg.base_dir)
      print(p.ready())
      print(p.search("周杰伦")[:2])
      print(p.prepare(p.search("周杰伦")[0], media))
      EOF
