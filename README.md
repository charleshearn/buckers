# The Alloy Buck Board

Static leaderboard for the Big Buck Hunter cabinet registered as **"Alloy" — New York, NY**
on the official Play Mechanix network.

The site is plain static files in `public/` — no build toolchain, no runtime, no
dependencies beyond the Python 3.8+ standard library.

## Refresh the standings

```sh
./scripts/update.sh         # fetch + rebuild, safe to run from cron
```

Or the two steps separately:

```sh
python3 scripts/fetch.py    # re-pull data/standings.json from bigbuckhunter.com
python3 scripts/build.py    # re-render public/ + artifact.html
```

## Hosting

The data cannot refresh from the browser — `bigbuckhunter.com` sends no CORS headers, so
JavaScript on your page is not allowed to read the response. Something outside the browser
has to fetch it. Three ways, covered in **[DEPLOY.md](DEPLOY.md)**:

- **GitHub Actions + Pages** — daily auto-refresh, no server. Workflow is already in
  `.github/workflows/refresh.yml`; push the repo and turn Pages on.
- **`artifact.html`** — the whole board in one file. Drop it anywhere; data frozen at build time.
- **Your own box** — `scripts/update.sh` from cron, systemd, or launchd.

## Files

| Path | What it is |
|---|---|
| `public/` | **The site.** Deploy this directory as-is |
| `public/index.html` | The page |
| `public/assets/styles.css`, `public/assets/board.js` | Fingerprinted assets |
| `public/standings.json` | The data, published alongside the page |
| `artifact.html` | Same page inlined into one file, for publishing as a Claude Artifact |
| `roster.json` | Allowlist — who appears on the board. Never overwritten by a fetch |
| `data/standings.json` | Fetched data, one record per hunter (everyone, shown or not) |
| `scripts/update.sh` | Fetch + build + optional deploy, with locking |
| `scripts/fetch.py` | Scraper — retries, atomic writes, refuses to clobber good data |
| `scripts/build.py` | Renderer — all layout and copy lives here |

## Who shows up

The network assigns a hunter to a venue by their *current* home location, not where they
registered — so visitors and old accounts drift onto the cabinet. `roster.json` is the
allowlist. Flip a `show` flag and rebuild:

```json
"1009901": { "name": "Harley Lewis", "show": false }
```

Hidden hunters stay in `data/standings.json` but drop out of the ranks, header totals, and
house records. New hunters arrive **hidden** — `build.py` prints them so you can flip the
ones you recognize.

## Where the data comes from

Two public, unauthenticated endpoints:

- `GET /world/qualifiers_search?search=Alloy&limit=500` — JSON. Matches on player *and*
  location name, so filtering to `location_name == "Alloy"` yields the cabinet's roster
  with current-season score, accuracy, and world rank.
- `GET /profile/player/<id>` — server-rendered HTML. Scraped for lifetime totals: cumulative
  score, bucks, perfect sites, longest streak, marksman awards, join date.

The season score resets each qualifier season; lifetime figures do not. That is why Matt Khalil
holds the all-time house record (3.7M) while sitting 4th on the current season board.
