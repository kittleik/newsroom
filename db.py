"""
Newsroom Database — SQLite + FTS5 for report storage, indexing, and cross-linking.

Schema:
- reports: each markdown file with metadata
- entities: extracted countries, people, organizations, topics
- report_entities: many-to-many linking
- links: cross-references between reports (same entity across days)
- sources: every URL cited in reports with trust rating

Usage:
    from db import NewsDB
    db = NewsDB()
    db.index_reports("/path/to/reports/")
    results = db.search("Iran nuclear")
    links = db.find_connections("Iran", days=7)
    timeline = db.entity_timeline("Ukraine")
"""

import sqlite3
import os
import re
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path


class NewsDB:
    def __init__(self, db_path="/home/hk/Projects/newsroom/newsroom.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                slug TEXT NOT NULL,
                category TEXT,
                title TEXT,
                content TEXT,
                word_count INTEGER,
                file_path TEXT UNIQUE,
                file_hash TEXT,
                indexed_at TEXT,
                UNIQUE(date, slug)
            );

            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                type TEXT,  -- country, person, org, topic
                lat REAL,
                lng REAL
            );

            CREATE TABLE IF NOT EXISTS report_entities (
                report_id INTEGER REFERENCES reports(id),
                entity_id INTEGER REFERENCES entities(id),
                mention_count INTEGER DEFAULT 1,
                context TEXT,  -- snippet around first mention
                PRIMARY KEY (report_id, entity_id)
            );

            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                report_id INTEGER REFERENCES reports(id),
                url TEXT,
                source_name TEXT,
                trust_rating TEXT,  -- HIGH, MED, STATE
                title TEXT,
                used_in_report INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY,
                entity_id INTEGER REFERENCES entities(id),
                report_id_a INTEGER REFERENCES reports(id),
                report_id_b INTEGER REFERENCES reports(id),
                connection_type TEXT,  -- 'same_story', 'follow_up', 'related'
                strength REAL DEFAULT 1.0,
                UNIQUE(entity_id, report_id_a, report_id_b)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS reports_fts USING fts5(
                title, content, date, slug, category,
                content='reports',
                content_rowid='id'
            );

            CREATE TABLE IF NOT EXISTS debate_scores (
                id INTEGER PRIMARY KEY,
                report_id INTEGER REFERENCES reports(id),
                perspective TEXT,
                factual_score INTEGER,
                consistency_score INTEGER,
                predictive_score INTEGER,
                independence_score INTEGER,
                total_score INTEGER,
                steelman TEXT,
                weakness TEXT
            );

            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY,
                report_id INTEGER REFERENCES reports(id),
                market_question TEXT,
                probability REAL,
                volume REAL,
                url TEXT,
                fetched_at TEXT
            );
        """)
        self.conn.commit()

    # --- Known entities ---
    COUNTRIES = {
        "norway": ("country", 59.9, 10.7), "sweden": ("country", 59.3, 18.1),
        "finland": ("country", 60.2, 24.9), "uk": ("country", 51.5, -0.1),
        "france": ("country", 48.9, 2.3), "germany": ("country", 52.5, 13.4),
        "ukraine": ("country", 50.4, 30.5), "russia": ("country", 55.8, 37.6),
        "turkey": ("country", 41.0, 28.9), "iran": ("country", 35.7, 51.4),
        "israel": ("country", 31.8, 35.2), "palestine": ("country", 31.9, 35.2),
        "gaza": ("country", 31.5, 34.5), "lebanon": ("country", 33.9, 35.5),
        "saudi arabia": ("country", 24.7, 46.7), "qatar": ("country", 25.3, 51.5),
        "uae": ("country", 24.5, 54.4), "iraq": ("country", 33.3, 44.4),
        "syria": ("country", 33.5, 36.3), "china": ("country", 39.9, 116.4),
        "japan": ("country", 35.7, 139.7), "india": ("country", 28.6, 77.2),
        "south korea": ("country", 37.6, 127.0), "pakistan": ("country", 33.7, 73.0),
        "bangladesh": ("country", 23.8, 90.4), "indonesia": ("country", -6.2, 106.8),
        "taiwan": ("country", 25.0, 121.5), "usa": ("country", 38.9, -77.0),
        "united states": ("country", 38.9, -77.0),
        "canada": ("country", 45.4, -75.7), "brazil": ("country", -15.8, -47.9),
        "venezuela": ("country", 10.5, -66.9), "sudan": ("country", 15.6, 32.5),
        "ethiopia": ("country", 9.0, 38.7), "south africa": ("country", -33.9, 18.4),
        "nigeria": ("country", 9.1, 7.5), "madagascar": ("country", -18.9, 47.5),
        "kenya": ("country", -1.3, 36.8), "switzerland": ("country", 46.9, 7.4),
        "oman": ("country", 23.6, 58.5), "niger": ("country", 13.5, 2.1),
        "ghana": ("country", 5.6, -0.2), "mozambique": ("country", -25.9, 32.6),
        "spain": ("country", 40.4, -3.7), "italy": ("country", 41.9, 12.5),
        "belgium": ("country", 50.8, 4.4), "yemen": ("country", 15.4, 44.2),
    }

    def _ensure_entity(self, name, etype=None, lat=None, lng=None):
        """Get or create an entity, return its id."""
        row = self.conn.execute("SELECT id FROM entities WHERE name=?", (name.lower(),)).fetchone()
        if row:
            return row["id"]
        self.conn.execute(
            "INSERT INTO entities (name, type, lat, lng) VALUES (?, ?, ?, ?)",
            (name.lower(), etype, lat, lng)
        )
        self.conn.commit()
        return self.conn.execute("SELECT id FROM entities WHERE name=?", (name.lower(),)).fetchone()["id"]

    def _extract_entities(self, content):
        """Extract country/entity mentions from report content."""
        found = {}
        content_lower = content.lower()
        for name, (etype, lat, lng) in self.COUNTRIES.items():
            count = content_lower.count(name)
            if count > 0:
                # Get context snippet
                idx = content_lower.index(name)
                start = max(0, idx - 80)
                end = min(len(content), idx + len(name) + 80)
                context = content[start:end].replace("\n", " ").strip()
                found[name] = {"type": etype, "lat": lat, "lng": lng, "count": count, "context": context}
        return found

    def _extract_sources(self, content):
        """Extract URLs and source info from report content."""
        sources = []
        # Match markdown links [text](url)
        for match in re.finditer(r'\[([^\]]+)\]\((https?://[^\)]+)\)', content):
            title, url = match.group(1), match.group(2)
            # Determine trust from context
            trust = "HIGH"
            line_start = content.rfind("\n", 0, match.start()) + 1
            line = content[line_start:match.end() + 50]
            if "🔴" in line or "STATE" in line:
                trust = "STATE"
            elif "🟡" in line or "MED" in line:
                trust = "MED"
            # Extract source name from URL
            from urllib.parse import urlparse
            source_name = urlparse(url).netloc.replace("www.", "")
            sources.append({"url": url, "title": title, "source_name": source_name, "trust": trust})
        
        # Also match bare URLs
        for match in re.finditer(r'(?<!\()(https?://\S+?)(?=[)\s,\]]|$)', content):
            url = match.group(1)
            from urllib.parse import urlparse
            source_name = urlparse(url).netloc.replace("www.", "")
            sources.append({"url": url, "title": "", "source_name": source_name, "trust": "HIGH"})
        
        return sources

    def _parse_filename(self, filename):
        """Parse YYYY-MM-DD-slug.md into (date, slug, category)."""
        m = re.match(r'(\d{4}-\d{2}-\d{2})-(.+)\.md$', filename)
        if not m:
            return None, None, None
        date, slug = m.group(1), m.group(2)
        
        # Category mapping
        if slug in ("world",):
            cat = "world"
        elif slug in ("europe", "mideast", "africa", "asia", "americas", "state-media"):
            cat = "regional"
        elif slug.startswith("tech"):
            cat = "tech"
        elif slug.startswith("debate"):
            cat = "debate"
        else:
            cat = "other"
        return date, slug, cat

    def _extract_title(self, content):
        """Get the first H1 from markdown."""
        m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        return m.group(1) if m else None

    def index_file(self, file_path):
        """Index a single report file."""
        path = Path(file_path)
        if not path.exists() or path.suffix != ".md":
            return False
        if path.name.startswith("TEMPLATE"):
            return False

        date, slug, category = self._parse_filename(path.name)
        if not date:
            return False

        content = path.read_text(encoding="utf-8")
        file_hash = hashlib.md5(content.encode()).hexdigest()

        # Check if already indexed with same hash
        existing = self.conn.execute(
            "SELECT id, file_hash FROM reports WHERE file_path=?", (str(path),)
        ).fetchone()
        if existing and existing["file_hash"] == file_hash:
            return False  # No changes

        title = self._extract_title(content) or f"{date} {slug}"
        word_count = len(content.split())

        if existing:
            report_id = existing["id"]
            self.conn.execute(
                "UPDATE reports SET content=?, title=?, word_count=?, file_hash=?, indexed_at=?, category=? WHERE id=?",
                (content, title, word_count, file_hash, datetime.now().isoformat(), category, report_id)
            )
            # Clean old relations
            self.conn.execute("DELETE FROM report_entities WHERE report_id=?", (report_id,))
            self.conn.execute("DELETE FROM sources WHERE report_id=?", (report_id,))
            # Update FTS (delete + reinsert for content-sync tables)
            self.conn.execute("INSERT INTO reports_fts (reports_fts, rowid, title, content, date, slug, category) VALUES ('delete', ?, ?, ?, ?, ?, ?)",
                (report_id, title, content, date, slug, category))
        else:
            self.conn.execute(
                "INSERT INTO reports (date, slug, category, title, content, word_count, file_path, file_hash, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (date, slug, category, title, word_count, content, str(path), file_hash, datetime.now().isoformat())
            )
            report_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # Extract and link entities
        entities = self._extract_entities(content)
        for name, info in entities.items():
            entity_id = self._ensure_entity(name, info["type"], info["lat"], info["lng"])
            self.conn.execute(
                "INSERT OR REPLACE INTO report_entities (report_id, entity_id, mention_count, context) VALUES (?, ?, ?, ?)",
                (report_id, entity_id, info["count"], info["context"])
            )

        # Extract sources
        sources = self._extract_sources(content)
        for s in sources:
            self.conn.execute(
                "INSERT INTO sources (report_id, url, source_name, trust_rating, title) VALUES (?, ?, ?, ?, ?)",
                (report_id, s["url"], s["source_name"], s["trust"], s["title"])
            )

        # Update FTS
        self.conn.execute(
            "INSERT INTO reports_fts (rowid, title, content, date, slug, category) VALUES (?, ?, ?, ?, ?, ?)",
            (report_id, title, content, date, slug, category)
        )

        self.conn.commit()
        return True

    def index_reports(self, reports_dir="/home/hk/.openclaw/workspace/reports/"):
        """Index all reports in a directory."""
        count = 0
        for f in sorted(Path(reports_dir).glob("*.md")):
            if self.index_file(f):
                count += 1
        self._build_connections()
        return count

    def _build_connections(self):
        """Build cross-report connections via shared entities."""
        self.conn.execute("DELETE FROM connections")
        # Find reports that share entities
        rows = self.conn.execute("""
            SELECT e.id as entity_id, e.name,
                   a.report_id as rid_a, b.report_id as rid_b,
                   ra.date as date_a, rb.date as date_b
            FROM report_entities a
            JOIN report_entities b ON a.entity_id = b.entity_id AND a.report_id < b.report_id
            JOIN entities e ON e.id = a.entity_id
            JOIN reports ra ON ra.id = a.report_id
            JOIN reports rb ON rb.id = b.report_id
        """).fetchall()

        for r in rows:
            # Stronger connection if same entity appears across different days
            if r["date_a"] != r["date_b"]:
                conn_type = "follow_up"
                strength = 2.0
            else:
                conn_type = "same_day"
                strength = 1.0

            self.conn.execute(
                "INSERT OR IGNORE INTO connections (entity_id, report_id_a, report_id_b, connection_type, strength) VALUES (?, ?, ?, ?, ?)",
                (r["entity_id"], r["rid_a"], r["rid_b"], conn_type, strength)
            )
        self.conn.commit()

    # --- Query API ---

    def search(self, query, limit=20):
        """Full-text search across all reports."""
        rows = self.conn.execute(
            "SELECT rowid, highlight(reports_fts, 1, '<mark>', '</mark>') as snippet, date, slug, category FROM reports_fts WHERE content MATCH ? ORDER BY rank LIMIT ?",
            (query, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def find_connections(self, entity_name, days=30):
        """Find all reports mentioning an entity, with cross-links."""
        entity = self.conn.execute("SELECT id FROM entities WHERE name=?", (entity_name.lower(),)).fetchone()
        if not entity:
            return []
        rows = self.conn.execute("""
            SELECT r.date, r.slug, r.title, r.category, re.mention_count, re.context
            FROM report_entities re
            JOIN reports r ON r.id = re.report_id
            WHERE re.entity_id = ?
            ORDER BY r.date DESC
            LIMIT 100
        """, (entity["id"],)).fetchall()
        return [dict(r) for r in rows]

    def entity_timeline(self, entity_name):
        """Get a timeline of how an entity appeared across reports over time."""
        return self.find_connections(entity_name, days=365)

    def get_report(self, date, slug):
        """Get a single report."""
        row = self.conn.execute(
            "SELECT * FROM reports WHERE date=? AND slug=?", (date, slug)
        ).fetchone()
        return dict(row) if row else None

    def get_dates(self):
        """Get all dates that have reports."""
        rows = self.conn.execute(
            "SELECT DISTINCT date FROM reports ORDER BY date DESC"
        ).fetchall()
        return [r["date"] for r in rows]

    def get_reports_for_date(self, date):
        """Get all reports for a given date."""
        rows = self.conn.execute(
            "SELECT id, date, slug, category, title, word_count FROM reports WHERE date=? ORDER BY category, slug",
            (date,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_related(self, report_id, limit=10):
        """Get reports related to a given report via shared entities."""
        rows = self.conn.execute("""
            SELECT DISTINCT r.date, r.slug, r.title, r.category, e.name as shared_entity, c.strength
            FROM connections c
            JOIN reports r ON (r.id = c.report_id_b AND c.report_id_a = ?) OR (r.id = c.report_id_a AND c.report_id_b = ?)
            JOIN entities e ON e.id = c.entity_id
            WHERE r.id != ?
            ORDER BY c.strength DESC, r.date DESC
            LIMIT ?
        """, (report_id, report_id, report_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_top_entities(self, date=None, limit=20):
        """Get most-mentioned entities, optionally filtered by date."""
        if date:
            rows = self.conn.execute("""
                SELECT e.name, e.type, e.lat, e.lng, SUM(re.mention_count) as total_mentions
                FROM report_entities re
                JOIN entities e ON e.id = re.entity_id
                JOIN reports r ON r.id = re.report_id
                WHERE r.date = ?
                GROUP BY e.id ORDER BY total_mentions DESC LIMIT ?
            """, (date, limit)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT e.name, e.type, e.lat, e.lng, SUM(re.mention_count) as total_mentions
                FROM report_entities re
                JOIN entities e ON e.id = re.entity_id
                GROUP BY e.id ORDER BY total_mentions DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_source_stats(self, date=None):
        """Get source usage statistics."""
        if date:
            rows = self.conn.execute("""
                SELECT source_name, trust_rating, COUNT(*) as count
                FROM sources s JOIN reports r ON r.id = s.report_id
                WHERE r.date = ?
                GROUP BY source_name, trust_rating ORDER BY count DESC
            """, (date,)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT source_name, trust_rating, COUNT(*) as count
                FROM sources GROUP BY source_name, trust_rating ORDER BY count DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def stats(self):
        """Get database statistics."""
        return {
            "reports": self.conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
            "entities": self.conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "sources": self.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "connections": self.conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0],
            "dates": len(self.get_dates()),
        }


if __name__ == "__main__":
    db = NewsDB()
    n = db.index_reports()
    print(f"Indexed {n} new/updated reports")
    stats = db.stats()
    print(f"DB: {stats['reports']} reports, {stats['entities']} entities, {stats['sources']} sources, {stats['connections']} connections across {stats['dates']} days")
