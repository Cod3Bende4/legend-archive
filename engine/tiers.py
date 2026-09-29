#!/usr/bin/env python3
"""Legend Archive tiers: official-channel series (episode mode) and the 7-tier ranking.

Audio classes
  A1  original background audio + English audio   (official English-dub channels)
  A2  original background audio + English subs    (official studio channels)
  A3  English dub without original background audio (the four dub channels)

Shelves
  1 Epic, English audio   A1, completed, 10h+, rated 7.5+
  2 Epic, subtitled       A2, completed, 10h+, rated 7.5+
  3 Epic, dubbed          A3, 10h+
  4 Long, English audio   A1, completed, 5h+, rated 7.5+
  5 Long, subtitled       A2, completed, 5h+, rated 7.5+
  6 Long, dubbed          A3, 5h+
  7 Short picks           A1/A2, completed, under 5h, rated 7.5+
  8 Ongoing               A1/A2, not finished yet, rated 7.5+ or not rated yet
  9 Awaiting review       A1/A2, not rated yet (Claude rates these on its scheduled runs)
  10 Extras               A3 under 5h
  hidden                  AI slop, rated under 7.5, or hidden by hand

Per-series facts that need judgment (rating, completed, display name, hide) live in
curated.json under "meta", keyed by each series' "key". Claude's scheduled runs fill them in.
"""
import hashlib, json, os, re

ENG = os.path.dirname(os.path.abspath(__file__))

SEASON_WORDS = re.compile(
    r"\b(season|s)\s*0*(\d+)\b|第\s*(\d+)\s*季|\bpart\s*(\d+)\b", re.I)
JUNK = re.compile(
    r"【[^】]*】|\[[^\]]*\]|\((?:[^)]*(?:sub|dub|eng|multi|full|4k|1080|ep|episode|trailer)[^)]*)\)|"
    r"\b(eng(lish)?\s*sub(bed|s)?|multi\s*sub|full\s*(version|episodes?|movie)?|all\s*episodes?|"
    r"4k|1080p|hd|uhd|donghua|anime|chinese animation|official|playlist|collection|compilation|"
    r"episodes?\s*\d+\s*[-~]\s*\d+|ep\s*\d+\s*[-~]\s*\d+|marathon)\b", re.I)
EPNUM = re.compile(r"\b(?:ep(?:isode)?\.?\s*|第\s*)(\d{1,4})", re.I)
SKIP = re.compile(r"trailer|teaser|pv\b|preview|opening|ending|\bop\b|\bed\b|ost|mv\b|behind the scenes|shorts|clip|highlight", re.I)


def norm_name(title):
    t = JUNK.sub(" ", title)
    t = SEASON_WORDS.sub(" ", t)
    t = re.sub(r"[|｜:：\-–—·•,，!！?？]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def key_of(name):
    return re.sub(r"[^a-z0-9一-鿿]+", "", name.lower())[:60]


def season_num(title):
    m = SEASON_WORDS.search(title)
    if m:
        for g in m.groups()[1:]:
            if g:
                return int(g)
    m = re.search(r"\b(\d)\s*$", norm_name(title))
    return 1


def fmt(s):
    s = s or 0
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def official_series(genre, PAL, split_title, meta=None):
    """Group every official upload into series > seasons > episodes by parsing its title.

    Skips trailers, clips, OSTs, members-only and Chinese-subtitle-only uploads. Individual episodes win;
    multi-episode "EP31-40" uploads fill gaps; whole-season uploads count only when a season has nothing else.
    meta[key]["merge_into"] folds one series key into another (for naming variants).
    """
    import difflib
    import epparse
    meta = meta or {}
    scan_dir = os.path.join(ENG, "scan")
    if not os.path.isdir(scan_dir):
        return []
    chans = []
    for f in sorted(os.listdir(scan_dir)):
        if f.endswith(".json") and f != "quality.json":
            chans.append(json.load(open(os.path.join(scan_dir, f), encoding="utf-8")))
    epparse.learn(v["t"] for s in chans for v in s.get("uploads", []))
    by = {}
    for s in chans:
        cname = re.sub(r"\s*-\s*(get|chinese).*$", "", s.get("channel") or s["name"], flags=re.I).strip()
        for v in s.get("uploads", []):
            if v.get("gone"):
                continue
            p = epparse.parse(v.get("t") or "", v.get("d"))
            if not p:
                continue
            k = epparse.key_of(p["name"]) + ("-dub" if p["dub"] else "")
            ser = by.setdefault(k, dict(key=k, names={}, chans=set(), dub=p["dub"], seasons={}))
            ser["names"][p["name"]] = ser["names"].get(p["name"], 0) + 1
            ser["chans"].add(cname)
            ser["seasons"].setdefault(p["season"], []).append(dict(p, id=v["id"], d=v["d"], ch=cname, t=v["t"],
                                                                  fs=v.get("first_seen", "2026-09-28")))
    # fold near-identical keys (typos, "Tale"/"Tales") and hand-made merges into one series
    keys = sorted(by, key=lambda k: -sum(len(x) for x in by[k]["seasons"].values()))
    for i, k in enumerate(keys):
        if k not in by:
            continue
        target = meta.get(k, {}).get("merge_into")
        if not target:
            for k2 in keys[:i]:
                if k2 in by and by[k2]["dub"] == by[k]["dub"] and len(k) > 6 and difflib.SequenceMatcher(None, k, k2).ratio() >= 0.92:
                    target = k2
                    break
        if target and target in by and target != k:
            src = by.pop(k)
            dst = by[target]
            for n, c in src["names"].items():
                dst["names"][n] = dst["names"].get(n, 0) + c
            dst["chans"] |= src["chans"]
            for sn, eps in src["seasons"].items():
                dst["seasons"].setdefault(sn, []).extend(eps)
    out = []
    for k, ser in by.items():
        seas, total, n_eps = [], 0, 0
        for sn in sorted(ser["seasons"]):
            items = ser["seasons"][sn]
            covered, chosen = set(), []
            for it in sorted([x for x in items if not x["full"] and x["a"] == x["b"]], key=lambda x: -x["d"]):
                if it["a"] not in covered:
                    covered.add(it["a"]); chosen.append(it)
            for it in sorted([x for x in items if not x["full"] and x["b"] > x["a"]], key=lambda x: (x["a"], -x["b"])):
                rng = set(range(it["a"], it["b"] + 1))
                if rng.isdisjoint(covered):
                    covered |= rng; chosen.append(it)
            if not chosen:
                fulls = sorted([x for x in items if x["full"]], key=lambda x: -x["d"])
                chosen = fulls[:1]
            if not chosen:
                continue
            chosen.sort(key=lambda x: x["a"])
            dur = sum(x["d"] for x in chosen)
            if dur < 1200:
                continue
            total += dur
            n_eps += len(covered) or 1
            gaps = [n for n in range(min(covered), max(covered) + 1) if n not in covered] if covered else []
            first = chosen[0]
            lab = lambda x: "Full" if x["full"] else (f"EP{x['a']}" if x["a"] == x["b"] else f"EP{x['a']}-{x['b']}")
            seas.append(dict(label=f"Season {sn}", short=f"S{sn}",
                             pick=dict(id=first["id"], ch=first["ch"], dur=fmt(dur), t=first["t"][:160]),
                             alts=[], gaps=len(gaps),
                             eps=[dict(n=lab(x), id=x["id"], dur=fmt(x["d"]), ch=x["ch"]) for x in chosen]))
        if not seas or total < 1800:
            continue
        import datetime
        newest = max(x["fs"] for s_ in ser["seasons"].values() for x in s_)
        week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        name = max(ser["names"].items(), key=lambda kv: (kv[1], sum(c.isascii() for c in kv[0])))[0]
        if ser["dub"]:
            name += " (English Dub)"
        title, tag = split_title(name)
        g = genre(name + " " + " ".join(x["t"] for s_ in ser["seasons"].values() for x in s_[:30])[:4000])
        h = int(hashlib.md5(k.encode()).hexdigest(), 16)
        c1, c2, ac = PAL[g]
        tl = len(title)
        out.append(dict(key=k, title=title, tag=tag, genre=g, seasons=len(seas), total=total, totalF=fmt(total),
                        chans=sorted(ser["chans"]), conf="", note="", missing=[], seas=seas, c1=c1, c2=c2, ac=ac,
                        px=h % 70 + 15, py=(h >> 8) % 60 + 10, rx=(h >> 16) % 80 + 10, ry=(h >> 24) % 70 + 20,
                        fs=34 if tl <= 22 else 28 if tl <= 38 else 23 if tl <= 60 else 19,
                        fresh=newest > "2026-09-28" and newest >= week_ago, newest=newest, q="", audio="A1" if ser["dub"] else "A2", episodes=n_eps,
                        gaps=sum(s_["gaps"] for s_ in seas)))
    return out


SHELF_NAMES = {
    1: ("Tier 1 · Epic, English audio", "Completed, 10h+, original sound kept, English voices, rated 7.5+."),
    2: ("Tier 2 · Epic, subtitled", "Completed, 10h+, original audio with English subtitles, rated 7.5+."),
    3: ("Tier 3 · Epic, dubbed", "10h+, English dub without the original background audio."),
    4: ("Tier 4 · Long, English audio", "Completed, 5h+, original sound kept, English voices, rated 7.5+."),
    5: ("Tier 5 · Long, subtitled", "Completed, 5h+, original audio with English subtitles, rated 7.5+."),
    6: ("Tier 6 · Long, dubbed", "5h+, English dub without the original background audio."),
    7: ("Tier 7 · Short picks", "Under 5 hours, original sound kept, rated 7.5+."),
    8: ("Ongoing", "Still airing. Moves into a tier when it finishes."),
    9: ("Awaiting review", "New from official channels. Rated and sorted on the next review."),
    10: ("Extras · short dubs", "English dubs under 5 hours."),
}


def apply(series, cur, Q):
    meta = cur.get("meta", {})
    shown, hidden = [], 0
    for x in series:
        x.setdefault("audio", "A3")
        x.setdefault("key", "live:" + x["title"])
        m = meta.get(x["key"], {})
        if m.get("name"):
            x["title"] = m["name"]
        ids = [s["pick"]["id"] for s in x["seas"]] + [e["id"] for s in x["seas"] for e in s.get("eps", [])]
        labels = {Q[i]["label"] for i in ids if i in Q}
        if m.get("quality"):
            labels = {m["quality"]}
        if x["audio"] != "A3" or not x.get("q"):
            x["q"] = "ai" if ("ai" in labels or "slop" in labels) else ("quality" if "quality" in labels else x.get("q", ""))
        slop = "slop" in labels and "quality" not in labels
        rating = m.get("rating")
        x["rating"] = rating
        x["ratingSrc"] = m.get("rating_src", "")
        x["completed"] = m.get("completed", x["audio"] == "A3")
        if m.get("hide") or slop or (rating is not None and rating < 7.5):
            hidden += 1
            continue
        hrs = x["total"] / 3600
        if x["audio"] == "A3":
            tier = 3 if hrs >= 10 else 6 if hrs >= 5 else 10
        elif rating is None:
            tier = 8 if m.get("completed") is False else 9
        elif not x["completed"]:
            tier = 8
        else:
            a1 = x["audio"] == "A1"
            tier = (1 if a1 else 2) if hrs >= 10 else (4 if a1 else 5) if hrs >= 5 else 7
        x["tier"] = tier
        bits = []
        if rating is not None:
            bits.append(f"{x['ratingSrc'] or 'Rating'} {rating}")
        bits.append({"A1": "English audio, original sound", "A2": "Original audio, English subs", "A3": "English dub"}[x["audio"]])
        if x.get("episodes"):
            bits.append(f"{x['episodes']} episodes")
        if x["audio"] != "A3":
            bits.append("Completed" if x["completed"] else "Ongoing")
        x["facts"] = " · ".join(bits)
        shown.append(x)
    shown.sort(key=lambda x: (x["tier"], x.get("q") == "ai", -(x.get("rating") or 0), -x["total"]))
    return shown, hidden
