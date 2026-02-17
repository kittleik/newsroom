#!/usr/bin/env python3
"""Newsroom — Daily Intelligence Report Dashboard"""

import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, abort, request
import markdown

from config import REPORTS_DIR, HOST, PORT, DEBUG, DB_PATH
from constants import (
    COORDS, LOCATION_ALIASES, LOCATION_RE, CATEGORY_MAP, SLUG_LABELS,
    SLUG_ORDER, PERSPECTIVE_COLORS, extract_countries, parse_filename,
    slug_to_category,
)

app = Flask(__name__)

# Lazy DB singleton
_db = None
def get_db():
    global _db
    if _db is None:
        from db import NewsDB
        _db = NewsDB(DB_PATH)
    return _db

# Location lookup (flat dict: name/alias → coords key)
_all_locations = {}
for k in COORDS:
    _all_locations[k] = k
for alias, key in LOCATION_ALIASES.items():
    _all_locations[alias] = key


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
    html = markdown.markdown(text, extensions=["tables", "fenced_code", "nl2br"])
    html = html.replace("<a ", '<a target="_blank" rel="noopener" ')
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


def extract_headings(text):
    headings = []
    for m in re.finditer(r'^##\s+(.+)$', text, re.MULTILINE):
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
        found = LOCATION_RE.findall(section)
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
    data = {"scores": {}, "divergence": {}, "agreement": {}, "truth": {}, "perspectives": list(PERSPECTIVE_COLORS.keys())}

    scores_match = re.search(r'<!-- DEBATE_SCORES\n(.*?)\n-->', text, re.DOTALL)
    if scores_match:
        for line in scores_match.group(1).strip().splitlines():
            m = re.match(r'(\w[\w\s]*?):\s*(\d+)', line.strip())
            if m:
                data["scores"][m.group(1).strip().lower()] = int(m.group(2))

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

    agr_match = re.search(r'<!-- DEBATE_AGREEMENT\n(.*?)\n-->', text, re.DOTALL)
    if agr_match:
        for line in agr_match.group(1).strip().splitlines():
            m = re.match(r'([\w\s]+)-([\w\s]+):\s*(\w+)', line.strip())
            if m:
                a, b, val = m.group(1).strip().lower(), m.group(2).strip().lower(), m.group(3).strip().lower()
                data["agreement"][f"{a}-{b}"] = val

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

    # Fallback: parse scores from natural format
    if not data["scores"]:
        perspective_map = {
            "western establishment": "western", "western critical": "critical",
            "russian": "russian", "chinese": "chinese", "israeli": "israeli",
            "arab": "arab", "sunni": "arab", "iranian": "iranian", "shia": "iranian",
            "global south": "global south",
        }
        current_perspective = None
        for line in text.splitlines():
            h3 = re.match(r'^###\s+(.+)', line)
            if h3:
                heading = re.sub(r'[\U0001F1E0-\U0001F1FF\U0001F300-\U0001F9FF]', '', h3.group(1)).strip().lower()
                current_perspective = None
                for key, val in perspective_map.items():
                    if key in heading:
                        current_perspective = val
                        break
            score_m = re.match(r'\*\*Evidence Score:\s*(\d+)/100\*\*', line.strip())
            if score_m and current_perspective:
                data["scores"][current_perspective] = int(score_m.group(1))

    # Auto-generate agreement from score proximity
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

    if not data["truth"] and data["scores"]:
        avg = sum(data["scores"].values()) / len(data["scores"])
        data["truth"] = {"position": round(avg), "left_label": "Strong Evidence", "right_label": "Weak Evidence"}

    data["perspectives"] = [p for p in PERSPECTIVE_COLORS if p in data["scores"]]
    data["colors"] = {p: PERSPECTIVE_COLORS[p] for p in data["perspectives"]}

    return data


# === Routes ===

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
            countries = extract_countries(content)
            headings = extract_headings(content)
            read_time = reading_time_minutes(content)
            log_file = REPORTS_DIR / f"{date}-{slug}-log.md"
            has_log = log_file.exists()
            is_debate = is_debate_report(slug)

            reports_list.append({
                "slug": slug, "label": label, "html": html,
                "countries": countries, "headings": headings,
                "readTime": read_time, "hasLog": has_log, "isDebate": is_debate,
            })

            markers = extract_geo_markers(content, slug, label)
            all_markers.extend(markers)

    slug_order_map = {s: i for i, s in enumerate(SLUG_ORDER)}
    reports_list.sort(key=lambda r: slug_order_map.get(r["slug"], 99))

    return jsonify({"reports": reports_list, "markers": all_markers})


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


@app.route("/api/search")
def api_search():
    """Full-text search across all reports."""
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"error": "query too short", "results": []}), 400
    limit = min(int(request.args.get("limit", 20)), 50)
    try:
        db = get_db()
        results = db.search(q, limit=limit)
        return jsonify({"results": results, "query": q})
    except Exception as e:
        return jsonify({"error": str(e), "results": []}), 500


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
                    "title": m["headline"], "section": m["label"], "trust": m["trust"],
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
    return jsonify({k: {"lat": v[0], "lng": v[1]} for k, v in COORDS.items()})


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
