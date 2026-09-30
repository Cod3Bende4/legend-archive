# Legend Archive

A browsable archive of long-form animation in three sections: Donghua (Chinese), Anime (Japanese) and Korean (webtoon and manhwa adaptations), from official YouTube channels plus four English-dub channels, sorted into quality tiers. Every play button opens or embeds the YouTube video; nothing is downloaded or rehosted.

## How it runs
- **22:00 IST, GitHub Actions** (`.github/workflows/nightly.yml`): asks the YouTube Data API for uploads newer than the ones already saved, checks new series' comments for AI slop, rebuilds `index.html`, publishes to GitHub Pages.
- **23:13 IST, Claude scheduled task**: researches ratings and completion for unrated series and commits them to `engine/curated.json`; that push triggers a rebuild.
- Any push to `engine/` or the workflow rebuilds and republishes in about 2 minutes. Put `[skip ci]` in a commit message to push without publishing (the curation job does this for its progress commits).

## Files
| Path | What |
|---|---|
| `engine/config.json` | Channels: `channels` (English-dub, tier 3/6) and `candidates` (official, subtitled or dubbed with original sound; `origin` CN, JP or KR) |
| `engine/curated.json` | Hand curation. `meta[series_key]`: `name`, `rating`, `rating_src`, `completed`, `hide`, `quality`, `merge_into`, `origin` (CN, JP, KR), `members_ok`, `summary` (English premise shown on the series page), `summary_status` ("unavailable" when researched but no reliable premise was found; the page then says so instead of "not written yet"), `note`, `checked` (date last researched), `checked_eps` (episode count then), `verify_tried` (date a recalled score could not be verified); the nightly run uses these to work only on deltas |
| `engine/videos.json`, `engine/scan/*.json` | Saved uploads (one per line), with `first_seen` dates |
| `engine/scan/quality.json` | AI verdict per checked video: `quality`, `ai`, `slop`, `unknown` |
| `engine/tiers.py` | Tier rules, origin split, members-only hiding (see its docstring) |
| `engine/epparse.py` | Title parser: series, season, episode; drops trailers, clips, members-only |

Secret needed: `YT_API_KEY` (YouTube Data API v3 key). Free quota is 10,000 units a day; a normal night uses under 500.
