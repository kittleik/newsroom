#!/usr/bin/env python3
"""Newsroom — Daily Intelligence Report Dashboard"""

import os
import re
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, abort
import markdown

app = Flask(__name__)

REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/home/hk/.openclaw/workspace/reports"))

CATEGORY_MAP = {
    "world": ("🌍 World Overview", 0),
    "europe": ("📰 Regional", 1),
    "mideast": ("📰 Regional", 1),
    "africa": ("📰 Regional", 1),
    "asia": ("📰 Regional", 1),
    "americas": ("📰 Regional", 1),
    "state-media": ("📰 Regional", 1),
    "tech": ("💻 Tech", 2),
    "tech-ai": ("💻 Tech", 2),
    "tech-security": ("💻 Tech", 2),
    "tech-crypto": ("💻 Tech", 2),
}

PERSPECTIVE_COLORS = {
    "western": "#3b82f6",
    "russian": "#ef4444",
    "chinese": "#f97316",
    "israeli": "#14b8a6",
    "arab": "#22c55e",
    "iranian": "#a855f7",
    "critical": "#06b6d4",
    "global south": "#eab308",
}

SLUG_LABELS = {
    "world": "🌍 World",
    "europe": "📰 Europe",
    "mideast": "📰 Mideast",
    "africa": "📰 Africa",
    "asia": "📰 Asia-Pacific",
    "americas": "📰 Americas",
    "state-media": "📰 State Media",
    "tech": "💻 Tech",
    "tech-ai": "💻 AI",
    "tech-security": "💻 Security",
    "tech-crypto": "💻 Crypto",
}

# Canonical order for tab display
SLUG_ORDER = [
    "world", "europe", "mideast", "africa", "asia", "americas",
    "state-media", "tech", "tech-ai", "tech-security", "tech-crypto",
]

COORDS = {
    "norway": (59.9, 10.7), "sweden": (59.3, 18.1), "finland": (60.2, 24.9),
    "uk": (51.5, -0.1), "france": (48.9, 2.3), "germany": (52.5, 13.4),
    "spain": (40.4, -3.7), "italy": (41.9, 12.5), "belgium": (50.8, 4.4),
    "ukraine": (50.4, 30.5), "russia": (55.8, 37.6), "turkey": (41.0, 28.9),
    "iran": (35.7, 51.4), "israel": (31.8, 35.2), "palestine": (31.9, 35.2),
    "gaza": (31.5, 34.5), "lebanon": (33.9, 35.5), "saudi": (24.7, 46.7),
    "qatar": (25.3, 51.5), "uae": (24.5, 54.4), "iraq": (33.3, 44.4),
    "syria": (33.5, 36.3), "yemen": (15.4, 44.2),
    "china": (39.9, 116.4), "japan": (35.7, 139.7), "india": (28.6, 77.2),
    "south korea": (37.6, 127.0), "pakistan": (33.7, 73.0), "bangladesh": (23.8, 90.4),
    "indonesia": (6.2, 106.8), "taiwan": (25.0, 121.5),
    "usa": (38.9, -77.0), "canada": (45.4, -75.7), "mexico": (19.4, -99.1),
    "brazil": (-15.8, -47.9), "venezuela": (10.5, -66.9),
    "sudan": (15.6, 32.5), "ethiopia": (9.0, 38.7), "south africa": (-33.9, 18.4),
    "nigeria": (9.1, 7.5), "madagascar": (-18.9, 47.5), "kenya": (-1.3, 36.8),
    "mozambique": (-25.9, 32.6), "niger": (13.5, 2.1), "ghana": (5.6, -0.2),
    "switzerland": (46.9, 7.4), "oman": (23.6, 58.5),
}

LOCATION_ALIASES = {
    "united states": "usa", "u.s.": "usa", "america": "usa", "washington": "usa",
    "american": "usa", "pentagon": "usa", "white house": "usa",
    "britain": "uk", "british": "uk", "england": "uk", "london": "uk",
    "scottish": "uk", "scotland": "uk",
    "paris": "france", "french": "france",
    "berlin": "germany", "german": "germany",
    "moscow": "russia", "russian": "russia", "kremlin": "russia",
    "beijing": "china", "chinese": "china",
    "tokyo": "japan", "japanese": "japan",
    "iranian": "iran", "tehran": "iran",
    "israeli": "israel", "tel aviv": "israel", "jerusalem": "israel", "netanyahu": "israel",
    "palestinian": "palestine", "west bank": "palestine",
    "turkish": "turkey", "ankara": "turkey", "istanbul": "turkey",
    "ukrainian": "ukraine", "kyiv": "ukraine", "kiev": "ukraine",
    "saudi arabia": "saudi", "riyadh": "saudi",
    "iraqi": "iraq", "baghdad": "iraq",
    "syrian": "syria", "damascus": "syria",
    "lebanese": "lebanon", "beirut": "lebanon", "hezbollah": "lebanon",
    "yemeni": "yemen", "houthi": "yemen", "houthis": "yemen",
    "indian": "india", "delhi": "india", "mumbai": "india", "new delhi": "india",
    "pakistani": "pakistan",
    "south korean": "south korea", "seoul": "south korea", "korean": "south korea",
    "taiwanese": "taiwan", "taipei": "taiwan",
    "brazilian": "brazil",
    "mexican": "mexico",
    "canadian": "canada", "ottawa": "canada",
    "sudanese": "sudan", "khartoum": "sudan",
    "ethiopian": "ethiopia",
    "nigerian": "nigeria",
    "kenyan": "kenya", "nairobi": "kenya",
    "swiss": "switzerland", "geneva": "switzerland", "zurich": "switzerland",
    "omani": "oman", "muscat": "oman",
    "spanish": "spain", "madrid": "spain",
    "italian": "italy", "rome": "italy",
    "belgian": "belgium", "brussels": "belgium",
    "norwegian": "norway", "oslo": "norway",
    "swedish": "sweden", "stockholm": "sweden",
    "finnish": "finland", "helsinki": "finland",
    "qatari": "qatar", "doha": "qatar",
    "emirati": "uae", "dubai": "uae", "abu dhabi": "uae",
    "venezuelan": "venezuela", "caracas": "venezuela",
    "indonesian": "indonesia", "jakarta": "indonesia",
    "ghanaian": "ghana", "accra": "ghana",
    "strait of hormuz": "oman",
    "arabian sea": "oman",
}

_all_locations = {}
for k in COORDS:
    _all_locations[k] = k
for alias, key in LOCATION_ALIASES.items():
    _all_locations[alias] = key
_LOCATION_PATTERNS = sorted(_all_locations.keys(), key=len, reverse=True)
_LOCATION_RE = re.compile(
    r'\b(' + '|'.join(re.escape(p) for p in _LOCATION_PATTERNS) + r')(?:\b|(?=\s|[,.\-:;\'"!\?]))',
    re.IGNORECASE
)


def parse_filename(name):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", name)
    if not m:
        return None
    return m.group(1), m.group(2)


def render_md(text):
    text = re.sub(r"🟢\s*HIGH", '<span class="badge badge-high">🟢 HIGH</span>', text)
    text = re.sub(r"🟡\s*MED", '<span class="badge badge-med">🟡 MED</span>', text)
    text = re.sub(r"🔴\s*STATE", '<span class="badge badge-state">🔴 STATE</span>', text)
    html = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "codehilite", "nl2br", "smarty"],
        extension_configs={"codehilite": {"css_class": "highlight"}},
    )
    html = html.replace("<a ", '<a target="_blank" rel="noopener" ')
    return html


def render_log_md(text):
    """Render log markdown - make all URLs clickable even if not in markdown link format."""
    # First do normal markdown render
    html = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    html = html.replace("<a ", '<a target="_blank" rel="noopener" ')
    # Make bare URLs clickable (not already in href)
    html = re.sub(
        r'(?<!href=")(?<!">)(https?://[^\s<>"]+)',
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        html
    )
    return html


def word_count(text):
    return len(re.findall(r'\w+', text))


def reading_time_minutes(text):
    return max(1, round(word_count(text) / 230))


def extract_headline(text):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line.lstrip("# ").strip()
        if line.startswith("## "):
            return line.lstrip("## ").strip()
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("---") and not line.startswith("*"):
            return line[:120]
    return "Report"


def extract_headings(html):
    """Extract h2 headings for TOC generation (done client-side, but we pass raw text headings)."""
    headings = []
    for m in re.finditer(r'^##\s+(.+)$', html, re.MULTILINE):
        headings.append(m.group(1).strip())
    return headings


def detect_trust(text):
    high = len(re.findall(r"🟢\s*HIGH", text))
    med = len(re.findall(r"🟡\s*MED", text))
    state = len(re.findall(r"🔴\s*STATE", text))
    if state > 0 and state >= high and state >= med:
        return "state"
    if med > 0 and med >= high:
        return "med"
    return "high"


def extract_countries_from_text(text):
    """Return list of unique country keys mentioned in text."""
    found = _LOCATION_RE.findall(text)
    seen = []
    seen_keys = set()
    for loc_match in found:
        key = _all_locations.get(loc_match.lower())
        if key and key not in seen_keys:
            seen_keys.add(key)
            seen.append(key)
    return seen


def extract_geo_markers(text, slug, label):
    headline = extract_headline(text)
    sections = re.split(r'\n(?=## )', text)
    markers = []
    seen_locations = set()

    for section in sections:
        section_headline = headline
        first_line = section.strip().split('\n')[0].strip()
        if first_line.startswith("## "):
            section_headline = first_line.lstrip("# ").strip()
        trust = detect_trust(section)
        found = _LOCATION_RE.findall(section)
        for loc_match in found:
            key = _all_locations.get(loc_match.lower())
            if not key or key in seen_locations:
                continue
            seen_locations.add(key)
            lat, lng = COORDS[key]
            markers.append({
                "lat": lat, "lng": lng, "trust": trust,
                "headline": section_headline[:150],
                "label": label, "country": key.title(),
                "countryKey": key,
            })
    return markers


def parse_source_diversity(text):
    """Parse source diversity from log files for visualization."""
    scores = {}
    in_diversity = False
    for line in text.splitlines():
        if 'source diversity' in line.lower() or 'source balance' in line.lower():
            in_diversity = True
            continue
        if in_diversity:
            m = re.match(r'[-*]\s*\*?\*?(.+?)\*?\*?\s*:\s*(\d+)', line.strip())
            if m:
                scores[m.group(1).strip()] = int(m.group(2))
            elif line.strip() == '' or line.startswith('#'):
                if scores:
                    break
    return scores


def is_debate_report(slug):
    return "debate" in slug


def parse_debate_data(text):
    """Parse debate metadata from markdown comments."""
    data = {"scores": {}, "divergence": {}, "agreement": {}, "truth": {}, "perspectives": list(PERSPECTIVE_COLORS.keys())}

    # Parse scores
    scores_match = re.search(r'<!-- DEBATE_SCORES\n(.*?)\n-->', text, re.DOTALL)
    if scores_match:
        for line in scores_match.group(1).strip().splitlines():
            m = re.match(r'(\w[\w\s]*?):\s*(\d+)', line.strip())
            if m:
                data["scores"][m.group(1).strip().lower()] = int(m.group(2))

    # Parse divergence dimensions
    div_match = re.search(r'<!-- DEBATE_DIVERGENCE\n(.*?)\n-->', text, re.DOTALL)
    if div_match:
        for line in div_match.group(1).strip().splitlines():
            m = re.match(r'(\w+):\s*(.*)', line.strip())
            if m:
                dim_name = m.group(1).strip().lower()
                vals = {}
                for pair in m.group(2).split(','):
                    pm = re.match(r'\s*(\w[\w\s]*?)=(\d+)', pair.strip())
                    if pm:
                        vals[pm.group(1).strip().lower()] = int(pm.group(2))
                data["divergence"][dim_name] = vals

    # Parse agreement matrix
    agr_match = re.search(r'<!-- DEBATE_AGREEMENT\n(.*?)\n-->', text, re.DOTALL)
    if agr_match:
        for line in agr_match.group(1).strip().splitlines():
            m = re.match(r'([\w\s]+)-([\w\s]+):\s*(\w+)', line.strip())
            if m:
                a, b, val = m.group(1).strip().lower(), m.group(2).strip().lower(), m.group(3).strip().lower()
                data["agreement"][f"{a}-{b}"] = val

    # Parse truth landscape
    truth_match = re.search(r'<!-- DEBATE_TRUTH\n(.*?)\n-->', text, re.DOTALL)
    if truth_match:
        for line in truth_match.group(1).strip().splitlines():
            m = re.match(r'(\w+):\s*"?([^"]*)"?', line.strip())
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                try:
                    data["truth"][key] = int(val)
                except ValueError:
                    data["truth"][key] = val

    # Fallback: parse scores from natural format (### Heading ... **Evidence Score: XX/100**)
    if not data["scores"]:
        perspective_map = {
            "western establishment": "western",
            "western critical": "critical",
            "russian": "russian",
            "chinese": "chinese",
            "israeli": "israeli",
            "arab": "arab",
            "sunni": "arab",
            "iranian": "iranian",
            "shia": "iranian",
            "global south": "global south",
        }
        current_perspective = None
        for line in text.splitlines():
            h3 = re.match(r'^###\s+(.+)', line)
            if h3:
                heading = re.sub(r'[🇺🇸🇬🇧🇫🇷🇷🇺🇨🇳🇮🇱🇸🇦🇶🇦🇮🇷🌍📰\U0001F1E0-\U0001F1FF]', '', h3.group(1)).strip().lower()
                current_perspective = None
                for key, val in perspective_map.items():
                    if key in heading:
                        current_perspective = val
                        break
            score_m = re.match(r'\*\*Evidence Score:\s*(\d+)/100\*\*', line.strip())
            if score_m and current_perspective:
                data["scores"][current_perspective] = int(score_m.group(1))

    # Auto-generate agreement matrix from score proximity if not provided
    if not data["agreement"] and len(data["scores"]) >= 2:
        perspectives = list(data["scores"].keys())
        for i, a in enumerate(perspectives):
            for b in perspectives[i+1:]:
                diff = abs(data["scores"][a] - data["scores"][b])
                if diff <= 10:
                    val = "agree"
                elif diff <= 25:
                    val = "partial"
                else:
                    val = "conflict"
                data["agreement"][f"{a}-{b}"] = val

    # Auto-generate truth position from mean score if not provided
    if not data["truth"] and data["scores"]:
        avg = sum(data["scores"].values()) / len(data["scores"])
        data["truth"] = {"position": round(avg), "left_label": "Strong Evidence", "right_label": "Weak Evidence"}

    # Filter perspectives to only those with scores
    data["perspectives"] = [p for p in PERSPECTIVE_COLORS if p in data["scores"]]
    data["colors"] = {p: PERSPECTIVE_COLORS[p] for p in data["perspectives"]}

    return data


@app.route("/api/debate-data/<date>")
def api_debate_data(date):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "bad date"}), 400

    debates = {}
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.iterdir()):
            parsed = parse_filename(f.name)
            if not parsed or parsed[0] != date or not is_debate_report(parsed[1]):
                continue
            content = f.read_text(encoding="utf-8")
            debate = parse_debate_data(content)
            debate["slug"] = parsed[1]
            debate["headline"] = extract_headline(content)
            debates[parsed[1]] = debate

    return jsonify(debates)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dates")
def api_dates():
    dates = set()
    if REPORTS_DIR.exists():
        for f in REPORTS_DIR.iterdir():
            parsed = parse_filename(f.name)
            if parsed and not f.name.endswith("-log.md"):
                dates.add(parsed[0])
    return jsonify(sorted(dates, reverse=True))


@app.route("/api/reports/<date>")
def api_reports(date):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "bad date"}), 400

    reports_list = []
    all_markers = []

    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.iterdir()):
            parsed = parse_filename(f.name)
            if not parsed or parsed[0] != date or f.name.endswith("-log.md"):
                continue
            slug = parsed[1]
            content = f.read_text(encoding="utf-8")
            html = render_md(content)
            if is_debate_report(slug):
                label = "⚖️ " + extract_headline(content)[:40]
            else:
                label = SLUG_LABELS.get(slug, slug.replace("-", " ").title())
            countries = extract_countries_from_text(content)
            headings = extract_headings(content)
            read_time = reading_time_minutes(content)

            # Check if log file exists
            log_file = REPORTS_DIR / f"{date}-{slug}-log.md"
            has_log = log_file.exists()

            is_debate = is_debate_report(slug)

            reports_list.append({
                "slug": slug,
                "label": label,
                "html": html,
                "countries": countries,
                "headings": headings,
                "readTime": read_time,
                "hasLog": has_log,
                "isDebate": is_debate,
            })

            markers = extract_geo_markers(content, slug, label)
            all_markers.extend(markers)

    # Sort by canonical order
    slug_order_map = {s: i for i, s in enumerate(SLUG_ORDER)}
    reports_list.sort(key=lambda r: slug_order_map.get(r["slug"], 99))

    return jsonify({"reports": reports_list, "markers": all_markers})


@app.route("/api/map-data")
def api_map_data():
    dates = set()
    if REPORTS_DIR.exists():
        for f in REPORTS_DIR.iterdir():
            parsed = parse_filename(f.name)
            if parsed and not f.name.endswith("-log.md"):
                dates.add(parsed[0])
    if not dates:
        return jsonify([])
    date = max(dates)

    country_data = defaultdict(lambda: {"headlines": [], "trust": "high"})
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.iterdir()):
            parsed = parse_filename(f.name)
            if not parsed or parsed[0] != date or f.name.endswith("-log.md"):
                continue
            slug = parsed[1]
            label = SLUG_LABELS.get(slug, slug.replace("-", " ").title())
            content = f.read_text(encoding="utf-8")
            markers = extract_geo_markers(content, slug, label)
            for m in markers:
                key = m["country"]
                country_data[key]["lat"] = m["lat"]
                country_data[key]["lng"] = m["lng"]
                country_data[key]["country"] = key
                country_data[key]["countryKey"] = m["countryKey"]
                country_data[key]["headlines"].append({
                    "title": m["headline"],
                    "section": m["label"],
                    "trust": m["trust"],
                })
                cur = country_data[key]["trust"]
                if m["trust"] == "state" or cur == "state":
                    country_data[key]["trust"] = "state"
                elif m["trust"] == "med" or cur == "med":
                    country_data[key]["trust"] = "med"

    return jsonify(list(country_data.values()))


@app.route("/report/<date>/<slug>/log")
def report_log(date, slug):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        abort(400)
    log_file = REPORTS_DIR / f"{date}-{slug}-log.md"
    if not log_file.exists():
        abort(404)
    content = log_file.read_text(encoding="utf-8")
    html = render_log_md(content)
    label = SLUG_LABELS.get(slug, slug.replace("-", " ").title())
    diversity = parse_source_diversity(content)
    return render_template("log.html", html=html, date=date, slug=slug, label=label, diversity=diversity)


@app.route("/api/coords")
def api_coords():
    """Return all known coordinates for client-side map panning."""
    return jsonify({k: {"lat": v[0], "lng": v[1]} for k, v in COORDS.items()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3118, debug=False)
