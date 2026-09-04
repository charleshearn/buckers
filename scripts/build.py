#!/usr/bin/env python3
"""Render data/standings.json into the static site in public/ (and artifact.html)."""
import json, html
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "standings.json").read_text())
ROSTER_PATH = ROOT / "roster.json"

# Not everyone the network assigns to the Alloy cabinet is someone we know — a
# player's venue is their current home location, so visitors and old accounts
# drift in. roster.json is the allowlist: flip "show" to hide someone.

def load_roster(players):
    roster = json.loads(ROSTER_PATH.read_text())["hunters"] if ROSTER_PATH.exists() else {}
    added = []
    for pl in players:
        if pl["id"] not in roster:
            roster[pl["id"]] = {"name": pl["name"], "show": False}
            added.append(pl["name"])
        else:
            roster[pl["id"]]["name"] = pl["name"]      # keep names fresh
    ROSTER_PATH.write_text(json.dumps({
        "_comment": "Allowlist for the board. Set \"show\": false to hide a hunter — "
                    "they stay in data/standings.json but drop out of the ranks, "
                    "totals, and house records. New hunters arrive hidden — "
                    "flip them to true once you recognize them.",
        "hunters": dict(sorted(roster.items(), key=lambda kv: kv[1]["name"].lower())),
    }, indent=2) + "\n")
    return roster, added


ROSTER, NEW = load_roster(DATA["players"])
HIDDEN = [p for p in DATA["players"] if not ROSTER[p["id"]]["show"]]
P = [p for p in DATA["players"] if ROSTER[p["id"]]["show"]]
P.sort(key=lambda p: -(p["season_score"] or 0))
for i, p in enumerate(P, 1):          # ranks are over the visible board only
    p["house_rank"] = i


def n(v):
    return "—" if v is None else f"{v:,}"


def life(p, k):
    return p["lifetime"].get(k)


def join_year(p):
    """'2/4/06' -> 2006. Two-digit years; nothing on this network predates 2000."""
    d = life(p, "hunting_since")
    if not d:
        return None
    yy = int(d.split("/")[-1])
    return 2000 + yy if yy < 50 else 1900 + yy


def pills(p):
    out = []
    g = life(p, "global_rank")
    if p["house_rank"] == 1:
        out.append(("champ", "House Champ"))
    if g and g <= 500:
        out.append(("gold", f"Global #{g}"))
    cs = life(p, "cumulative_score") or 0
    if cs >= 1_000_000:
        out.append(("plain", f"{cs // 1_000_000}M Club"))
    mm = life(p, "marksman_awards") or 0
    if mm:
        out.append(("plain", f"Marksman ×{mm}"))
    yr = join_year(p)
    if yr and yr < 2015:
        out.append(("note", f"Legacy account · {yr}"))
    elif yr == 2026:
        out.append(("plain", "Rookie"))
    return out


# ---- house records -------------------------------------------------------
def best(key, fn=lambda p, k: p["lifetime"].get(k)):
    c = [p for p in P if fn(p, key) is not None]
    return max(c, key=lambda p: fn(p, key)) if c else None


def tie_note(key, base):
    """Records are often shared — say so instead of crowning one name."""
    top = max((p["lifetime"].get(key) for p in P if p["lifetime"].get(key) is not None), default=None)
    n = sum(1 for p in P if p["lifetime"].get(key) == top)
    return f"{base} — {n}-way tie" if n > 1 else base


acc_pool = [p for p in P if (life(p, "cumulative_score") or 0) > 100_000]
records = [
    ("Season high", P[0]["name"], f'{P[0]["season_score"]:,}', "points, current qualifier season"),
    ("All-time points", (b := best("cumulative_score"))["name"], f'{life(b,"cumulative_score"):,}', "lifetime cumulative score"),
    ("Most bucks", (b := best("bucks_killed"))["name"], f'{life(b,"bucks_killed"):,}', "bucks and bulls dropped"),
    ("Best accuracy", (b := max(acc_pool, key=lambda p: p["accuracy"]))["name"], f'{b["accuracy"]}%', "among high-volume hunters"),
    ("Longest streak", (b := best("longest_perfect_streak"))["name"], f'{life(b,"longest_perfect_streak")}', tie_note("longest_perfect_streak", "consecutive perfect sites")),
    ("Perfect sites", (b := best("perfect_sites"))["name"], f'{life(b,"perfect_sites"):,}', "no-miss sites, all time"),
]

hidden_note = (
    f"Showing {len(P)} of {len(DATA['players'])} hunters the network assigns to this cabinet; "
    f"{len(HIDDEN)} unrecognized {'account' if len(HIDDEN) == 1 else 'accounts'} hidden. "
) if HIDDEN else ""

champ = P[0]
runner = P[1]
gap = champ["season_score"] - runner["season_score"]
total_bucks = sum(life(p, "bucks_killed") or 0 for p in P)
total_life = sum(life(p, "cumulative_score") or 0 for p in P)
field = life(champ, "global_player_count")
max_season = max(p["season_score"] for p in P)
fetched = datetime.fromisoformat(DATA["fetched_at"]).strftime("%b %-d, %Y at %-I:%M %p UTC")

# ---- rows ----------------------------------------------------------------
rows = []
for p in P:
    ps = "".join(
        f'<span class="pill pill--{k}">{html.escape(t)}</span>' for k, t in pills(p)
    )
    acc = p["accuracy"] or 0
    rows.append(f'''          <tr data-rank="{p['house_rank']}">
            <td class="c-rank"><span class="rank">{p['house_rank']}</span></td>
            <td class="c-name">
              <a class="pname" href="{html.escape(p['profile_url'])}" target="_blank" rel="noopener">{html.escape(p['name'])}</a>
              <span class="meta">Hunting since {html.escape(life(p,'hunting_since') or '—')}</span>
              {f'<span class="pills">{ps}</span>' if ps else ''}
            </td>
            <td class="c-num">
              <span class="num">{n(p['season_score'])}</span>
              <span class="bar"><i style="width:{max(2.5, p['season_score'] / max_season * 100):.1f}%"></i></span>
            </td>
            <td class="c-num">
              <span class="num">{acc}%</span>
              <span class="bar bar--acc"><i style="width:{min(100, acc / 50 * 100):.1f}%"></i></span>
            </td>
            <td class="c-num"><span class="num">{n(life(p,'cumulative_score'))}</span></td>
            <td class="c-num"><span class="num">{n(life(p,'bucks_killed'))}</span></td>
            <td class="c-num"><span class="num">{n(life(p,'perfect_sites'))}</span></td>
            <td class="c-num"><span class="num">{n(life(p,'global_rank'))}</span></td>
          </tr>''')

recs = "".join(f'''        <div class="rec">
          <span class="rec__label">{html.escape(l)}</span>
          <span class="rec__value">{html.escape(v)}</span>
          <span class="rec__who">{html.escape(w)}</span>
          <span class="rec__note">{html.escape(note)}</span>
        </div>''' for l, w, v, note in records)

HTML = f'''<title>The Alloy Buck Board</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Ultra&family=Archivo:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root {{
  --ground:#EFEDE1; --surface:#F7F5EC; --sunk:#E4E2D3;
  --ink:#15190E; --ink-2:#3E452F; --muted:#6B7355;
  --line:#D3D2BF; --line-strong:#B9B9A2;
  --blaze:#BF4508; --blaze-soft:#E9762F; --brass:#8A6415; --brass-bg:#F0E4C4;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#14180F; --surface:#1D2215; --sunk:#0E1109;
    --ink:#EFEBDF; --ink-2:#CFCDB8; --muted:#98A07F;
    --line:#2E3524; --line-strong:#454E36;
    --blaze:#FF6B1A; --blaze-soft:#FF8B4A; --brass:#D9A441; --brass-bg:#332A12;
  }}
}}
:root[data-theme="dark"] {{
  --ground:#14180F; --surface:#1D2215; --sunk:#0E1109;
  --ink:#EFEBDF; --ink-2:#CFCDB8; --muted:#98A07F;
  --line:#2E3524; --line-strong:#454E36;
  --blaze:#FF6B1A; --blaze-soft:#FF8B4A; --brass:#D9A441; --brass-bg:#332A12;
}}

* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"Archivo","Helvetica Neue",Arial,sans-serif;
  font-size:16px; line-height:1.55; -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:1120px; margin:0 auto; padding:0 24px 88px; }}
a {{ color:inherit; }}
:focus-visible {{ outline:2px solid var(--blaze); outline-offset:3px; }}

/* ---- marquee ---- */
.marquee {{
  border-bottom:3px solid var(--ink); padding:38px 0 26px; margin-bottom:34px;
  display:flex; flex-wrap:wrap; align-items:flex-end; gap:20px 32px;
}}
.marquee__id {{ flex:1 1 380px; }}
.eyebrow {{
  font-family:"IBM Plex Mono",monospace; font-size:11px; font-weight:600;
  letter-spacing:.19em; text-transform:uppercase; color:var(--blaze); margin:0 0 12px;
}}
h1 {{
  font-family:"Ultra",Georgia,serif; font-weight:400; margin:0;
  font-size:clamp(2.5rem,7.5vw,4.6rem); line-height:.92; letter-spacing:-.015em;
  text-wrap:balance;
}}
h1 em {{ font-style:normal; color:var(--blaze); }}
.marquee__sub {{ margin:14px 0 0; color:var(--ink-2); max-width:56ch; }}
.marquee__stats {{ display:flex; gap:28px; flex-wrap:wrap; }}
.mstat {{ display:flex; flex-direction:column; }}
.mstat b {{
  font-family:"IBM Plex Mono",monospace; font-size:1.5rem; font-weight:600;
  font-variant-numeric:tabular-nums; line-height:1.1;
}}
.mstat span {{
  font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.15em;
  text-transform:uppercase; color:var(--muted); margin-top:4px;
}}

/* ---- champion ---- */
.champ {{
  display:grid; grid-template-columns:minmax(0,1.15fr) minmax(0,1fr); gap:0;
  border:2px solid var(--ink); background:var(--surface); margin-bottom:52px;
}}
.champ__main {{ padding:30px 32px; border-right:2px solid var(--ink); }}
.champ__crown {{
  font-family:"IBM Plex Mono",monospace; font-size:10px; font-weight:600;
  letter-spacing:.2em; text-transform:uppercase; color:var(--brass);
  display:inline-block; padding:4px 9px; background:var(--brass-bg); margin-bottom:16px;
}}
.champ__name {{
  font-family:"Ultra",Georgia,serif; font-size:clamp(1.9rem,4.4vw,2.9rem);
  line-height:1; margin:0 0 6px;
}}
.champ__line {{ color:var(--ink-2); margin:0; font-size:.95rem; }}
.champ__grid {{ display:grid; grid-template-columns:repeat(2,1fr); }}
.cg {{ padding:22px 24px; border-bottom:1px solid var(--line); }}
.cg:nth-child(odd) {{ border-right:1px solid var(--line); }}
.cg:nth-last-child(-n+2) {{ border-bottom:0; }}
.cg b {{
  display:block; font-family:"IBM Plex Mono",monospace; font-size:1.35rem;
  font-weight:600; font-variant-numeric:tabular-nums;
}}
.cg span {{
  font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.13em;
  text-transform:uppercase; color:var(--muted);
}}

/* ---- sections ---- */
.sec-head {{
  display:flex; align-items:baseline; justify-content:space-between;
  gap:16px; flex-wrap:wrap; border-bottom:2px solid var(--ink); padding-bottom:10px; margin-bottom:0;
}}
h2 {{
  font-family:"Ultra",Georgia,serif; font-weight:400; margin:0;
  font-size:clamp(1.35rem,3vw,1.85rem); line-height:1;
}}
.sec-note {{
  font-family:"IBM Plex Mono",monospace; font-size:11px; letter-spacing:.06em; color:var(--muted);
}}

/* ---- table ---- */
.tablewrap {{ overflow-x:auto; margin-bottom:56px; }}
table {{ width:100%; border-collapse:collapse; min-width:820px; }}
thead th {{
  font-family:"IBM Plex Mono",monospace; font-size:10px; font-weight:600;
  letter-spacing:.13em; text-transform:uppercase; color:var(--muted);
  text-align:right; padding:14px 12px; border-bottom:1px solid var(--line-strong);
  white-space:nowrap; cursor:pointer; user-select:none;
}}
thead th:first-child, thead th:nth-child(2) {{ text-align:left; }}
thead th:hover {{ color:var(--blaze); }}
thead th[aria-sort]:not([aria-sort="none"]) {{ color:var(--blaze); }}
thead th[aria-sort="descending"]::after {{ content:" ▾"; }}
thead th[aria-sort="ascending"]::after {{ content:" ▴"; }}
tbody tr {{ border-bottom:1px solid var(--line); }}
tbody tr:hover {{ background:var(--sunk); }}
tbody td {{ padding:15px 12px; vertical-align:top; }}
.c-rank {{ width:52px; }}
.rank {{
  font-family:"IBM Plex Mono",monospace; font-size:1.05rem; font-weight:600;
  font-variant-numeric:tabular-nums; color:var(--muted);
}}
tbody tr:first-child .rank {{ color:var(--blaze); }}
.c-name {{ min-width:230px; }}
.pname {{ font-weight:600; text-decoration:none; border-bottom:1px solid var(--line-strong); }}
.pname:hover {{ color:var(--blaze); border-color:var(--blaze); }}
.meta {{
  display:block; font-family:"IBM Plex Mono",monospace; font-size:10.5px;
  color:var(--muted); margin-top:3px;
}}
.pills {{ display:flex; flex-wrap:wrap; gap:5px; margin-top:7px; }}
.pill {{
  font-family:"IBM Plex Mono",monospace; font-size:9.5px; font-weight:600;
  letter-spacing:.09em; text-transform:uppercase; padding:3px 7px;
  border:1px solid var(--line-strong); color:var(--muted); white-space:nowrap;
}}
.pill--champ {{ background:var(--blaze); border-color:var(--blaze); color:var(--surface); }}
.pill--gold {{ background:var(--brass-bg); border-color:var(--brass); color:var(--brass); }}
.pill--note {{ border-style:dashed; }}
.c-num {{ text-align:right; white-space:nowrap; }}
.num {{
  font-family:"IBM Plex Mono",monospace; font-size:.94rem;
  font-variant-numeric:tabular-nums; display:block;
}}
.bar {{
  display:block; height:4px; background:var(--sunk); margin-top:6px;
  min-width:74px; border:1px solid var(--line);
}}
.bar i {{ display:block; height:100%; background:var(--blaze); }}
.bar--acc i {{ background:var(--blaze-soft); }}

/* ---- records ---- */
.records {{
  display:grid; grid-template-columns:repeat(3,1fr);
  border-top:1px solid var(--line-strong); border-left:1px solid var(--line-strong);
  margin-top:22px;
}}
.rec {{
  padding:20px 22px 22px; border-right:1px solid var(--line-strong);
  border-bottom:1px solid var(--line-strong); display:flex; flex-direction:column;
}}
.rec__label {{
  font-family:"IBM Plex Mono",monospace; font-size:10px; letter-spacing:.15em;
  text-transform:uppercase; color:var(--blaze); margin-bottom:10px;
}}
.rec__value {{
  font-family:"IBM Plex Mono",monospace; font-size:1.7rem; font-weight:600;
  font-variant-numeric:tabular-nums; line-height:1;
}}
.rec__who {{ font-weight:600; margin-top:7px; }}
.rec__note {{ font-size:.82rem; color:var(--muted); margin-top:2px; }}

footer {{
  margin-top:56px; padding-top:22px; border-top:2px solid var(--ink);
  font-family:"IBM Plex Mono",monospace; font-size:11.5px; color:var(--muted);
  display:flex; flex-wrap:wrap; gap:8px 24px; justify-content:space-between;
}}
footer a {{ color:var(--blaze); }}
.footnote {{ flex:1 1 100%; max-width:70ch; line-height:1.6; margin-bottom:6px; }}
.footnote em {{ color:var(--ink-2); font-style:italic; }}

@media (max-width:900px) {{ .records {{ grid-template-columns:repeat(2,1fr); }} }}
@media (max-width:760px) {{
  .records {{ grid-template-columns:1fr; }}
  .champ {{ grid-template-columns:1fr; }}
  .champ__main {{ border-right:0; border-bottom:2px solid var(--ink); }}
}}
</style>

<div class="wrap">
  <header class="marquee">
    <div class="marquee__id">
      <p class="eyebrow">Big Buck Hunter · Alloy · New York, NY</p>
      <h1>The Alloy <em>Buck Board</em></h1>
      <p class="marquee__sub">Standings for the crew on the Alloy office cabinet, pulled straight from the official Big Buck Hunter world leaderboard.</p>
    </div>
    <div class="marquee__stats">
      <div class="mstat"><b>{len(P)}</b><span>Hunters</span></div>
      <div class="mstat"><b>{total_bucks:,}</b><span>Bucks taken</span></div>
      <div class="mstat"><b>{total_life/1_000_000:.1f}M</b><span>Lifetime points</span></div>
    </div>
  </header>

  <section class="champ">
    <div class="champ__main">
      <span class="champ__crown">Reigning house champion</span>
      <p class="champ__name">{html.escape(champ['name'])}</p>
      <p class="champ__line">Leads the office by <strong>{gap:,}</strong> points over {html.escape(runner['name'])}, and sits <strong>#{life(champ,'global_rank'):,}</strong> of {field:,} hunters worldwide — the top {life(champ,'global_rank')/field*100:.1f}% of the planet.</p>
    </div>
    <div class="champ__grid">
      <div class="cg"><b>{champ['season_score']:,}</b><span>Season points</span></div>
      <div class="cg"><b>{champ['accuracy']}%</b><span>Accuracy</span></div>
      <div class="cg"><b>{life(champ,'bucks_killed'):,}</b><span>Bucks taken</span></div>
      <div class="cg"><b>{life(champ,'perfect_sites'):,}</b><span>Perfect sites</span></div>
    </div>
  </section>

  <div class="sec-head">
    <h2>Standings</h2>
    <span class="sec-note">Click any column to re-sort</span>
  </div>
  <div class="tablewrap">
    <table id="board">
      <thead>
        <tr>
          <th data-key="rank" data-dir="asc" aria-sort="ascending">#</th>
          <th data-key="name" data-dir="asc">Hunter</th>
          <th data-key="season" data-dir="desc">Season points</th>
          <th data-key="acc" data-dir="desc">Accuracy</th>
          <th data-key="life" data-dir="desc">Lifetime points</th>
          <th data-key="bucks" data-dir="desc">Bucks</th>
          <th data-key="perfect" data-dir="desc">Perfect sites</th>
          <th data-key="global" data-dir="asc">World rank</th>
        </tr>
      </thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>
  </div>

  <div class="sec-head">
    <h2>House records</h2>
    <span class="sec-note">All time, all hunters</span>
  </div>
  <div class="records">
{recs}
  </div>

  <footer>
    <span class="footnote">{hidden_note}A player&rsquo;s venue on the Big Buck Hunter network is their <em>current</em> home location, not where they first registered &mdash; so accounts older than Alloy itself (founded 2015) can drift onto this cabinet once they play here.</span>
    <span>Data: bigbuckhunter.com world qualifier leaderboard + public player profiles</span>
    <span>Fetched {fetched} · <a href="https://www.bigbuckhunter.com/world/qualifiers?search=Alloy" target="_blank" rel="noopener">Source</a></span>
  </footer>
</div>

<script>
(function () {{
  var table = document.getElementById('board');
  var tbody = table.tBodies[0];
  var rows = Array.prototype.slice.call(tbody.rows);
  function val(row, key) {{
    var i = {{rank:0, name:1, season:2, acc:3, life:4, bucks:5, perfect:6, global:7}}[key];
    var cell = row.cells[i];
    if (key === 'name') return cell.querySelector('.pname').textContent.toLowerCase();
    var raw = (cell.querySelector('.num, .rank') || cell).textContent.replace(/[^0-9.]/g, '');
    return raw === '' ? -1 : parseFloat(raw);
  }}
  table.tHead.addEventListener('click', function (e) {{
    var th = e.target.closest('th');
    if (!th) return;
    var key = th.dataset.key;
    var dir = th.getAttribute('aria-sort') === 'descending' ? 'asc' : 'desc';
    if (!th.hasAttribute('aria-sort')) dir = th.dataset.dir;
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (c) {{ c.setAttribute('aria-sort', 'none'); }});
    th.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');
    var sorted = rows.slice().sort(function (a, b) {{
      var x = val(a, key), y = val(b, key);
      var c = x < y ? -1 : x > y ? 1 : 0;
      return dir === 'asc' ? c : -c;
    }});
    sorted.forEach(function (r) {{ tbody.appendChild(r); }});
  }});
}})();
</script>
'''

# --- output -------------------------------------------------------------
# One template, three targets. artifact.html keeps everything inlined (the
# Claude Artifact host supplies the doctype/head/body and blocks external
# assets); public/ is the real static site, with CSS and JS as cacheable files.
import hashlib, shutil

css = HTML[HTML.index("<style>") + len("<style>"):HTML.index("</style>")].strip()
js = HTML[HTML.index("<script>") + len("<script>"):HTML.index("</script>")].strip()
head = HTML[:HTML.index("<style>")].strip()
body = HTML[HTML.index("</style>") + len("</style>"):HTML.index("<script>")].strip()

(ROOT / "artifact.html").write_text(HTML)

PUBLIC = ROOT / "public"
ASSETS = PUBLIC / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
(ASSETS / "styles.css").write_text(css + "\n")
(ASSETS / "board.js").write_text(js + "\n")

# Content hashes so a daily rebuild busts caches only when something changed.
def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:8]


doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
{head}
<link rel="stylesheet" href="assets/styles.css?v={digest(css)}">
</head>
<body>
{body}
<script src="assets/board.js?v={digest(js)}"></script>
</body>
</html>
"""
(PUBLIC / "index.html").write_text(doc)

# Public host, but not a search result: the board names colleagues, and nobody
# should land on it by googling one of them.
(PUBLIC / "robots.txt").write_text("User-agent: *\nDisallow: /\n")

# Ship the raw data alongside the page so the site is self-documenting.
shutil.copyfile(ROOT / "data" / "standings.json", PUBLIC / "standings.json")

print(f"wrote {PUBLIC}/ (index.html, assets/, standings.json, robots.txt)")
print(f"wrote {ROOT / 'artifact.html'}")
print(f"\nroster: {len(P)} shown, {len(HIDDEN)} hidden -> {ROSTER_PATH.name}")
for pl in HIDDEN:
    print(f"   hidden: {pl['name']}")
if NEW:
    print(f"   NEW (hidden by default, set show:true to add): {', '.join(NEW)}")
