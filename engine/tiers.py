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
  hidden                  AI slop, rated under 7.5, under 1 hour total, members-only, or hidden by hand

Origin (CN donghua, JP anime, KR Korean webtoon/manhwa) splits the site into three sections that each
carry the shelves above. It comes from the channel ("origin" in config.json, the four dub channels are CN),
then ORIGIN_HINTS for known titles, then meta[key]["origin"] set by hand.

Members-only: hidden when you could not watch it free from the start or to the end. A series is gated when an
upload naming it (clips and shorts included) pitches a membership ("Join to watch latest", 加入会员) or an
episode is locked (on the channel's members-only playlist, YouTube refused it as members-only, or its title says
"For Membership" / "Member Only"). A gated
series is hidden when its first episodes are locked or missing, when a finished season of it has locked or missing
episodes, or when it has finished airing and episodes are still locked or missing. Gaps in the season still airing
are early access to the newest episodes, which turn free later, so they are fine.
meta[key]["members"] = true hides one by hand; meta[key]["members_ok"] = true keeps one the detection got wrong.

Score: score() below ranks the Focus list and Explore; meta[key]["anim"] (1 to 5, animation quality) feeds it.

Summary: meta[key]["summary"] is a short spoiler-free English premise, shown when a series is opened.
When a run researched a series but found no reliable premise, it sets meta[key]["summary_status"] = "unavailable"
(and leaves summary out); the page then says the description is not available instead of saying it is not written yet.

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


LOCK = re.compile(r"for membership|members?[\s-]*only|member only|members? exclusive|会员专享(?!最新)", re.I)
PITCH = re.compile(r"join\s*(the\s*)?(members?|channel)|join to watch|加入会员|会员畅享|会员专享|会员抢先|抢先看|"
                   r"members?[\s-]*(only|preview|get|first)|member only", re.I)

ORIGINS = {"CN": "Donghua", "JP": "Anime", "KR": "Korean"}
# titles whose origin differs from their channel's (Muse Asia is mostly Japanese anime)
ORIGIN_HINTS = [
    ("KR", re.compile(r"god of high school|noblesse|tower of god|solo leveling|who made me a princess|fated magical princess|"
                      r"wind breaker|greatest estate developer|trash of the count|tomb raider king|omniscient reader|pick me up|"
                      r"lookism|hardcore leveling|eleceed|return of the mount hua|nano machine|mercenary enrollment|viral hit|"
                      r"how to fight|study group|dead account|terror man|killer peter|webtoon|manhwa", re.I)),
    ("CN", re.compile(r"lord of mysteries|link click|heaven official|scissor seven|immortal king|fog hill|to be hero|"
                      r"soul land|douluo|battle through the heavens|perfect world|renegade immortal|swallowed star|"
                      r"mo dao zu shi|grandmaster of demonic|the outcast|spare me,? great lord|ling cage|donghua", re.I)),
]


def origin_of(chan_origin, text):
    for o, rx in ORIGIN_HINTS:
        if rx.search(text):
            return o
    return chan_origin


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


def same_show(eps_season, full_season):
    """True when a full upload's title contains the name its season's episode titles use ("Kuma Kuma Kuma Bear - Punch!"
    in "Kuma Kuma Kuma Bear - Punch! - Episode 01"), so MyGO and Ave Mujica, alike in length, stay apart."""
    flat = lambda t: re.sub(r"[^a-z0-9]+", "", t.lower())
    name = re.split(r"\s[-|:]\s*(?:episode|ep\.?)\s*\d|\s(?:episode|ep\.?)\s*\d", eps_season["pick"]["t"], flags=re.I)[0]
    return len(flat(name)) >= 6 and flat(name) in flat(full_season["pick"]["t"])


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
    cands = json.load(open(os.path.join(ENG, "config.json"), encoding="utf-8")).get("candidates", {})
    chans = []
    for f in sorted(os.listdir(scan_dir)):
        if f.endswith(".json") and f != "quality.json":
            chans.append(json.load(open(os.path.join(scan_dir, f), encoding="utf-8")))
    epparse.learn(v["t"] for s in chans for v in s.get("uploads", []))
    qpath = os.path.join(scan_dir, "quality.json")
    locked = {i for i, q in (json.load(open(qpath, encoding="utf-8")) if os.path.exists(qpath) else {}).items()
              if "members-only" in (q.get("error") or "")}  # YouTube refused the nightly check: members only
    by, pitches, locks = {}, {}, {}
    for s in chans:
        cname = re.sub(r"\s*-\s*(get|chinese).*$", "", s.get("channel") or s["name"], flags=re.I).strip()
        corig = cands.get(s["name"], {}).get("origin", "CN")
        for v in s.get("uploads", []):
            if v.get("gone"):
                continue
            if v.get("locked"):  # on the channel's members-only playlist
                locked.add(v["id"])
            # any upload, clips and shorts included, that sells a membership or is locked behind one
            if v.get("t") and (PITCH.search(v["t"]) or v.get("id") in locked):
                pitches.setdefault(cname, []).append(v["t"])
            if v.get("t") and (v.get("id") in locked or LOCK.search(v["t"])):  # a locked episode: note it, never play it
                lp = epparse.parse(epparse.MEMBERS.sub(" ", LOCK.sub(" ", v["t"])), v.get("d"))
                if lp and not lp["full"]:
                    locks.setdefault(epparse.key_of(lp["name"]) + ("-dub" if lp["dub"] else ""), []).append((lp["season"], lp["a"], lp["b"]))
                continue
            p = epparse.parse(v.get("t") or "", v.get("d"))
            if not p:
                continue
            k = epparse.key_of(p["name"]) + ("-dub" if p["dub"] else "")
            ser = by.setdefault(k, dict(key=k, names={}, chans=set(), dub=p["dub"], seasons={}, gated=False, orig={}, locks=[]))
            ser["names"][p["name"]] = ser["names"].get(p["name"], 0) + 1
            ser["gated"] |= p["gated"]
            ser["orig"][corig] = ser["orig"].get(corig, 0) + 1
            ser["chans"].add(cname)
            ser["seasons"].setdefault(p["season"], []).append(dict(p, id=v["id"], d=v["d"], ch=cname, t=v["t"],
                                                                  fs=v.get("p") or v.get("first_seen", "2026-09-28")))
    # fold near-identical keys (typos, "Tale"/"Tales") and hand-made merges into one series
    dom = lambda ser: max(ser["orig"].items(), key=lambda kv: kv[1])[0]
    keys = sorted(by, key=lambda k: -sum(len(x) for x in by[k]["seasons"].values()))
    for i, k in enumerate(keys):
        if k not in by:
            continue
        target = meta.get(k, {}).get("merge_into")
        if not target:
            for k2 in keys[:i]:
                if k2 in by and by[k2]["dub"] == by[k]["dub"] and dom(by[k2]) == dom(by[k]) and len(k) > 6 and difflib.SequenceMatcher(None, k, k2).ratio() >= 0.92:
                    target = k2
                    break
        if target and target in by and target != k:
            src = by.pop(k)
            dst = by[target]
            shift = meta.get(k, {}).get("season_as", 0) and meta[k]["season_as"] - min(src["seasons"])
            if shift:  # "season_as": N files a later season uploaded under its own title as season N of the target
                src["seasons"] = {sn + shift: eps for sn, eps in src["seasons"].items()}
                src["locks"] = [(s_ + shift, a, b) for s_, a, b in src["locks"]]
            for n, c in src["names"].items():
                dst["names"][n] = dst["names"].get(n, 0) + c
            dst["chans"] |= src["chans"]
            dst["gated"] |= src["gated"]
            dst["locks"] += src["locks"] + locks.pop(k, [])
            for o, c in src["orig"].items():
                dst["orig"][o] = dst["orig"].get(o, 0) + c
            for sn, eps in src["seasons"].items():
                dst["seasons"].setdefault(sn, []).extend(eps)
    for k, ls in locks.items():
        k = meta.get(k, {}).get("merge_into") or k
        if k in by:
            by[k]["locks"] += ls
            by[k]["gated"] = True
    # a pitch names its series: give it to the longest series name it contains in that channel, so
    # "A Mortal's Journey to Immortality ... Join to watch" gates that show and not "Immortality"
    for cname, titles in pitches.items():
        here = [(n, ser) for ser in by.values() if cname in ser["chans"] for n in ser["names"] if len(n) >= 6]
        for t in titles:
            hits = [(len(n), ser) for n, ser in here if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", t, re.I)]
            if hits:
                max(hits, key=lambda h: h[0])[1]["gated"] = True
    out = []
    for k, ser in by.items():
        seas, total, n_eps = [], 0, 0
        start_locked, locked_n, holes, last_holes = False, 0, 0, 0
        for sn in sorted(ser["seasons"]):
            if sn in meta.get(k, {}).get("skip_seasons", []):  # a season label whose episodes another season already has
                continue
            first_ep = meta.get(k, {}).get("from_ep", 1)  # episodes before it are watched in another key
            items = [x for x in ser["seasons"][sn] if x["full"] or x["a"] >= first_ep]
            covered, chosen = set(), []
            for it in sorted([x for x in items if not x["full"] and x["a"] == x["b"]], key=lambda x: -x["d"]):
                if it["a"] not in covered:
                    covered.add(it["a"]); chosen.append(it)
            for it in sorted([x for x in items if not x["full"] and x["b"] > x["a"]], key=lambda x: (x["a"], -x["b"])):
                rng = set(range(it["a"], it["b"] + 1))
                if rng.isdisjoint(covered):
                    covered |= rng; chosen.append(it)
            # a multi-episode upload beats the pieces inside its range when it runs far longer than they do:
            # those pieces are clips mislabelled as episodes, or a few stray episodes of a season it covers whole
            for it in sorted([x for x in items if not x["full"] and x["b"] > x["a"] and x not in chosen], key=lambda x: -x["d"]):
                inside = [c for c in chosen if it["a"] <= c["a"] and c["b"] <= it["b"]]
                if any(c["a"] <= it["b"] and it["a"] <= c["b"] for c in chosen if c not in inside):
                    continue  # it straddles an upload already chosen
                if it["d"] > 1.5 * sum(c["d"] for c in inside):
                    chosen = [c for c in chosen if c not in inside] + [it]
                    covered |= set(range(it["a"], it["b"] + 1))
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
            last_holes = 0
            if covered:  # episodes you could not watch free: gaps, plus locked ones no free upload covers
                lost = {e for s_, a, b in ser["locks"] if s_ == sn for e in range(a, b + 1) if e not in covered}
                locked_n += len(set(gaps) | lost)
                last_holes = len(gaps) + sum(1 for e in lost if e < max(covered))  # older episodes, not the newest
                holes += last_holes
                if sn == min(ser["seasons"]) and (min(covered) > first_ep or any(first_ep <= e < first_ep + 3 for e in lost)):
                    start_locked = True
            first = chosen[0]
            lab = lambda x: "Full" if x["full"] else (f"EP{x['a']}" if x["a"] == x["b"] else f"EP{x['a']}-{x['b']}")
            seas.append(dict(label=f"Season {sn}", short=f"S{sn}",
                             pick=dict(id=first["id"], ch=first["ch"], dur=fmt(dur), t=first["t"][:160]),
                             alts=[], gaps=len(gaps),
                             eps=[dict(n=lab(x), id=x["id"], dur=fmt(x["d"]), ch=x["ch"]) for x in chosen], d=dur, one=chosen[0]["full"]))
        # a "Complete Series" upload often lands under its own season label: when one full upload runs within 1.5% of
        # another season and its title names what that season's episodes are called, it is that season again
        for s_ in [s_ for s_ in seas if s_["one"] and len(s_["eps"]) == 1]:
            if any(o is not s_ and not o["one"] and abs(o["d"] - s_["d"]) <= 0.015 * o["d"] and same_show(o, s_) for o in seas):
                seas.remove(s_)
                total -= s_["d"]
                n_eps -= 1
        for s_ in seas:
            s_.pop("d"); s_.pop("one")
        if not seas or total < 1800:
            continue
        import datetime
        newest = max(x["fs"] for s_ in ser["seasons"].values() for x in s_)
        week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        name = max(ser["names"].items(), key=lambda kv: (kv[1], sum(c.isascii() for c in kv[0])))[0]
        if ser["dub"]:
            name += " (English Dub)"
        orig = origin_of(dom(ser), name)
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
                        gaps=sum(s_["gaps"] for s_ in seas), origin=orig,
                        lock=dict(gated=ser["gated"], start=start_locked, missing=locked_n, holes=holes - last_holes)))
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


def score(x):
    """Worth-your-time score that orders the Focus list and Explore. None when the series is unrated.

    rating x 10 (75 to 95), plus up to 8 for length (0 at 2h, 8 at 32h+), plus (anim - 3) x 3 when
    meta["anim"] (1 to 5, animation quality) is set, minus up to 8 for missing episodes, minus 10 if
    flagged as AI-made, minus 3 for a dub without the original background audio.
    """
    if x.get("rating") is None:
        return None
    import math
    s = x["rating"] * 10
    s += max(0.0, min(8.0, 2 * math.log2(max(x["total"], 1) / 7200)))
    if x.get("anim"):
        s += (x["anim"] - 3) * 3
    if x.get("gaps") and x.get("episodes"):
        s -= min(8.0, 20 * x["gaps"] / (x["episodes"] + x["gaps"]))
    if x.get("q") == "ai":
        s -= 10
    if x.get("audio") == "A3":
        s -= 3
    return round(s, 1)


def apply(series, cur, Q):
    meta = cur.get("meta", {})
    shown, hidden = [], 0
    seen = set()
    for x in sorted(series, key=lambda x: -x["total"]):
        if "key" not in x:  # dub-channel series are keyed by title; two stories can share one, so the longest keeps it
            k = "live:" + x["title"]
            x["key"] = k if k not in seen else f"{k} | {(x.get('tag') or x['seas'][0]['pick']['t'])[:40]}"
        seen.add(x["key"])
    for x in series:
        x.setdefault("audio", "A3")
        m = meta.get(x["key"], {})
        x["origin"] = m.get("origin") or origin_of(x.get("origin", "CN"), x["title"])
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
        x["summary"] = m.get("summary", "")
        # "" = has a summary; "unavailable" = researched, no reliable source found; "pending" = not written yet
        x["summaryStatus"] = "" if x["summary"] else ("unavailable" if m.get("summary_status") == "unavailable" else "pending")
        x["completed"] = m.get("completed", x["audio"] == "A3")
        lk = x.pop("lock", None) or {}
        if x["audio"] == "A3" and any("members-only" in (Q.get(i, {}).get("error") or "") for i in ids):
            lk = dict(gated=True, start=True, missing=1, holes=0)  # a dub-channel upload behind a membership
        members = bool(m.get("members")) or (not m.get("members_ok") and lk.get("gated", False)
                                             and (lk["start"] or lk["holes"] > 0 or (x["completed"] and lk["missing"] > 0)))
        if m.get("hide") or slop or members or x["total"] < 3600 or (rating is not None and rating < 7.5):
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
        anim = m.get("anim") or (meta.get(x["key"][:-4], {}).get("anim") if x["key"].endswith("-dub") else None)
        if anim:
            bits.append(f"Animation {anim}/5")
        if x.get("episodes"):
            bits.append(f"{x['episodes']} episodes")
        if x["audio"] != "A3":
            bits.append("Completed" if x["completed"] else "Ongoing")
        x["facts"] = " · ".join(bits)
        x["anim"] = m.get("anim") or (meta.get(x["key"][:-4], {}).get("anim") if x["key"].endswith("-dub") else None)  # a dub looks like its original
        x["score"] = score(x)
        shown.append(x)
    shown.sort(key=lambda x: (x["tier"], x.get("q") == "ai", -(x.get("rating") or 0), -x["total"]))
    return shown, hidden
