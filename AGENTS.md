# AGENTS.md

## Project

BiliNotes — opencode skill for reading Bilibili video content. Turn a video URL into readable text.

## Structure

- `bilinotes/SKILL.md` — Skill definition (frontmatter + workflow instructions)
- `bilinotes/scripts/extract.py` — Core extraction script (subtitles → Whisper fallback)

## Commands

### Login (first time)

```bash
uv run bilinotes/scripts/extract.py --login
```

### Extract video content

```bash
uv run bilinotes/scripts/extract.py <bilibili_url>
```

### With danmaku and comments

```bash
uv run bilinotes/scripts/extract.py <url> --danmaku --comments
```

### With custom Whisper model

```bash
uv run bilinotes/scripts/extract.py <url> <sessdata> <model>
```

Models: tiny, base, small, medium, large

## Dependencies

- Core: `requests`, `qrcode[pil]` (declared in script metadata, auto-installed by uv)
- Fallback (Whisper): `yt-dlp`, `openai-whisper`, `ffmpeg`
- Optional: `browser_cookie3` (auto-detect browser cookie)

## Testing

No test framework configured. Verify manually:

```bash
uv run bilinotes/scripts/extract.py --login
uv run bilinotes/scripts/extract.py "https://www.bilibili.com/video/BV1GJ411x7h7" --danmaku --comments
```

## Packaging

```bash
python3 ~/.config/opencode/skills/skill-creator/scripts/package_skill.py bilinotes/
```
