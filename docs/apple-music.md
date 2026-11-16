# Apple Music 插件部署

Apple Music 的音频流是 DRM（Widevine）加密的，浏览器里能听，但不能像网易云那样直接拿一条
CDN 直链丢给播放器。所以 Apple 音源的链路是：

    iTunes 搜索 → gamdl 用你的账号下载并解密成 m4a → 面板内置媒体服务 → TS3AudioBot 播放

这套东西需要三样：**gamdl**、**Apple Music 会员账号的 cookies**、**面板里的路径配置**。

## 1. 安装 gamdl

    python3 -m venv /opt/gamdl/venv
    /opt/gamdl/venv/bin/pip install -U pip
    /opt/gamdl/venv/bin/pip install "gamdl[widevine]"

<code>[widevine]</code> 会带上 pywidevine 和内置的 L3 设备，Apple 的流就靠它解密。
装完验证：

    /opt/gamdl/venv/bin/gamdl --version

> 如果没有预编译 wheel，pip 会尝试从源码编译，需要 Rust 工具链。Debian 12 + Python 3.11 一般直接有 wheel。

## 2. 准备 gamdl 配置

复制 <code>examples/gamdl.yml</code> 到 <code>/opt/gamdl/gamdl.yml</code>，至少改两处：

    auth:
      mode: cookies
      cookies_path: /opt/gamdl/cookies.txt
    output:
      directory: /var/cache/applemusic

其余保持默认即可：AAC 优先、不写数据库、不存歌词、并发 1 首 / 4 分片（小内存机器友好）。

## 3. 导出 cookies

1. 用电脑浏览器打开 https://music.apple.com 并登录（账号需要有效会员）
2. 安装扩展：
   - Chrome / Edge：[Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - Firefox：[Export Cookies](https://addons.mozilla.org/addon/export-cookies-txt)
3. 在 music.apple.com 页面导出 <code>cookies.txt</code>（Netscape 格式）
4. 上传到服务器并收紧权限：

       scp cookies.txt root@your-server:/opt/gamdl/cookies.txt
       chmod 600 /opt/gamdl/cookies.txt

cookies 里必须有 <code>media-user-token</code> 这一条，否则 gamdl 无法鉴权。

## 4. 校验

仓库自带一个校验脚本，用 gamdl 的 venv 跑：

    /opt/gamdl/venv/bin/python scripts/apple/check_auth.py /opt/gamdl/cookies.txt

输出示例：

    {"ok": true, "storefront": "cn", "subscription": true, "name": "", "checked": 1794836067}

- <code>storefront</code>：你账号的商店区域，后面下载和「跨商店匹配」都依赖它
- <code>subscription</code>：是否确认有有效会员
- cookies 一般几个月有效，失效后重新导出覆盖，再跑一次校验即可（面板每 6 小时自动复检）

## 5. 接到面板

<code>/opt/jukebox/config.toml</code>：

    [plugins.applemusic]
    gamdl = "/opt/gamdl/venv/bin/gamdl"
    python = "/opt/gamdl/venv/bin/python"
    gamdl_config = "/opt/gamdl/gamdl.yml"
    cookies = "/opt/gamdl/cookies.txt"
    checker = "scripts/apple/check_auth.py"
    finder = "scripts/apple/find_track.py"
    status_file = "data/apple_status.json"
    cache = "/var/cache/applemusic"
    log = "data/apple_download.log"

重启面板，打开网页，Apple Music 标签不再是「离线」，就说明接好了。

## 6. 商店差异（重要）

搜索走的是 Apple 公开的 iTunes Search API，只能查 hk / tw / us 三个商店（大陆商店没有开放搜索接口）。
而你的账号可能在 cn 商店，**同一首歌在不同商店的 catalog id 不同，版权也不同**。

现象：点了周杰伦的歌，gamdl 报 <code>Media is unavailable in this storefront</code>。

处理：面板会自动调用 <code>scripts/apple/find_track.py</code>，用「歌名 / 歌手 / 专辑」在你账号的商店里
再搜一次，按相似度挑最像的一首，用新 id 重新下载。对用户来说只是多等几秒（多花 10 秒左右）。

匹配阈值：歌名相似度 ≥ 0.55 参与打分，总分 = 0.62×歌名 + 0.24×歌手 + 0.14×专辑。
如果匹配错了，可以手动用 gamdl 下载后把文件放进缓存目录（文件名 = 原曲目 id + <code>.m4a</code>）。

## 7. 缓存

下载的文件放在 <code>cache</code> 目录，命名 <code>&lt;trackId&gt;.m4a</code>，由面板的媒体服务直接提供给机器人。
超过 <code>max_files</code>（默认 400）或 <code>max_gigabytes</code>（默认 4）会按最后访问时间删最旧的。
同一首歌第二次点歌直接命中缓存，不重复下载。

## 8. 常见错误

| 报错 | 原因 / 处理 |
|---|---|
| authentication rejected (HTTP 403) | cookies 过期或账号无会员，重新导出 |
| Media is unavailable in this storefront | 见第 6 节；兜底后仍失败说明账号商店也没版权 |
| No usable DRM initialization data | 该曲目没有 Widevine 流（少见），换一首 |
| gamdl 下载超时 | 网络或 Apple 风控，可在 config 里调大 timeout |
| Unable to load the provisioned DRM device | pywidevine 没装好，重装 gamdl[widevine] |
