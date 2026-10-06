#!/usr/bin/env python3
"""Mature section tagger: asks AniList which series are adult-oriented story-driven titles and where to watch them.

Writes engine/mature.json {series_key: {"mature": bool, "watch": [{"site","url"}], "checked": date}} (delta only:
a series is looked up once, then again after RECHECK_DAYS). refresh.py overlays it on curated meta, and hand
settings in curated.json always win. Anything AniList flags adult is never tagged; this section is not explicit.
Standard library only. Needs network access to graphql.anilist.co (GitHub Actions has it).
"""
import datetime, json, os, re, sys, time, urllib.request

ENG = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(ENG, "mature.json")
URL = "https://graphql.anilist.co"
RECHECK_DAYS = 90
PER_RUN = 150  # AniList allows about 90 requests a minute
QUERY = """query($s:String){Media(search:$s,type:ANIME){title{romaji english} isAdult genres
  tags{name rank} externalLinks{site url type}}}"""
MATURE_TAGS = {"Seinen": 50, "Josei": 50, "Gore": 60}


def lookup(name):
    req = urllib.request.Request(URL, json.dumps({"query": QUERY, "variables": {"s": name}}).encode(),
                                 {"Content-Type": "application/json", "User-Agent": "legend-archive"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["Media"]


def judge(media):
    """(mature, watch links) from one AniList Media record."""
    if not media or media.get("isAdult"):
        return False, []
    tags = {t["name"]: t["rank"] for t in media.get("tags") or []}
    mature = any(tags.get(n, 0) >= r for n, r in MATURE_TAGS.items())
    watch = [{"site": l["site"], "url": l["url"]} for l in media.get("externalLinks") or []
             if l.get("type") == "STREAMING" and str(l.get("url", "")).startswith("https://")]
    return mature, watch


def load():
    return json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else {}


def overlay(cur):
    """Merge mature.json into cur["meta"] without overriding anything set by hand."""
    meta = cur.setdefault("meta", {})
    for k, v in load().items():
        m = meta.setdefault(k, {})
        if v.get("mature"):
            m.setdefault("mature", True)
        if v.get("watch"):
            m.setdefault("watch", v["watch"])


def main(cur=None):
    cur = cur or json.load(open(os.path.join(ENG, "curated.json"), encoding="utf-8"))
    done, today = load(), datetime.date.today()
    todo = [(k, m["name"]) for k, m in cur.get("meta", {}).items()
            if m.get("name") and not m.get("hide") and (m.get("origin") in ("JP", None))
            and not re.search(r"\(English Dub\)", m["name"])
            and (k not in done or (today - datetime.date.fromisoformat(done[k]["checked"])).days >= RECHECK_DAYS)]
    n = 0
    for k, name in todo[:PER_RUN]:
        try:
            mature, watch = judge(lookup(name))
        except Exception as e:
            print(f"mature: {name}: {e}")
            continue
        done[k] = {"mature": mature, "watch": watch, "checked": today.isoformat()}
        n += 1
        time.sleep(0.8)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=0, sort_keys=True)
    return n


if __name__ == "__main__":
    print(f"mature: {main()} looked up")
