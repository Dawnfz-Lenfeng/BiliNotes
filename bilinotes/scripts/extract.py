# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests>=2.28",
#   "qrcode[pil]>=7.4",
# ]
# ///

import hashlib
import json
import os
import re
import sys
import tempfile
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}

API_VIEW = "https://api.bilibili.com/x/web-interface/view"
API_PLAYER_V2 = "https://api.bilibili.com/x/player/v2"
API_PLAYER_WBI = "https://api.bilibili.com/x/player/wbi/v2"
API_NAV = "https://api.bilibili.com/x/web-interface/nav"
API_DANMAKU = "https://api.bilibili.com/x/v1/dm/list.so"
API_COMMENTS = "https://api.bilibili.com/x/v2/reply"
API_QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
API_QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"

COOKIE_DIR = Path.home() / ".bilinotes"
COOKIE_FILE = COOKIE_DIR / "cookie.json"

COOKIE_HELP = (
    "请先登录B站账号。运行: uv run extract.py --login\n"
    "或手动设置环境变量: export BILIBILI_SESSDATA=\"你的SESSDATA\""
)

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

SUBTITLE_LANG_PRIORITY = ("ai-zh", "zh-CN", "zh")


# ── Cookie Management ──────────────────────────────────────────


def save_cookie(sessdata: str, extra: dict | None = None):
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    data = {"SESSDATA": sessdata}
    if extra:
        data.update(extra)
    COOKIE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.chmod(COOKIE_FILE, 0o600)
    print(f"[OK] Cookie已保存到 {COOKIE_FILE}", file=sys.stderr)


def load_cookie() -> str:
    if COOKIE_FILE.exists():
        try:
            data = json.loads(COOKIE_FILE.read_text())
            return data.get("SESSDATA", "")
        except Exception:
            pass
    return ""


def _extract_cookie_from_browser(cookie_fn) -> str:
    try:
        import browser_cookie3
        cj = cookie_fn(domain_name=".bilibili.com")
        for c in cj:
            if c.name == "SESSDATA":
                return c.value
    except Exception:
        pass
    return ""


def try_browser_cookie() -> str:
    import browser_cookie3
    for fn in [browser_cookie3.chrome, browser_cookie3.edge, browser_cookie3.safari]:
        val = _extract_cookie_from_browser(fn)
        if val:
            return val
    return ""


def get_sessdata(cli_arg: str = "") -> str:
    if cli_arg:
        return cli_arg
    env = os.environ.get("BILIBILI_SESSDATA", "")
    if env:
        return env
    saved = load_cookie()
    if saved:
        return saved
    return try_browser_cookie()


# ── QR Code Login ──────────────────────────────────────────────


def qr_login():
    print("正在生成B站登录二维码...", file=sys.stderr)
    resp = requests.get(API_QR_GENERATE, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"生成二维码失败: {data.get('message', 'unknown')}")

    qrcode_url = data["data"]["url"]
    qrcode_key = data["data"]["qrcode_key"]

    import qrcode
    qr = qrcode.QRCode(border=1)
    qr.add_data(qrcode_url)
    qr.make(fit=True)
    qr.print_ascii(out=sys.stderr, invert=True)

    png_path = COOKIE_DIR / "login_qr.png"
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(str(png_path))
    print(f"\n二维码已保存到: {png_path}", file=sys.stderr)

    try:
        subprocess.run(["open", str(png_path)], capture_output=True)
    except Exception:
        pass

    print("\n请用B站APP扫描二维码登录（3分钟内有效）...", file=sys.stderr)

    for _ in range(60):
        time.sleep(3)
        poll_resp = requests.get(
            API_QR_POLL,
            params={"qrcode_key": qrcode_key},
            headers=HEADERS,
            timeout=15,
        )
        poll_data = poll_resp.json()
        status = poll_data.get("data", {}).get("code", 0)

        if status == 0:
            sessdata = ""
            extra = {}
            for c in poll_resp.cookies:
                if c.name == "SESSDATA":
                    sessdata = c.value
                elif c.name == "bili_jct":
                    extra["bili_jct"] = c.value
                elif c.name == "DedeUserID":
                    extra["DedeUserID"] = c.value
            if not sessdata:
                cookie_header = poll_resp.headers.get("Set-Cookie", "")
                m = re.search(r"SESSDATA=([^;]+)", cookie_header)
                if m:
                    sessdata = m.group(1)
            if sessdata:
                save_cookie(sessdata, extra)
                print("\n登录成功！", file=sys.stderr)
                return sessdata
            else:
                raise RuntimeError("登录成功但未获取到SESSDATA")

        elif status == 86038:
            raise RuntimeError("二维码已过期，请重新运行 --login")
        elif status == 86090:
            print("已扫码，请在手机上确认登录...", file=sys.stderr)

    raise RuntimeError("登录超时，请重新运行 --login")


# ── WBI Signing ────────────────────────────────────────────────


def get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def get_wbi_keys(sessdata: str = "") -> tuple[str, str]:
    cookies = make_cookies(sessdata)
    resp = requests.get(API_NAV, headers=HEADERS, cookies=cookies, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    wbi_img = data.get("data", {}).get("wbi_img", {})
    img_url = wbi_img.get("img_url", "")
    sub_url = wbi_img.get("sub_url", "")
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    return img_key, sub_key


def sign_wbi_params(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = get_mixin_key(img_key + sub_key)
    params = dict(params)
    params["wts"] = int(time.time())
    params = {k: v for k, v in sorted(params.items())}
    filtered = {}
    for k, v in params.items():
        v_str = str(v)
        for ch in "!'()*":
            v_str = v_str.replace(ch, "")
        filtered[k] = v_str
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in sorted(filtered.items()))
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    filtered["w_rid"] = w_rid
    return filtered


# ── URL Parsing ────────────────────────────────────────────────


def extract_bvid(url: str) -> str:
    m = re.search(r"BV[\w]+", url)
    if m:
        return m.group(0)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "bvid" in qs:
        return qs["bvid"][0]
    path_parts = parsed.path.strip("/").split("/")
    for part in path_parts:
        if part.startswith("BV"):
            return part
    return ""


def resolve_short_url(url: str) -> str:
    if "b23.tv" in url:
        resp = requests.head(url, allow_redirects=True, headers=HEADERS, timeout=10)
        return str(resp.url)
    return url


def make_cookies(sessdata: str) -> dict:
    return {"SESSDATA": sessdata} if sessdata else {}


# ── Video Info ─────────────────────────────────────────────────


def get_video_info(bvid: str, sessdata: str = "") -> dict:
    params = {"bvid": bvid}
    cookies = make_cookies(sessdata)
    resp = requests.get(API_VIEW, params=params, headers=HEADERS, cookies=cookies, timeout=15)
    if resp.status_code == 412:
        raise RuntimeError(f"请求被B站拒绝(412)，需要登录态。\n{COOKIE_HELP}")
    resp.raise_for_status()
    data = resp.json()
    if data["code"] != 0:
        msg = data.get("message", "unknown")
        if "登录" in msg or "权限" in msg or data["code"] in (-352, -403, 62002):
            raise RuntimeError(f"B站API错误: {msg}\n{COOKIE_HELP}")
        raise RuntimeError(f"B站API错误: {msg}")
    return data["data"]


# ── Subtitles ──────────────────────────────────────────────────


def get_subtitle_info(bvid: str, cid: int, sessdata: str = "") -> list:
    cookies = make_cookies(sessdata)
    params = {"bvid": bvid, "cid": cid}

    try:
        img_key, sub_key = get_wbi_keys(sessdata)
        signed = sign_wbi_params(params, img_key, sub_key)
        resp = requests.get(API_PLAYER_WBI, params=signed, headers=HEADERS, cookies=cookies, timeout=15)
    except Exception:
        resp = requests.get(API_PLAYER_V2, params=params, headers=HEADERS, cookies=cookies, timeout=15)

    if resp.status_code == 412:
        raise RuntimeError(f"请求被B站拒绝(412)，需要登录态。\n{COOKIE_HELP}")
    resp.raise_for_status()
    data = resp.json()
    if data["code"] != 0:
        msg = data.get("message", "unknown")
        if "登录" in msg or "权限" in msg:
            raise RuntimeError(f"获取字幕失败: {msg}\n{COOKIE_HELP}")
        return []
    subtitle = data.get("data", {}).get("subtitle", {})
    return subtitle.get("subtitles", [])


def download_subtitle_text(subtitle_url: str) -> str:
    if subtitle_url.startswith("//"):
        subtitle_url = "https:" + subtitle_url
    resp = requests.get(subtitle_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    subtitle_data = resp.json()
    body = subtitle_data.get("body", [])
    lines = []
    for item in body:
        content = item.get("content", "").strip()
        if content:
            lines.append(content)
    return "\n".join(lines)


def pick_subtitle(subtitles: list) -> dict | None:
    for lang in SUBTITLE_LANG_PRIORITY:
        for sub in subtitles:
            if sub.get("subtitle_lang") == lang:
                return sub
    return subtitles[0] if subtitles else None


# ── Danmaku ────────────────────────────────────────────────────


def get_danmaku(cid: int, sessdata: str = "") -> list[str]:
    cookies = make_cookies(sessdata)
    try:
        resp = requests.get(API_DANMAKU, params={"oid": cid}, headers=HEADERS, cookies=cookies, timeout=15)
        resp.raise_for_status()
    except Exception:
        return []

    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)
        danmakus = []
        for d in root.findall(".//d"):
            text = d.text
            if text and text.strip():
                danmakus.append(text.strip())
        return danmakus
    except Exception:
        return []


def format_danmaku(danmakus: list[str], max_count: int = 200) -> str:
    if not danmakus:
        return ""
    selected = danmakus[:max_count]
    return "\n".join(f"[弹幕] {d}" for d in selected)


# ── Comments ───────────────────────────────────────────────────


def get_comments(oid: int, sessdata: str = "", max_pages: int = 5) -> list[dict]:
    cookies = make_cookies(sessdata)
    all_comments = []

    for page in range(1, max_pages + 1):
        params = {"type": 1, "oid": oid, "pn": page, "ps": 20, "sort": 1}
        try:
            resp = requests.get(API_COMMENTS, params=params, headers=HEADERS, cookies=cookies, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        if data.get("code") != 0:
            break

        replies = data.get("data", {}).get("replies") or []
        if not replies:
            break

        for r in replies:
            comment = {
                "user": r.get("member", {}).get("uname", ""),
                "content": r.get("content", {}).get("message", ""),
                "like": r.get("like", 0),
            }
            sub_replies = r.get("replies") or []
            if sub_replies:
                comment["replies"] = [
                    {
                        "user": sr.get("member", {}).get("uname", ""),
                        "content": sr.get("content", {}).get("message", ""),
                    }
                    for sr in sub_replies
                ]
            all_comments.append(comment)

        page_info = data.get("data", {}).get("page", {})
        total = page_info.get("count", 0)
        if page * 20 >= total:
            break

    return all_comments


def format_comments(comments: list[dict], max_count: int = 30) -> str:
    if not comments:
        return ""
    lines = []
    for c in comments[:max_count]:
        lines.append(f"@{c['user']}: {c['content']} (👍{c['like']})")
        for r in c.get("replies", [])[:5]:
            lines.append(f"  ↳ @{r['user']}: {r['content']}")
    return "\n".join(lines)


# ── Whisper Fallback ───────────────────────────────────────────


def whisper_transcribe(audio_path: str, model_size: str = "base") -> str:
    try:
        import whisper
    except ImportError:
        raise RuntimeError("whisper未安装。请运行: pip install openai-whisper")
    model = whisper.load_model(model_size)
    result = model.transcribe(audio_path, language="zh")
    return result["text"].strip()


def download_audio_with_ytdlp(url: str, output_dir: str, sessdata: str = "") -> str:
    try:
        subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("yt-dlp未安装。请运行: pip install yt-dlp 或 brew install yt-dlp")

    output_template = str(Path(output_dir) / "audio.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "-o", output_template,
        "--no-playlist",
    ]
    if sessdata:
        cmd += ["--add-header", f"Cookie: SESSDATA={sessdata}"]
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "412" in stderr or "Precondition Failed" in stderr:
            raise RuntimeError(f"yt-dlp下载被B站拒绝(412)，需要登录态。\n{COOKIE_HELP}")
        raise RuntimeError(f"yt-dlp下载失败: {stderr}")
    audio_file = Path(output_dir) / "audio.mp3"
    if not audio_file.exists():
        for ext in ["m4a", "webm", "opus", "wav"]:
            alt = Path(output_dir) / f"audio.{ext}"
            if alt.exists():
                audio_file = alt
                break
    if not audio_file.exists():
        raise RuntimeError("音频下载失败，找不到输出文件")
    return str(audio_file)


# ── Main Extract ───────────────────────────────────────────────


def extract(
    url: str,
    sessdata: str = "",
    whisper_model: str = "base",
    include_danmaku: bool = False,
    include_comments: bool = False,
) -> dict:
    url = resolve_short_url(url)
    bvid = extract_bvid(url)
    if not bvid:
        raise RuntimeError(f"无法从URL中提取bvid: {url}")

    info = get_video_info(bvid, sessdata)
    aid = info.get("aid", 0)
    title = info.get("title", "")
    author = info.get("owner", {}).get("name", "")
    desc = info.get("desc", "")
    duration = info.get("duration", 0)
    stat = info.get("stat", {})
    pages = info.get("pages", [])

    all_content = []
    method = ""

    for i, page in enumerate(pages):
        cid = page.get("cid")
        page_title = page.get("part", "")
        if not cid:
            continue

        subtitles = get_subtitle_info(bvid, cid, sessdata)
        sub = pick_subtitle(subtitles)
        page_content = ""

        if sub:
            subtitle_url = sub.get("subtitle_url", "")
            if subtitle_url:
                page_content = download_subtitle_text(subtitle_url)
                if not method:
                    method = "subtitle"

        if not page_content and i == 0:
            with tempfile.TemporaryDirectory() as tmpdir:
                page_url = url if len(pages) == 1 else f"{url}?p={i + 1}"
                audio_path = download_audio_with_ytdlp(page_url, tmpdir, sessdata)
                page_content = whisper_transcribe(audio_path, whisper_model)
                if not method:
                    method = "whisper"

        if len(pages) > 1 and page_title:
            all_content.append(f"## {page_title}\n{page_content}")
        else:
            all_content.append(page_content)

    content = "\n\n".join(all_content)

    result = {
        "title": title,
        "author": author,
        "description": desc,
        "duration_seconds": duration,
        "bvid": bvid,
        "aid": aid,
        "url": url,
        "pages": len(pages),
        "method": method,
        "stat": {
            "view": stat.get("view", 0),
            "danmaku": stat.get("danmaku", 0),
            "reply": stat.get("reply", 0),
            "favorite": stat.get("favorite", 0),
            "coin": stat.get("coin", 0),
            "like": stat.get("like", 0),
        },
        "content": content,
    }

    if include_danmaku and pages:
        danmakus = get_danmaku(pages[0]["cid"], sessdata)
        result["danmaku"] = format_danmaku(danmakus)

    if include_comments and aid:
        comments = get_comments(aid, sessdata)
        result["comments"] = format_comments(comments)

    return result


# ── CLI ────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print(
            "用法:\n"
            "  uv run extract.py <bilibili_url> [options]    提取视频内容\n"
            "  uv run extract.py --login                     扫码登录B站\n"
            "\n"
            "选项:\n"
            "  --login          扫码登录，保存Cookie\n"
            "  --danmaku        附带弹幕内容\n"
            "  --comments       附带评论内容\n"
            "  [sessdata]       手动传入SESSDATA\n"
            "  [model]          Whisper模型: tiny/base/small/medium/large",
            file=sys.stderr,
        )
        sys.exit(1)

    if "--login" in sys.argv:
        try:
            qr_login()
        except Exception as e:
            print(f"登录失败: {e}", file=sys.stderr)
            sys.exit(1)
        return

    url = sys.argv[1]
    include_danmaku = "--danmaku" in sys.argv
    include_comments = "--comments" in sys.argv

    positional = [a for a in sys.argv[2:] if not a.startswith("--")]
    sessdata_arg = ""
    whisper_model = "base"
    for arg in positional:
        if arg in ("tiny", "base", "small", "medium", "large"):
            whisper_model = arg
        elif not sessdata_arg:
            sessdata_arg = arg

    sessdata = get_sessdata(sessdata_arg)

    if not sessdata:
        print("未检测到B站Cookie，部分功能可能受限。运行以下命令登录:", file=sys.stderr)
        print("  uv run extract.py --login", file=sys.stderr)
        print(file=sys.stderr)

    try:
        result = extract(url, sessdata, whisper_model, include_danmaku, include_comments)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
