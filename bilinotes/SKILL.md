---
name: bilinotes
description: Read and extract content from Bilibili videos for summarization, Q&A, and analysis. Use when the user provides a bilibili.com or b23.tv URL, or asks to watch/read/summarize/analyze a B站 video, or mentions "B站", "bilibili", or any URL containing "bilibili.com" or "b23.tv". Extracts subtitles (with Whisper fallback), danmaku, and comments.
---

# BiliNotes

Turn a Bilibili video URL into readable text for LLM summarization and Q&A.

## Workflow

1. If no cookie available, prompt user to run `--login` first
2. Run `extract.py` with the user's URL (and optional flags for danmaku/comments)
3. Use the JSON output as context to fulfill the user's request (summarize, answer questions, translate, etc.)

## Setup: Login (First Time)

```bash
uv run scripts/extract.py --login
```

Displays a QR code in terminal + saves a PNG. User scans with B站 APP, cookie auto-saved to `~/.bilinotes/cookie.json` for future use.

Cookie resolution order: CLI argument → `BILIBILI_SESSDATA` env var → `~/.bilinotes/cookie.json` → browser cookie auto-detection (Chrome/Safari via `browser_cookie3`).

## Extract Video Content

```bash
uv run scripts/extract.py <bilibili_url> [--danmaku] [--comments]
```

**Options:**
- `--danmaku` — Include danmaku (弹幕) content
- `--comments` — Include top comments with replies
- `--login` — QR code login flow
- Third positional arg: Whisper model (`tiny`/`base`/`small`/`medium`/`large`, default `base`)

**Output** — JSON with fields:
- `title`, `author`, `description`, `duration_seconds`, `bvid`, `aid`, `url`, `pages`
- `method` — `"subtitle"` or `"whisper"`
- `stat` — View/danmaku/reply/favorite/coin/like counts
- `content` — Full video text (subtitle or Whisper transcription)
- `danmaku` — (optional) Formatted danmaku text
- `comments` — (optional) Formatted comments with replies

**How it works:**
1. Resolve short URL → extract bvid
2. Fetch video metadata + stats via B站 API (WBI-signed)
3. Priority: `ai-zh` → `zh-CN` → `zh` subtitle → first available
4. Multi-page videos: extract subtitles per page, separated by `## Page Title`
5. No subtitles → download audio via yt-dlp → transcribe with Whisper
6. Optional: fetch danmaku (XML API) and/or comments (paginated)

## Fallback Dependencies

For videos without subtitles:

```bash
pip install yt-dlp openai-whisper
brew install ffmpeg
```

For browser cookie auto-detection (optional):

```bash
pip install browser_cookie3
```
