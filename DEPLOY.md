# Running the Buck Board

Everything here is Python 3.8+ **standard library only** — no pip install, no virtualenv,
no API key, no login.

## Why the data can't refresh itself in the browser

`bigbuckhunter.com` sends **no `Access-Control-Allow-Origin` header** on either endpoint.
Verified:

```console
$ curl -sS -D - -o /dev/null -H 'Origin: https://example.com' \
    'https://www.bigbuckhunter.com/world/qualifiers_search?search=Alloy&limit=5&offset=0'
HTTP/2 200
content-type: text/html; charset=UTF-8
```

No CORS header in the response. A browser will happily send that request from your page and
then refuse to let JavaScript read the reply — that's the same-origin policy, and nothing you
do in the page can override it. The profile pages are plain HTML with the same problem.

So **something outside the browser has to fetch the data.** Three ways to arrange that, in
order of how little you have to maintain:

| Option | Refreshes | You maintain |
|---|---|---|
| **A. GitHub Actions + Pages** | Daily, automatically | Nothing — no server |
| **B. One HTML file, data frozen** | Only when you rebuild | Nothing, but it goes stale |
| **C. Your own box on cron** | Daily, automatically | A machine |

---

## Option A — GitHub Actions + Pages (no machine at all)

`.github/workflows/refresh.yml` is already in this repo. It runs `fetch.py` + `build.py` on a
daily schedule, commits the refreshed data, and publishes `public/` to GitHub Pages.

```sh
git init && git add -A && git commit -m "Buck Board"
gh repo create bbh-standings --private --source=. --push
```

Then in the repo: **Settings → Pages → Source: GitHub Actions**. That's it. The first run
publishes; after that it refreshes itself every morning. Run it on demand any time from the
Actions tab (`workflow_dispatch`).

The schedule is `20 11 * * *` — 11:20 UTC. GitHub cron is UTC-only and doesn't shift with DST,
so that's 7:20am ET in summer, 6:20am in winter. Edit the cron line to taste. Scheduled runs on
GitHub can lag the requested minute by several minutes under load; that's normal and harmless
for a daily job.

If a fetch fails, the workflow still builds and republishes the **previous** data and adds a
warning annotation to the run, rather than shipping a blank board.

**Private repos:** GitHub Pages requires a paid plan to serve from a private repo. If that's a
problem, either make the repo public — the data is already public — or use Option C. Note the
page itself is world-readable once Pages is on, so if the board should stay internal, host it
behind your own auth with Option C.

---

## Option B — one file, no refresh

`artifact.html` is the whole board inlined into a single file: styles, script, and data. Drop
it on any web host, S3 bucket, or file share and it works with zero setup.

The tradeoff is in the name — the data is baked in at build time. It shows the numbers from
whenever you last ran `./scripts/update.sh`, and the footer says so. Fine for a one-off share;
it will not update on its own.

---

## Option C — your own machine on a timer

---

### 1. Install

```sh
git clone <your-remote> /opt/bbh-standings      # or just scp the directory over
cd /opt/bbh-standings
./scripts/update.sh                             # fetch + build once to verify
```

You should see `wrote .../public/` and a roster summary. Open `public/index.html` to confirm.

`update.sh` is the only entry point you need to schedule. It:

1. takes a lock so overlapping runs can't collide,
2. runs `scripts/fetch.py` → `data/standings.json`,
3. runs `scripts/build.py` → `public/`,
4. runs `$DEPLOY_CMD` if you set one,
5. **exits non-zero and leaves the previous site intact if the fetch fails.**

---

### 2. Schedule it daily

Pick whichever matches the box. Run it **once a day** — the upstream leaderboard only
recomputes every few hours, so anything more frequent is just load on someone else's server.

### systemd (Linux — preferred)

`/etc/systemd/system/bbh-standings.service`:

```ini
[Unit]
Description=Refresh the Alloy Buck Board
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/opt/bbh-standings
Environment=DEPLOY_CMD=rsync -a --delete public/ /var/www/buckboard/
ExecStart=/opt/bbh-standings/scripts/update.sh
```

`/etc/systemd/system/bbh-standings.timer`:

```ini
[Unit]
Description=Daily Buck Board refresh

[Timer]
OnCalendar=*-*-* 07:20:00
RandomizedDelaySec=20m
Persistent=true

[Install]
WantedBy=timers.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now bbh-standings.timer
systemctl list-timers bbh-standings.timer     # confirm next run
journalctl -u bbh-standings.service -n 50     # read the last run's log
```

`Persistent=true` catches up after downtime; `RandomizedDelaySec` keeps you from hammering
upstream at the same second every day.

### cron (anything POSIX)

```cron
20 7 * * * /opt/bbh-standings/scripts/update.sh >> /var/log/bbh-standings.log 2>&1
```

cron runs with a nearly empty `PATH`. If `python3` isn't found, pin it:

```cron
20 7 * * * PYTHON=/usr/bin/python3 /opt/bbh-standings/scripts/update.sh >> /var/log/bbh-standings.log 2>&1
```

### launchd (macOS)

`~/Library/LaunchAgents/com.alloy.buckboard.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.alloy.buckboard</string>
  <key>ProgramArguments</key>
  <array><string>/opt/bbh-standings/scripts/update.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>20</integer></dict>
  <key>StandardOutPath</key><string>/tmp/buckboard.log</string>
  <key>StandardErrorPath</key><string>/tmp/buckboard.err</string>
</dict>
</plist>
```

```sh
launchctl load ~/Library/LaunchAgents/com.alloy.buckboard.plist
```

---

### 3. Serve `public/`

`public/` is plain static files — no server-side anything. Point any of these at it:

| Target | Set `DEPLOY_CMD` to |
|---|---|
| Same box, nginx/Caddy | *(nothing — set the webroot to `/opt/bbh-standings/public`)* |
| Another web server | `rsync -a --delete public/ web:/var/www/buckboard/` |
| S3 + CloudFront | `aws s3 sync public/ s3://your-bucket/ --delete` |
| GitHub Pages | `git add -A public && git commit -m "daily refresh" && git push` (Pages source: `/public`) |
| Netlify / Cloudflare Pages | `netlify deploy --prod --dir=public` |

Minimal nginx:

```nginx
server {
    listen 80;
    server_name buckboard.internal;
    root /opt/bbh-standings/public;
    index index.html;
}
```

Assets are fingerprinted (`styles.css?v=a1b2c3d4`), so you can cache them hard and still get
instant updates when they change.

---

---

## The data source, if you ever need to rewrite this

Two public endpoints on `https://www.bigbuckhunter.com`. **Both reject the default
`urllib`/`curl` user agent with a 403** — send a browser UA.

### Season leaderboard (JSON)

```sh
curl -s -G 'https://www.bigbuckhunter.com/world/qualifiers_search' \
  --data-urlencode 'order_by=WildcardRank' \
  --data-urlencode 'order_direction=asc' \
  --data-urlencode 'search=Alloy' \
  --data-urlencode 'limit=500' \
  --data-urlencode 'offset=0' \
  -H 'User-Agent: Mozilla/5.0' -H 'X-Requested-With: XMLHttpRequest'
```

Returns a JSON array. Useful fields per row:

| Field | Meaning |
|---|---|
| `id` | player id, used for the profile URL |
| `name`, `first_name`, `last_name` | as entered on the cabinet |
| `location_name`, `location_city`, `location_state` | the player's **current** home venue |
| `overall_score` | current qualifier-season cumulative score |
| `accuracy` | season accuracy percentage |
| `overall_rank`, `wildcard_rank` | season ranks across the whole network |
| `player_link` | absolute profile URL |

Two gotchas:

- **`search` matches player names *and* venue names.** Searching `Alloy` also returns a player
  named "Malloy," so filter on `location_name == "Alloy"` — that's exactly what `fetch.py` does.
- **`limit` is capped at 100 server-side** regardless of what you ask for. Fine for one venue;
  page with `offset` if you ever enumerate the whole network.

### Player profile (HTML)

```sh
curl -s 'https://www.bigbuckhunter.com/profile/player/1002404' -H 'User-Agent: Mozilla/5.0'
```

Server-rendered, so lifetime figures are scrapeable by label: `Cumulative Score`,
`Bucks/Bulls Killed`, `Critters Killed`, `Dangerous Trophies Killed`, `Perfect Sites`,
`Double Perfect Bonus`, `Longest Perfect Streak`, `Marksman Awards`, `Showdown Wins`,
`Showdown Losses`, plus `Rank Position: N / M` and `Hunting Since: M/D/YY`.

This is scraping an HTML page nobody promised to keep stable. If the labels move, `fetch.py`
records `null` for those fields rather than crashing, and the season data still lands.

### Be a good citizen

`fetch.py` sleeps 0.4s between profile requests (`--delay` to change) — roughly 16 requests
per daily run for a 15-player venue. Keep it there. There's no published rate limit, which is
a reason for restraint, not license.

---

## Curating who appears

`roster.json` is the allowlist, and **it is not overwritten by a fetch** — your choices survive
every refresh.

```json
"1009901": { "name": "Harley Lewis", "show": false }
```

New hunters are added **hidden**, and `build.py` prints them at the end of every run:

```
NEW (hidden by default, set show:true to add): Jane Doe
```

So a stranger wandering onto the cabinet never silently appears on the board — but you'll see
them in the daily log and can flip them on. Hidden players stay in `data/standings.json` and
drop out of ranks, header totals, and house records.

---

## When it breaks

| Symptom | What happened | What to do |
|---|---|---|
| `ABORT: no players found` | Upstream returned an empty list | Site untouched. Usually transient; check the venue still exists. |
| `ABORT: roster fell 15 -> 4 (>50% drop)` | Suspicious shrink | Site untouched. If the drop is real, `./scripts/update.sh --force`. |
| `GET ... failed after 4 attempts` | Network or upstream down | Site untouched. The next day's run recovers on its own. |
| `profile NNNN failed` | One profile page 500'd | Non-fatal — that hunter keeps season data, lifetime fields go `null`. |
| Page renders unstyled | `assets/` didn't deploy | Check your `DEPLOY_CMD` copies the whole `public/` tree, not just `index.html`. |

Exit codes: `0` wrote new data, `1` failed and left the previous data alone. Any monitoring
that watches exit status works — e.g. append a healthcheck ping to `DEPLOY_CMD`:

```sh
DEPLOY_CMD='rsync -a --delete public/ web:/var/www/buckboard/ && curl -fsS https://hc-ping.com/<uuid>'
```

Because a failed fetch never overwrites `data/standings.json`, the worst case for a multi-day
outage is a stale board with an honest "Fetched ..." timestamp in the footer — never a blank
or half-broken page.
