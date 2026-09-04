#!/usr/bin/env python3
"""Fetch Big Buck Hunter standings for one cabinet into data/standings.json.

Public, unauthenticated endpoints — no API key, no login:
  GET /world/qualifiers_search?search=<venue>   JSON, current-season leaderboard
  GET /profile/player/<id>                      HTML, lifetime totals

Built to run unattended on a timer: it retries transient failures, refuses to
replace good data with a suspicious result, and writes atomically so a crash
mid-run can never leave a truncated file behind.

Exit codes:  0 wrote new data   1 failed, previous data left untouched
"""
import argparse, json, os, random, re, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.bigbuckhunter.com"
# The site's WAF rejects default urllib/curl agents with a 403.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "standings.json"


def log(msg):
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%SZ}] {msg}", file=sys.stderr, flush=True)


def get(url, headers=None, tries=4, timeout=45):
    """GET with exponential backoff. Raises the last error if every try fails."""
    last = None
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last = e
            if attempt == tries:
                break
            delay = min(60, 2 ** attempt) + random.uniform(0, 1)
            log(f"  attempt {attempt}/{tries} failed ({e}); retrying in {delay:.1f}s")
            time.sleep(delay)
    raise RuntimeError(f"GET {url} failed after {tries} attempts: {last}")


def season_rows(location):
    """Season leaderboard rows whose venue is exactly `location`.

    The search matches player names AND venue names, so filter on the venue to
    drop coincidental name hits (searching "Alloy" also returns a "Malloy").
    """
    qs = urllib.parse.urlencode({
        "order_by": "WildcardRank", "order_direction": "asc",
        "search": location, "limit": 500, "offset": 0,
    })
    raw = get(f"{BASE}/world/qualifiers_search?{qs}", {"X-Requested-With": "XMLHttpRequest"})
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"leaderboard did not return JSON (endpoint changed?): {e}")
    if not isinstance(rows, list):
        raise RuntimeError(f"leaderboard returned {type(rows).__name__}, expected a list")
    return [r for r in rows if (r.get("location_name") or "").strip().lower() == location.lower()]


LIFETIME_LABELS = [
    ("cumulative_score", "Cumulative Score"),
    ("bucks_killed", "Bucks/Bulls Killed"),
    ("critters_killed", "Critters Killed"),
    ("dangerous_trophies", "Dangerous Trophies Killed"),
    ("perfect_sites", "Perfect Sites"),
    ("double_perfect_bonus", "Double Perfect Bonus"),
    ("longest_perfect_streak", "Longest Perfect Streak"),
    ("marksman_awards", "Marksman Awards"),
    ("showdown_wins", "Showdown Wins"),
    ("showdown_losses", "Showdown Losses"),
]


def profile(player_id):
    """Lifetime stats, scraped from the server-rendered profile page."""
    text = re.sub(r"<[^>]+>", " ", get(f"{BASE}/profile/player/{player_id}"))
    text = re.sub(r"\s+", " ", text.replace("&nbsp;", " "))
    out = {}
    for key, label in LIFETIME_LABELS:
        m = re.search(re.escape(label) + r"\s+([\d,]+)", text)
        out[key] = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r"Rank Position:\s*([\d,]+)\s*/\s*([\d,]+)", text)
    if m:
        out["global_rank"] = int(m.group(1).replace(",", ""))
        out["global_player_count"] = int(m.group(2).replace(",", ""))
    m = re.search(r"Hunting Since:\s*(\d{1,2}/\d{1,2}/\d{2,4})", text)
    out["hunting_since"] = m.group(1) if m else None
    return out


def write_atomic(path, payload):
    """Write via a temp file in the same directory, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".standings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--location", default="Alloy", help="venue name to filter on (default: Alloy)")
    ap.add_argument("--out", type=Path, default=OUT, help=f"output path (default: {OUT})")
    ap.add_argument("--delay", type=float, default=0.4,
                    help="seconds between profile requests (default: 0.4)")
    ap.add_argument("--force", action="store_true",
                    help="write even if the roster shrank sharply or came back empty")
    args = ap.parse_args()

    rows = season_rows(args.location)
    log(f"{len(rows)} players at location {args.location!r}")

    # Guard: never let a bad upstream day wipe a good board. An empty result or
    # a sudden large drop is far more likely an API change than 15 people
    # unregistering overnight.
    if args.out.exists():
        try:
            prev = len(json.loads(args.out.read_text())["players"])
        except Exception:
            prev = 0
        if prev and len(rows) < prev * 0.5 and not args.force:
            log(f"ABORT: roster fell {prev} -> {len(rows)} (>50% drop). "
                f"Keeping existing data. Re-run with --force if this is real.")
            return 1
    if not rows and not args.force:
        log(f"ABORT: no players found at {args.location!r}. Keeping existing data.")
        return 1

    players, failed = [], 0
    for r in rows:
        pid = str(r["id"])
        try:
            lifetime = profile(pid)
        except Exception as e:                  # season data is still worth keeping
            log(f"  profile {pid} ({r['name']}) failed: {e}")
            lifetime, failed = {}, failed + 1
        players.append({
            "id": pid,
            "name": r["name"].strip(),
            "first_name": r["first_name"].strip(),
            "last_name": r["last_name"].strip(),
            "profile_url": r["player_link"],
            "location": r["location_name"],
            "city": r["location_city"],
            "state": r["location_state"],
            "season_score": r["overall_score"],
            "accuracy": r["accuracy"],
            "season_rank": r["overall_rank"],
            "wildcard_rank": r["wildcard_rank"],
            "lifetime": lifetime,
        })
        time.sleep(args.delay)

    players.sort(key=lambda p: -(p["season_score"] or 0))
    write_atomic(args.out, {
        "location": args.location,
        "city": players[0]["city"] if players else None,
        "state": players[0]["state"] if players else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": f"{BASE}/world/qualifiers",
        "players": players,
    })
    log(f"wrote {args.out} ({len(players)} players, {failed} profile failures)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
