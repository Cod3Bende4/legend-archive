#!/usr/bin/env python3
"""Legend Archive daily refresh.

Lists every upload on the channels in config.json (metadata only, nothing is downloaded),
merges them into videos.json, groups them into series and seasons, links the same story
across channels, and rebuilds ../index.html. Standard library only.

Run by launchd at 22:00 and at login. Skips if the last good run was under 12 hours ago,
unless called with --force.
"""
import datetime, difflib, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ENG = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENG)
TODAY = datetime.date.today().isoformat()
NOW = datetime.datetime.now()


def log(msg):
    print(f"[{NOW:%Y-%m-%d %H:%M}] {msg}", flush=True)


def load(name, default=None):
    p = os.path.join(ENG, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dumps_lines(obj):
    """JSON with one list item / dict entry per line, so git diffs stay small."""
    def enc(v):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    parts = []
    for k, v in obj.items():
        if isinstance(v, list) and len(v) > 20:
            body = ",\n".join(enc(x) for x in v)
            parts.append(f"{enc(k)}:[\n{body}\n]")
        elif isinstance(v, dict) and len(v) > 20:
            body = ",\n".join(f"{enc(kk)}:{enc(vv)}" for kk, vv in v.items())
            parts.append(f"{enc(k)}:{{\n{body}\n}}")
        else:
            parts.append(f"{enc(k)}:{enc(v)}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def write_lines(path, obj):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(dumps_lines(obj))
    os.replace(tmp, path)


def save(name, obj):
    write_lines(os.path.join(ENG, name), obj)


def notify(text):
    try:
        subprocess.run(["osascript", "-e", f'display notification "{text}" with title "Legend Archive"'],
                       timeout=10, capture_output=True)
    except Exception:
        pass


# ---------------------------------------------------------------- fetch
def ytdlp():
    for p in [shutil.which("yt-dlp"), "/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp"]:
        if p and os.path.exists(p):
            return p
    return None


def use_api():
    return bool(os.environ.get("YT_API_KEY"))


def fetch(url, known=frozenset(), full=True):
    """Newest-first uploads [{id,title,dur}]. With the YouTube API (cloud) only new pages are read
    unless full=True; with yt-dlp (Mac) the whole list is read."""
    if use_api():
        import ytapi
        res = ytapi.uploads(url, known=known, full=full)
        return [dict(id=i["id"], title=i["t"], dur=i.get("d")) for i in res["items"]]
    exe = ytdlp()
    if not exe:
        raise RuntimeError("yt-dlp not found (brew install yt-dlp)")
    r = subprocess.run([exe, "--flat-playlist", "-J", "--no-warnings", url],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-300:])
    entries = [e for e in (json.loads(r.stdout).get("entries") or []) if e and e.get("id")]
    return [dict(id=e["id"], title=e.get("title") or "", dur=int(e["duration"]) if e.get("duration") else None)
            for e in entries]


# ---------------------------------------------------------------- text helpers
def strip_emoji(s):
    import unicodedata
    return "".join(c for c in s if unicodedata.category(c)[0] in "LNPZ" or c in "'’-")


def season_of(t):
    if re.search(r"Seasons\s*1-3", t):
        return "Comp 1-3"
    m = re.search(r"Season\s*(\d+)", t, re.I) or re.search(r"\bS(\d+)\]", t) or re.search(r"\bS(\d+)\s", t + " ")
    return int(m.group(1)) if m else 1


def base_of(t):
    s = re.sub(r"【[^】]*】", "", t)
    s = re.sub(r"Comp:\s*Seasons\s*1-3!?", "", s)
    s = re.sub(r"Season\s*\d+\s*[|:：]?", "", s, flags=re.I)
    s = re.sub(r"#\S+", "", s)
    s = re.sub(r"\bS\d+\b", "", s)
    s = strip_emoji(s)
    return re.sub(r"\s+", " ", s).strip(" |:：-—")


def tag_of(t):
    m = re.match(r"\[([^\]]+)\]", t)
    if not m or m.group(1) == "Anime Story":
        return None
    return re.sub(r"\s*S\d+$", "", m.group(1)).strip()


def tsr(a, b):
    """token-set similarity 0-100, like rapidfuzz.token_set_ratio."""
    ta, tb = set(a.lower().split()), set(b.lower().split())
    inter = " ".join(sorted(ta & tb))
    s1 = (inter + " " + " ".join(sorted(ta - tb))).strip()
    s2 = (inter + " " + " ".join(sorted(tb - ta))).strip()
    r = lambda x, y: difflib.SequenceMatcher(None, x, y).ratio() * 100
    return max(r(inter, s1), r(inter, s2), r(s1, s2)) if inter else r(s1, s2)


STOP = set("the a an and to of in i my me he his her she is are was for with on at by as it until then now so why every all into from but this that who".split())


def words(t):
    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP and len(w) > 2}


# ---------------------------------------------------------------- build
G = [("Horror & Ghost", r"horror|ghost|eerie|cthulhu|weird|haunt|slit-mouth|exorcis|nightmare|yama|undead emperor|asylum|rules horror|possession"),
     ("Mecha & Sci-Fi", r"mecha|mech\b|starship|interstellar|galaxy|titan|robot|federation|stellar|planet|alien|sci-?fi|xing tian"),
     ("Sea & Survival", r"\bsea\b|ocean|island|raft|ship|fish|angler|whale|turtle|xuanwu|pirate|shelter|survival|frozen|ice\b|desert|tribe|igloo"),
     ("Apocalypse", r"apocalyp|zombie|doomsday|doom|wasteland|endless night|mutant"),
     ("Beast & Evolution", r"beast|snake|dragon|fox|koi|carp|evolv|evolution|devour|zoo|tiger|wolf|lizard|ant\b|slime|monster|pet"),
     ("Cultivation", r"cultivat|immortal|sect|sage|heaven|wukong|ruyi|monkey king|martial|god|divine")]
PAL = {"Horror & Ghost": ("#5b1426", "#12060b", "#ff5c78"), "Mecha & Sci-Fi": ("#1c3d63", "#080f1c", "#7cc8ff"),
       "Sea & Survival": ("#0d5160", "#04161b", "#5fe3d8"), "Apocalypse": ("#62270f", "#170a06", "#ff8a45"),
       "Beast & Evolution": ("#22512f", "#08140c", "#a4e36a"), "Cultivation": ("#40275f", "#110a1c", "#d9b8ff"),
       "System & Summoner": ("#2c2f70", "#0c0d22", "#ffc857")}


def genre(txt):
    t = txt.lower()
    for g, p in G:
        if re.search(p, t):
            return g
    return "System & Summoner"


def fmt(s):
    s = s or 0
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def split_title(name):
    n = re.sub(r"^\s*[\W_]+", "", name).strip()
    for sep in ["—", "…", "...", " – ", ": ", "! ", "? "]:
        if sep in n:
            a, b = n.split(sep, 1)
            if len(a.strip()) >= 10 and len(b.strip()) >= 8:
                return a.strip().rstrip(",") + ("!" if sep == "! " else "?" if sep == "? " else ""), b.strip()
    if len(n) > 40 and ", " in n:
        a, b = n.split(", ", 1)
        if len(a) >= 10:
            b = b.strip()
            return a.strip(), b[:1].upper() + b[1:]
    return n, ""


def clean_t(t):
    t = re.sub(r"#\S+", "", t)
    t = re.sub(r"【DUB】|【FULL】", "", t)
    return re.sub(r"\s+", " ", t).strip()


def build(state, cur):
    seed = state["seed_date"]
    rows = {}
    for vid, v in state["videos"].items():
        if v.get("gone"):
            continue
        r = dict(id=vid, ch=v["ch"], title=v["title"], dur=v["dur"], order=v["pos"], first_seen=v["first_seen"])
        r["season"], r["base"], r["tag"] = season_of(r["title"]), base_of(r["title"]), tag_of(r["title"])
        rows[vid] = r
    for k, s in cur["seasons"].items():
        if k in rows:
            rows[k]["season"] = s

    # series inside each channel
    groups = []
    for r in sorted(rows.values(), key=lambda r: (r["ch"], r["order"])):
        for g in groups:
            if g["ch"] != r["ch"]:
                continue
            if r["tag"] or g["tag"]:
                if r["tag"] and r["tag"] == g["tag"]:
                    g["ids"].append(r["id"]); break
            elif tsr(r["base"], g["key"]) >= 92:
                g["ids"].append(r["id"]); break
        else:
            groups.append(dict(ch=r["ch"], key=r["tag"] or r["base"], tag=r["tag"], ids=[r["id"]]))

    def gof(i):
        return next((g for g in groups if i in g["ids"]), None)

    for a, b in cur["same"]:
        ga, gb = gof(a), gof(b)
        if ga and gb and ga is not gb:
            ga["ids"] += gb["ids"]; groups.remove(gb)

    # curated cross-channel links
    stories, owner = [], {}
    for L in cur["links"]:
        gs = []
        for i in L["ids"]:
            g = gof(i)
            if g and g not in gs and id(g) not in owner:
                gs.append(g)
        if not gs:
            continue
        s = dict(name=L["name"], conf=L["conf"], note=L["note"], groups=gs)
        stories.append(s)
        for g in gs:
            owner[id(g)] = s

    # automatic matching, only for groups holding a video first seen after the seed list
    fresh = lambda g: any(rows[i]["first_seen"] > seed for i in g["ids"])
    loose = [g for g in groups if id(g) not in owner]
    for g in loose:
        if not fresh(g) or id(g) in owner:
            continue
        r0 = rows[g["ids"][0]]
        best = None
        for h in groups:
            if h is g:
                continue
            for j in h["ids"]:
                o = rows[j]
                if not (r0["dur"] and o["dur"]) or abs(r0["dur"] - o["dur"]) > 10:
                    continue
                shared = len(words(r0["base"]) & words(o["base"]))
                score = tsr(r0["base"], o["base"])
                if shared >= 2 or score >= 60:
                    if not best or score > best[0]:
                        best = (score, h, o)
        if best:
            _, h, o = best
            if id(h) in owner:
                s = owner[id(h)]; s["groups"].append(g); owner[id(g)] = s
                s["note"] = (s["note"] + f". New upload on {r0['ch']} matched automatically").strip(". ")
            else:
                s = dict(name=None, conf="auto", groups=[h, g],
                         note=f"Matched automatically: runtime within 10s of the {o['ch']} upload and similar title. Check it.")
                stories.append(s); owner[id(h)] = owner[id(g)] = s
    for g in groups:
        if id(g) not in owner:
            s = dict(name=None, conf=None, note=None, groups=[g]); stories.append(s); owner[id(g)] = s

    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    qpath = os.path.join(ENG, "scan", "quality.json")
    Q = json.load(open(qpath, encoding="utf-8")) if os.path.exists(qpath) else {}
    out, hidden = [], 0
    for s in stories:
        eps = [rows[i] for g in s["groups"] for i in g["ids"]]
        labels = {Q[e["id"]]["label"] for e in eps if e["id"] in Q}
        if "slop" in labels and "quality" not in labels:
            hidden += 1
            continue
        qual = "ai" if "ai" in labels or "slop" in labels else ("quality" if "quality" in labels else "")
        if not s["name"]:
            g = s["groups"][0]; r0 = rows[g["ids"][0]]
            nm = (g["tag"].title() if g["tag"] and g["tag"].isupper() else g["tag"]) or re.sub(r"^\[[^\]]+\]\s*", "", r0["base"])
            s["name"] = re.sub(r"\s+", " ", nm).strip()
        by = {}
        for e in eps:
            by.setdefault(str(e["season"]), []).append(e)
        keys = sorted(by, key=lambda k: (0, int(k)) if k.isdigit() else (1, k))
        seas, total = [], 0
        for k in keys:
            es = sorted(by[k], key=lambda e: -(e["dur"] or 0))
            pk = es[0]
            if k.isdigit():
                total += pk["dur"] or 0
            item = lambda e: dict(id=e["id"], ch=e["ch"], dur=fmt(e["dur"]) if e["dur"] else "?", t=clean_t(e["title"]),
                                  new=e["first_seen"] > seed and e["first_seen"] >= week_ago)
            seas.append(dict(label=f"Season {k}" if k.isdigit() else "S1–3 compilation",
                             short=("S" + k) if k.isdigit() else "S1–3", pick=item(pk), alts=[item(e) for e in es[1:]]))
        nums = sorted(int(k) for k in keys if k.isdigit())
        missing = [n for n in range(1, max(nums) + 1) if n not in nums] if nums else []
        title, tag = split_title(s["name"])
        if not tag:
            _, tag = split_title(clean_t(re.sub(r"^\[[^\]]+\]\s*", "", eps[0]["title"])))
        tag = re.sub(r"^Season \d+\s*\|\s*", "", tag)
        g_ = genre(s["name"] + " " + " ".join(e["title"] for e in eps))
        h = int(hashlib.md5(s["name"].encode()).hexdigest(), 16)
        c1, c2, ac = PAL[g_]
        tl = len(title)
        newest = max(e["first_seen"] for e in eps)
        x = dict(title=title, tag=tag, genre=g_, seasons=len(nums), total=total, totalF=fmt(total),
                 chans=sorted({e["ch"] for e in eps}), conf=s["conf"] or "", note=s["note"] or "", missing=missing,
                 seas=seas, c1=c1, c2=c2, ac=ac, px=h % 70 + 15, py=(h >> 8) % 60 + 10, rx=(h >> 16) % 80 + 10,
                 ry=(h >> 24) % 70 + 20, fs=34 if tl <= 22 else 28 if tl <= 38 else 23 if tl <= 60 else 19,
                 fresh=newest > seed and newest >= week_ago, newest=newest, q=qual)
        x["tier"] = (1 if x["seasons"] >= 3 else 2 if x["seasons"] == 2 else
                     3 if total >= 3 * 3600 else 4 if total >= 2 * 3600 else 5)
        out.append(x)
    out.sort(key=lambda x: (x["tier"], x["q"] == "ai", -x["total"]))
    build.hidden = hidden
    return out


def render(series, meta):
    with open(os.path.join(ENG, "template.html"), encoding="utf-8") as f:
        html = f.read()
    data = json.dumps(series, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("__DATA__", data).replace("__META__", json.dumps(meta))
    outdir = os.environ.get("SITE_DIR", ROOT)
    os.makedirs(outdir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=outdir, suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(outdir, "index.html"))


def main():
    force = "--force" in sys.argv
    offline = "--rebuild" in sys.argv
    cfg, cur, state = load("config.json"), load("curated.json"), load("videos.json")
    if not force and not offline and state.get("last_success"):
        last = datetime.datetime.fromisoformat(state["last_success"])
        if (NOW - last).total_seconds() < 12 * 3600:
            log(f"skipped, last refresh {last:%d %b %H:%M}")
            return
    added, failed = [], []
    full_dub = not use_api() or not state.get("last_full") or \
        (NOW - datetime.datetime.fromisoformat(state["last_full"])).days >= 30
    if not offline:
        for ch, url in cfg["channels"].items():
            try:
                known = frozenset(k for k, v in state["videos"].items() if v["ch"] == ch)
                items = fetch(url, known, full_dub)
            except Exception as e:
                failed.append(ch); log(f"{ch}: fetch failed: {e}"); continue
            seen = set()
            n = len(items)
            for i, it in enumerate(items):
                seen.add(it["id"])
                v = state["videos"].get(it["id"])
                if v:
                    v.update(title=it["title"] or v["title"], dur=it["dur"] or v["dur"], ch=ch)
                    if full_dub:
                        v["pos"] = n - i
                    v.pop("gone", None)
                else:
                    top = max([v["pos"] for v in state["videos"].values() if v["ch"] == ch] or [0])
                    state["videos"][it["id"]] = dict(ch=ch, title=it["title"], dur=it["dur"], first_seen=TODAY,
                                                     pos=(n - i) if full_dub else top + (n - i))
                    added.append(it["title"])
            if full_dub:  # a partial (delta) listing cannot tell removed videos apart
                for vid, v in state["videos"].items():
                    if v["ch"] == ch and vid not in seen:
                        v["gone"] = True
            log(f"{ch}: {n} uploads listed")
    if not offline and cfg.get("candidates"):
        try:
            import scan  # delta: newest 150 per official channel; full listing monthly
            added_official = scan.main()
            if added_official:
                added += [f"{added_official} official episode uploads"]
        except Exception as e:
            log(f"official scan failed: {e}")
    if not offline and cfg.get("candidates"):
        try:
            import quality
            quality.main(limit=150)
        except Exception as e:
            log(f"nightly quality check failed: {e}")
    series = build(state, cur)
    import tiers
    qpath = os.path.join(ENG, "scan", "quality.json")
    Q = json.load(open(qpath, encoding="utf-8")) if os.path.exists(qpath) else {}
    try:
        official = tiers.official_series(genre, PAL, split_title, cur.get("meta", {}))
    except Exception as e:
        log(f"official series failed: {e}"); official = []
    series, hid = tiers.apply(series + official, cur, Q)
    build.hidden = getattr(build, "hidden", 0) + hid
    ok = not offline and len(failed) < len(cfg["channels"])
    if ok:
        state["last_success"] = NOW.isoformat(timespec="minutes")
        if full_dub and not offline:
            state["last_full"] = NOW.isoformat(timespec="minutes")
    meta = dict(updated=state.get("last_success") or TODAY, added=len(added), failed=failed,
                hidden=getattr(build, "hidden", 0),
                shelves=[dict(id=k, name=v[0], sub=v[1]) for k, v in tiers.SHELF_NAMES.items()])
    render(series, meta)
    save("videos.json", state)
    log(f"built {len(series)} series; {len(added)} new uploads; failed: {failed or 'none'}")
    if added:
        notify(f"{len(added)} new upload{'s' if len(added) > 1 else ''}. First: {added[0][:60]}")
    elif failed and len(failed) == len(cfg["channels"]):
        notify("Refresh failed. Check logs/refresh.log")


if __name__ == "__main__":
    main()
