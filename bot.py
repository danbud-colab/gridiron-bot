#!/usr/bin/env python3
"""
Gridiron Nation auto-poster.

- Reads NFL / college football schedules and scores from ESPN's public scoreboard JSON.
- ~6 hours before kickoff: builds a "Game Day" image + title + text + hashtags and posts it to your Page.
- ~10-30 minutes after the final whistle: builds a "Final" image with the score and posts it.
- Remembers what it already posted in state.json, so nothing is posted twice.

Run it every ~10 minutes (GitHub Actions or Task Scheduler / cron). See README.md.

Usage:
    python bot.py --demo        # make sample images in ./out, no internet or Facebook needed
    python bot.py --dry-run     # fetch real games, make images in ./out, DO NOT post
    python bot.py               # real run (posts to Facebook)
"""
import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent

try:
    from dotenv import load_dotenv

    load_dotenv(BASE / ".env")
except ImportError:
    pass

# ----------------------------------------------------------------------------- config
PAGE_ID = os.getenv("FB_PAGE_ID", "")
PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN", "")
GRAPH_VERSION = os.getenv("FB_GRAPH_VERSION", "v26.0")
PAGE_NAME = os.getenv("PAGE_NAME", "GRIDIRON NATION USA")

LEAGUES = [x.strip() for x in os.getenv("LEAGUES", "nfl,college-football").split(",") if x.strip()]
PREVIEW_HOURS = float(os.getenv("PREVIEW_HOURS_BEFORE", "6"))
POLL_HOURS = float(os.getenv("POLL_HOURS_BEFORE", "3"))
# Spacing: after each post the bot waits this long before the next one (inside the same run).
POST_GAP_SECONDS = int(os.getenv("POST_GAP_SECONDS", "180"))      # preview / poll posts: 3 min apart
RESULT_GAP_SECONDS = int(os.getenv("RESULT_GAP_SECONDS", "45"))   # final-score posts: shorter gap
MAX_POSTS_PER_RUN = int(os.getenv("MAX_POSTS_PER_RUN", "12"))     # safety cap per run (0 = no cap)
MAX_RUN_MINUTES = int(os.getenv("MAX_RUN_MINUTES", "30"))         # stop starting new posts after this
RESULT_DELAY_MIN = int(os.getenv("RESULT_DELAY_MINUTES", "10"))
ONLY_TOP25_COLLEGE = os.getenv("ONLY_TOP25_COLLEGE", "true").lower() == "true"
DISPLAY_TZ = ZoneInfo(os.getenv("DISPLAY_TZ", "America/New_York"))

STATE_FILE = BASE / "state.json"
OUT_DIR = BASE / "out"

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/{league}/scoreboard"
LEAGUE_LABEL = {"nfl": "NFL", "college-football": "NCAAF"}
LEAGUE_TAG = {"nfl": "#NFL", "college-football": "#CollegeFootball"}


# ----------------------------------------------------------------------------- data
def fetch_league_day(league, day):
    params = {"dates": day.strftime("%Y%m%d"), "limit": 100}
    if league == "college-football":
        params["groups"] = "80"  # FBS
    r = requests.get(ESPN.format(league=league), params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("events", [])


def parse_event(ev, league):
    comp = ev["competitions"][0]
    side = {}
    for c in comp["competitors"]:
        t = c["team"]
        score = c.get("score")
        recs = c.get("records") or []
        side[c["homeAway"]] = {
            "name": t.get("displayName", "TBD"),
            "short": t.get("shortDisplayName") or t.get("name") or t.get("displayName", "TBD"),
            "abbr": t.get("abbreviation", "TBD"),
            "color": "#" + (t.get("color") or "1f2a44"),
            "score": int(score) if score not in (None, "") and str(score).isdigit() else None,
            "record": recs[0].get("summary", "") if recs else "",
            "rank": (c.get("curatedRank") or {}).get("current", 99),
        }
    st = ev["status"]["type"]
    venue = (comp.get("venue") or {}).get("fullName", "")
    tv = ", ".join(sorted({n for b in comp.get("broadcasts", []) for n in b.get("names", [])}))
    return {
        "id": f"{league}-{ev['id']}",
        "league": league,
        "start": datetime.fromisoformat(ev["date"].replace("Z", "+00:00")),
        "state": st.get("state"),
        "completed": bool(st.get("completed")),
        "home": side["home"],
        "away": side["away"],
        "venue": venue,
        "tv": tv,
    }


def collect_games(now):
    games = {}
    days = [now - timedelta(days=1), now, now + timedelta(days=1)]
    for league in LEAGUES:
        for day in days:
            try:
                events = fetch_league_day(league, day)
            except Exception as e:  # network / API hiccup: skip, try again next run
                print(f"[warn] {league} {day:%Y-%m-%d}: {e}")
                continue
            for ev in events:
                try:
                    g = parse_event(ev, league)
                except Exception as e:
                    print(f"[warn] could not parse event {ev.get('id')}: {e}")
                    continue
                if league == "college-football" and ONLY_TOP25_COLLEGE:
                    if min(g["home"]["rank"], g["away"]["rank"]) > 25:
                        continue
                games[g["id"]] = g
    return list(games.values())


# ----------------------------------------------------------------------------- image
W = H = 1080
FONT_CANDIDATES = [
    os.getenv("FONT_PATH", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def font(size):
    for p in FONT_CANDIDATES:
        if p and Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def usable(c):
    """Darken very light team colours so white text stays readable."""
    lum = (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255
    if lum > 0.5:
        k = 0.5 / lum
        return tuple(int(x * k) for x in c)
    return c


def when_text(dt):
    dt = dt.astimezone(DISPLAY_TZ)
    return f"{dt:%a %b} {dt.day}", f"{dt.hour % 12 or 12}:{dt:%M} {dt:%p} {dt.tzname()}"


def make_card(g, kind, path):
    away, home = g["away"], g["home"]
    ca, ch = usable(hex_rgb(away["color"])), usable(hex_rgb(home["color"]))

    # horizontal blend between the two team colours
    strip = Image.new("RGB", (W, 1))
    for x in range(W):
        t = min(max((x - 380) / 320, 0), 1)
        t = t * t * (3 - 2 * t)
        strip.putpixel((x, 0), tuple(int(ca[i] * (1 - t) + ch[i] * t) for i in range(3)))
    img = strip.resize((W, H))

    # darken towards the bottom
    mask = Image.linear_gradient("L").resize((W, H)).point(lambda p: int(p * 0.6))
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, mask)
    d = ImageDraw.Draw(img)

    def text(xy, s, f, fill=(255, 255, 255)):
        d.text((xy[0] + 3, xy[1] + 3), s, font=f, fill=(0, 0, 0), anchor="mm")
        d.text(xy, s, font=f, fill=fill, anchor="mm")

    def fit(s, size, maxw):
        while size > 20:
            f = font(size)
            if d.textlength(s, font=f) <= maxw:
                return f
            size -= 2
        return font(20)

    day, clock = when_text(g["start"])
    label = {"preview": "GAME DAY", "poll": "WHO WINS?"}.get(kind, "FINAL")
    text((W // 2, 105), label, font(82))
    text((W // 2, 185), f"{LEAGUE_LABEL.get(g['league'], '')}  |  {day}", font(36), (225, 225, 225))

    xs = {"away": 270, "home": 810}
    if kind == "preview":
        abbr_y, name_y, rec_y = 410, 570, 625
    elif kind == "poll":
        abbr_y, name_y, rec_y = 340, 450, 505
    else:
        abbr_y, name_y, rec_y = 375, 485, 540

    for key, team in (("away", away), ("home", home)):
        cx = xs[key]
        if team["rank"] <= 25:
            text((cx, abbr_y - 115), f"#{team['rank']}", font(42), (255, 215, 90))
        text((cx, abbr_y), team["abbr"], fit(team["abbr"], 190, 440))
        text((cx, name_y), team["short"], fit(team["short"], 44, 440))
        if team["record"]:
            text((cx, rec_y), f"({team['record']})", font(34), (215, 215, 215))

    if kind == "preview":
        text((W // 2, abbr_y), "AT", font(60), (230, 230, 230))
        text((W // 2, 810), clock, font(78))
        sub = " | ".join(x for x in (g["venue"], g["tv"]) if x)
        if sub:
            text((W // 2, 895), sub, fit(sub, 34, 960), (225, 225, 225))
    elif kind == "poll":
        text((W // 2, abbr_y), "VS", font(56), (230, 230, 230))
        opts = [
            ("LIKE", away["abbr"], "WINS", (110, 160, 255)),
            ("LOVE", "OT", "OVERTIME", (255, 120, 150)),
            ("WOW", home["abbr"], "WINS", (255, 215, 90)),
        ]
        bw, gap, top, bh = 300, 30, 620, 250
        for i, (react, big, small, col) in enumerate(opts):
            x0 = 60 + i * (bw + gap)
            d.rounded_rectangle((x0, top, x0 + bw, top + bh), radius=28, fill=(12, 14, 26), outline=(255, 255, 255), width=4)
            cx = x0 + bw // 2
            text((cx, top + 55), f"{react} =", font(40), col)
            text((cx, top + 140), big, fit(big, 90, bw - 30))
            if small:
                text((cx, top + 210), small, font(40), (225, 225, 225))
        text((W // 2, 920), "React on this post to vote", font(38), (255, 255, 255))
        text((W // 2, 975), f"Kickoff {clock}", font(32), (215, 215, 215))
    else:
        a, h = away["score"] or 0, home["score"] or 0
        for key, sc, other in (("away", a, h), ("home", h, a)):
            fill = (255, 255, 255) if sc >= other else (170, 170, 170)
            text((xs[key], 735), str(sc), font(240), fill)
        text((W // 2, 735), "-", font(100), (200, 200, 200))
        if g["venue"]:
            text((W // 2, 900), g["venue"], fit(g["venue"], 34, 960), (225, 225, 225))

    text((W // 2, 1030), PAGE_NAME, font(30), (200, 200, 200))
    img.save(path)


# ----------------------------------------------------------------------------- text
def clean_tag(s):
    return "#" + re.sub(r"[^A-Za-z0-9]", "", s)


def hashtags(g, kind):
    tags = [LEAGUE_TAG.get(g["league"], "#Football")]
    for t in (g["away"], g["home"]):
        tags.append(clean_tag(t["short"]))
    tags += ["#Football", "#GridironNation"]
    tags.append({"preview": "#GameDay", "poll": "#PredictTheWinner"}.get(kind, "#FinalScore"))
    seen, out = set(), []
    for t in tags:
        if t.lower() not in seen and len(t) > 1:
            seen.add(t.lower())
            out.append(t)
    return " ".join(out)


PREVIEW_PROMPTS = [
    "Who takes this one? Drop your pick below!",
    "Predict the score in the comments!",
    "Which side are you on today? Let us know!",
    "Big one today. Who wins and why?",
]
RESULT_PROMPTS = [
    "What did you think of this one? Tell us below!",
    "Who was your player of the game?",
    "Did you call it? Share your thoughts!",
    "Was that the result you expected?",
]


def build_text(g, kind):
    a, h = g["away"], g["home"]
    day, clock = when_text(g["start"])
    if kind == "preview":
        title = f"GAME DAY: {a['name']} at {h['name']}"
        lines = [f"Kickoff: {day} at {clock}"]
        if g["venue"]:
            lines.append(f"Venue: {g['venue']}")
        if g["tv"]:
            lines.append(f"TV: {g['tv']}")
        recs = [f"{t['short']} ({t['record']})" for t in (a, h) if t["record"]]
        if recs:
            lines.append("Records: " + " vs ".join(recs))
        lines.append("")
        lines.append(random.choice(PREVIEW_PROMPTS))
    elif kind == "poll":
        title = f"POLL: Who wins, {a['name']} or {h['name']}?"
        lines = [
            f"Kickoff: {day} at {clock}",
            "",
            "Vote with a reaction on this post:",
            f"\U0001F44D Like = {a['short']} win",
            "\u2764\ufe0f Love = Goes to overtime",
            f"\U0001F62E Wow = {h['short']} win",
            "",
            "We will post the final score after the game!",
        ]
    else:
        sa, sh = a["score"] or 0, h["score"] or 0
        if sa == sh:
            title = f"FINAL: {a['name']} {sa}, {h['name']} {sh} (tie)"
        else:
            w, l = (a, h) if sa > sh else (h, a)
            title = f"FINAL: {w['name']} beat {l['name']} {max(sa, sh)}-{min(sa, sh)}"
        lines = [f"{a['short']} {sa}  |  {h['short']} {sh}"]
        if g["venue"]:
            lines.append(f"At {g['venue']}")
        recs = [f"{t['short']} ({t['record']})" for t in (a, h) if t["record"]]
        if recs:
            lines.append("Records: " + " | ".join(recs))
        lines.append("")
        lines.append(random.choice(RESULT_PROMPTS))
    tags = hashtags(g, kind)
    caption = title + "\n\n" + "\n".join(lines) + "\n\n" + tags
    return title, caption


# ----------------------------------------------------------------------------- facebook
def post_photo(img_path, caption):
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{PAGE_ID}/photos"
    with open(img_path, "rb") as f:
        r = requests.post(
            url,
            data={"caption": caption, "access_token": PAGE_TOKEN},
            files={"source": f},
            timeout=90,
        )
    if not r.ok:
        raise RuntimeError(f"Facebook error {r.status_code}: {r.text[:400]}")
    return r.json()


def publish(g, kind, dry_run):
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"{g['id']}_{kind}.png"
    try:
        make_card(g, kind, path)
        title, caption = build_text(g, kind)
    except Exception as e:
        import traceback

        print(f"[error] could not build {kind} for {g['id']}: {e}")
        traceback.print_exc()
        return False
    print(f"\n=== {kind.upper()}: {title}\n{caption}\n(image: {path})")
    if dry_run:
        return True
    try:
        res = post_photo(path, caption)
        print(f"[posted] {res}")
        return True
    except Exception as e:
        print(f"[error] {e}")
        return False


# ----------------------------------------------------------------------------- state
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True))


# ----------------------------------------------------------------------------- main
def run(dry_run):
    now = datetime.now(timezone.utc)
    games = collect_games(now)
    print(f"[info] {len(games)} games in window at {now:%Y-%m-%d %H:%M} UTC")
    state = load_state()
    changed = False

    # ---- 1) decide what is due (priority: result 0, poll 1, preview 2)
    jobs = []
    for g in games:
        s = state.setdefault(g["id"], {})
        until = g["start"] - now

        if g["state"] == "pre" and timedelta(0) < until:
            if not s.get("poll") and until <= timedelta(hours=POLL_HOURS):
                jobs.append((1, g["start"], g, "poll"))
            if not s.get("preview") and until <= timedelta(hours=PREVIEW_HOURS):
                jobs.append((2, g["start"], g, "preview"))

        if g["completed"] and not s.get("result") and now - g["start"] < timedelta(hours=30):
            seen = s.get("final_seen")
            if not seen:
                s["final_seen"] = now.isoformat()
                changed = True
                seen_dt = now
            else:
                seen_dt = datetime.fromisoformat(seen)
            wait = timedelta(minutes=max(RESULT_DELAY_MIN - 2, 0))
            long_over = now - g["start"] >= timedelta(hours=3, minutes=40)
            if dry_run or long_over or now - seen_dt >= wait:
                jobs.append((0, g["start"], g, "result"))

    jobs.sort(key=lambda j: (j[0], j[1]))
    if jobs:
        print(f"[info] {len(jobs)} posts due: " + ", ".join(f"{j[3]}:{j[2]['id']}" for j in jobs))

    # ---- 2) post them one by one with a gap in between
    t0 = time.monotonic()
    posted = 0
    for i, (_, _, g, kind) in enumerate(jobs):
        if MAX_POSTS_PER_RUN and posted >= MAX_POSTS_PER_RUN:
            print(f"[info] reached MAX_POSTS_PER_RUN={MAX_POSTS_PER_RUN}; rest goes in the next run")
            break
        if not dry_run and time.monotonic() - t0 > MAX_RUN_MINUTES * 60:
            print(f"[info] reached MAX_RUN_MINUTES={MAX_RUN_MINUTES}; rest goes in the next run")
            break
        if publish(g, kind, dry_run):
            state[g["id"]][kind] = now.isoformat()
            changed = True
            posted += 1
            if not dry_run:
                save_state(state)
                if i + 1 < len(jobs):
                    gap = RESULT_GAP_SECONDS if kind == "result" else POST_GAP_SECONDS
                    print(f"[info] waiting {gap}s before the next post ...")
                    time.sleep(gap)

    if changed and not dry_run:
        save_state(state)


def demo():
    """Sample images + captions, no network needed."""
    base = {
        "id": "demo-1",
        "league": "nfl",
        "start": datetime.now(timezone.utc) + timedelta(hours=6),
        "venue": "Sample Stadium, Kansas City, MO",
        "tv": "CBS",
        "away": {"name": "Buffalo Bills", "short": "Bills", "abbr": "BUF", "color": "#00338d", "score": None, "record": "6-2", "rank": 99},
        "home": {"name": "Kansas City Chiefs", "short": "Chiefs", "abbr": "KC", "color": "#e31837", "score": None, "record": "5-3", "rank": 99},
    }
    pre = dict(base, state="pre", completed=False)
    res = json.loads(json.dumps(base, default=str))
    res["start"] = base["start"]
    res["away"] = dict(base["away"], score=24)
    res["home"] = dict(base["home"], score=27)
    res.update(state="post", completed=True)
    college = dict(
        res,
        id="demo-2",
        league="college-football",
        away=dict(base["away"], name="Ohio State Buckeyes", short="Ohio State", abbr="OSU", color="#bb0000", rank=2, record="8-0", score=31),
        home=dict(base["home"], name="Michigan Wolverines", short="Michigan", abbr="MICH", color="#00274c", rank=14, record="6-2", score=17),
    )
    for g, kind in ((pre, "preview"), (pre, "poll"), (res, "result"), (college, "result")):
        publish(g, kind, dry_run=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="make sample images, no network")
    ap.add_argument("--dry-run", action="store_true", help="real data, but do not post")
    args = ap.parse_args()
    if args.demo:
        demo()
        sys.exit(0)
    if not args.dry_run and not (PAGE_ID and PAGE_TOKEN):
        sys.exit("Set FB_PAGE_ID and FB_PAGE_TOKEN (see .env.example), or use --dry-run.")
    run(args.dry_run)
