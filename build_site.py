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


ADJ_FIELDS = ["matches", "bat_innings", "not_outs", "runs", "fifties", "hundreds", "ducks", "fours",
              "sixes", "balls_bowled", "maidens", "runs_conceded", "wickets", "five_wi", "catches",
              "wk_catches", "stumpings", "run_outs"]


def official_adjustments(con, players, pid_to_idx, matches, seasons, season_idx, bat, bowl, field, app):
    """Per profile & season: Play Cricket's official totals minus what the exported
    scorecard rows add up to. The site adds these rows so its totals match Play Cricket.

    Row: [profile, season, category, *deltas(ADJ_FIELDS), hs, hs_not_out, best_w, best_r]
    hs / best_w are -1 unless Play Cricket's best is better than any published scorecard.
    """
    from collections import Counter, defaultdict

    blank = lambda: {**{f: 0 for f in ADJ_FIELDS}, "hs": -1, "hsno": 0, "bw": -1, "br": 0}
    sc = defaultdict(blank)
    cat_count = defaultdict(Counter)
    for mi, p in app:
        m = matches[mi]
        sc[(p, m[0])]["matches"] += 1
        cat_count[p][m[2]] += 1
        cat_count[(p, m[0])][m[2]] += 1
    for mi, p, runs, balls, fours, sixes, no in bat:
        r = sc[(p, matches[mi][0])]
        r["bat_innings"] += 1; r["not_outs"] += no; r["runs"] += runs
        r["fours"] += fours; r["sixes"] += sixes
        if runs >= 100: r["hundreds"] += 1
        elif runs >= 50: r["fifties"] += 1
        if runs == 0 and not no: r["ducks"] += 1
        if runs > r["hs"] or (runs == r["hs"] and no): r["hs"], r["hsno"] = runs, no
    for mi, p, balls, mdn, rc, w in bowl:
        r = sc[(p, matches[mi][0])]
        r["balls_bowled"] += balls; r["maidens"] += mdn; r["runs_conceded"] += rc; r["wickets"] += w
        if w >= 5: r["five_wi"] += 1
        if w > r["bw"] or (w == r["bw"] and rc < r["br"]): r["bw"], r["br"] = w, rc
    for mi, p, c, wk, st, ro in field:
        r = sc[(p, matches[mi][0])]
        r["catches"] += c; r["wk_catches"] += wk; r["stumpings"] += st; r["run_outs"] += ro

    target = defaultdict(blank)
    cols = ", ".join(ADJ_FIELDS)
    for row in con.execute(f"SELECT player_id, season, {cols}, high_score, hs_not_out, best_w, best_r, "
                           f"bat_innings FROM season_stats"):
        pid, season = row[0], row[1]
        if pid not in pid_to_idx or season not in season_idx:
            continue
        t = target[(pid_to_idx[pid], season_idx[season])]
        for f, v in zip(ADJ_FIELDS, row[2:2 + len(ADJ_FIELDS)]):
            t[f] += v or 0
        hs, hsno, bw, br, inn = row[2 + len(ADJ_FIELDS):]
        if inn and hs is not None and (hs > t["hs"] or (hs == t["hs"] and hsno)):
            t["hs"], t["hsno"] = hs, hsno or 0
        if bw is not None and (bw > t["bw"] or (bw == t["bw"] and (br or 0) < t["br"])):
            t["bw"], t["br"] = bw, br or 0

    out = []
    for key in set(target) | set(sc):
        p, s = key
        t, m = target.get(key), sc.get(key, blank())
        if t is None:  # profile has scorecards but no season_stats row (shouldn't happen)
            continue
        deltas = [t[f] - m[f] for f in ADJ_FIELDS]
        hs = t["hs"] if (t["hs"] > m["hs"] or (t["hs"] == m["hs"] and t["hsno"] and not m["hsno"])) else -1
        better_bb = t["bw"] > m["bw"] or (t["bw"] == m["bw"] and t["bw"] >= 0 and t["br"] < m["br"])
        bw, br = (t["bw"], t["br"]) if better_bb else (-1, 0)
        if not any(deltas) and hs < 0 and bw < 0:
            continue
        cats = cat_count.get((p, s)) or cat_count.get(p) or Counter({0: 1})
        out.append([p, s, cats.most_common(1)[0][0], *deltas, hs, t["hsno"] if hs >= 0 else 0, bw, br])
    out.sort()
    return out


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
    seasons = sorted({r["season"] for r in m_rows} |
                     {r[0] for r in q("SELECT DISTINCT season FROM season_stats WHERE season IS NOT NULL")})
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

    adj = official_adjustments(con, players, pid_to_idx, matches, seasons, season_idx, bat, bowl, field, app)

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
        "adj": adj,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB): "
          f"{len(matches)} matches, {len(players)} players, {len(bat)} innings")


if __name__ == "__main__":
    main()
