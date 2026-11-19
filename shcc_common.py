"""
Shared code for the Sydenham-Hillside Cricket Club (SHCC) stats scraper.

Data source: the JSON API behind play.cricket.com.au
(grassrootsapiproxy.cricket.com.au), which is what the website itself calls.

Flow:
    seasons -> SHCC teams per season -> grades each team played in
    -> all matches in each grade (filtered to ones involving SHCC)
    -> full scorecard per match (cached as raw JSON)
    -> parsed into SQLite, counting ONLY SHCC players' performances for SHCC.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

CLUB_ID = "293bd37b-87d8-eb11-a7ad-2818780da0cc"
CLUB_NAME = "Sydenham-Hillside Cricket Club"
API = "https://grassrootsapiproxy.cricket.com.au"
QS = {"jsconfig": "eccn:true"}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw_matches"          # one JSON file per match scorecard
PLAYER_DIR = DATA_DIR / "raw_players"       # one JSON file per player: official Play Cricket season totals
NON_SHCC_FILE = DATA_DIR / "non_shcc_matches.json"  # matches checked during discovery that aren't SHCC
DB_PATH = DATA_DIR / "shcc_stats.db"

# Batting entries that mean the player did not actually bat
DID_NOT_BAT = {"did not bat", "absent", "absent hurt", "absent out"}
NOT_OUT = {"not out", "retired not out", "retired hurt", "retired"}
# Statuses for matches that haven't been played yet
UNPLAYED = {"UPCOMING", "SCHEDULED", "NOT_STARTED"}

log = logging.getLogger("shcc")


# --------------------------------------------------------------------------- #
# HTTP client
# --------------------------------------------------------------------------- #
class Client:
    def __init__(self, delay: float = 0.35, retries: int = 4, timeout: int = 30):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://play.cricket.com.au",
            "Referer": "https://play.cricket.com.au/",
        })
        self._last = 0.0

    def get(self, path: str, **params):
        """GET an API path. Returns parsed JSON, or None for 204/404."""
        url = API + path
        q = {**params, **QS}
        for attempt in range(1, self.retries + 1):
            wait = self.delay - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = self.s.get(url, params=q, timeout=self.timeout)
            except requests.RequestException as e:
                log.warning("Request error %s (%s), attempt %d", url, e, attempt)
                time.sleep(2 ** attempt)
                continue
            if r.status_code in (204, 404):
                return None
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                log.warning("HTTP %s on %s, backing off (attempt %d)", r.status_code, url, attempt)
                time.sleep(2 ** attempt * 2)
                continue
            r.raise_for_status()
        raise RuntimeError(f"Failed after {self.retries} attempts: {url}")

    # ---- endpoints -------------------------------------------------------- #
    def seasons(self) -> list[dict]:
        j = self.get(f"/fixturesladders/organisations/{CLUB_ID}/seasons") or {}
        return j.get("seasons", [])

    def club_teams(self, season_id: str) -> list[dict]:
        j = self.get(f"/fixturesladders/organisations/{CLUB_ID}/teams", seasonId=season_id) or {}
        return j.get("teams", [])

    def grade_matches(self, grade_id: str) -> list[dict]:
        j = self.get(f"/scores/grades/{grade_id}/matches") or {}
        return j.get("matches", [])

    def match(self, match_id: str) -> dict | None:
        return self.get(f"/scores/matches/{match_id}", responseModifier="includeScorecard")

    # Player endpoints (the ones the play.cricket.com.au player "Career" tab uses)
    def player_seasons(self, player_id: str) -> list[dict]:
        return self.get(f"/participants/players/{player_id}/seasons") or []

    def player_summary(self, player_id: str, season_id: str = "") -> dict:
        """Official Play Cricket totals for this player, SHCC matches only."""
        return self.get(f"/participants/players/{player_id}/summary-statistics",
                        seasonId=season_id, organisationId=CLUB_ID) or {}

    def player_matches(self, player_id: str, season_id: str) -> list[dict]:
        """Every match the player played in a season (all clubs/rep sides)."""
        return self.get(f"/scores/players/{player_id}/match-performances", seasonId=season_id) or []


# --------------------------------------------------------------------------- #
# Discovery: which matches did SHCC play in a season?
# --------------------------------------------------------------------------- #
def is_shcc_team(team: dict) -> bool:
    return (team.get("owningOrganisation") or {}).get("id") == CLUB_ID


def season_matches(client: Client, season: dict) -> list[dict]:
    """Return match summaries (from grade fixture lists) involving SHCC in a season."""
    teams = client.club_teams(season["id"])
    grade_ids: dict[str, str] = {}
    for t in teams:
        for g in (t.get("grades") or []) + ([t["grade"]] if t.get("grade") else []):
            grade_ids[g["id"]] = g.get("name", "")
    found: dict[str, dict] = {}
    for gid, gname in grade_ids.items():
        for m in client.grade_matches(gid):
            if any(is_shcc_team(t) for t in m.get("teams", [])):
                m["_season"] = season["name"]
                m["_grade_id"] = gid
                m["_grade_name"] = gname
                found[m["id"]] = m
    log.info("%s: %d teams, %d grades, %d SHCC matches",
             season["name"], len(teams), len(grade_ids), len(found))
    return list(found.values())


def match_start(m: dict) -> datetime | None:
    sched = m.get("matchSchedule") or []
    if not sched:
        return None
    try:
        return datetime.fromisoformat(sched[0]["startDateTime"].replace("0000000", "000"))
    except (KeyError, ValueError):
        return None


def is_played(m: dict) -> bool:
    if (m.get("status") or "").upper() in UNPLAYED:
        return False
    start = match_start(m)
    return start is None or start <= datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Raw cache
# --------------------------------------------------------------------------- #
def raw_path(match_id: str) -> Path:
    return RAW_DIR / f"{match_id}.json"


def save_raw(match_id: str, payload: dict, meta: dict) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["_meta"] = {
        "season": meta.get("_season"),
        "grade_id": meta.get("_grade_id"),
        "grade_name": meta.get("_grade_name"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    raw_path(match_id).write_text(json.dumps(payload))


def load_raw(match_id: str) -> dict | None:
    p = raw_path(match_id)
    return json.loads(p.read_text()) if p.exists() else None


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id      TEXT PRIMARY KEY,
    season        TEXT,
    grade_name    TEXT,
    round_name    TEXT,
    match_date    TEXT,
    match_type    TEXT,
    status        TEXT,
    shcc_team     TEXT,
    opponent      TEXT,
    result_text   TEXT,
    shcc_won      INTEGER,
    has_scorecard INTEGER,
    fetched_at    TEXT
);
CREATE TABLE IF NOT EXISTS players (
    player_id  TEXT PRIMARY KEY,
    name       TEXT,
    short_name TEXT
);
-- every SHCC player named in a team list (used for "matches played")
CREATE TABLE IF NOT EXISTS appearances (
    match_id  TEXT,
    player_id TEXT,
    PRIMARY KEY (match_id, player_id)
);
CREATE TABLE IF NOT EXISTS batting (
    match_id     TEXT,
    innings_no   INTEGER,
    player_id    TEXT,
    bat_order    INTEGER,
    runs         INTEGER,
    balls        INTEGER,
    fours        INTEGER,
    sixes        INTEGER,
    dismissal    TEXT,
    dismissal_text TEXT,
    batted       INTEGER,   -- 0 = DNB / absent
    not_out      INTEGER,
    PRIMARY KEY (match_id, innings_no, player_id)
);
CREATE TABLE IF NOT EXISTS bowling (
    match_id       TEXT,
    innings_no     INTEGER,
    player_id      TEXT,
    balls          INTEGER,
    overs          TEXT,
    maidens        INTEGER,
    runs_conceded  INTEGER,
    wickets        INTEGER,
    wides          INTEGER,
    no_balls       INTEGER,
    PRIMARY KEY (match_id, innings_no, player_id)
);
CREATE TABLE IF NOT EXISTS fielding (
    match_id     TEXT,
    innings_no   INTEGER,
    player_id    TEXT,
    catches      INTEGER,
    wk_catches   INTEGER,
    stumpings    INTEGER,
    run_outs     INTEGER,
    PRIMARY KEY (match_id, innings_no, player_id)
);
-- Official Play Cricket season totals per player (SHCC matches only), from the
-- summary-statistics endpoint that powers the player "Career" tab. Source of truth.
CREATE TABLE IF NOT EXISTS official_season_stats (
    player_id     TEXT,
    season        TEXT,
    matches       INTEGER, bat_innings INTEGER, not_outs INTEGER, runs INTEGER,
    high_score    INTEGER, hs_not_out INTEGER, fifties INTEGER, hundreds INTEGER,
    ducks         INTEGER, fours INTEGER, sixes INTEGER,
    balls_bowled  INTEGER, maidens INTEGER, runs_conceded INTEGER, wickets INTEGER,
    best_w        INTEGER, best_r INTEGER, five_wi INTEGER, ten_wm INTEGER,
    catches       INTEGER, wk_catches INTEGER, stumpings INTEGER, run_outs INTEGER,
    PRIMARY KEY (player_id, season)
);
-- players whose official totals have been fetched
CREATE TABLE IF NOT EXISTS official_sync (
    player_id TEXT PRIMARY KEY,
    synced_at TEXT
);
-- One row per player per season: official totals where synced, otherwise
-- totals derived from scorecards. All career figures are built from this.
CREATE TABLE IF NOT EXISTS season_stats (
    player_id     TEXT,
    season        TEXT,
    source        TEXT,      -- 'official' | 'scorecards'
    matches       INTEGER, bat_innings INTEGER, not_outs INTEGER, runs INTEGER,
    high_score    INTEGER, hs_not_out INTEGER, fifties INTEGER, hundreds INTEGER,
    ducks         INTEGER, fours INTEGER, sixes INTEGER,
    balls_bowled  INTEGER, maidens INTEGER, runs_conceded INTEGER, wickets INTEGER,
    best_w        INTEGER, best_r INTEGER, five_wi INTEGER, ten_wm INTEGER,
    catches       INTEGER, wk_catches INTEGER, stumpings INTEGER, run_outs INTEGER,
    sr_balls      INTEGER,   -- balls faced in innings where balls were recorded (scorecards)
    sr_runs       INTEGER,   -- runs from those innings, for strike rate
    three_fors    INTEGER,   -- scorecards only (not in the official summary)
    PRIMARY KEY (player_id, season)
);
CREATE INDEX IF NOT EXISTS ix_bat_player  ON batting(player_id);
CREATE INDEX IF NOT EXISTS ix_bowl_player ON bowling(player_id);
CREATE INDEX IF NOT EXISTS ix_fld_player  ON fielding(player_id);
CREATE INDEX IF NOT EXISTS ix_app_player  ON appearances(player_id);

-- A "profile" is everyone sharing the same name (case/whitespace-insensitive).
-- PlayHQ sometimes issues the same person more than one participant ID, so all
-- career views aggregate by profile rather than by player_id.
-- Placeholder names (hidden '********', 'Unknown Player_N', blank) are NOT
-- merged: they stand for different people, so they keep one profile per ID.
DROP VIEW IF EXISTS player_profiles;
CREATE VIEW player_profiles AS
SELECT player_id,
       CASE WHEN name IS NULL
              OR TRIM(name) NOT GLOB '*[A-Za-z]*'
              OR LOWER(TRIM(name)) LIKE 'unknown player%'
            THEN 'id:' || player_id
            ELSE 'name:' || LOWER(TRIM(name))
       END AS profile
FROM players;

DROP VIEW IF EXISTS career_batting;
CREATE VIEW career_batting AS
SELECT pp.profile,
       SUM(b.batted)                                         AS innings,
       SUM(b.batted * b.not_out)                             AS not_outs,
       SUM(b.runs)                                           AS runs,
       SUM(b.balls)                                          AS balls_faced,
       SUM(b.fours)                                          AS fours,
       SUM(b.sixes)                                          AS sixes,
       SUM(CASE WHEN b.runs >= 50 AND b.runs < 100 THEN 1 ELSE 0 END) AS fifties,
       SUM(CASE WHEN b.runs >= 100 THEN 1 ELSE 0 END)        AS hundreds,
       SUM(CASE WHEN b.batted = 1 AND b.runs = 0 AND b.not_out = 0 THEN 1 ELSE 0 END) AS ducks,
       MAX(b.runs)                                           AS high_score,
       ROUND(1.0 * SUM(b.runs) / NULLIF(SUM(b.batted) - SUM(b.batted * b.not_out), 0), 2) AS average,
       ROUND(100.0 * SUM(b.runs) / NULLIF(SUM(b.balls), 0), 2) AS strike_rate
FROM batting b JOIN player_profiles pp USING(player_id)
GROUP BY pp.profile;

DROP VIEW IF EXISTS career_bowling;
CREATE VIEW career_bowling AS
SELECT pp.profile,
       COUNT(*)                                              AS bowling_innings,
       SUM(w.balls)                                          AS balls_bowled,
       (SUM(w.balls) / 6) || '.' || (SUM(w.balls) % 6)       AS overs,
       SUM(w.maidens)                                        AS maidens,
       SUM(w.runs_conceded)                                  AS runs_conceded,
       SUM(w.wickets)                                        AS wickets,
       SUM(CASE WHEN w.wickets >= 3 AND w.wickets < 5 THEN 1 ELSE 0 END) AS three_fors,
       SUM(CASE WHEN w.wickets >= 5 THEN 1 ELSE 0 END)       AS five_wicket_hauls,
       ROUND(1.0 * SUM(w.runs_conceded) / NULLIF(SUM(w.wickets), 0), 2) AS average,
       ROUND(6.0 * SUM(w.runs_conceded) / NULLIF(SUM(w.balls), 0), 2)   AS economy,
       ROUND(1.0 * SUM(w.balls) / NULLIF(SUM(w.wickets), 0), 1)         AS strike_rate
FROM bowling w JOIN player_profiles pp USING(player_id)
GROUP BY pp.profile;

DROP VIEW IF EXISTS career_bowling_best;
CREATE VIEW career_bowling_best AS
SELECT profile, wickets || '/' || runs_conceded AS best_bowling FROM (
    SELECT pp.profile, w.wickets, w.runs_conceded,
           ROW_NUMBER() OVER (PARTITION BY pp.profile
                              ORDER BY w.wickets DESC, w.runs_conceded ASC) AS rn
    FROM bowling w JOIN player_profiles pp USING(player_id) WHERE w.balls > 0)
WHERE rn = 1;

DROP VIEW IF EXISTS career_high_score;
CREATE VIEW career_high_score AS
SELECT profile, runs || CASE WHEN not_out = 1 THEN '*' ELSE '' END AS high_score FROM (
    SELECT pp.profile, b.runs, b.not_out,
           ROW_NUMBER() OVER (PARTITION BY pp.profile
                              ORDER BY b.runs DESC, b.not_out DESC) AS rn
    FROM batting b JOIN player_profiles pp USING(player_id) WHERE b.batted = 1)
WHERE rn = 1;

DROP VIEW IF EXISTS ten_wicket_matches;
CREATE VIEW ten_wicket_matches AS
SELECT profile, COUNT(*) AS ten_wicket_matches FROM (
    SELECT pp.profile, w.match_id FROM bowling w JOIN player_profiles pp USING(player_id)
    GROUP BY pp.profile, w.match_id HAVING SUM(w.wickets) >= 10)
GROUP BY profile;

DROP VIEW IF EXISTS career_fielding;
CREATE VIEW career_fielding AS
SELECT pp.profile,
       SUM(f.catches)    AS catches,
       SUM(f.wk_catches) AS wk_catches,
       SUM(f.stumpings)  AS stumpings,
       SUM(f.run_outs)   AS run_outs
FROM fielding f JOIN player_profiles pp USING(player_id) GROUP BY pp.profile;

DROP VIEW IF EXISTS career_appearances;
CREATE VIEW career_appearances AS
SELECT pp.profile,
       COUNT(DISTINCT a.match_id) AS matches,
       MIN(m.season)              AS first_season,
       MAX(m.season)              AS last_season
FROM appearances a JOIN player_profiles pp USING(player_id)
LEFT JOIN matches m USING(match_id)
GROUP BY pp.profile;

-- Career totals per profile, built from season_stats (official Play Cricket
-- figures wherever available). Same-name player IDs are merged into one profile.
DROP VIEW IF EXISTS career_stats;
CREATE VIEW career_stats AS
WITH s AS (
    SELECT pp.profile, ss.* FROM season_stats ss JOIN player_profiles pp USING(player_id)
),
agg AS (
    SELECT profile,
           SUM(matches) matches, MIN(season) first_season, MAX(season) last_season,
           SUM(bat_innings) bat_innings, SUM(not_outs) not_outs, SUM(runs) runs,
           SUM(fifties) fifties, SUM(hundreds) hundreds, SUM(ducks) ducks,
           SUM(fours) fours, SUM(sixes) sixes, SUM(sr_balls) sr_balls, SUM(sr_runs) sr_runs,
           SUM(balls_bowled) balls_bowled, SUM(maidens) maidens,
           SUM(runs_conceded) runs_conceded, SUM(wickets) wickets,
           SUM(three_fors) three_fors, SUM(five_wi) five_wi, SUM(ten_wm) ten_wm,
           SUM(catches) catches, SUM(wk_catches) wk_catches,
           SUM(stumpings) stumpings, SUM(run_outs) run_outs
    FROM s GROUP BY profile
),
hs AS (
    SELECT profile, high_score || CASE WHEN hs_not_out = 1 THEN '*' ELSE '' END AS high_score FROM (
        SELECT profile, high_score, hs_not_out,
               ROW_NUMBER() OVER (PARTITION BY profile ORDER BY high_score DESC, hs_not_out DESC) rn
        FROM s WHERE bat_innings > 0)
    WHERE rn = 1
),
bb AS (
    SELECT profile, best_w || '/' || best_r AS best_bowling FROM (
        SELECT profile, best_w, best_r,
               ROW_NUMBER() OVER (PARTITION BY profile ORDER BY best_w DESC, best_r ASC) rn
        FROM s WHERE best_w IS NOT NULL AND (balls_bowled > 0 OR wickets > 0))
    WHERE rn = 1
),
pr AS (
    SELECT pp.profile, MAX(TRIM(p.name)) AS name, GROUP_CONCAT(p.player_id, ';') AS player_ids
    FROM players p JOIN player_profiles pp USING(player_id) GROUP BY pp.profile
)
SELECT pr.player_ids, pr.name,
       COALESCE(a.matches,0) AS matches, a.first_season, a.last_season,
       COALESCE(a.bat_innings,0) AS bat_innings, COALESCE(a.not_outs,0) AS not_outs,
       COALESCE(a.runs,0) AS runs, hs.high_score,
       ROUND(1.0 * a.runs / NULLIF(a.bat_innings - a.not_outs, 0), 2) AS bat_average,
       ROUND(100.0 * a.sr_runs / NULLIF(a.sr_balls, 0), 2) AS bat_strike_rate,
       COALESCE(a.fifties,0) AS fifties, COALESCE(a.hundreds,0) AS hundreds,
       COALESCE(a.ducks,0) AS ducks, COALESCE(a.fours,0) AS fours, COALESCE(a.sixes,0) AS sixes,
       (COALESCE(a.balls_bowled,0) / 6) || '.' || (COALESCE(a.balls_bowled,0) % 6) AS overs,
       COALESCE(a.maidens,0) AS maidens, COALESCE(a.runs_conceded,0) AS runs_conceded,
       COALESCE(a.wickets,0) AS wickets, bb.best_bowling,
       ROUND(1.0 * a.runs_conceded / NULLIF(a.wickets, 0), 2) AS bowl_average,
       ROUND(6.0 * a.runs_conceded / NULLIF(a.balls_bowled, 0), 2) AS economy,
       ROUND(1.0 * a.balls_bowled / NULLIF(a.wickets, 0), 1) AS bowl_strike_rate,
       COALESCE(a.three_fors,0) AS three_wicket_hauls,
       COALESCE(a.five_wi,0) AS five_wicket_hauls, COALESCE(a.ten_wm,0) AS ten_wicket_matches,
       COALESCE(a.catches,0) AS catches, COALESCE(a.wk_catches,0) AS wk_catches,
       COALESCE(a.stumpings,0) AS stumpings, COALESCE(a.run_outs,0) AS run_outs
FROM pr
LEFT JOIN agg a ON a.profile = pr.profile
LEFT JOIN hs    ON hs.profile = pr.profile
LEFT JOIN bb    ON bb.profile = pr.profile;
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    return con


# --------------------------------------------------------------------------- #
# Parsing a scorecard into rows
# --------------------------------------------------------------------------- #
def _i(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def overs_to_balls(overs) -> int:
    """'12.4' -> 76 balls. Handles ints, floats and strings."""
    if overs in (None, ""):
        return 0
    s = str(overs)
    whole, _, part = s.partition(".")
    return _i(whole) * 6 + _i(part[:1] or 0)


def ingest_match(con: sqlite3.Connection, d: dict) -> None:
    """Replace everything stored for this match with what's in the scorecard `d`."""
    mid = d["id"]
    meta = d.get("_meta", {})
    for table in ("batting", "bowling", "fielding", "appearances"):
        con.execute(f"DELETE FROM {table} WHERE match_id = ?", (mid,))

    teams = d.get("teams") or []
    summary_teams = {t["id"]: t for t in (d.get("matchSummary") or {}).get("teams", [])}
    shcc_ids = {t["id"] for t in teams if is_shcc_team(t)}
    if not shcc_ids:  # fallback: match teams by name
        shcc_ids = {t["id"] for t in teams if "sydenham" in (t.get("displayName") or "").lower()}
    team_ids = [t["id"] for t in teams]

    # players & appearances (SHCC only)
    for t in teams:
        if t["id"] not in shcc_ids:
            continue
        for p in t.get("players") or []:
            pid = p.get("participantId")
            if not pid:
                continue
            con.execute(
                "INSERT INTO players(player_id, name, short_name) VALUES (?,?,?) "
                "ON CONFLICT(player_id) DO UPDATE SET "
                "name = COALESCE(excluded.name, players.name), "
                "short_name = COALESCE(excluded.short_name, players.short_name)",
                (pid, p.get("name"), p.get("shortName")))
            con.execute("INSERT OR IGNORE INTO appearances VALUES (?,?)", (mid, pid))

    def ensure_player(pid, short):
        con.execute("INSERT OR IGNORE INTO players(player_id, name, short_name) VALUES (?,?,?)",
                    (pid, short, short))
        con.execute("INSERT OR IGNORE INTO appearances VALUES (?,?)", (mid, pid))

    innings_list = d.get("innings") or []
    for n, inn in enumerate(innings_list, start=1):
        inn_no = _i(inn.get("inningsOrder")) or n
        bat_team = inn.get("battingTeamId")
        others = [x for x in team_ids if x != bat_team]
        field_team = others[0] if others else None

        if bat_team in shcc_ids:
            for b in inn.get("batting") or []:
                pid = b.get("participantId")
                if not pid:
                    continue
                ensure_player(pid, b.get("playerShortName"))
                dtype = (b.get("dismissalType") or "").strip()
                batted = 0 if (dtype.lower() in DID_NOT_BAT or b.get("dismissalTypeId") == 0) else 1
                not_out = 1 if (dtype.lower() in NOT_OUT or b.get("dismissalTypeId") == 1) else 0
                con.execute(
                    "INSERT OR REPLACE INTO batting VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (mid, inn_no, pid, _i(b.get("batOrder")), _i(b.get("runsScored")),
                     _i(b.get("ballsFaced")), _i(b.get("foursScored")), _i(b.get("sixesScored")),
                     dtype, b.get("dismissalText"), batted, not_out if batted else 0))

        if field_team in shcc_ids:
            for w in inn.get("bowling") or []:
                pid = w.get("participantId")
                if not pid:
                    continue
                ensure_player(pid, w.get("playerShortName"))
                con.execute(
                    "INSERT OR REPLACE INTO bowling VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (mid, inn_no, pid, overs_to_balls(w.get("oversBowled")), str(w.get("oversBowled")),
                     _i(w.get("maidensBowled")), _i(w.get("runsConceded")), _i(w.get("wicketsTaken")),
                     _i(w.get("wideBalls")), _i(w.get("noBalls"))))
            for f in inn.get("fielding") or []:
                pid = f.get("participantId")
                if not pid:
                    continue
                ensure_player(pid, f.get("playerShortName"))
                run_outs = _i(f.get("runOuts")) or (_i(f.get("unassistedRunOuts")) + _i(f.get("assistedRunOuts")))
                con.execute(
                    "INSERT OR REPLACE INTO fielding VALUES (?,?,?,?,?,?,?)",
                    (mid, inn_no, pid, _i(f.get("catches")), _i(f.get("wicketKeeperCatches")),
                     _i(f.get("stumpings")), run_outs))

    # match row
    shcc_team = next((t for t in teams if t["id"] in shcc_ids), {})
    opp = next((t for t in teams if t["id"] not in shcc_ids), {})
    won = summary_teams.get(shcc_team.get("id"), {}).get("isWinner")
    start = match_start(d)
    con.execute(
        "INSERT OR REPLACE INTO matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (mid, meta.get("season"), (d.get("grade") or {}).get("name") or meta.get("grade_name"),
         (d.get("round") or {}).get("name"), start.date().isoformat() if start else None,
         d.get("matchType"), d.get("status"), shcc_team.get("displayName"), opp.get("displayName"),
         (d.get("matchSummary") or {}).get("resultText"),
         None if won is None else int(bool(won)),
         int(any((i.get("batting") or i.get("bowling")) for i in innings_list)),
         meta.get("fetched_at")))


def rebuild_from_cache(con: sqlite3.Connection) -> int:
    """Re-parse every cached raw match JSON (and official player totals) into the database."""
    n = 0
    for p in sorted(RAW_DIR.glob("*.json")):
        ingest_match(con, json.loads(p.read_text()))
        n += 1
    load_official_cache(con)
    materialize_season_stats(con)
    con.commit()
    return n


# --------------------------------------------------------------------------- #
# Official Play Cricket totals (source of truth for career/season figures)
# --------------------------------------------------------------------------- #
OFFICIAL_COLS = ["matches", "bat_innings", "not_outs", "runs", "high_score", "hs_not_out",
                 "fifties", "hundreds", "ducks", "fours", "sixes", "balls_bowled", "maidens",
                 "runs_conceded", "wickets", "best_w", "best_r", "five_wi", "ten_wm",
                 "catches", "wk_catches", "stumpings", "run_outs"]


def parse_summary(j: dict) -> dict | None:
    """summary-statistics JSON -> official_season_stats columns (None if nothing played)."""
    if not j or not any(_i(j.get(k)) for k in ("matches", "battingInnings", "bowlingBalls",
                                                  "fieldingTotalCatches", "fieldingRunOuts")):
        return None
    best = str(j.get("bowlingBestInnings") or "")
    bw, _, br = best.partition("-")
    return {
        "matches": _i(j.get("matches")), "bat_innings": _i(j.get("battingInnings")),
        "not_outs": _i(j.get("battingNotOuts")), "runs": _i(j.get("battingAggregate")),
        "high_score": _i(j.get("battingHighScore")), "hs_not_out": int(bool(j.get("isBattingHSNotOut"))),
        "fifties": _i(j.get("batting50s")), "hundreds": _i(j.get("batting100s")),
        "ducks": _i(j.get("batting0s")), "fours": _i(j.get("battingFours")),
        "sixes": _i(j.get("battingSixes")), "balls_bowled": _i(j.get("bowlingBalls")),
        "maidens": _i(j.get("bowlingMaidens")), "runs_conceded": _i(j.get("bowlingRuns")),
        "wickets": _i(j.get("bowlingWickets")),
        "best_w": _i(bw) if best else None, "best_r": _i(br) if best else None,
        "five_wi": _i(j.get("bowling5WIs")), "ten_wm": _i(j.get("bowling10WMs")),
        "catches": _i(j.get("fieldingCatchesNonWK")), "wk_catches": _i(j.get("fieldingCatchesWK")),
        "stumpings": _i(j.get("fieldingStumpings")), "run_outs": _i(j.get("fieldingRunOuts")),
    }


def player_cache_path(player_id: str) -> Path:
    return PLAYER_DIR / f"{player_id}.json"


def store_official(con: sqlite3.Connection, player_id: str, cache: dict) -> None:
    """Write one player's cached official season totals into official_season_stats."""
    con.execute("DELETE FROM official_season_stats WHERE player_id = ?", (player_id,))
    for season, j in (cache.get("summaries") or {}).items():
        row = parse_summary(j)
        if row:
            con.execute(f"INSERT INTO official_season_stats (player_id, season, {', '.join(OFFICIAL_COLS)}) "
                        f"VALUES (?, ?, {', '.join('?' * len(OFFICIAL_COLS))})",
                        (player_id, season, *[row[c] for c in OFFICIAL_COLS]))
    con.execute("INSERT OR REPLACE INTO official_sync VALUES (?, ?)", (player_id, cache.get("fetched_at")))


def load_official_cache(con: sqlite3.Connection) -> int:
    n = 0
    for p in sorted(PLAYER_DIR.glob("*.json")) if PLAYER_DIR.exists() else []:
        store_official(con, p.stem, json.loads(p.read_text()))
        n += 1
    return n


def scorecard_season_stats(con: sqlite3.Connection) -> dict:
    """{(player_id, season): stats} computed from scorecards, in season_stats columns."""
    out: dict = {}

    def row(pid, season):
        k = (pid, season)
        if k not in out:
            out[k] = {c: 0 for c in OFFICIAL_COLS + ["sr_balls", "sr_runs", "three_fors"]}
            out[k].update(high_score=None, best_w=None, best_r=None)
        return out[k]

    for pid, season, n in con.execute(
            "SELECT a.player_id, m.season, COUNT(*) FROM appearances a JOIN matches m USING(match_id) "
            "GROUP BY a.player_id, m.season"):
        row(pid, season)["matches"] = n
    for pid, season, runs, balls, fours, sixes, no in con.execute(
            "SELECT b.player_id, m.season, b.runs, b.balls, b.fours, b.sixes, b.not_out "
            "FROM batting b JOIN matches m USING(match_id) WHERE b.batted = 1"):
        r = row(pid, season)
        r["bat_innings"] += 1; r["runs"] += runs; r["fours"] += fours; r["sixes"] += sixes
        r["not_outs"] += no
        if balls > 0:
            r["sr_balls"] += balls; r["sr_runs"] += runs
        if runs >= 100: r["hundreds"] += 1
        elif runs >= 50: r["fifties"] += 1
        if runs == 0 and not no: r["ducks"] += 1
        if r["high_score"] is None or runs > r["high_score"] or (runs == r["high_score"] and no):
            r["high_score"], r["hs_not_out"] = runs, no
    for pid, season, balls, mdn, rc, w in con.execute(
            "SELECT w.player_id, m.season, w.balls, w.maidens, w.runs_conceded, w.wickets "
            "FROM bowling w JOIN matches m USING(match_id)"):
        r = row(pid, season)
        r["balls_bowled"] += balls; r["maidens"] += mdn; r["runs_conceded"] += rc; r["wickets"] += w
        if w >= 5: r["five_wi"] += 1
        elif w >= 3: r["three_fors"] += 1
        if balls > 0 and (r["best_w"] is None or w > r["best_w"] or (w == r["best_w"] and rc < r["best_r"])):
            r["best_w"], r["best_r"] = w, rc
    for pid, season, n in con.execute(
            "SELECT w.player_id, m.season, COUNT(*) FROM (SELECT player_id, match_id FROM bowling "
            "GROUP BY player_id, match_id HAVING SUM(wickets) >= 10) w JOIN matches m USING(match_id) "
            "GROUP BY w.player_id, m.season"):
        row(pid, season)["ten_wm"] = n
    for pid, season, c, wk, st, ro in con.execute(
            "SELECT f.player_id, m.season, SUM(catches), SUM(wk_catches), SUM(stumpings), SUM(run_outs) "
            "FROM fielding f JOIN matches m USING(match_id) GROUP BY f.player_id, m.season"):
        r = row(pid, season)
        r["catches"], r["wk_catches"], r["stumpings"], r["run_outs"] = c, wk, st, ro
    return out


def materialize_season_stats(con: sqlite3.Connection) -> None:
    """Fill season_stats: official totals for synced players, scorecard totals for the rest."""
    sc = scorecard_season_stats(con)
    synced = {r[0] for r in con.execute("SELECT player_id FROM official_sync")}
    official = {(r[0], r[1]): dict(zip(OFFICIAL_COLS, r[2:])) for r in con.execute(
        f"SELECT player_id, season, {', '.join(OFFICIAL_COLS)} FROM official_season_stats")}
    con.execute("DELETE FROM season_stats")
    cols = ["player_id", "season", "source"] + OFFICIAL_COLS + ["sr_balls", "sr_runs", "three_fors"]
    sql = f"INSERT INTO season_stats ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    for (pid, season), r in sc.items():
        if pid in synced:
            continue
        con.execute(sql, (pid, season, "scorecards", *[r[c] for c in OFFICIAL_COLS],
                          r["sr_balls"], r["sr_runs"], r["three_fors"]))
    for (pid, season), o in official.items():
        s = sc.get((pid, season), {})
        con.execute(sql, (pid, season, "official", *[o[c] for c in OFFICIAL_COLS],
                          s.get("sr_balls", 0), s.get("sr_runs", 0), s.get("three_fors", 0)))


def _load_non_shcc() -> set:
    return set(json.loads(NON_SHCC_FILE.read_text())) if NON_SHCC_FILE.exists() else set()


def _save_non_shcc(ids: set) -> None:
    NON_SHCC_FILE.write_text(json.dumps(sorted(ids)))


SHCC_NAME_HINTS = ("sydenham", "hillside", "shcc", "s/h", "s-h")


def discover_player_matches(con, client: Client, player_id: str, season_id: str, season_name: str,
                            non_shcc: set) -> int:
    """Find SHCC matches this player played that the grade walk missed. Returns # added."""
    known = {r[0] for r in con.execute("SELECT match_id FROM matches")}
    added = 0
    for m in client.player_matches(player_id, season_id):
        mid = m.get("id")
        if not mid or mid in known or mid in non_shcc:
            continue
        names = " ".join((t.get("displayName") or "").lower() for t in m.get("teams") or [])
        if not any(h in names for h in SHCC_NAME_HINTS):
            non_shcc.add(mid)
            continue
        d = client.match(mid)
        if not d or not any(is_shcc_team(t) for t in d.get("teams") or []):
            non_shcc.add(mid)
            continue
        meta = {"_season": season_name, "_grade_name": (m.get("grade") or {}).get("name"),
                "_grade_id": (m.get("grade") or {}).get("id")}
        save_raw(mid, d, meta)
        ingest_match(con, load_raw(mid))
        known.add(mid)
        added += 1
        log.info("  + found missing match %s  %s  %s", season_name, meta["_grade_name"],
                 (d.get("matchSummary") or {}).get("resultText", ""))
    return added


def sync_player(con, client: Client, player_id: str, only_seasons: set | None = None,
                discover: bool = True, non_shcc: set | None = None) -> int:
    """Fetch official season totals for a player (cached), and pull in any SHCC matches
    that are missing for seasons where our scorecards disagree with Play Cricket.
    Returns the number of matches added."""
    PLAYER_DIR.mkdir(parents=True, exist_ok=True)
    path = player_cache_path(player_id)
    cache = json.loads(path.read_text()) if path.exists() else {"summaries": {}}
    non_shcc = non_shcc if non_shcc is not None else _load_non_shcc()
    seasons = client.player_seasons(player_id)
    added = 0
    for se in seasons:
        name = se.get("name")
        if only_seasons and name not in only_seasons:
            continue
        j = client.player_summary(player_id, se["id"])
        cache["summaries"][name] = j
        off = parse_summary(j)
        if not (discover and off):
            continue
        ours = con.execute(
            "SELECT COUNT(*) FROM appearances a JOIN matches m USING(match_id) "
            "WHERE a.player_id = ? AND m.season = ?", (player_id, name)).fetchone()[0]
        runs = con.execute(
            "SELECT COALESCE(SUM(b.runs),0) FROM batting b JOIN matches m USING(match_id) "
            "WHERE b.player_id = ? AND m.season = ?", (player_id, name)).fetchone()[0]
        if ours < off["matches"] or runs < off["runs"]:
            added += discover_player_matches(con, client, player_id, se["id"], name, non_shcc)
    cache["fetched_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(cache))
    store_official(con, player_id, cache)
    _save_non_shcc(non_shcc)
    return added


def export_csv(con: sqlite3.Connection, out: Path | None = None) -> Path:
    import csv
    out = out or DATA_DIR / "shcc_career_stats.csv"
    cur = con.execute("SELECT * FROM career_stats WHERE matches > 0 OR bat_innings > 0 "
                      "ORDER BY runs DESC, wickets DESC")
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([c[0] for c in cur.description])
        w.writerows(cur)
    return out


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
