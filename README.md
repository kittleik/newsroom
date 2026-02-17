# Newsroom — Intelligence Dashboard

A Flask-based daily intelligence report dashboard with interactive maps, narrative analysis, and full-text search.

## Features

- **10+ regional & tech reports** generated daily by AI agents
- **Debate reports** with steelman analysis and prediction market data
- **Interactive Leaflet map** with country-level markers and trust indicators
- **Full-text search** (SQLite FTS5) across all reports
- **Editorial transparency** — companion log files track every source visited
- **Dark Bloomberg-terminal theme** with collapsible sections, keyboard navigation

## Quick Start

```bash
pip install -r requirements.txt

# Configure (optional — defaults work for local dev)
export NEWSROOM_REPORTS_DIR=/path/to/reports    # default: ./data/reports/
export NEWSROOM_DB_PATH=./newsroom.db           # default
export NEWSROOM_PORT=3118                       # default

python app.py
```

Open `http://localhost:3118`

## Report Format

Reports are markdown files named `YYYY-MM-DD-slug.md` in the reports directory:

```
2026-02-17-world.md        # World overview
2026-02-17-europe.md       # Regional: Europe
2026-02-17-tech-ai.md      # Tech: AI
2026-02-17-debate-xyz.md   # Debate analysis
2026-02-17-world-log.md    # Editorial log (companion)
```

### Trust Badges

Use in reports for source trust indicators:
- `🟢 HIGH` — verified, mainstream sources
- `🟡 MED` — credible but less established
- `🔴 STATE` — state-controlled media (flagged with warning)

## Architecture

```
app.py          # Flask routes and rendering
db.py           # SQLite + FTS5 indexing and search
constants.py    # Shared geo data, categories, slugs
config.py       # Environment-based configuration
static/
  style.css     # All styles
  app.js        # All client-side JS
templates/
  index.html    # Main dashboard (thin shell)
  log.html      # Editorial log viewer
```

## Keyboard Shortcuts

- `←` / `→` — navigate between reports
- `/` — focus search

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/dates` | List available report dates |
| `GET /api/reports/<date>` | Get all reports + map markers for a date |
| `GET /api/search?q=<query>` | Full-text search across all reports |
| `GET /api/debate-data/<date>` | Debate visualization data |
| `GET /api/coords` | Country coordinate data for map |
| `GET /api/map-data` | Aggregated map marker data |

## License

Private project.
