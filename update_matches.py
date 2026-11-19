#!/usr/bin/env python3
"""
Incremental update: pull in SHCC matches played since the last run.

    python update_matches.py              # current season (+ last season, to catch late corrections)
    python update_matches.py --seasons 1  # current season only
    python update_matches.py --seasons 3  # three most recent seasons

A match is (re)downloaded if:
  * it has been played and isn't in the cache yet, or
  * its status has changed since it was cached (e.g. IN_PROGRESS -> COMPLETED), or
  * it was still IN_PROGRESS last time (e.g. a two-day game captured after day 1).
Afterwards it re-syncs the official Play Cricket season totals for every player
who appeared in those seasons (and picks up any SHCC matches the grade walk missed).
Run it weekly (e.g. Sunday/Monday night) via cron or Task Scheduler.
"""
import argparse

from shcc_common import (Client, _load_non_shcc, _save_non_shcc, connect, export_csv, ingest_match,
                         is_played, load_raw, log, materialize_season_stats, save_raw, season_matches,
                         setup_logging, sync_player)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", type=int, default=2, help="how many recent seasons to check")
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--no-official", action="store_true", help="skip re-syncing Play Cricket player totals")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    setup_logging(args.verbose)

    con = connect()
    client = Client(delay=args.delay)
    seasons = sorted(client.seasons(), key=lambda s: s.get("startDate", ""), reverse=True)
    current = [s for s in seasons if s.get("isCurrentSeason")]
    start = seasons.index(current[0]) if current else 0
    targets = seasons[start:start + args.seasons]
    log.info("Checking seasons: %s", ", ".join(s["name"] for s in targets))

    new = updated = 0
    for season in targets:
        for m in season_matches(client, season):
            if not is_played(m):
                continue
            cached = load_raw(m["id"])
            # unchanged since last time (and not a live game) -> nothing new
            if cached and cached.get("status") == m.get("status") and m.get("status") != "IN_PROGRESS":
                continue
            d = client.match(m["id"])
            if not d:
                continue
            save_raw(m["id"], d, m)
            ingest_match(con, load_raw(m["id"]))
            if cached:
                updated += 1
                log.info("Updated  %s  %s", m["id"], d.get("matchSummary", {}).get("resultText", ""))
            else:
                new += 1
                log.info("Added    %s  %s", m["id"], d.get("matchSummary", {}).get("resultText", ""))
    con.commit()
    log.info("Done. %d new matches, %d updated", new, updated)

    if not args.no_official:
        names = {s["name"] for s in targets}
        q = ",".join("?" * len(names))
        pids = [r[0] for r in con.execute(
            f"SELECT DISTINCT a.player_id FROM appearances a JOIN matches m USING(match_id) "
            f"JOIN players p USING(player_id) WHERE m.season IN ({q}) AND p.name GLOB '*[A-Za-z]*' "
            f"AND LOWER(p.name) NOT LIKE 'unknown player%'", list(names))]
        log.info("Syncing Play Cricket totals for %d players (%s)", len(pids), ", ".join(sorted(names)))
        non_shcc, found = _load_non_shcc(), 0
        for i, pid in enumerate(pids, 1):
            try:
                found += sync_player(con, client, pid, only_seasons=names, non_shcc=non_shcc)
            except Exception as e:
                log.error("Failed player %s: %s", pid, e)
            if i % 50 == 0:
                con.commit()
        _save_non_shcc(non_shcc)
        log.info("Official totals synced; %d extra SHCC matches found", found)
    materialize_season_stats(con)
    con.commit()
    log.info("Career stats CSV: %s", export_csv(con))


if __name__ == "__main__":
    main()
