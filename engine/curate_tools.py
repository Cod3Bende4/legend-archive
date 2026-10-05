#!/usr/bin/env python3
"""Read-only helpers for the nightly curation run. Nothing here writes files.

  python3 engine/curate_tools.py todo [N]     worklist (deltas only): new series, unrated retries that are due,
                                              recalled scores to verify
  python3 engine/curate_tools.py stamp KEY..  print today's "checked" stamp for keys (helper; see below)
  python3 engine/curate_tools.py members      gated series to review (members-only rule, see tiers.py)
  python3 engine/curate_tools.py check        sanity check of meta edits since the last commit (merges, cycles, runtimes)
  python3 engine/curate_tools.py ongoing [N]  Sunday list: shown series marked not completed, best first
  python3 engine/curate_tools.py dubs [N]     dub-channel (A3) series for a light review
  python3 engine/curate_tools.py summaries [N] after a local rebuild: shown series without a summary, tiers 1-7 first
                                              (researched but no reliable premise found: set meta[key]["summary_status"]
                                              = "unavailable" so the page says so; those are listed last)
  python3 engine/curate_tools.py anim [N]     after a local rebuild: shown rated series without meta[key]["anim"]
                                              (animation quality 1 to 5), complete and best-scored first
  python3 engine/curate_tools.py midstory     after a local rebuild: shown series that start at a later season
  python3 engine/curate_tools.py report       after a local rebuild: counts per section and tier, sources, borderline

Series under 1 hour total are hidden by tiers.apply, so every list here skips them.

Delta tracking: every series a run researches gets meta[key]["checked"] = "YYYY-MM-DD" and, for official
series, meta[key]["checked_eps"] = its episode count at that time. todo then lists an unrated series again
only when it is due: never checked, new episodes since the check, an "anime-planet 429" note, or the check
is older than RETRY_DAYS (votes accumulate, so a rating can appear later). summaries skips "unavailable"
premises checked within SUMMARY_RETRY_DAYS. A recalled score whose verification failed gets
meta[key]["verify_tried"] = "YYYY-MM-DD" and leaves list C for RETRY_DAYS. Everything else with data is left alone.
"""
import collections, json, os, re, subprocess, sys

ENG = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENG)
import refresh, tiers  # noqa: E402

RECALLED = re.compile(r"recall|approx|from memory|estimate", re.I)
MIN_TOTAL = 3600
RETRY_DAYS = 30
SUMMARY_RETRY_DAYS = 60
TODAY = __import__("datetime").date.today()


def age(m):
    """Days since meta entry m was last researched (None if never)."""
    try:
        return (TODAY - __import__("datetime").date.fromisoformat(m["checked"])).days
    except Exception:
        return None


def due(s, m):
    """Why an unrated series should be researched again, or "" if its data is still fresh."""
    a = age(m)
    if a is None:
        return "never checked"
    if "429" in m.get("note", ""):
        return "anime-planet 429"
    if s["episodes"] > m.get("checked_eps", s["episodes"]):
        return f"new episodes ({m.get('checked_eps')} -> {s['episodes']})"
    if a >= RETRY_DAYS:
        return f"last checked {a} days ago"
    return ""
SITE = os.environ.get("SITE_DIR", "/tmp/site")


def load_meta(text=None):
    cur = json.loads(text) if text else json.load(open(os.path.join(ENG, "curated.json"), encoding="utf-8"))
    return cur.get("meta", {})


def series(meta):
    return tiers.official_series(refresh.genre, refresh.PAL, refresh.split_title, meta)


def line(s, m):
    return (f"{s['key']} | {m.get('name', s['title'])} | {s['totalF']} | {s['episodes']} eps, gaps {s['gaps']} | "
            f"{s['audio']} | origin {m.get('origin') or s.get('origin')} | {', '.join(s['chans'])} | "
            f"{s['seas'][0]['pick']['t'][:80]}")


def todo(n):
    meta = load_meta()
    ser = [s for s in series(meta) if s["total"] >= MIN_TOTAL]
    new = sorted([s for s in ser if s["key"] not in meta], key=lambda s: -s["total"])
    unrated = [s for s in ser if s["key"] in meta and meta[s["key"]].get("rating") is None
               and not meta[s["key"]].get("hide") and not meta[s["key"]].get("merge_into")]
    retry = sorted([s for s in unrated if due(s, meta[s["key"]])], key=lambda s: -s["total"])
    fresh = len(unrated) - len(retry)
    rec = [s for s in ser if meta.get(s["key"], {}).get("rating") is not None
           and RECALLED.search(meta[s["key"]].get("note", "")) and not meta[s["key"]].get("hide")
           and (age({"checked": meta[s["key"]].get("verify_tried", "")}) or RETRY_DAYS) >= RETRY_DAYS]
    rec.sort(key=lambda s: (not 7.2 <= meta[s["key"]]["rating"] <= 7.8, -s["total"]))
    print(f"A) {len(new)} new (no meta entry)  B) {len(retry)} unrated and due for a retry "
          f"({fresh} unrated but checked recently, skipped)  C) {len(rec)} with a recalled score (7.2-7.8 band first)")
    for label, rows in (("A NEW", new), ("B RETRY", retry), ("C VERIFY", rec)):
        print(f"\n== {label}")
        for s in rows[:n]:
            m = meta.get(s["key"], {})
            extra = (f" | rating {m.get('rating')} | due: {due(s, m)} | note: {m.get('note', '')[:90]}"
                     if label == "B RETRY" else f" | rating {m.get('rating')} | note: {m.get('note', '')[:90]}" if m else "")
            print(line(s, m) + extra)


def members():
    """Gated series (an upload sells a membership or an episode is locked) worth a human look, not yet reviewed:
    HIDDEN ones rated 7.5+ (is the lock real?) and SHOWN ones with episodes missing (will they turn free?).
    A run that reviews one sets meta[key]["members_checked"] = today, plus "members" or "members_ok" when needed."""
    meta = load_meta()
    for s in sorted(series(meta), key=lambda s: -s["total"]):
        m, lk = meta.get(s["key"], {}), s.get("lock") or {}
        if not lk.get("gated") or m.get("hide") or m.get("merge_into") or m.get("members_checked") or s["total"] < MIN_TOTAL:
            continue
        done = m.get("completed", False)
        hidden = bool(m.get("members")) or (not m.get("members_ok") and (lk["start"] or lk["holes"] > 0 or (done and lk["missing"] > 0)))
        if (hidden and (m.get("rating") or 0) >= 7.5) or (not hidden and lk["missing"] > 0):
            print(f"{'HIDDEN' if hidden else 'SHOWN '} {s['key']} | {m.get('name', s['title'])} | {s['totalF']} | rating {m.get('rating')} | "
                  f"completed {done} | first eps locked {lk['start']} | holes {lk['holes']} | missing {lk['missing']} | {m.get('note', '')[:70]}")


def check():
    now = load_meta()
    try:
        old = load_meta(subprocess.run(["git", "show", "HEAD:engine/curated.json"], cwd=os.path.dirname(ENG),
                                       capture_output=True, text=True, check=True).stdout)
    except Exception:
        old = {}
    bad = 0
    for k, m in now.items():
        t = m.get("merge_into")
        if not t:
            continue
        seen, cur = {k}, t
        while cur:
            if cur in seen:
                print("CYCLE", k, "->", t); bad += 1; break
            seen.add(cur)
            nxt = now.get(cur, {}).get("merge_into")
            if nxt:
                print("CHAIN", k, "->", cur, "->", nxt, "(point it at the final key)"); bad += 1
            cur = nxt
        if k.endswith("-dub") != t.endswith("-dub"):
            print("AUDIO MIX", k, "->", t, "(never merge a dub key into a subbed one or back)"); bad += 1
        if now.get(t, {}).get("hide") and not now[k].get("hide"):  # hiding the source too says the family goes
            print("TARGET HIDDEN", k, "->", t); bad += 1
    before = {s["key"]: s for s in series(old)}
    after = {s["key"]: s for s in series(now)}
    for k, m in now.items():
        t = m.get("merge_into")
        if not t or old.get(k, {}).get("merge_into") == t or k not in before:
            continue
        if t not in before:
            print("MISSING TARGET", k, "->", t); bad += 1; continue
        src, b, a = before[k], before[t], after.get(t)
        gain = (a["total"] if a else 0) - b["total"]
        nums = [int(x["short"][1:]) for x in src["seas"] if x["short"][1:].isdigit()]
        shift = m.get("season_as", 0) and nums and m["season_as"] - min(nums)  # filed as a later season of the target
        labels = {f"Season {int(x['short'][1:]) + shift}" if shift and x["short"][1:].isdigit() else x["label"] for x in src["seas"]}
        shared = labels & {x["label"] for x in b["seas"]}
        flag = "DOUBLE?" if shared and gain > 0.9 * src["total"] and b["total"] > 3600 else "ok"
        lost = "LOST RUNTIME" if a and a["total"] < b["total"] else ""
        print(f"{flag:8} {lost} {k} ({src['totalF']}) -> {t}: {b['totalF']} => {a['totalF'] if a else '?'} "
              f"| src {sorted(labels)} tgt {sorted(x['label'] for x in b['seas'])}")
    print("problems:", bad, "(DOUBLE? = same season label and the target grew by the whole source: "
          "likely the same episodes under another numbering; hide the source as a duplicate instead)")


def ongoing(n):
    meta = load_meta()
    rows = [s for s in series(meta) if meta.get(s["key"], {}).get("completed") is False and s["total"] >= MIN_TOTAL
            and not meta[s["key"]].get("hide") and not meta[s["key"]].get("merge_into")]
    rows.sort(key=lambda s: (-(meta[s["key"]].get("rating") or 0), -s["total"]))
    print(len(rows), "not completed")
    for s in rows[:n]:
        m = meta[s["key"]]
        print(line(s, m) + f" | rating {m.get('rating')} | note: {m.get('note', '')[:90]}")


def stamp(keys):
    meta = load_meta()
    eps = {s["key"]: s["episodes"] for s in series(meta)}
    out = {k: {"checked": TODAY.isoformat(), **({"checked_eps": eps[k]} if k in eps else {})} for k in keys}
    print(json.dumps(out, ensure_ascii=False))


def data():
    h = open(os.path.join(SITE, "index.html"), encoding="utf-8").read()
    return json.loads(re.search(r"const DATA = (.*);\nconst META", h).group(1))


def dubs(n):
    meta = load_meta()
    rows = sorted([x for x in data() if x["audio"] == "A3" and x["key"] not in meta], key=lambda x: -x["total"])
    print(len(rows), "shown dub-channel series without a meta entry")
    for x in rows[:n]:
        print(f"{x['key']} | {x['title']} | {x['totalF']} | tier {x['tier']} | conf {x.get('conf')} | "
              f"q {x.get('q')} | {', '.join(x['chans'])} | {x['seas'][0]['pick']['t'][:70]}")


def anim(n):
    """Shown, rated series with no animation grade yet, the ones most likely to reach the Focus lists first."""
    todo = sorted([x for x in data() if x.get("rating") is not None and not x.get("anim") and x.get("audio") != "A3"],
                  key=lambda x: (not x.get("completed"), -(x.get("score") or 0)))
    print(len(todo), "rated series without an animation grade (complete ones first, best score first)")
    for x in todo[:n]:
        print(x["key"], "|", x["title"], "|", x.get("origin"), "|", "complete" if x.get("completed") else "airing",
              "| score", x.get("score"), "|", x["totalF"], "|", x["seas"][0]["pick"]["t"][:70])


def midstory():
    """Shown series that look like a later part with no beginning: lowest season label above 1, or a title that says
    season 2+, part II and the like. Merge it into the earlier seasons with merge_into + season_as when those exist,
    otherwise hide it with a note starting "starts mid-story:". Reviewed keys get midstory_checked = today."""
    meta = load_meta()
    later = re.compile(r"season\s*[2-9]|\b\d+(st|nd|rd|th) season|second season|\b(ii|iii|iv)\b|part\s*(2|ii)|\b[2-9]$", re.I)
    for x in data():
        nums = [int(s["short"][1:]) for s in x["seas"] if s["short"][1:].isdigit()]
        if meta.get(x["key"], {}).get("midstory_checked"):
            continue
        if (nums and min(nums) > 1) or later.search(x["title"]):
            print(x["key"], "|", x["title"], "|", x["totalF"], "| seasons", [s["short"] for s in x["seas"]], "| rating", x.get("rating"))


def summaries(n):
    meta = load_meta()
    skip = {x["key"] for x in data() if x.get("summaryStatus") == "unavailable"
            and (age(meta.get(x["key"], {})) or 0) < SUMMARY_RETRY_DAYS and "checked" in meta.get(x["key"], {})}
    todo = sorted([x for x in data() if not x.get("summary") and x["key"] not in skip],
                  key=lambda x: (x.get("summaryStatus") == "unavailable", x["tier"], -x["total"]))
    un = sum(1 for x in todo if x.get("summaryStatus") == "unavailable")
    print(len(data()), "shown,", len(todo) + len(skip), "without summary:", len(todo) - un, "not written yet,",
          un, f"unavailable and due for a retry (listed last), {len(skip)} unavailable and checked recently (skipped)")
    for x in todo[:n]:
        print(x["key"], "|", x["title"], "|", x.get("origin"), "| tier", x["tier"], "|", x["totalF"], "|",
              x["seas"][0]["pick"]["t"][:80])


def report():
    meta = load_meta()
    d = data()
    names = {1: "T1", 2: "T2", 3: "T3", 4: "T4", 5: "T5", 6: "T6", 7: "T7", 8: "Ongoing", 9: "Awaiting", 10: "Extras"}
    print(len(d), "series shown")
    for o in ("JP", "CN", "KR"):
        c = collections.Counter(x["tier"] for x in d if x.get("origin") == o)
        if c:
            print(o, " ".join(f"{names[t]} {c[t]}" for t in sorted(c)))
    src = collections.Counter()
    for m in meta.values():
        if m.get("rating") is not None and not m.get("hide") and not m.get("merge_into"):
            s = m.get("rating_src", "?")
            src[s + (" (recalled)" if RECALLED.search(m.get("note", "")) else "")] += 1
    print("ratings by source:", dict(src))
    ser = [s for s in series(meta) if s["total"] >= MIN_TOTAL]
    un = [s for s in ser if meta.get(s["key"], {}).get("rating") is None and not meta.get(s["key"], {}).get("hide")
          and not meta.get(s["key"], {}).get("merge_into")]
    why = collections.Counter("new" if s["key"] not in meta else "no rating found" for s in un)
    print("unrated:", len(un), dict(why), "|", sum(1 for s in un if s["total"] >= 18000), "of them 5h+")
    border = sorted([(m["rating"], k, m.get("name", k), m.get("rating_src", "")) for k, m in meta.items()
                     if m.get("rating") is not None and 7.3 <= m["rating"] < 7.5 and not m.get("hide")
                     and not m.get("merge_into")], reverse=True)
    print(len(border), "borderline (7.3 to 7.49, hidden by the 7.5 cut):")
    for r, k, nm, s in border:
        print(f"  {nm} {r} {s}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "todo"
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 60
    {"todo": lambda: todo(n), "members": members, "check": check, "ongoing": lambda: ongoing(n),
     "dubs": lambda: dubs(n), "stamp": lambda: stamp(sys.argv[2:]), "summaries": lambda: summaries(n), "anim": lambda: anim(n), "midstory": midstory, "report": report}[cmd]()
