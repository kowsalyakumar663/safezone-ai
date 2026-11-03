# SafeZone AI — Disaster Rescue Intelligence

This project reuses your `index.html` dashboard and adds a Python Flask backend with SQLite.

## Features
- Dashboard risk counts and overall score
- Interactive Leaflet map with risk markers
- Risk search/filter APIs
- Weighted demo risk-score calculation
- Relocation site inventory and capacity assignments
- Emergency alert records stored in SQLite
- Analytics and health endpoints

## Requirements
- Python 3.10 or newer
- Internet connection for the Leaflet/OpenStreetMap map tiles and CDN library on first use

## Run on Windows
1. Extract the ZIP file.
2. Open Command Prompt in the extracted `safezone_ai_flask` folder.
3. Create a virtual environment (recommended):
   `python -m venv .venv`
4. Activate it:
   `.venv\Scripts\activate`
5. Install dependencies:
   `pip install -r requirements.txt`
6. Start the app:
   `python app.py`
7. Open `http://127.0.0.1:5000` in your browser.

## Run on macOS/Linux
1. Open a terminal in this folder.
2. Create and activate a virtual environment:
   `python3 -m venv .venv`
   `source .venv/bin/activate`
3. Install and start:
   `pip install -r requirements.txt`
   `python app.py`
4. Open `http://127.0.0.1:5000`.

## Useful API endpoints
- `GET /health`
- `GET /api/meta`
- `GET /api/dashboard`
- `GET /api/risks`
- `GET /api/risks?level=critical`
- `GET /api/search?q=India`
- `GET /api/relocation-sites`
- `GET /api/relocation-assignments`
- `GET /api/alerts`
- `GET /api/analytics`
- `POST /api/risks`
- `POST /api/relocation-sites`
- `POST /api/relocation-assignments`
- `POST /api/alerts`
- `POST /api/calculate-risk`

## Important safety note
This is a student project prototype. Seeded risk scores, locations, population counts, and alerts are illustrative demo data, not live official emergency information. The risk calculation is a transparent weighted heuristic, not a validated forecasting model. Do not use this prototype for real emergency decisions without verified official data sources and appropriate review.

## Project structure
- `app.py` — Python Flask server, database schema, validation, and API routes
- `templates/index.html` — your existing dashboard plus backend integration
- `requirements.txt` — Python dependency
- `safezone.db` — generated automatically the first time the app runs
