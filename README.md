# Legend Archive

A browsable archive of long-form animation in four sections: Donghua (Chinese), Anime (Japanese), Korean (webtoon and manhwa adaptations) and Mature (adult-oriented, story-driven, never explicit), from official YouTube channels plus four English-dub channels, sorted into quality tiers. Every play button opens or embeds the YouTube video; nothing is downloaded or rehosted.

## The page
- **Focus** (home): 15 slots holding the best complete, rated series, ranked by `score()` in `engine/tiers.py` (rating, length, upload gaps, `anim`). Series you have started come first. A slot only changes hands when you finish a series or mark it "Not for me". An original and its English-dub upload share one slot. Tabs: Top 15 (all), Top 15 Anime, Top 15 Donghua, each with its own slots.
- **Explore**: every series, best first, filterable by Donghua, Anime or Korean.
- **Episodes from anywhere**: each series is a list of episode slots, each filled from the best free upload on any tracked channel: a single-episode upload first, else the episode inside a compilation, at its chapter time when the description lists chapters (read once per compilation by the scan), else at an even split (marked ≈). Tapping an episode offers Play here (only that stretch of a compilation) or Play on YouTube (opens at the episode's start). Locked uploads are never used.
- **My List**: what you are watching, want to watch (the "+ My List" button on a series), finished and dropped.
- Opening an episode records your place. Progress is kept in the browser's local storage. **Cloud save** (on My List) also commits it to `progress.json` in this repo using a fine-grained GitHub token kept in the browser (this repo only, Contents read and write); the newer copy wins, so a cleared browser or another device gets everything back. `progress.json` sits outside `engine/`, so saving it does not rebuild the site. Back up / Restore to a file also works.

## How it runs
- **22:00 IST, GitHub Actions** (`.github/workflows/nightly.yml`): asks the YouTube Data API for uploads newer than the ones already saved, reads each official channel's members-only playlist ("UUMO" + channel ID) to mark locked uploads, checks new series' comments for AI slop, rebuilds `index.html`, publishes to GitHub Pages.
- **23:13 IST, Claude scheduled task**: researches ratings and completion for unrated series and commits them to `engine/curated.json`; that push triggers a rebuild.
- Any push to `engine/` or the workflow rebuilds and republishes in about 2 minutes. Put `[skip ci]` in a commit message to push without publishing (the curation job does this for its progress commits).

## Files
| Path | What |
|---|---|
| `engine/config.json` | Channels: `channels` (English-dub, tier 3/6) and `candidates` (official, subtitled or dubbed with original sound; `origin` CN, JP or KR) |
| `engine/curated.json` | Hand curation. `meta[series_key]`: `name`, `rating`, `rating_src`, `completed`, `hide`, `quality`, `anim` (animation quality 1 to 5; raises or lowers the series' score) with `anim_note` and `anim_tried`, `members` (hide as members-only by hand), `members_ok` (keep one the members-only detection got wrong), `members_checked`, `merge_into` with `season_as` (file the source as season N of the target), `skip_seasons` (season labels whose episodes another season already holds), `from_ep` (start the series at this episode; earlier ones are watched in another key), `origin` (CN, JP, KR), `summary` (English premise shown on the series page), `summary_status` ("unavailable" when researched but no reliable premise was found; the page then says so instead of "not written yet"), `note`, `checked` (date last researched), `checked_eps` (episode count then), `verify_tried` (date a recalled score could not be verified); the nightly run uses these to work only on deltas |
| `engine/videos.json`, `engine/scan/*.json` | Saved uploads (one per line), with `first_seen` dates |
| `engine/scan/quality.json` | AI verdict per checked video: `quality`, `ai`, `slop`, `unknown` |
| `engine/mature.py`, `engine/mature.json` | Nightly AniList lookup: tags Seinen, Josei or gory series as Mature (anything AniList flags adult is skipped) and saves official "Also watch on" links; hand settings `mature` and `watch` in curated meta win |
| `engine/tiers.py` | Score, tier rules, origin split, members-only hiding (see its docstring) |
| `engine/epparse.py` | Title parser: series, season, episode; drops trailers, clips, members-only |

Secret needed: `YT_API_KEY` (YouTube Data API v3 key). Free quota is 10,000 units a day; a normal night uses under 500.
