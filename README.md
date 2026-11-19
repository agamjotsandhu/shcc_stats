# Sydenham-Hillside CC – career stats scraper

Builds a database of every SHCC player's career stats **for SHCC only**, using the JSON API behind play.cricket.com.au.

## Setup
```bash
pip install requests
```

## Usage
```bash
python scrape_history.py          # one-off full history (resumable – just re-run if interrupted)
python sync_official.py           # align every player's totals with Play Cricket (resumable, ~1 hr first time)
python update_matches.py          # afterwards: pull new/changed matches + re-sync totals (current + last season)
python build_site.py              # refresh the website data
```

### Play Cricket is the source of truth
`career_stats` (and the CSV and website) use each player's official Play Cricket totals: the "Career" tab on play.cricket.com.au with Club = Sydenham-Hillside, fetched per season by `sync_official.py` into `official_season_stats` and merged into `season_stats`. Scorecards alone can't reproduce them, because Play Cricket counts some games it doesn't publish scorecards for and skips some it does. The sync also uses each player's match list to find SHCC matches the grade walk misses (e.g. T20 knockouts). Same-name player IDs are still merged into one profile by summing their official totals. A player whose profile is private on Play Cricket keeps scorecard-derived totals.
Useful flags:
- `scrape_history.py --from 2015`: only seasons from 2015/16 onwards
- `scrape_history.py --rebuild-only`: rebuild the DB from cached JSON without any network calls (e.g. after changing parsing logic)
- `scrape_history.py --refetch`: re-download everything
- `update_matches.py --seasons 1`: current season only
- `--delay 0.5`: slow down requests (default 0.35 s)

A full run makes roughly 1 request per grade plus 1 per match. Expect a few thousand requests, around 20–40 minutes.

## Output (in `data/`)
| File | What |
|---|---|
| `shcc_stats.db` | SQLite database (open with DB Browser for SQLite, pandas, Power BI via ODBC, etc.) |
| `shcc_career_stats.csv` | One row per player with all career totals, regenerated on every run |
| `raw_matches/*.json` | Raw scorecard for every match (source of truth; DB can be rebuilt from these) |

### Tables
- `matches`: one row per SHCC match (season, grade, round, date, type, opponent, result, won)
- `players`: player_id (PlayHQ participant ID), name
- `appearances`: player × match (counts matches played, including games where they didn't bat or bowl)
- `batting` / `bowling` / `fielding`: one row per player per innings

### Views
- `player_profiles`: maps each player_id to a profile. Players with the exact same name (ignoring case and surrounding spaces) share one profile, because PlayHQ sometimes gives one person several IDs. Placeholder names (`********`, `Unknown Player_N`) stay one profile per ID.
- `career_stats`: one row per profile (`player_ids` lists the merged IDs, separated by `;`), everything combined: matches, innings, NOs, runs, HS, average, SR, 50s, 100s, ducks, 4s, 6s, overs, maidens, wickets, best bowling, bowling average/economy/SR, 3-fors, 5-wicket hauls, 10-wicket matches, catches, keeper catches, stumpings, run outs
- `career_appearances`, `career_batting`, `career_bowling`, `career_bowling_best`, `career_high_score`, `career_fielding`, `ten_wicket_matches` (all keyed by `profile`)

Example queries:
```sql
SELECT name, runs, high_score, hundreds, fifties FROM career_stats ORDER BY runs DESC LIMIT 20;
SELECT name, wickets, best_bowling, five_wicket_hauls FROM career_stats ORDER BY wickets DESC LIMIT 20;
-- season-by-season runs for one player
SELECT m.season, SUM(b.runs) FROM batting b JOIN matches m USING(match_id)
JOIN players p USING(player_id) WHERE p.name LIKE '%Culph%' GROUP BY m.season;
-- seniors only (filter by grade name)
SELECT p.name, SUM(b.runs) runs FROM batting b JOIN matches m USING(match_id) JOIN players p USING(player_id)
WHERE m.grade_name NOT LIKE 'U1%' GROUP BY LOWER(TRIM(p.name)) ORDER BY runs DESC;
```

## How "SHCC only" is enforced
- Matches are found by walking SHCC's own teams in every season, then keeping only fixtures where one side's owning organisation is SHCC's club ID.
- Within each scorecard, batting is counted only for innings where an SHCC team was batting. Bowling and fielding are counted only for innings where an SHCC team was in the field.
- So a player's runs or wickets for another club never enter the database, even when the same person has played elsewhere.

## Notes / caveats
- **Data coverage:** seasons go back to 1999/00, but older games often have results only and no scorecard. 2010-era scorecards may have runs but no balls, 4s or 6s. The `matches.has_scorecard` column flags this.
- **Junior and senior games are both included.** Filter on `grade_name` if you want seniors only.
- **5-wicket hauls** are per innings. **10-wicket matches** are per match (relevant for two-day games).
- **Ducks** = dismissed for 0. Not-outs on 0 aren't counted.
- Overs are assumed to be 6 balls.
- If a two-day game is captured after day 1, `update_matches.py` will re-fetch it once its status changes.
- **Scheduling:** e.g. cron `0 22 * * 0,1 cd /path/to/shcc_stats && python update_matches.py`, or Windows Task Scheduler.

## Stats website (`site/`)
A static, minimal stats site (leaderboards, records, milestone clubs, player profiles, season results) styled with the brand tokens from `player-announcements.md`.
```bash
python build_site.py                      # export the DB to site/data.json (re-run after update_matches.py)
python -m http.server -d site 8000        # preview at http://localhost:8000
```
The `site/` folder can be deployed as-is to any static host (GitHub Pages, Netlify, Cloudflare Pages).
Competitions are classified as Seniors / Women / Juniors from the grade and team names in `build_site.py` (`category()`).
