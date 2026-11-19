#!/usr/bin/env python3
"""
Full historical scrape of every Sydenham-Hillside CC match on play.cricket.com.au.

    python scrape_history.py                 # all seasons (resumable)
    python scrape_history.py --from 2015     # only seasons starting 2015 onwards
    python scrape_history.py --rebuild-only  # re-parse cached JSON, no network
    python scrape_history.py --refetch       # ignore the cache and re-download everything

Raw scorecards are cached in data/raw_matches/, so if the run is interrupted
just run it again and it picks up where it left off.
"""
import argparse

from shcc_common import (Client, connect, export_csv, ingest_match, is_played, load_raw,
                         log, rebuild_from_cache, save_raw, season_matches, setup_logging)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="from_year", type=int, help="first season start year to include")
    ap.add_argument("--to", dest="to_year", type=int, help="last season start year to include")
    ap.add_argument("--delay", type=float, default=0.35, help="seconds between API requests")
    ap.add_argument("--refetch", action="store_true", help="re-download matches already cached")
    ap.add_argument("--rebuild-only", action="store_true", help="rebuild DB from cache only")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    setup_logging(args.verbose)

    con = connect()
    if args.rebuild_only:
        n = rebuild_from_cache(con)
        log.info("Rebuilt database from %d cached matches", n)
        log.info("Career stats CSV: %s", export_csv(con))
        return

    client = Client(delay=args.delay)
    seasons = client.seasons()
    seasons.sort(key=lambda s: s.get("startDate", ""))
    log.info("Found %d seasons (%s to %s)", len(seasons), seasons[0]["name"], seasons[-1]["name"])

    fetched = skipped = failed = 0
    for season in seasons:
        year = int(season.get("startDate", "0000")[:4] or 0)
        if (args.from_year and year < args.from_year) or (args.to_year and year > args.to_year):
            continue
        for m in season_matches(client, season):
            if not is_played(m):
                continue
            cached = load_raw(m["id"])
            if cached and not args.refetch and cached.get("status") == m.get("status"):
                skipped += 1
                continue
            try:
                d = client.match(m["id"])
            except Exception as e:  # keep going; a re-run will retry it
                log.error("Failed match %s: %s", m["id"], e)
                failed += 1
                continue
            if not d:
                continue
            save_raw(m["id"], d, m)
            ingest_match(con, load_raw(m["id"]))
            fetched += 1
            if fetched % 25 == 0:
                con.commit()
                log.info("...%d scorecards fetched so far", fetched)
        con.commit()

    log.info("Done. fetched=%d cached/skipped=%d failed=%d", fetched, skipped, failed)
    # Re-parse everything so the DB exactly matches the cache
    n = rebuild_from_cache(con)
    log.info("Database holds %d matches", n)
    log.info("Career stats CSV: %s", export_csv(con))


if __name__ == "__main__":
    main()
