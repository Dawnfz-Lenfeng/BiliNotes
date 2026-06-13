# BiliNotes

让 AI 能"看"B站视频。

给定一个B站视频URL，自动提取视频的文本内容（字幕/弹幕/评论），用于总结、问答、翻译等场景。

## 为什么需要这个？

B站视频是一个封闭的信息源——你不能"搜索"视频里的内容，不能"引用"视频里说过的话。BiliNotes 把视频变成文本，让 AI 可以像阅读文章一样阅读视频。

与其他B站工具不同，BiliNotes 不是API浏览器，而是视频阅读器：一条命令，一个输出，不需要理解B站API。

## 快速开始

### 1. 首次使用：登录B站

```bash
uv run bilinotes/scripts/extract.py --login
```

终端会显示二维码，用B站APP扫码即可。Cookie 自动保存到 `~/.bilinotes/cookie.json`，后续无需重复登录。

> 也可以手动设置环境变量：`export BILIBILI_SESSDATA="你的SESSDATA"`

### 2. 提取视频内容

```bash
uv run bilinotes/scripts/extract.py "https://www.bilibili.com/video/BVxxxxxx"
```

也支持 `b23.tv` 短链接。

### 3. 可选参数

```bash
# 附带弹幕内容
uv run bilinotes/scripts/extract.py "https://..." --danmaku

# 附带评论内容
uv run bilinotes/scripts/extract.py "https://..." --comments

# 同时获取弹幕和评论
uv run bilinotes/scripts/extract.py "https://..." --danmaku --comments
```

## 工作原理

```
B站视频URL
    ↓
1. 解析URL → 提取视频ID
    ↓
2. 获取视频元数据（标题、UP主、播放数据等）
    ↓
3. 提取字幕（优先 ai-zh → zh-CN → zh）
    ↓  无字幕？
4. 下载音频 → Whisper 转写为文字
    ↓
5. 输出完整 JSON
```

## 输出格式

| 字段 | 说明 |
|------|------|
| `title` | 视频标题 |
| `author` | UP主 |
| `description` | 视频简介 |
| `duration_seconds` | 时长（秒） |
| `bvid` / `aid` | 视频ID |
| `url` | 视频URL |
| `pages` | 分P数量 |
| `method` | 提取方式：`subtitle` 或 `whisper` |
| `stat` | 播放/弹幕/评论/收藏/投币/点赞数 |
| `content` | 视频全文文本 |
| `danmaku` | 弹幕文本（需 `--danmaku`） |
| `comments` | 评论文本（需 `--comments`） |

## Cookie 说明

程序按以下顺序查找B站Cookie：

1. **命令行参数** — `uv run extract.py <url> <sessdata>`
2. **环境变量** — `BILIBILI_SESSDATA`
3. **本地缓存** — `~/.bilinotes/cookie.json`（扫码登录后自动保存）
4. **浏览器Cookie** — 自动从 Chrome/Safari 读取（需安装 `browser_cookie3`）

首次使用建议运行 `--login` 扫码，一劳永逸。

## 音频转写（兜底方案）

当视频没有字幕时，自动使用 yt-dlp 下载音频 + Whisper 转写。需要额外安装：

```bash
pip install yt-dlp openai-whisper
brew install ffmpeg
```

可通过参数指定 Whisper 模型大小（默认 `base`）：

```bash
uv run bilinotes/scripts/extract.py "https://..." "" "small"
```

可选模型：`tiny`、`base`、`small`、`medium`、`large`

## 作为 opencode Skill 使用

本项目是一个 opencode skill。安装后在 opencode 中可直接使用：

1. 将 `bilinotes/` 目录放到 `~/.config/opencode/skills/` 下
2. 提供B站链接，skill 自动触发提取
3. 提取内容后直接进行总结、问答、翻译等

## 项目结构

```
bilinotes/
├── SKILL.md          # opencode skill 定义
└── scripts/
    └── extract.py    # 核心提取脚本
```
