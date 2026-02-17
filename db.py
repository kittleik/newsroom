"""
Newsroom Database — SQLite + FTS5 for report storage, indexing, and cross-linking.

Usage:
    from db import NewsDB
    db = NewsDB()
    db.index_reports()
    results = db.search("Iran nuclear")
    timeline = db.entity_timeline("Ukraine")
"""

import sqlite3
import re
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from config import DB_PATH, REPORTS_DIR
from constants import COORDS, extract_countries, parse_filename, slug_to_category


class NewsDB:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.conn = sqlite3.connect(self.db_path)
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
                type TEXT,
                lat REAL,
                lng REAL
            );

            CREATE TABLE IF NOT EXISTS report_entities (
                report_id INTEGER REFERENCES reports(id),
                entity_id INTEGER REFERENCES entities(id),
                mention_count INTEGER DEFAULT 1,
                context TEXT,
                PRIMARY KEY (report_id, entity_id)
            );

            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                report_id INTEGER REFERENCES reports(id),
                url TEXT,
                source_name TEXT,
                trust_rating TEXT,
                title TEXT,
                used_in_report INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY,
                entity_id INTEGER REFERENCES entities(id),
                report_id_a INTEGER REFERENCES reports(id),
                report_id_b INTEGER REFERENCES reports(id),
                connection_type TEXT,
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

    def _ensure_entity(self, name, etype=None, lat=None, lng=None):
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
        """Extract country mentions using shared regex (word-boundary, no niger-in-nigeria bug)."""
        found = {}
        countries = extract_countries(content)
        content_lower = content.lower()
        for key in countries:
            if key in COORDS:
                lat, lng = COORDS[key]
                # Count occurrences via regex for accuracy
                count = len(re.findall(r'\b' + re.escape(key) + r'\b', content_lower))
                count = max(count, 1)
                # Get context snippet
                idx = content_lower.find(key)
                start = max(0, idx - 80)
                end = min(len(content), idx + len(key) + 80)
                context = content[start:end].replace("\n", " ").strip()
                found[key] = {"type": "country", "lat": lat, "lng": lng, "count": count, "context": context}
        return found

    def _extract_sources(self, content):
        sources = []
        for match in re.finditer(r'\[([^\]]+)\]\((https?://[^\)]+)\)', content):
            title, url = match.group(1), match.group(2)
            trust = "HIGH"
            line_start = content.rfind("\n", 0, match.start()) + 1
            line = content[line_start:match.end() + 50]
            if "🔴" in line or "STATE" in line:
                trust = "STATE"
            elif "🟡" in line or "MED" in line:
                trust = "MED"
            source_name = urlparse(url).netloc.replace("www.", "")
            sources.append({"url": url, "title": title, "source_name": source_name, "trust": trust})

        for match in re.finditer(r'(?<!\()(https?://\S+?)(?=[)\s,\]]|$)', content):
            url = match.group(1)
            source_name = urlparse(url).netloc.replace("www.", "")
            sources.append({"url": url, "title": "", "source_name": source_name, "trust": "HIGH"})

        return sources

    def _extract_title(self, content):
        m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        return m.group(1) if m else None

    def index_file(self, file_path):
        path = Path(file_path)
        if not path.exists() or path.suffix != ".md":
            return False
        if path.name.startswith("TEMPLATE"):
            return False

        parsed = parse_filename(path.name)
        if not parsed:
            return False
        date, slug = parsed
        category = slug_to_category(slug)

        content = path.read_text(encoding="utf-8")
        file_hash = hashlib.md5(content.encode()).hexdigest()

        existing = self.conn.execute(
            "SELECT id, file_hash FROM reports WHERE file_path=?", (str(path),)
        ).fetchone()
        if existing and existing["file_hash"] == file_hash:
            return False

        title = self._extract_title(content) or f"{date} {slug}"
        wc = len(content.split())

        if existing:
            report_id = existing["id"]
            self.conn.execute(
                "UPDATE reports SET content=?, title=?, word_count=?, file_hash=?, indexed_at=?, category=? WHERE id=?",
                (content, title, wc, file_hash, datetime.now().isoformat(), category, report_id)
            )
            self.conn.execute("DELETE FROM report_entities WHERE report_id=?", (report_id,))
            self.conn.execute("DELETE FROM sources WHERE report_id=?", (report_id,))
            self.conn.execute(
                "INSERT INTO reports_fts (reports_fts, rowid, title, content, date, slug, category) VALUES ('delete', ?, ?, ?, ?, ?, ?)",
                (report_id, title, content, date, slug, category)
            )
        else:
            self.conn.execute(
                "INSERT INTO reports (date, slug, category, title, content, word_count, file_path, file_hash, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (date, slug, category, title, wc, content, str(path), file_hash, datetime.now().isoformat())
            )
            report_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        entities = self._extract_entities(content)
        for name, info in entities.items():
            entity_id = self._ensure_entity(name, info["type"], info["lat"], info["lng"])
            self.conn.execute(
                "INSERT OR REPLACE INTO report_entities (report_id, entity_id, mention_count, context) VALUES (?, ?, ?, ?)",
                (report_id, entity_id, info["count"], info["context"])
            )

        sources = self._extract_sources(content)
        for s in sources:
            self.conn.execute(
                "INSERT INTO sources (report_id, url, source_name, trust_rating, title) VALUES (?, ?, ?, ?, ?)",
                (report_id, s["url"], s["source_name"], s["trust"], s["title"])
            )

        self.conn.execute(
            "INSERT INTO reports_fts (rowid, title, content, date, slug, category) VALUES (?, ?, ?, ?, ?, ?)",
            (report_id, title, content, date, slug, category)
        )

        self.conn.commit()
        return True

    def index_reports(self, reports_dir=None):
        rdir = Path(reports_dir) if reports_dir else REPORTS_DIR
        count = 0
        for f in sorted(rdir.glob("*.md")):
            if self.index_file(f):
                count += 1
        self._build_connections()
        return count

    def _build_connections(self):
        self.conn.execute("DELETE FROM connections")
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
        rows = self.conn.execute(
            "SELECT rowid, highlight(reports_fts, 1, '<mark>', '</mark>') as snippet, date, slug, category FROM reports_fts WHERE content MATCH ? ORDER BY rank LIMIT ?",
            (query, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    def find_connections(self, entity_name, days=30):
        entity = self.conn.execute("SELECT id FROM entities WHERE name=?", (entity_name.lower(),)).fetchone()
        if not entity:
            return []
        rows = self.conn.execute("""
            SELECT r.date, r.slug, r.title, r.category, re.mention_count, re.context
            FROM report_entities re
            JOIN reports r ON r.id = re.report_id
            WHERE re.entity_id = ?
            ORDER BY r.date DESC LIMIT 100
        """, (entity["id"],)).fetchall()
        return [dict(r) for r in rows]

    def entity_timeline(self, entity_name):
        return self.find_connections(entity_name, days=365)

    def get_report(self, date, slug):
        row = self.conn.execute("SELECT * FROM reports WHERE date=? AND slug=?", (date, slug)).fetchone()
        return dict(row) if row else None

    def get_dates(self):
        rows = self.conn.execute("SELECT DISTINCT date FROM reports ORDER BY date DESC").fetchall()
        return [r["date"] for r in rows]

    def get_reports_for_date(self, date):
        rows = self.conn.execute(
            "SELECT id, date, slug, category, title, word_count FROM reports WHERE date=? ORDER BY category, slug",
            (date,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_related(self, report_id, limit=10):
        rows = self.conn.execute("""
            SELECT DISTINCT r.date, r.slug, r.title, r.category, e.name as shared_entity, c.strength
            FROM connections c
            JOIN reports r ON (r.id = c.report_id_b AND c.report_id_a = ?) OR (r.id = c.report_id_a AND c.report_id_b = ?)
            JOIN entities e ON e.id = c.entity_id
            WHERE r.id != ?
            ORDER BY c.strength DESC, r.date DESC LIMIT ?
        """, (report_id, report_id, report_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_top_entities(self, date=None, limit=20):
        if date:
            rows = self.conn.execute("""
                SELECT e.name, e.type, e.lat, e.lng, SUM(re.mention_count) as total_mentions
                FROM report_entities re JOIN entities e ON e.id = re.entity_id
                JOIN reports r ON r.id = re.report_id WHERE r.date = ?
                GROUP BY e.id ORDER BY total_mentions DESC LIMIT ?
            """, (date, limit)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT e.name, e.type, e.lat, e.lng, SUM(re.mention_count) as total_mentions
                FROM report_entities re JOIN entities e ON e.id = re.entity_id
                GROUP BY e.id ORDER BY total_mentions DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_source_stats(self, date=None):
        if date:
            rows = self.conn.execute("""
                SELECT source_name, trust_rating, COUNT(*) as count
                FROM sources s JOIN reports r ON r.id = s.report_id WHERE r.date = ?
                GROUP BY source_name, trust_rating ORDER BY count DESC
            """, (date,)).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT source_name, trust_rating, COUNT(*) as count
                FROM sources GROUP BY source_name, trust_rating ORDER BY count DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def stats(self):
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
