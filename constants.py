"""Shared constants for the Newsroom app — single source of truth for geo, categories, and slugs."""

import re

# === Coordinates ===
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

# === Location Aliases (maps alias → COORDS key) ===
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

# Build unified location lookup and compiled regex
_all_locations = {}
for k in COORDS:
    _all_locations[k] = k
for alias, key in LOCATION_ALIASES.items():
    _all_locations[alias] = key
_LOCATION_PATTERNS = sorted(_all_locations.keys(), key=len, reverse=True)
LOCATION_RE = re.compile(
    r'\b(' + '|'.join(re.escape(p) for p in _LOCATION_PATTERNS) + r')(?:\b|(?=\s|[,.\-:;\'"!\?]))',
    re.IGNORECASE
)


def extract_countries(text):
    """Return list of unique country keys mentioned in text (uses word-boundary regex, not substring)."""
    found = LOCATION_RE.findall(text)
    seen = []
    seen_keys = set()
    for loc_match in found:
        key = _all_locations.get(loc_match.lower())
        if key and key not in seen_keys:
            seen_keys.add(key)
            seen.append(key)
    return seen


# === Category Mapping ===
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

SLUG_ORDER = [
    "world", "europe", "mideast", "africa", "asia", "americas",
    "state-media", "tech", "tech-ai", "tech-security", "tech-crypto",
]

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


def parse_filename(name):
    """Parse YYYY-MM-DD-slug.md → (date, slug) or None."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)\.md$", name)
    if not m:
        return None
    return m.group(1), m.group(2)


def slug_to_category(slug):
    """Map slug to category string for DB."""
    if slug in ("world",):
        return "world"
    if slug in ("europe", "mideast", "africa", "asia", "americas", "state-media"):
        return "regional"
    if slug.startswith("tech"):
        return "tech"
    if slug.startswith("debate"):
        return "debate"
    return "other"
