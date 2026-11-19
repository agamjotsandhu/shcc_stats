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
Run it weekly (e.g. Sunday/Monday night) via cron or Task Scheduler.
"""
import argparse

from shcc_common import (Client, connect, export_csv, ingest_match, is_played, load_raw,
                         log, save_raw, season_matches, setup_logging)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seasons", type=int, default=2, help="how many recent seasons to check")
    ap.add_argument("--delay", type=float, default=0.35)
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
    log.info("Career stats CSV: %s", export_csv(con))


if __name__ == "__main__":
    main()
