#!/usr/bin/env python3
"""Legend Archive official-channel scan (titles and runtimes only, nothing is downloaded).

Delta by default: lists only each channel's newest 150 uploads (YouTube lists newest first)
and adds the video IDs it has not seen before, stamped with first_seen. Known IDs are never
re-checked. A full listing runs once a month (or with --full) to catch deleted videos and
retitled episodes; it keeps every first_seen date.

Every run also reads the channel's members-only playlist and marks those uploads "locked": true, and reads the
description of each compilation once ("cq") for a chapter list: "chap": [[seconds, episode], ...].
Saves engine/scan/<name>.json: {name, url, channel, audio, scanned, last_full, uploads:[{id,t,d,first_seen,gone?,locked?,cq?,chap?}]}
"""
import datetime, json, os, subprocess, sys

ENG = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ENG, "scan")
sys.path.insert(0, ENG)
from refresh import ytdlp, log, load  # noqa: E402
# delta listing: newest first, stops at already-known videos

TODAY = datetime.date.today().isoformat()
DELTA_ITEMS = 150
# multi-episode uploads whose descriptions may list chapters ("EP1-10", "合集", "完整版", "Complete Series")
import re  # noqa: E402
COMPILATION = re.compile(r"EP\s*\d+\s*[-~–]\s*(?:EP)?\s*\d+|合集|完整版|全集|collection|complete series|full season|all episodes", re.I)
FULL_EVERY_DAYS = 30


def listing(url, limit=None, known=frozenset()):
    if os.environ.get("YT_API_KEY"):
        import ytapi
        res = ytapi.uploads(url.replace("/videos", ""), known=known, full=limit is None)
        return dict(channel=res["channel"]), [dict(id=i["id"], t=i["t"], d=i.get("d"), p=i.get("p"), chap=i.get("chap") or None)
                                              for i in res["items"]]
    cmd = [ytdlp(), "--flat-playlist", "-J", "--no-warnings"]
    if limit:
        cmd += ["--playlist-end", str(limit)]
    r = subprocess.run(cmd + [url], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:])
    j = json.loads(r.stdout)
    items = [dict(id=e["id"], t=e.get("title") or "", d=int(e["duration"]) if e.get("duration") else None)
             for e in (j.get("entries") or []) if e and e.get("id")]
    return j, items


def scan_channel(name, c, full):
    path = os.path.join(OUT, name + ".json")
    old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else None
    known = {v["id"]: v for v in (old or {}).get("uploads", [])}
    for v in known.values():
        v.setdefault("first_seen", "2026-09-28")
    if old and not old.get("last_full") and old.get("scanned"):
        old["last_full"] = old["scanned"]  # first scans were full listings
    full = full or old is None or not old.get("last_full") or \
        (datetime.date.today() - datetime.date.fromisoformat(old["last_full"][:10])).days >= FULL_EVERY_DAYS
    j, items = listing(c["url"].rstrip("/") + "/videos", None if full else DELTA_ITEMS, frozenset(known))
    new = [dict({k: x for k, x in v.items() if x is not None}, first_seen=TODAY) for v in items if v["id"] not in known]
    if full:
        seen = {v["id"] for v in items}
        for v in items:  # refresh titles/durations of known videos
            if v["id"] in known:
                known[v["id"]].update(t=v["t"] or known[v["id"]]["t"], d=v["d"] or known[v["id"]]["d"])
                known[v["id"]].pop("gone", None)
        gone = 0
        for vid, v in known.items():
            if vid not in seen and not v.get("gone"):
                v["gone"] = True
                gone += 1
    uploads = new + list(known.values())
    if os.environ.get("YT_API_KEY"):  # chapters of compilations seen before chapters were read (once per video)
        import ytapi
        todo = [v for v in uploads if "cq" not in v and not v.get("gone") and (v.get("d") or 0) >= 2400 and COMPILATION.search(v.get("t") or "")]
        try:
            for i in range(0, min(len(todo), 2000), 50):
                info = ytapi.details([v["id"] for v in todo[i:i + 50]])
                for v in todo[i:i + 50]:
                    v["cq"] = 1
                    ch = ytapi.chapters((info.get(v["id"]) or {}).get("description"))
                    if ch:
                        v["chap"] = ch
        except Exception as e:
            log(f"{name}: chapter backfill stopped: {e}")
    for v in new:
        v["cq"] = 1
    locked = set()
    if os.environ.get("YT_API_KEY"):  # every run: early-access videos turn free, new ones get locked
        import ytapi
        try:
            locked = ytapi.members_only(c["url"])
        except Exception as e:
            log(f"{name}: members-only list failed: {e}")
            locked = {v["id"] for v in uploads if v.get("locked")}
    for v in uploads:
        if v["id"] in locked:
            v["locked"] = True
        else:
            v.pop("locked", None)
    res = dict(name=name, url=c["url"], channel=j.get("channel") or j.get("uploader") or (old or {}).get("channel"),
               audio=c.get("audio"), scanned=datetime.datetime.now().isoformat(timespec="minutes"),
               last_full=datetime.datetime.now().isoformat(timespec="minutes") if full else old.get("last_full"),
               uploads=uploads)
    from refresh import write_lines
    write_lines(path, res)
    log(f"{name}: {'full' if full else 'delta'} listing, {len(new)} new" + (f", {gone} removed" if full else "") +
        f", {len(uploads)} known, {len(locked)} members-only")
    return len(new)


def main():
    cfg = load("config.json")
    os.makedirs(OUT, exist_ok=True)
    full = "--full" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    total_new = 0
    for name, c in cfg.get("candidates", {}).items():
        if only and name not in only:
            continue
        try:
            total_new += scan_channel(name, c, full)
        except Exception as e:
            log(f"{name}: scan failed: {e}")
    with open(os.path.join(OUT, "last_scan"), "w") as f:
        f.write(datetime.datetime.now().isoformat(timespec="minutes"))
    log(f"scan finished, {total_new} new official uploads")
    return total_new


if __name__ == "__main__":
    main()
    if "--no-quality" not in sys.argv:
        try:
            import quality
            quality.main(limit=None if "--full" in sys.argv else 150)
        except Exception as e:
            log(f"quality check failed: {e}")
