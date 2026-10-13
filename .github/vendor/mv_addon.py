#!/usr/bin/env python3
r"""Muvyo 第三方插件签名脚本（Python 3 + cryptography；带图标时还需要 Pillow）。

在 Muvyo「第三方插件 → 开发者」用 GitHub 账号领取证书时会下载签名凭据 muvyo-signing.json
（里面是作者证书和签名私钥），放在运行本脚本的目录即可。插件源码是一个文件夹：

  my-plugin/
    manifest.json      插件 ID 必须以你的命名空间开头，如 alice.search
                       更新时递增 version；可选 release_notes（最多 5000 字，纯文本）
                       与 min_mv_version（最低 Muvyo 版本，如 3.9.0）。这些声明会一起签名。
    main.js            入口文件（manifest 的 entry）
    README.md          可选
    icon.png           可选，在 manifest.json 中声明 "icon": "icon.png"
    mascot-idle.png    可选，慕慕形象立绘：在 capabilities.mascot.frames 里按动作声明，如
                       "mascot": {"name": "小雪", "frames": {"idle": "mascot-idle.png", "waveA": "mascot-wave.png"}}

  python3 mv_addon.py sign ./my-plugin                 # 加密代码并签名，写入插件库目录 ./dist（可用 -o 指定）
  python3 mv_addon.py verify ./dist/plugins/alice.search

签名结果是一个插件库：index.json + plugins/<插件ID>/（manifest.json、加密后的 encrypted.json、
README.md、可选图标、signature.json）。只把这些加密签名产物推到 GitHub 插件仓库，不上传 src、明文代码或签名凭据。
源码留在本地或独立私有开发仓库；发布流程不使用 --no-encrypt。Muvyo 里添加插件仓库地址就能安装。
图标只支持插件目录内的静态 PNG/JPEG/WebP，文件名仅字母、数字、短横线、下划线，扩展名小写；
不支持目录、外链或 SVG。原图最多 256 KB、宽高各不超过 1024 像素；建议使用正方形透明底 PNG。
带图标时先安装依赖：pip install cryptography Pillow。图标与代码一起签名，不需要额外联网权限；
Muvyo 验签后统一转换成最长边 128 像素的 PNG 展示。没有图标或头像加载失败仍显示文字头像。
慕慕形象：插件可以替换慕慕 AI 助手的名字和 / 或外观（能力不变），在 capabilities.mascot 里声明
"name"（最多 12 个字，只能用汉字、字母、数字、空格、间隔号与短横线）与 / 或 "frames"。立绘动作名：idle（待机，必填）、idle_blink、
idle_talk、look_left、look_upleft、look_right、waveA、waveB、point_left、popcorn、thumbs、jump、crouch、
sitsmile，缺的动作按相近动作回退到 idle。每张是插件目录内的静态透明 PNG/WebP，不超过 512 KB、宽高各不超过
2048 像素；建议 320×480、人物脚底贴着画面下沿、各帧同一比例。Muvyo 验签后统一放进 320×480 画布（等比缩放、
底边居中）。整个插件包不超过 8 MB。
凭据里有签名私钥：妥善保管，不要提交到仓库或发给别人；丢了就在 Muvyo 里重新领取，旧证书签过的插件照样有效。

纯命名能力（api: 1）：
  manifest.capabilities = {"naming": {"media_types": ["movie", "tv"]}}
  可与其它能力共存；纯命名插件 permissions.domains 可留空。
  main.js 定义 function naming(context)。一个命名方案只选一个插件，每次处理一个文件：
    null                              不修改，使用内置结果
    {vars: {audioCodec: "TrueHD.7.1"}}  合并展示变量，用原模板重新渲染
    {template: "{{name}}{{fileExt}}"}  只换模板，使用原变量
    {template: "...", vars: {...}}     同时修改模板和展示变量
    {rendered: "目录/文件名.mkv"}       直接返回最终相对路径
  rendered 不可与 template/vars 混用，不接受其他字段。失败停止当前文件，不静默回落。
  不支持草案里的 renameFiles、插件链、upstream、post_replace 或 mv.words。
  context 的只读字段为 media_type、tmdb_id、title、original_title、year、season、
  episodes（全部集号数组）、part（无分卷为 0）、source_name（不带路径的原文件名）、
  template（本次原模板）、rendered（内置相对路径）、category（二级分类）、vars（原模板变量）。
  vars 包含 title/original_title/name/en_name/year/tmdbid/season/episode/season_episode/
  resolution/videoFormat/resourceType/videoCodec/audioCodec/releaseGroup/part/effect/edition/
  customization/webSource/episode_title/fileExt；不含 original_name 或源目录。
  返回的 vars 只允许展示文字（至多 32 项、每项 1024 字符），可新增简单变量名，
  不能覆盖作品身份、类型、年份、季集、多集范围、分卷、扩展名或原文件名；
  不允许路径、地址、凭据字段、控制字符、数组或对象。
  mv.config 只包含本插件声明并通过校验的非敏感设置（如分隔符、字段选择和模板文本）：
  secret、URL、服务地址、凭据命名的字段及未知字段不提供。mv.service 始终为空，
  mv.fetch 与 mv.storage.get/set/remove 均拒绝；插件的其它能力不受这些调用级限制。
  输入递归冻结。命名执行最多 3 秒，输入/返回/安全配置分别最多 16 KiB。
  模板不是完整 Jinja2：最多 4096 字符、512 个 AST 节点、嵌套深度 16。
  只支持文本、{{变量}}、if/elif/else、and/or/not、标量比较，以及固定展示过滤器：
  lower、upper、title、trim（无参数）；default('兜底', true)；replace('原文', '替换', 次数)。
  过滤器参数只能是字面常量；default 参数可省略，replace 次数可省略且最大 4096。
  禁止循环、函数调用、属性/下标访问、容器、算术、赋值、宏、导入、包含和继承；
  不支持 format/attr 等其它过滤器，变量与每一步过滤展开都有长度上限。
  mv.render(template, vars) 在 Muvyo 主进程用同一有界渲染器计算并校验相对路径。
  参数可省略（或 template 传 undefined 使用原模板）；单次命名最多调用 4 次，
  计入同一个 3 秒时限。若要对新渲染结果做正则，在 QuickJS 中处理后返回 rendered：
    function naming(c) {
      const vars = {audioCodec: String(c.vars.audioCodec || '').replace(/\s+/g, mv.config.separator || '.')};
      const rendered = mv.render(undefined, vars);
      return {rendered: rendered.replace(/Atmos/gi, 'ATMOS')};
    }
  原模板不在上述支持子集内时同样拒绝；不把 Python 正则或通用 Jinja2 执行能力交给插件。
  最终路径至多 12 层目录，每段最多 240 UTF-8 字节，完整相对路径最多 1024 字节。
  不允许绝对路径、. / ..、控制字符、段内分隔符、系统保留名称或首尾空格。
  扩展名原样保留；剧集必须保留 S01E01（多集 S01E01-E03 或 S01E01E03），
  分卷保留 part1 等标识，不得增加、删除或变更这些身份标识。

定时任务与沙箱缓存（api: 1）：
  manifest.capabilities.tasks = [
    {"id": "refresh", "title": "更新热门片单", "description": "刷新片单缓存", "interval_minutes": 60}
  ]
  最多 8 个任务；id 为英文字母开头的字母、数字或下划线，最多 40 字符。
  main.js 定义 function scheduledTask(args)，args.task 是声明的任务 id。
  任务默认关闭，由管理员设置 5–10080 分钟间隔；同插件任务不重叠，不补跑错过的周期。
  可使用原有 mv.fetch 联网能力，但仍受管理员批准的网站、服务地址、次数及执行时限限制。
  任务与手动调用一样核验授权、启停和吊销状态；不能启动常驻线程或自己设置定时器。
  mv.cache.get(key) 返回 JSON 副本，未命中或过期返回 null。
  mv.cache.set(key, value, ttl_seconds) 暂存 JSON 值；mv.cache.delete(key) 暂存删除。
  set/delete 返回 null，只有整个调用成功且提交时权限仍有效才原子发布；
  调用失败、超时、取消或配额不足不发布本次缓存改动，旧值仍按原有效期过期。
  key 为 ASCII 字母或数字开头，后续可含字母、数字、点、下划线、冒号、短横线，
  共 1–128 字符；ttl_seconds 必填整数 1–604800，自 set 调用时起算。
  单条最多 256 KiB；每插件最多 20 MiB / 512 条；全部插件合计 64 MiB / 4096 条。
  mv.cache.limits 是只读的当前配额（entry_bytes、plugin_bytes、plugin_entries、transfer_bytes、
  operations、max_ttl_seconds，单位为字节、条或秒），可据此规划体积；旧版 Muvyo 没有这个对象，
  每插件按 8 MiB 兜底。
  JSON 深度最多 32、节点最多 32768；每次调用最多 1024 次缓存操作、传输 16 MiB。
  缓存由主程序按插件隔离并加密保存，重启可复用；不能指定路径或读其他插件的数据。
  插件更新、卸载或配置/服务身份变化会清掉其缓存；缓存不是永久业务数据存储。
  命名调用不能使用缓存；其它调用即使命中缓存，也不能绕过授权和权限校验。
  任务成功（即使未写 mv.cache）会失效本插件的 Muvyo 内容结果缓存；
  其它调用成功写缓存后也会失效本插件的内容结果缓存，不影响其它插件。
  播放直链不应长期缓存。定时刷新失败时不要先删旧值，也不要把失败结果作为正常数据提交。
  示例（与 content 能力共同声明）：
    function scheduledTask(args) {
      if (args.task !== 'refresh') throw new Error('Unknown task');
      const r = mv.fetch({url: 'https://api.example.org/catalog'});
      if (r.status !== 200) throw new Error('Refresh failed');
      const page = JSON.parse(r.body);
      if (!page || !Array.isArray(page.items)) throw new Error('Invalid catalog');
      mv.cache.set('catalog', page, 7200);
      return null;
    }
    function contentList(args) {
      const page = mv.cache.get('catalog');
      if (page === null) throw new Error('Please refresh the catalog first');
      return page;
    }
  远端 catalog 必须符合内容库列表协议；正式插件应按分类/页码隔离缓存键，
  未命中时自行取回数据，不应把空列表兜底当作成功刷新。

Muvyo 事件（api: 1）：
  manifest.capabilities.webhook = {"events": ["organize.completed", "subscription.completed"]}
  可选事件（与「Webhook 推送」同一套事件名）：
    media.uploaded / media.upload_failed / media.upload_skipped   上传成功、失败、跳过
    strm.generated / strm.failed                                  STRM 生成、失败（全量生成会逐个文件报）
    library.sync_completed / library.sync_failed                  文件同步、媒体库扫描完成或失败
    organize.completed / organize.failed                          整理完成、失败
    subscription.completed / subscription.failed                  订阅完成、失败
    download.completed / download.failed                          下载、离线、BT 完成或失败
    backup.completed / backup.failed                              备份完成、失败
    webhook.received                                              收到媒体服务器的 Webhook
  媒体服务器的入库、播放、标记已看等事件（library.new、playback.* 等）已下线：旧包里的这些声明
  安装时忽略，不再投递。main.js 定义 function webhookEvent(e)。管理员要在插件设置里打开
  「接收 Muvyo 事件」（安装后默认关）；更新版本新增事件时，开关会被关掉，等管理员重新确认。
  e 的字段：
    event   事件名
    time    事件转交时间（ISO 8601，带时区）
    data    事件内容，只含事件实际带的字段：
            source        来源模块，如 upload / organize / strm / subscription / backup
            status        结果状态；reason 为失败原因代码（如 search_failed）
            title, media_type, tmdb_id, season, episode, year   作品信息
            file_name     文件名（不含目录）；storage_type 网盘类型（如 115）
            library_name  媒体库名称；backup_type 备份类型（local / cloud）
            size, files, directories, created, skipped, failed, success,
            completed, total, elapsed   数量、体积（字节）、耗时（秒）
            webhook.received 另有 event_type（媒体服务器事件名）、item_name、item_type、server
  不提供文件路径、目录、网盘实例、任务与记录编号。投递在后台进行，业务不等待插件；
  单次最多 30 秒（不超过运行设置的时限）；每个插件同时最多处理 2 个事件，
  插件忙或排队过多时本次事件直接丢弃，不补发，不会挤占插件的搜索、播放等调用。
  返回值被忽略；可用 mv.fetch 推送到已声明的网站，也可用 mv.storage / mv.cache 记录状态。
    function webhookEvent(e) {
      if (e.event !== 'organize.completed' || !e.data.tmdb_id) return null;
      mv.fetch({url: 'https://api.example.org/notify', method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({tmdb: e.data.tmdb_id, type: e.data.media_type,
                                      season: e.data.season, title: e.data.title})});
      return null;
    }

使用 Muvyo 的服务（permissions.muvyo）：
  请 Muvyo 用用户已经配好的实例办事，插件不用自己再要账号。manifest 里声明要用的服务：
    "permissions": {"domains": [], "muvyo": ["library.lookup", "telegram.search", "share.inspect"]}
  管理员安装 / 更新时逐项确认后才生效；新版本新增的服务在确认更新前用不了。凭据和登录会话不进沙箱，
  插件只拿到下面这些结果。mv.can('library.lookup') 判断这一项是否已授权，没授权的调用会抛出异常。
  命名插件与「测试运行环境」时不能使用。
    mv.library.lookup({tmdb_id: 1399, type: 'tv', season: 1})        查媒体库（Emby / Jellyfin / Plex / Vyo 合并）
      tmdb_id、season 必须是数字（'1399' 这样的字符串会被拒绝）。
      → {tmdb_id, type, exists, complete, season, episodes: [1, 2, ...]}；电影没有 season / episodes。
      也可以一次传一组（最多 20 部），按顺序返回一组。complete=false 表示有媒体服务器没答上来。
    mv.telegram.search({keyword: '示例', limit: 20})                  搜用户配置的公开 / 私有频道（limit 1–50）
      → {items: [{channel, date, title, text, share_link?, pan_type?, share_code?, magnets?}], failed}
      只搜频道，不经搜索机器人；failed 为没搜成的频道数。
    mv.share.inspect({url: 'https://115.com/s/xxxx', code: 'ab12'})   用同一家网盘的账号读分享（不转存）
      → {valid: true, drive, title, total, files: [{name, size, dir}]}（第一页，最多 100 个）
      或 {valid: false, drive, reason}（reason 为「分享已失效」「提取码不对」）；读取失败会抛异常，不代表分享无效。
  上限：每次调用 library.lookup 5 次、telegram.search 2 次、share.inspect 5 次；每个插件每分钟
  查 200 部 / 搜 6 次 / 读 12 次，所有插件另有合计上限；同一部片、关键词、分享短时间内重复查询直接用上次的结果。参数多给字段、类型不对都会被拒绝。
  别把查询结果原样写进日志。
"""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import sys
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# 与 app/services/addons/author_authority.py 一致（tests/test_addon_author_signing.py 校验）
ROOT_PUBLIC_KEY_B64 = "8M+V4JhFIeXuXlUck07OXcXutKzTfdN3WL+NgsUYFh4="
SIGNATURE_FILE = "signature.json"
CERT_PREFIX = b"Muvyo addon author v1\x00"
PACKAGE_PREFIX = b"Muvyo addon package v1\x00"
ENCRYPTED_FILE = "encrypted.json"
SEAL_INFO = b"Muvyo addon code v1"


CREDENTIAL_FILE = "muvyo-signing.json"
MAX_FILE = 1024 * 1024
ALLOWED = {"manifest.json", "README.md", SIGNATURE_FILE, ENCRYPTED_FILE}
MAX_ICON_BYTES = 256 * 1024
ICON_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}\.(?:png|jpg|jpeg|webp)")


def check_icon(manifest, files):
    name = manifest.get("icon")
    if name is None:
        return
    if not isinstance(name, str) or not ICON_NAME.fullmatch(name):
        raise SystemExit("icon 必须是插件目录内的 PNG、JPEG 或 WebP 文件名，不支持目录、外链或 SVG")
    data = files.get(name)
    if data is None:
        raise SystemExit("缺少 manifest.json 声明的图标文件")
    if len(data) > MAX_ICON_BYTES:
        raise SystemExit("插件图标不能超过 256 KB")
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("带图标的插件需要 Pillow，请先运行 pip install Pillow") from None
    try:
        with Image.open(io.BytesIO(data), formats=["PNG", "JPEG", "WEBP"]) as image:
            expected = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP"}[name.rsplit(".", 1)[1]]
            if image.format != expected:
                raise SystemExit("插件图标的实际格式与文件扩展名不一致")
            if not (0 < image.width <= 1024 and 0 < image.height <= 1024):
                raise SystemExit("插件图标的宽高不能超过 1024 像素")
            if getattr(image, "n_frames", 1) != 1:
                raise SystemExit("插件图标只支持静态图片")
            image.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise SystemExit("插件图标不是有效的 PNG、JPEG 或 WebP 图片") from None


MASCOT_FRAMES = ("idle", "idle_blink", "idle_talk", "look_left", "look_upleft", "look_right", "waveA", "waveB",
                 "point_left", "popcorn", "thumbs", "jump", "crouch", "sitsmile")
MAX_MASCOT_BYTES = 512 * 1024
MASCOT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}\.(?:png|webp)")
MASCOT_TITLE = re.compile(r"[\w·\- ]{1,12}")


def mascot_files(manifest):
    """capabilities.mascot.frames 里声明的 {动作: 文件名}；没有声明返回空。"""
    mascot = (manifest.get("capabilities") or {}).get("mascot")
    if mascot is None:
        return {}
    if not isinstance(mascot, dict):
        raise SystemExit("capabilities.mascot 必须是对象")
    name = mascot.get("name")
    if name is not None and (not isinstance(name, str) or not MASCOT_TITLE.fullmatch(name) or not name.strip()
                             or "_" in name):
        raise SystemExit("慕慕的名字最多 12 个字，只能用汉字、字母、数字、空格、间隔号与短横线")
    frames = mascot.get("frames")
    if frames is None:
        if name is None:
            raise SystemExit("capabilities.mascot 至少要提供名字（name）或立绘（frames）")
        return {}
    if not isinstance(frames, dict) or "idle" not in frames:
        raise SystemExit("capabilities.mascot.frames 必须按动作声明图片，并且包含待机帧 idle")
    unknown = set(frames) - set(MASCOT_FRAMES)
    if unknown:
        raise SystemExit("不支持的慕慕动作：" + "、".join(sorted(unknown)))
    names = list(frames.values())
    if len(names) != len(set(names)):
        raise SystemExit("慕慕形象每个动作要用不同的图片文件")
    for name in names:
        if not isinstance(name, str) or not MASCOT_NAME.fullmatch(name):
            raise SystemExit("慕慕形象图片必须是插件目录内的 PNG 或 WebP 文件名，不支持目录、外链或 SVG")
    return frames


def check_mascot(manifest, files):
    frames = mascot_files(manifest)
    if not frames:
        return
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("带慕慕形象的插件需要 Pillow，请先运行 pip install Pillow") from None
    for name in frames.values():
        data = files.get(name)
        if data is None:
            raise SystemExit(f"缺少 manifest.json 声明的慕慕形象图片 {name}")
        if len(data) > MAX_MASCOT_BYTES:
            raise SystemExit(f"慕慕形象图片 {name} 不能超过 512 KB")
        try:
            with Image.open(io.BytesIO(data), formats=["PNG", "WEBP"]) as image:
                if image.format != {"png": "PNG", "webp": "WEBP"}[name.rsplit(".", 1)[1]]:
                    raise SystemExit(f"慕慕形象图片 {name} 的实际格式与文件扩展名不一致")
                if not (0 < image.width <= 2048 and 0 < image.height <= 2048):
                    raise SystemExit(f"慕慕形象图片 {name} 的宽高不能超过 2048 像素")
                if getattr(image, "n_frames", 1) != 1:
                    raise SystemExit(f"慕慕形象图片 {name} 只支持静态图片")
                image.load()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise SystemExit(f"慕慕形象图片 {name} 不是有效的 PNG 或 WebP 图片") from None
    if sum(len(data) for data in files.values()) > 8 * 1024 * 1024:
        raise SystemExit("整个插件包不能超过 8 MB，请压缩慕慕形象图片")


def read_file(path, limit=MAX_FILE):
    if os.path.islink(path) or not os.path.isfile(path):
        raise SystemExit(f"{path} 不是普通文件")
    with open(path, "rb") as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:
        raise SystemExit(f"{os.path.basename(path)} 过大")
    return data


def read_source(folder):
    """从插件源码目录读清单、入口、可选说明和声明的图标，其它文件忽略。"""
    if not os.path.isdir(folder):
        raise SystemExit(f"找不到插件源码目录 {folder}")
    try:
        manifest = json.loads(read_file(os.path.join(folder, "manifest.json")).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SystemExit("manifest.json 不是有效的 JSON") from None
    entry = manifest.get("entry", "main.js")
    if not isinstance(entry, str) or "/" in entry or "\\" in entry or entry in ALLOWED:
        raise SystemExit("manifest.json 的 entry 必须是插件目录下的一个 JS 文件名")
    files = {"manifest.json": read_file(os.path.join(folder, "manifest.json")),
             entry: read_file(os.path.join(folder, entry))}
    if os.path.exists(os.path.join(folder, "README.md")):
        files["README.md"] = read_file(os.path.join(folder, "README.md"))
    icon = manifest.get("icon")
    if icon is not None:
        if not isinstance(icon, str) or not ICON_NAME.fullmatch(icon):
            raise SystemExit("icon 必须是插件目录内的 PNG、JPEG 或 WebP 文件名，不支持目录、外链或 SVG")
        files[icon] = read_file(os.path.join(folder, icon), MAX_ICON_BYTES)
    check_icon(manifest, files)
    for name in mascot_files(manifest).values():
        if name in files:
            raise SystemExit(f"慕慕形象图片 {name} 不能与清单、入口、说明或图标同名")
        files[name] = read_file(os.path.join(folder, name), MAX_MASCOT_BYTES)
    check_mascot(manifest, files)
    return manifest, files


def seal(code, manifest, cert):
    """与 Muvyo 客户端 app/services/addons/sealing.py 同一格式：X25519 + HKDF-SHA256 + AES-256-GCM。"""
    recipient = X25519PublicKey.from_public_bytes(base64.b64decode(cert["content_key"]))
    ephemeral = X25519PrivateKey.generate()
    raw = lambda key: key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)  # noqa: E731
    epk = raw(ephemeral.public_key())
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=epk + raw(recipient), info=SEAL_INFO).derive(
        ephemeral.exchange(recipient))
    nonce = os.urandom(12)
    aad = json.dumps({"plugin_id": manifest["id"], "version": manifest["version"], "entry": manifest.get("entry", "main.js"),
                      "author_id": cert["author_id"], "key_version": cert["content_key_version"]},
                     sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return json.dumps({"version": 1, "alg": "x25519-hkdf-sha256-aes256gcm", "key_version": cert["content_key_version"],
                       "epk": base64.b64encode(epk).decode(), "nonce": base64.b64encode(nonce).decode(),
                       "ciphertext": base64.b64encode(AESGCM(key).encrypt(nonce, code, aad)).decode()}, indent=1).encode()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def public_b64(key):
    return base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                          serialization.PublicFormat.Raw)).decode()


def check_certificate(envelope):
    cert = envelope["certificate"]
    if not ROOT_PUBLIC_KEY_B64:
        raise SystemExit("这个版本的工具没有内置 Muvyo 根公钥，无法校验作者证书")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(ROOT_PUBLIC_KEY_B64)).verify(
            base64.b64decode(envelope["signature"]), CERT_PREFIX + canonical_json(cert))
    except (InvalidSignature, ValueError):
        raise SystemExit("作者证书不是 Muvyo 签发的") from None
    if time.time() >= cert["expires_at"]:
        raise SystemExit("作者证书已过期，请重新领取")
    return cert


def load_credential(path):
    try:
        with open(path, encoding="utf-8") as fh:
            credential = json.load(fh)
        envelope = credential["certificate"]
        key = serialization.load_pem_private_key(credential["private_key"].encode(), password=None)
    except FileNotFoundError:
        raise SystemExit(f"找不到签名凭据 {path}：把领取证书时下载的 {CREDENTIAL_FILE} 放到当前目录，"
                         "或用 -c 指定位置") from None
    except (OSError, ValueError, KeyError, TypeError):
        raise SystemExit(f"签名凭据读取失败：请使用在 Muvyo 里领取证书时下载的 {CREDENTIAL_FILE}") from None
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("签名凭据里的私钥无效")
    return envelope, key


def update_index(repo, manifest, rel_path):
    path = os.path.join(repo, "index.json")
    index = {"name": "", "sequence": 0, "plugins": []}
    if os.path.exists(path):
        try:
            index = json.loads(read_file(path, 1024 * 1024).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise SystemExit(f"{path} 不是有效的 JSON，请修好或删掉后重试") from None
    entry = {"id": manifest["id"], "name": manifest.get("name") or manifest["id"], "version": manifest["version"],
             "description": manifest.get("description", ""), "author": manifest.get("author", ""),
             "path": rel_path, "api": manifest.get("api", 1)}
    plugins = [p for p in index.get("plugins", []) if isinstance(p, dict) and p.get("id") != manifest["id"]]
    index["plugins"] = sorted(plugins + [entry], key=lambda p: str(p.get("id")))
    index["sequence"] = int(index.get("sequence") or 0) + 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    if index.get("public_key"):
        print("注意：index.json 带仓库签名公钥，请重新生成 index.json.sig，否则已添加这个仓库的 Muvyo 会拒绝读取")


def sign(args):
    envelope, key = load_credential(args.credential)
    cert = check_certificate(envelope)
    if public_b64(key) != cert["public_key"]:
        raise SystemExit("私钥与证书不匹配")
    manifest, files = read_source(args.source)
    plugin_id, version = manifest.get("id"), manifest.get("version")
    if not isinstance(plugin_id, str) or not isinstance(version, str):
        raise SystemExit("manifest.json 缺少 id 或 version")
    if not plugin_id.startswith(cert["namespace"] + ".") or "/" in plugin_id or ".." in plugin_id:
        raise SystemExit(f"插件 ID 必须以你的命名空间「{cert['namespace']}.」开头，如 {cert['namespace']}.search")
    entry = manifest.get("entry", "main.js")
    if not args.no_encrypt:
        if not cert.get("content_key"):
            raise SystemExit("这张证书不支持加密，请在 Muvyo 里重新领取证书后再签名发布")
        files[ENCRYPTED_FILE] = seal(files.pop(entry), manifest, cert)
    payload = {"plugin_id": plugin_id, "version": version,
               "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    document = {"version": 1, "certificate": envelope, "payload": payload,
                "signature": base64.b64encode(key.sign(PACKAGE_PREFIX + canonical_json(payload))).decode()}
    rel_path = "plugins/" + plugin_id
    target = os.path.join(args.output, "plugins", plugin_id)
    os.makedirs(target, exist_ok=True)
    # 清掉上一次签名留下的文件（比如从不加密切到加密后残留的明文入口）
    for name in os.listdir(target):
        full = os.path.join(target, name)
        if os.path.isfile(full) and not os.path.islink(full):
            os.remove(full)
    for name, data in files.items():
        with open(os.path.join(target, name), "wb") as fh:
            fh.write(data)
    with open(os.path.join(target, SIGNATURE_FILE), "w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False, indent=1)
    update_index(args.output, manifest, rel_path)
    print(f"已签名：{plugin_id} {version}" + ("（代码已加密）" if ENCRYPTED_FILE in files else "（代码未加密）"))
    print(f"插件库目录：{os.path.abspath(args.output)}，推到 GitHub 仓库后在 Muvyo 里添加这个仓库即可安装")


def verify(args):
    folder = args.folder
    try:
        document = json.loads(read_file(os.path.join(folder, SIGNATURE_FILE), 64 * 1024).decode("utf-8"))
        listed = document["payload"]["files"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError):
        raise SystemExit("signature.json 格式不正确") from None
    cert = check_certificate(document["certificate"])
    files = {}
    for name in listed:
        if "/" in name or "\\" in name or name.startswith("."):
            raise SystemExit("签名里的文件名不合规")
        files[name] = read_file(os.path.join(folder, name), 2 * MAX_FILE)
    manifest = json.loads(files["manifest.json"])
    check_icon(manifest, files)
    check_mascot(manifest, files)
    if not manifest["id"].startswith(cert["namespace"] + "."):
        raise SystemExit(f"插件 ID 不在作者命名空间「{cert['namespace']}.」内，Muvyo 会拒绝安装")
    expected = {"plugin_id": manifest["id"], "version": manifest["version"],
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    if document["payload"] != expected:
        raise SystemExit("插件文件与签名不符")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(cert["public_key"])).verify(
            base64.b64decode(document["signature"]), PACKAGE_PREFIX + canonical_json(expected))
    except InvalidSignature:
        raise SystemExit("签名无效") from None
    print(f"签名有效：{manifest['id']} {manifest['version']}，作者 {cert['author']}（证书 #{cert['serial']}）"
          + ("，代码已加密" if ENCRYPTED_FILE in files else "，代码未加密"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Muvyo 第三方插件作者工具")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sign", help="加密代码并签名，写入插件库目录")
    p.add_argument("source", help="插件源码目录（manifest.json + 入口 JS，可带 README.md、声明的图标与慕慕形象）")
    p.add_argument("-o", "--output", default="dist", help="插件库目录，默认 ./dist")
    p.add_argument("-c", "--credential", default=CREDENTIAL_FILE, help=f"签名凭据，默认 ./{CREDENTIAL_FILE}")
    p.add_argument("--no-encrypt", action="store_true", help="不加密代码（默认用证书里的加密公钥加密）")
    p.set_defaults(func=sign)
    p = sub.add_parser("verify", help="检查插件库里某个插件目录的签名")
    p.add_argument("folder", help="如 ./dist/plugins/alice.search")
    p.set_defaults(func=verify)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
