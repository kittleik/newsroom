#!/usr/bin/env python3
"""Newsroom — Daily Intelligence Report Dashboard"""

import os
import re
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template
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

SLUG_LABELS = {
    "world": "World Overview",
    "europe": "Europe",
    "mideast": "Middle East",
    "africa": "Africa",
    "asia": "Asia-Pacific",
    "americas": "Americas",
    "state-media": "State Media Watch",
    "tech": "Tech Overview",
    "tech-ai": "AI & ML",
    "tech-security": "Cybersecurity",
    "tech-crypto": "Crypto & Blockchain",
}

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

# Aliases that map to a COORDS key
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
    "iranian": "iran", "tehran": "iran", "tehran": "iran",
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

# Build a sorted (longest-first) pattern list for matching
_all_locations = {}
for k in COORDS:
    _all_locations[k] = k
for alias, key in LOCATION_ALIASES.items():
    _all_locations[alias] = key
# Sort by length descending so "south korea" matches before "south" or "korea"
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


def extract_headline(text):
    """Get the first H1 or H2 or first non-empty line."""
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


def detect_trust(text):
    """Dominant trust rating in a paragraph."""
    high = len(re.findall(r"🟢\s*HIGH", text))
    med = len(re.findall(r"🟡\s*MED", text))
    state = len(re.findall(r"🔴\s*STATE", text))
    if state > 0 and state >= high and state >= med:
        return "state"
    if med > 0 and med >= high:
        return "med"
    return "high"


def extract_geo_markers(text, slug, label):
    """Extract geo markers from report text. Returns list of {lat,lng,trust,headline,label,country}."""
    headline = extract_headline(text)

    # Split into sections by H2
    sections = re.split(r'\n(?=## )', text)
    markers = []
    seen_locations = set()  # per-report dedup by country key

    for section in sections:
        section_headline = headline
        first_line = section.strip().split('\n')[0].strip()
        if first_line.startswith("## "):
            section_headline = first_line.lstrip("# ").strip()

        trust = detect_trust(section)

        # Find all location mentions
        found = _LOCATION_RE.findall(section)
        for loc_match in found:
            key = _all_locations.get(loc_match.lower())
            if not key or key in seen_locations:
                continue
            seen_locations.add(key)
            lat, lng = COORDS[key]
            markers.append({
                "lat": lat,
                "lng": lng,
                "trust": trust,
                "headline": section_headline[:150],
                "label": label,
                "country": key.title(),
            })

    return markers


@app.route("/api/map-data")
def api_map_data():
    """Return all geo markers from the most recent date's reports."""
    # Find most recent date
    dates = set()
    if REPORTS_DIR.exists():
        for f in REPORTS_DIR.iterdir():
            parsed = parse_filename(f.name)
            if parsed:
                dates.add(parsed[0])
    if not dates:
        return jsonify([])
    date = max(dates)

    # Collect markers, group by country
    country_data = defaultdict(lambda: {"headlines": [], "trust": "high"})
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.iterdir()):
            parsed = parse_filename(f.name)
            if not parsed or parsed[0] != date:
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
                country_data[key]["headlines"].append({
                    "title": m["headline"],
                    "section": m["label"],
                    "trust": m["trust"],
                })
                # Worst trust wins
                cur = country_data[key]["trust"]
                if m["trust"] == "state" or cur == "state":
                    country_data[key]["trust"] = "state"
                elif m["trust"] == "med" or cur == "med":
                    country_data[key]["trust"] = "med"

    return jsonify(list(country_data.values()))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dates")
def api_dates():
    dates = set()
    if REPORTS_DIR.exists():
        for f in REPORTS_DIR.iterdir():
            parsed = parse_filename(f.name)
            if parsed:
                dates.add(parsed[0])
    return jsonify(sorted(dates, reverse=True))


@app.route("/api/reports/<date>")
def api_reports(date):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return jsonify({"error": "bad date"}), 400

    groups = defaultdict(list)
    all_markers = []

    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.iterdir()):
            parsed = parse_filename(f.name)
            if not parsed or parsed[0] != date:
                continue
            slug = parsed[1]
            cat, order = CATEGORY_MAP.get(slug, ("📰 Regional", 1))
            content = f.read_text(encoding="utf-8")
            html = render_md(content)
            label = SLUG_LABELS.get(slug, slug.replace("-", " ").title())
            groups[cat].append({"slug": slug, "label": label, "html": html, "order": order})

            markers = extract_geo_markers(content, slug, label)
            all_markers.extend(markers)

    result = []
    seen = set()
    for cat in sorted(groups.keys(), key=lambda c: groups[c][0]["order"]):
        if cat in seen:
            continue
        seen.add(cat)
        items = sorted(groups[cat], key=lambda x: x["slug"])
        result.append({
            "category": cat,
            "reports": [{"slug": r["slug"], "label": r["label"], "html": r["html"]} for r in items],
        })

    return jsonify({"groups": result, "markers": all_markers})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3118, debug=False)
