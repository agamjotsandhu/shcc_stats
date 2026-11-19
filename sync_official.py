#!/usr/bin/env python3
"""
Sync every SHCC player's official Play Cricket totals (the numbers on their
play.cricket.com.au "Career" tab with Club = Sydenham-Hillside), and use them
to find SHCC matches the grade walk missed (e.g. T20 knockouts).

    python sync_official.py              # all players not yet synced (resumable)
    python sync_official.py --refresh    # re-sync everyone
    python sync_official.py --player <id>  # one player

Play Cricket's totals are the source of truth: season_stats / career_stats /
the CSV / the website use them wherever they exist. Scorecards still supply
match-level detail (records, results, format splits).
"""
import argparse
import json
import sqlite3

from shcc_common import (Client, PLAYER_DIR, _load_non_shcc, _save_non_shcc, connect, export_csv,
                         log, materialize_season_stats, player_cache_path, setup_logging, sync_player)

PLACEHOLDER_SQL = ("name IS NULL OR TRIM(name) NOT GLOB '*[A-Za-z]*' "
                   "OR LOWER(TRIM(name)) LIKE 'unknown player%'")


def report(con: sqlite3.Connection) -> None:
    """How many synced players' scorecard totals still differ from Play Cricket."""
    rows = con.execute("""
        WITH sc AS (
            SELECT a.player_id, COUNT(DISTINCT a.match_id) m FROM appearances a GROUP BY a.player_id),
        scr AS (SELECT player_id, SUM(runs) r FROM batting GROUP BY player_id),
        off AS (SELECT player_id, SUM(matches) m, SUM(runs) r FROM official_season_stats GROUP BY player_id)
        SELECT COUNT(*),
               SUM(COALESCE(off.m,0) = COALESCE(sc.m,0) AND COALESCE(off.r,0) = COALESCE(scr.r,0))
        FROM official_sync s LEFT JOIN off USING(player_id) LEFT JOIN sc USING(player_id)
        LEFT JOIN scr USING(player_id)""").fetchone()
    log.info("Synced players: %d. Scorecards already identical to Play Cricket for %d; "
             "the rest use Play Cricket's totals (matches it counts but doesn't publish scorecards for, "
             "or scorecards it doesn't count).", rows[0], rows[1] or 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="re-sync players already synced")
    ap.add_argument("--player", help="sync a single player id")
    ap.add_argument("--no-discover", action="store_true", help="only fetch totals, don't look for missing matches")
    ap.add_argument("--delay", type=float, default=0.3)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    setup_logging(args.verbose)

    con = connect()
    client = Client(delay=args.delay)
    non_shcc = _load_non_shcc()
    done: set = set()
    total_added = 0
    pass_no = 0
    while True:
        pass_no += 1
        if args.player:
            todo = [args.player]
        else:
            todo = [r[0] for r in con.execute(f"SELECT player_id FROM players WHERE NOT ({PLACEHOLDER_SQL}) "
                                              "ORDER BY player_id")]
            todo = [p for p in todo if p not in done
                    and (args.refresh or not player_cache_path(p).exists())]
        if not todo:
            break
        log.info("Pass %d: syncing %d players", pass_no, len(todo))
        for i, pid in enumerate(todo, 1):
            try:
                total_added += sync_player(con, client, pid, discover=not args.no_discover, non_shcc=non_shcc)
            except Exception as e:  # keep going; re-run picks it up
                log.error("Failed player %s: %s", pid, e)
            done.add(pid)
            if i % 25 == 0:
                con.commit()
                _save_non_shcc(non_shcc)
                log.info("...%d/%d players, %d missing matches added so far", i, len(todo), total_added)
        con.commit()
        if args.player:
            break  # new players found in added matches are picked up on the next full run

    materialize_season_stats(con)
    con.commit()
    log.info("Done. %d missing matches added.", total_added)
    report(con)
    log.info("Career stats CSV: %s", export_csv(con))


if __name__ == "__main__":
    main()
