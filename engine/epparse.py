"""Parse official-channel video titles into (series, season, episodes). Titles only."""
import re

JUNK = re.compile(r"trailer|预告|\bpv\d*\b|teaser|highlight|精彩看点|\bclips?\b|\bost\b|\[ost\]|\bop\b|\bed\b|opening|ending theme|"
                  r"#shorts|\bshorts\b|behind the scenes|making of|\bmv\b|reaction|character song|片头曲|片尾曲|主题曲|插曲|花絮|"
                  r"special program|\blive\b|直播|announcement|countdown|recap|总集|anime highlight|\bpreview\b(?!.*full)", re.I)
MEMBERS = re.compile(r"ai (eng )?dub|ai dubbed|会员专享|premiere|members? onl|members? get|see first|members?[\s-]*only|members?\s*preview|member only|\bvip\b|会员专区|付费|抢先看", re.I)
# free uploads that pitch a paid membership for the rest of the series ("Join member to watch latest episode")
GATED = re.compile(r"join\s*(the\s*)?members?|加入会员|会员畅享|members?[\s-]*(only|preview|get)|会员专享|会员抢先|抢先看", re.I)
CN_SUB_ONLY = re.compile(r"【中字】|\[中字\]|中字")
DUB = re.compile(r"english dub|\[dub\]|\beng ?dub\b", re.I)
EP = re.compile(r"(?:\bEP|\bEpisode|\bEps?\.)\s*0*(\d{1,4})(?:\s*[-~–—]\s*(?:EP)?\s*0*(\d{1,4}))?|第\s*(\d{1,4})\s*[集话話]|\bS\d{1,2}\s*E0*(\d{1,4})\b", re.I)
SEASON = re.compile(r"\bS(?:eason)?\s*0*(\d{1,2})(?=\s*(?:EP|E\d|\b))|\bSeason\s*0*(\d{1,2})|第\s*([一二三四五六七八九十\d]{1,3})\s*季|\bS(\d{1,2})E\d", re.I)
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
ROMAN = {"Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4, "Ⅴ": 5, "II": 2, "III": 3, "IV": 4, "V": 5}
BRACKET_JUNK = re.compile(r"eng\s*sub|multi\s*sub|engsub|multisub|member|trailer|预告|this season ended|limited free|get app|"
                          r"subscribe|join|free|会员|sp\b|full|合集|new|hot|最新|official", re.I)
TAILS = re.compile(r"\|.*$|【.*$|\[english (sub|dub)\]|\(s\d+e\d+\)|youku.*$|iqiyi.*$|tencent.*$|腾讯视频.*$|made ?by ?bilibili.*$|"
                   r"chinese (fantasy|ancient|fighting|donghua).*$|xianxia animation|xuanhuan animation", re.I)
HAN = re.compile(r"[㐀-鿿]")


def cn_int(s):
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if len(s) == 2 and s[0] == "十":
        return 10 + CN_NUM.get(s[1], 0)
    if len(s) == 2 and s[1] == "十":
        return CN_NUM.get(s[0], 1) * 10
    return CN_NUM.get(s, 1)


def clean_name(n):
    n = EP.sub(" ", n)
    n = re.sub(r"[\[\]【】《》「」]", " ", n)
    n = re.sub(r"(?i)\b(eng ?dub|english dub|eng ?sub|multi ?sub|full)\b", " ", n)
    n = re.sub(r"\((?:[^)]*[a-z][^)]*)\)", " ", n, flags=re.I) if re.search(r"[A-Za-z].*\(", n) else n  # (DouLuo DaLu)
    n = TAILS.sub("", n)
    latin = re.sub(r"[㐀-鿿《》【】「」（）！？，。、：]+", " ", n) if re.search(r"[A-Za-z]{3,}", n) else n
    n = latin
    n = re.sub(r"\b(ENG ?SUB|MULTI ?SUB|FULL|Collection|合集|SP)\b", " ", n, flags=re.I)
    n = re.sub(r"[\"“”'‘’|｜:：\-–—·•,，!！?？.~]+$", "", n.strip())
    n = re.sub(r"^[\"“”'‘’|｜:：\-–—·•,，!！?？.~\s]+", "", n)
    n = re.sub(r"\s+", " ", n).strip(" -|:")
    return n


def split_season(name):
    """'Apotheosis3' -> ('Apotheosis', 3); 'The Great Ruler S2' -> ('The Great Ruler', 2); 'Against the Gods Ⅱ' -> 2."""
    m = re.search(r"\s*(?:\bS(?:eason)?\s*0*(\d{1,2})|第\s*([一二三四五六七八九十\d]{1,3})\s*季)\s*$", name, re.I)
    if m:
        return name[:m.start()].strip(), int(m.group(1)) if m.group(1) else cn_int(m.group(2))
    m = re.search(r"\s*\b(Ⅱ|Ⅲ|Ⅳ|Ⅴ|II|III|IV)\s*$", name)
    if m:
        return name[:m.start()].strip(), ROMAN[m.group(1)]
    m = re.search(r"(?<=[A-Za-z])\s?([2-9])$", name)
    if m and len(name) > 4:
        return name[:m.start()].strip(), int(m.group(1))
    return name, None


PROMO_BR = re.compile(r"【[^】]*(?:subscribe|join|member|watch|fantasy|fighting|history|cultivation|novel|passionate|martial arts|"
                      r"made by bilibili|eng ?sub|eng ?dub|english dub|multi ?sub|season ended|limited free|get app|4k|free|highlight|"
                      r"complete series|all episodes)[^】]*】", re.I)
OTHER_LANG = re.compile(r"JPDUB|FRDUB|ESDUB|PTDUB|日配|中配|【中字】|\[中字\]|中字|Épisode|Episodio|Folge", re.I)
FULL = re.compile(r"all episodes|complete series|full season|\bcollection\b|chapter one|全集", re.I)
CN2EN = {}


def learn(titles):
    """Build a Chinese-name -> English-name map from titles that carry both."""
    for t in titles:
        for cn, rest in re.findall(r"《([^》]+)》\s*[|｜]?\s*\"?([A-Za-z][^|｜《【\[]{2,80})", t):
            en = EP.split(rest)[0].strip(' "')
            if re.search(r"[A-Za-z]{3,}", en) and not re.match(r"(eng|multi)\s*sub", en, re.I):
                CN2EN.setdefault(cn.strip(), en)
        for inner in re.findall(r"【([^】]+)】", t):
            m = re.match(r"([\u3400-\u9fff][^A-Za-z]*?)\s+([A-Za-z].+)$", inner.strip())
            if m:
                CN2EN.setdefault(m.group(1).strip(), m.group(2).strip())


def parse(title, dur):
    if not title or not dur or dur < 240:
        return None
    if JUNK.search(title) and not re.search(r"合集|collection|EP\s*\d+\s*[-~]\s*\d+", title, re.I):
        return None
    if MEMBERS.search(title) or CN_SUB_ONLY.search(title) or OTHER_LANG.search(title):
        return None
    dub = bool(DUB.search(title))
    gated = bool(GATED.search(title))
    full = bool(FULL.search(title)) and dur >= 2400
    title = PROMO_BR.sub(" ", title)
    title = re.sub(r"\[(?:english (?:sub|dub)|eng ?sub|multi ?sub)\]", " ", title, flags=re.I)
    title = re.sub(r"\[([^\]]{3,80})\]", r"\1", title)
    for cn, en in CN2EN.items():
        if "《" + cn + "》" in title and en not in title:
            title = title.replace("《" + cn + "》", "《" + cn + "》" + en + " ")
    m = EP.search(title)
    if m:
        a = int(m.group(1) or m.group(3) or m.group(4))
        b = int(m.group(2)) if m.group(2) else a
        if b < a or b - a > 200:
            b = a
    elif full:
        a = b = 0
    else:
        return None
    # candidate name sources, best first
    name = None
    mm = re.search(r"《([^》]+)》\s*\|?\s*([^|《【\[]*)", title)
    if mm:
        after = EP.split(mm.group(2))[0] if mm.group(2) else ""
        after = re.sub(r"\bS\d{1,2}\s*$", lambda x: x.group(0), after).strip()
        name = after if re.search(r"[A-Za-z]{3,}", after) else mm.group(1)
        if name is mm.group(1) or not re.search(r"[A-Za-z]{3,}", name):
            # English may follow after a bar: 《一人之下 第五季》| The Outcast S5 EP05
            parts = [p for p in re.split(r"[|｜]", title) if re.search(r"[A-Za-z]{3,}", p) and EP.search(p)]
            if parts:
                name = EP.split(parts[0])[0]
            season_cn = SEASON.search(mm.group(1))
    if not name:
        for br in re.findall(r"【([^】]+)】", title):
            if re.search(r"[A-Za-z]{3,}", br) and not BRACKET_JUNK.fullmatch(br.strip()) and not re.search(r"^(eng|multi)\s*sub$|members|trailer|preview|season ended|limited free|get app", br, re.I):
                name = br
                break
    if not name:
        mq = re.search(r"[\"“]([^\"”]{3,80})[\"”]", title)
        if mq:
            name = mq.group(1)
    if not name and full:
        name = re.split(r"(?i)all episodes|complete series|full season|collection|chapter one|全集", title)[0]
    if not name:
        segs = re.split(r"[|｜]", title)
        seg = next((s for s in segs if EP.search(s)), title)
        pre = EP.split(seg)[0]
        if not re.search(r"[A-Za-z㐀-鿿]{2,}", pre):
            idx = segs.index(seg) if seg in segs else 0
            pre = segs[idx - 1] if idx > 0 else pre
        name = pre
    season = None
    ms = SEASON.search(title)
    if ms:
        g = next(x for x in ms.groups() if x)
        season = cn_int(g)
    name = clean_name(name)
    name, s2 = split_season(name)
    name = clean_name(name)
    if season is None:
        season = s2 or 1
    if len(re.sub(r"\W", "", name)) < 2 or re.fullmatch(r"(?i)(end|top|s\d+|a\d|new|hot|sp|full|eng.*|multi.*)", name):
        return None
    return dict(name=name, season=season, a=a, b=b, dub=dub, full=a == 0, gated=gated)


def key_of(name):
    k = re.sub(r"^the\s+", "", name.lower())
    return re.sub(r"[^a-z0-9㐀-鿿]+", "", k)[:60]
