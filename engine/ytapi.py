"""Minimal YouTube Data API v3 client (standard library only). Reads YT_API_KEY from the environment.

Quota (10,000 units/day free): every call used here costs 1 unit.
  uploads(channel)   1 call to resolve the channel + 1 call per 50 uploads (stops early at known IDs)
  details(ids)       1 call per 50 videos (duration, views, likes)
  comments(id)       1 call per video (top 60 by relevance)
  members_only(url)  1 call to resolve the channel + 1 call per 50 members-only videos
"""
import json, os, re, time, urllib.error, urllib.parse, urllib.request

API = "https://www.googleapis.com/youtube/v3/"
CALLS = {"n": 0}


class QuotaError(RuntimeError):
    pass


def key():
    k = os.environ.get("YT_API_KEY", "").strip()
    if not k:
        raise RuntimeError("YT_API_KEY is not set")
    return k


def get(endpoint, **params):
    params["key"] = key()
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            CALLS["n"] += 1
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 403 and "quotaExceeded" in body:
                raise QuotaError("YouTube API daily quota used up")
            if e.code == 403 and ("commentsDisabled" in body or "forbidden" in body.lower()):
                raise PermissionError(body[:200])
            if e.code == 404:
                raise LookupError(body[:200])
            if e.code in (500, 503) and attempt < 3:
                time.sleep(2 ** attempt); continue
            raise RuntimeError(f"HTTP {e.code}: {body[:300]}")
        except urllib.error.URLError:
            if attempt < 3:
                time.sleep(2 ** attempt); continue
            raise


def channel(url):
    """(channel_id, title, uploads_playlist_id) from a youtube.com/@handle or /channel/UC... URL."""
    m = re.search(r"/channel/(UC[\w-]{22})", url)
    if m:
        j = get("channels", part="snippet,contentDetails", id=m.group(1))
    else:
        h = re.search(r"/@([^/?#]+)", url).group(1)
        j = get("channels", part="snippet,contentDetails", forHandle="@" + h)
    it = (j.get("items") or [None])[0]
    if not it:
        raise LookupError("channel not found: " + url)
    return it["id"], it["snippet"]["title"], it["contentDetails"]["relatedPlaylists"]["uploads"]


def iso_seconds(d):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return None
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 86400 + h * 3600 + mi * 60 + s


def details(ids):
    """{id: {d, views, likes, title}} for up to any number of IDs, 50 per call."""
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 50):
        j = get("videos", part="contentDetails,statistics,snippet", id=",".join(ids[i:i + 50]), maxResults=50)
        for it in j.get("items", []):
            st = it.get("statistics", {})
            out[it["id"]] = dict(d=iso_seconds(it["contentDetails"].get("duration")),
                                 views=int(st.get("viewCount", 0) or 0), likes=int(st.get("likeCount", 0) or 0),
                                 title=it["snippet"].get("title", ""), description=it["snippet"].get("description", ""),
                                 tags=it["snippet"].get("tags", []))
    return out


def uploads(url, known=frozenset(), full=False):
    """Newest-first uploads of a channel as [{id, t, d}]. Stops at the first page made only of known
    IDs unless full=True. Durations are fetched only for IDs not in `known`."""
    cid, title, pl = channel(url)
    items, token = [], None
    while True:
        params = dict(part="snippet", playlistId=pl, maxResults=50)
        if token:
            params["pageToken"] = token
        try:
            j = get("playlistItems", **params)
        except LookupError:
            break
        page = [dict(id=it["snippet"]["resourceId"]["videoId"], t=it["snippet"].get("title", ""),
                     p=(it["snippet"].get("publishedAt") or "")[:10])
                for it in j.get("items", []) if it["snippet"].get("resourceId", {}).get("videoId")]
        items += page
        token = j.get("nextPageToken")
        if not token or (not full and page and all(p["id"] in known for p in page)):
            break
    fresh = [p["id"] for p in items if p["id"] not in known]
    info = details(fresh) if fresh else {}
    for p in items:
        if p["id"] in info:
            p["d"] = info[p["id"]]["d"]
    return dict(channel_id=cid, channel=title, items=items)


def comments(video_id, n=60):
    """Top comments (relevance order) as plain text. [] when comments are off."""
    try:
        j = get("commentThreads", part="snippet", videoId=video_id, maxResults=min(n, 100),
                order="relevance", textFormat="plainText")
    except (PermissionError, LookupError):
        return []
    return [it["snippet"]["topLevelComment"]["snippet"].get("textDisplay", "") for it in j.get("items", [])]


def members_only(url):
    """IDs of a channel's members-only videos. YouTube keeps them in an automatic playlist named "UUMO" plus the
    channel ID without its "UC" (next to "UU", the uploads playlist). An empty set when the channel has none."""
    cid, _, _ = channel(url)
    ids, token = set(), None
    while True:
        params = dict(part="snippet", playlistId="UUMO" + cid[2:], maxResults=50)
        if token:
            params["pageToken"] = token
        try:
            j = get("playlistItems", **params)
        except (LookupError, PermissionError):
            break
        ids |= {it["snippet"]["resourceId"]["videoId"] for it in j.get("items", [])
                if it["snippet"].get("resourceId", {}).get("videoId")}
        token = j.get("nextPageToken")
        if not token:
            break
    return ids
