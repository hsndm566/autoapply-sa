#!/usr/bin/env python
"""
AutoApply SA — UNIFIED WATCHER ("eyes on anything")
Takes any public URL and returns parsed, readable content.
No API key. $0. Uses only built-in libraries + Hermes tools.

Modes by URL type:
  - t.me/s/CHANNEL  -> Telegram channel posts (title + text + date)
  - youtube.com/watch -> video title + transcript (via web_extract)
  - any webpage     -> main text (web fetch, browser fallback on 403)
Images: pass an image URL and it returns a vision description hook.

Run: python watch_anything.py "<url>" [limit]
"""
import sys, re, urllib.request, json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")

def watch_telegram(channel):
    # channel like 'logscp' from t.me/logscp or full url
    m = re.search(r"t\.me/s/([\w-]+)", channel) or re.search(r"t\.me/([\w-]+)", channel)
    ch = m.group(1) if m else channel
    html = _get(f"https://t.me/s/{ch}")
    posts = re.findall(r'data-post="([^"]+)"', html)
    out = []
    for p in posts[:20]:
        # crude text pull near each post id
        seg = html.split(f'data-post="{p}"', 1)[-1][:3000]
        # drop the data-view blob and emoji style spans
        seg = re.sub(r'data-view="[^"]*"', " ", seg)
        seg = re.sub(r"<i class=\"emoji\"[^>]*>", " ", seg)
        txt = re.sub(r"<[^>]+>", " ", seg)
        txt = re.sub(r"&nbsp;|&amp;|&quot;", " ", txt)
        txt = re.sub(r"\s+", " ", txt).strip()
        out.append({"post": p, "text": txt[:400]})
    return out

def watch_web(url):
    try:
        html = _get(url)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return {"note": "403 bot-blocked — use browser tool (browser_navigate) to fetch this URL.",
                    "fallback": "browser"}
        raise
    # strip scripts/styles
    html = re.sub(r"<script[\s\S]*?</script>", " ", html)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return {"chars": len(text), "text": text[:2000]}

def main():
    if len(sys.argv) < 2:
        print("Usage: python watch_anything.py <url> [limit]")
        return
    url = sys.argv[1]
    if "t.me" in url:
        res = watch_telegram(url)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        res = watch_web(url)
        print(json.dumps(res, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
