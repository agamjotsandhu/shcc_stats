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

DROP VIEW IF EXISTS career_stats;
CREATE VIEW career_stats AS
SELECT pr.player_ids, pr.name,
       COALESCE(ap.matches,0) AS matches,
       ap.first_season,
       ap.last_season,
       COALESCE(b.innings,0)  AS bat_innings,
       COALESCE(b.not_outs,0) AS not_outs,
       COALESCE(b.runs,0)     AS runs,
       hs.high_score,
       b.average              AS bat_average,
       b.strike_rate          AS bat_strike_rate,
       COALESCE(b.fifties,0)  AS fifties,
       COALESCE(b.hundreds,0) AS hundreds,
       COALESCE(b.ducks,0)    AS ducks,
       COALESCE(b.fours,0)    AS fours,
       COALESCE(b.sixes,0)    AS sixes,
       COALESCE(w.overs,'0.0')  AS overs,
       COALESCE(w.maidens,0)    AS maidens,
       COALESCE(w.runs_conceded,0) AS runs_conceded,
       COALESCE(w.wickets,0)    AS wickets,
       bb.best_bowling,
       w.average                AS bowl_average,
       w.economy                AS economy,
       w.strike_rate            AS bowl_strike_rate,
       COALESCE(w.three_fors,0) AS three_wicket_hauls,
       COALESCE(w.five_wicket_hauls,0) AS five_wicket_hauls,
       COALESCE(t.ten_wicket_matches,0) AS ten_wicket_matches,
       COALESCE(f.catches,0)    AS catches,
       COALESCE(f.wk_catches,0) AS wk_catches,
       COALESCE(f.stumpings,0)  AS stumpings,
       COALESCE(f.run_outs,0)   AS run_outs
FROM (SELECT pp.profile,
             MAX(TRIM(p.name))              AS name,
             GROUP_CONCAT(p.player_id, ';') AS player_ids
      FROM players p JOIN player_profiles pp USING(player_id)
      GROUP BY pp.profile) pr
LEFT JOIN career_appearances  ap ON ap.profile = pr.profile
LEFT JOIN career_batting      b  ON b.profile  = pr.profile
LEFT JOIN career_high_score   hs ON hs.profile = pr.profile
LEFT JOIN career_bowling      w  ON w.profile  = pr.profile
LEFT JOIN career_bowling_best bb ON bb.profile = pr.profile
LEFT JOIN ten_wicket_matches  t  ON t.profile  = pr.profile
LEFT JOIN career_fielding     f  ON f.profile  = pr.profile;
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
    """Re-parse every cached raw match JSON into the database."""
    n = 0
    for p in sorted(RAW_DIR.glob("*.json")):
        ingest_match(con, json.loads(p.read_text()))
        n += 1
    con.commit()
    return n


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
