#!/usr/bin/env python3
"""Legend Archive quality check: quality animation >> AI-made >> AI slop.

For one representative video per series (first episode of each official playlist, and each
first-season upload on the dub channels) it reads the video's details and its top 60 comments
(metadata and text only, nothing is downloaded), then scores:

  - comments that call it AI / AI voice / slop / soulless (and whether they complain)
  - comments praising the animation itself
  - "#ai" or "AI" in the title, tags or description
  - likes per 1,000 views

Results are cached in engine/scan/quality.json, so each video is checked once.
Labels: "quality", "ai" (AI-made but watchable), "slop" (hidden from the archive).
"""
import json, os, re, subprocess, sys, time

ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENG)
from refresh import ytdlp, log, load, season_of  # noqa: E402

CACHE = os.path.join(ENG, "scan", "quality.json")
AI = re.compile(r"\bai\b|a\.i\.|\bartificial\b|ai[- ]generated|\bgenerated\b|chatgpt|midjourney|sora\b|robot(ic)? voice|"
                r"\btts\b|text[- ]to[- ]speech|synthetic voice|ai voice|ai art|ai anim|same face|6 fingers|six fingers|morphing", re.I)
SLOP = re.compile(r"slop|soulless|lazy|garbage|trash|unwatchable|cringe|stolen|scam|clickbait|report(ed)?\b|dislike|"
                  r"ruin|stop using|can'?t watch|hurts? my (eyes|ears)|disgusting|low effort|cheap", re.I)
GOOD = re.compile(r"animation (is|looks|was|quality)|beautiful(ly)? animated|art ?style|masterpiece|fight scene|"
                  r"choreograph|studio|cgi (is|looks) (great|good|amazing)|quality|gorgeous|stunning", re.I)


def details(vid):
    if os.environ.get("YT_API_KEY"):
        import ytapi
        info = ytapi.details([vid]).get(vid)
        if not info:
            raise RuntimeError("video not available")
        return dict(title=info["title"], description=info["description"], tags=info["tags"],
                    view_count=info["views"], like_count=info["likes"],
                    comments=[dict(text=t) for t in ytapi.comments(vid)])
    r = subprocess.run([ytdlp(), "--skip-download", "--write-comments", "--no-warnings",
                        "--extractor-args", "youtube:comment_sort=top;max_comments=60,60,0,0",
                        "-J", "https://www.youtube.com/watch?v=" + vid],
                       capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-200:])
    return json.loads(r.stdout)


def score(j):
    cs = [c.get("text") or "" for c in (j.get("comments") or [])]
    n = max(len(cs), 1)
    ai = [c for c in cs if AI.search(c)]
    slop = [c for c in ai if SLOP.search(c)] + [c for c in cs if re.search(r"\bslop\b", c, re.I) and c not in ai]
    good = [c for c in cs if GOOD.search(c) and not AI.search(c)]
    meta = " ".join([j.get("title") or "", j.get("description") or "", " ".join(j.get("tags") or [])])
    self_ai = bool(re.search(r"#ai\b|\bai[- ]generated\b|\bmade with ai\b|\bai animation\b", meta, re.I))
    views, likes = j.get("view_count") or 0, j.get("like_count") or 0
    lpk = round(likes * 1000 / views, 1) if views else None
    if len(slop) >= 3 or len(slop) / n >= 0.08:
        label = "slop"
    elif self_ai or len(ai) / n >= 0.05 or len(ai) >= 4:
        label = "ai"
    else:
        label = "quality"
    return dict(label=label, comments=len(cs), ai=len(ai), slop=len(slop), good=len(good), self_ai=self_ai,
                views=views, likes_per_k=lpk, upload_date=j.get("upload_date"),
                samples=[c[:140] for c in (slop or ai)[:4]])


def representatives():
    """(video id, source) pairs: the first free episode of every official series, then each
    first-season upload on the dub channels."""
    reps = []
    try:
        import refresh, tiers
        cur = load("curated.json") or {}
        for s in tiers.official_series(refresh.genre, refresh.PAL, refresh.split_title, cur.get("meta", {})):
            first = s["seas"][0]["eps"][0] if s["seas"][0].get("eps") else s["seas"][0]["pick"]
            reps.append((first["id"], "official:" + s["key"]))
    except Exception as e:
        log(f"quality: could not list official series: {e}")
    st = load("videos.json") or {"videos": {}}
    for vid, v in st["videos"].items():
        if not v.get("gone") and season_of(v["title"]) == 1:
            reps.append((vid, v["ch"]))
    seen, out = set(), []
    for r in reps:
        if r[0] not in seen:
            seen.add(r[0]); out.append(r)
    return out


def main(limit=None):
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    todo = [(v, s) for v, s in representatives() if v not in cache]
    if limit:
        todo = todo[:limit]
    log(f"quality check: {len(todo)} new videos to check ({len(cache)} cached)")
    for i, (vid, src) in enumerate(todo, 1):
        try:
            cache[vid] = dict(source=src, **score(details(vid)))
        except Exception as e:
            if type(e).__name__ == "QuotaError":
                log("quality check: API quota reached, continuing tomorrow")
                break
            cache[vid] = dict(source=src, label="unknown", error=str(e)[-120:])
        if i % 10 == 0 or i == len(todo):
            from refresh import write_lines
            write_lines(CACHE, cache)
            log(f"quality check: {i}/{len(todo)}")
        time.sleep(0 if os.environ.get("YT_API_KEY") else 0.7)
    tally = {}
    for v in cache.values():
        tally[v["label"]] = tally.get(v["label"], 0) + 1
    log(f"quality check done: {tally}")


if __name__ == "__main__":
    main()
