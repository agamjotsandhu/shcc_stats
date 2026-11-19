"""Export data/shcc_stats.db to site/data.json for the static stats website.

Usage:  python build_site.py
Then open site/ with any static server, e.g.  python -m http.server -d site 8000
Re-run after update_matches.py to refresh the site.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "data" / "shcc_stats.db"
OUT = ROOT / "site" / "data.json"

JUNIOR_RE = re.compile(
    r"\bU ?\d{1,2}|under ?\d|\bU/\d|junior|girls|grading|^\s*1[0-8] ?[A-H]\b|^\s*1[0-8][A-H]\b|"
    r"kurle|mccabe|ebkca|wringe|turner shield|molly strano|U1\d",
    re.I,
)
WOMEN_RE = re.compile(r"women|cathy moloney", re.I)
FORMATS = ["One Day", "Two Day", "T20"]


def category(grade, team):
    text = f"{grade} | {team}"
    if WOMEN_RE.search(text) and not re.search(r"girls|U ?1\d", text, re.I):
        return 1  # women
    if JUNIOR_RE.search(text):
        return 2  # junior
    return 0  # senior


def result_code(won, status, text):
    t = (text or "").lower()
    if status in ("BYE", "CANCELLED"):
        return "-"
    if won == 1:
        return "W"
    if "tie" in t and "won" not in t:
        return "T"
    if "won" in t:
        return "L"
    if status in ("PENDING", "LIVE", "IN PROGRESS", "STUMPS"):
        return "-"
    return "D"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    q = lambda sql: con.execute(sql).fetchall()

    # ---- players (merged profiles) ----
    prof_rows = q("""SELECT pp.profile, p.player_id, TRIM(p.name) name
                     FROM players p JOIN player_profiles pp USING(player_id)""")
    prof_index, players, pid_to_idx = {}, [], {}
    for r in prof_rows:
        if r["profile"] not in prof_index:
            placeholder = r["profile"].startswith("id:")
            prof_index[r["profile"]] = len(players)
            name = re.sub(r"\s+", " ", r["name"] or "Unknown")
            if name.isupper() or name.islower():
                name = name.title()
            players.append({"n": name, "x": 1 if placeholder else 0})
        pid_to_idx[r["player_id"]] = prof_index[r["profile"]]

    # ---- matches ----
    m_rows = q("""SELECT * FROM matches ORDER BY match_date, match_id""")
    seasons = sorted({r["season"] for r in m_rows})
    season_idx = {s: i for i, s in enumerate(seasons)}
    grades, grade_idx = [], {}
    matches, mid_to_idx = [], {}
    for r in m_rows:
        g = re.sub(r"\s+", " ", (r["grade_name"] or "").strip())
        if g not in grade_idx:
            grade_idx[g] = len(grades)
            grades.append(g)
        fmt = FORMATS.index(r["match_type"]) if r["match_type"] in FORMATS else -1
        mid_to_idx[r["match_id"]] = len(matches)
        matches.append([
            season_idx[r["season"]],
            grade_idx[g],
            category(g, r["shcc_team"] or ""),
            fmt,
            r["match_date"] or "",
            r["round_name"] or "",
            r["opponent"] or "",
            result_code(r["shcc_won"], r["status"], r["result_text"]),
            r["result_text"] or "",
            r["has_scorecard"] or 0,
        ])

    def m(mid):
        return mid_to_idx.get(mid)

    bat = []
    for r in q("""SELECT match_id, player_id, runs, balls, fours, sixes, not_out
                  FROM batting WHERE batted = 1"""):
        if m(r["match_id"]) is None or r["player_id"] not in pid_to_idx:
            continue
        bat.append([m(r["match_id"]), pid_to_idx[r["player_id"]], r["runs"] or 0,
                    r["balls"] or 0, r["fours"] or 0, r["sixes"] or 0, r["not_out"] or 0])

    bowl = []
    for r in q("""SELECT match_id, player_id, balls, maidens, runs_conceded, wickets
                  FROM bowling WHERE balls > 0 OR wickets > 0"""):
        if m(r["match_id"]) is None or r["player_id"] not in pid_to_idx:
            continue
        bowl.append([m(r["match_id"]), pid_to_idx[r["player_id"]], r["balls"] or 0,
                     r["maidens"] or 0, r["runs_conceded"] or 0, r["wickets"] or 0])

    field = []
    for r in q("""SELECT match_id, player_id, SUM(catches) c, SUM(wk_catches) wk,
                         SUM(stumpings) st, SUM(run_outs) ro
                  FROM fielding GROUP BY match_id, player_id"""):
        if m(r["match_id"]) is None or r["player_id"] not in pid_to_idx:
            continue
        vals = [r["c"] or 0, r["wk"] or 0, r["st"] or 0, r["ro"] or 0]
        if any(vals):
            field.append([m(r["match_id"]), pid_to_idx[r["player_id"]], *vals])

    # appearances, deduped per merged profile
    app = sorted({(m(r["match_id"]), pid_to_idx[r["player_id"]])
                  for r in q("SELECT match_id, player_id FROM appearances")
                  if m(r["match_id"]) is not None and r["player_id"] in pid_to_idx})

    data = {
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "seasons": [s.replace("Summer ", "") for s in seasons],
        "grades": grades,
        "players": [[p["n"], p["x"]] for p in players],
        "matches": matches,
        "bat": bat,
        "bowl": bowl,
        "field": field,
        "app": [list(a) for a in app],
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB): "
          f"{len(matches)} matches, {len(players)} players, {len(bat)} innings")


if __name__ == "__main__":
    main()
