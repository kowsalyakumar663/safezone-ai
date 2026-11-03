"""
SafeZone AI — Disaster Rescue Intelligence
Flask backend with SQLite storage and a JSON API.

IMPORTANT:
- Included risk data is illustrative demo data, not a live official warning feed.
- Do not use this prototype for real emergency decisions without verified data sources.
- Run locally with: python app.py
"""

from __future__ import annotations

import os
import sqlite3
import json
import math
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from flask import Flask, jsonify, render_template, request, g

APP_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("SAFEZONE_DATABASE", APP_DIR / "safezone.db"))
PORT = int(os.environ.get("PORT", "5000"))
HOST = os.environ.get("HOST", "127.0.0.1")
MAX_REQUEST_BYTES = 64 * 1024

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST_BYTES
app.config["JSON_SORT_KEYS"] = False
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("safezone")

RISK_LEVELS = ("critical", "high", "moderate", "low")
LEVEL_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
LEVEL_COLORS = {
    "critical": "#d33b35",
    "high": "#e48b00",
    "moderate": "#cba300",
    "low": "#299447",
}

# Illustrative seed records. Replace these with verified official data for real use.
DEFAULT_RISKS = [
    (23, 78, "India Risk Cluster", 92, 12400, "Flood + Landslide", "Immediate Relocation", "critical"),
    (35, 104, "East Asia Risk Area", 88, 8200, "Earthquake", "Immediate Attention", "critical"),
    (15, -86, "Central America Flood Zone", 84, 5300, "Flood + Storm", "Prepare for Relocation", "high"),
    (30, 47, "Middle East Heat Risk", 81, 4100, "Extreme Heat", "Emergency Monitoring", "high"),
    (-6, 106, "Southeast Asia Flood Zone", 78, 6900, "Flood", "Prepare for Relocation", "high"),
    (-23, -46, "South America Urban Risk", 74, 3800, "Heavy Rainfall", "Monitor Closely", "moderate"),
    (51, 0, "Western Europe", 56, 2100, "Storm", "Monitor", "moderate"),
    (64, 25, "Northern Europe Safe Area", 31, 700, "Low Exposure", "Safe Zone", "low"),
    (40, -100, "North America", 48, 1600, "Wildfire", "Monitor", "moderate"),
    (-33, 151, "Australia East", 39, 900, "Storm", "Monitor", "low"),
    (-1, 37, "East Africa", 72, 2900, "Drought + Flood", "Prepare", "high"),
    (19, -99, "Mexico Central", 67, 2300, "Earthquake", "Monitor", "moderate"),
    (28, 77, "Delhi Region", 86, 7600, "Flood + Heat", "Immediate Attention", "critical"),
    (10, 76, "South India", 63, 1900, "Heavy Rainfall", "Monitor", "moderate"),
    (1, 103, "Singapore Safe Zone", 24, 500, "Low Exposure", "Safe Zone", "low"),
    (55, 37, "Eastern Europe", 43, 1200, "Storm", "Monitor", "low"),
    (-34, 18, "Southern Africa", 37, 800, "Low Exposure", "Safe Zone", "low"),
    (35, 139, "Japan Risk Area", 82, 4400, "Earthquake + Tsunami", "Immediate Attention", "high"),
]

DEFAULT_SITES = [
    ("Government Higher Secondary School", 92, 2500, 1980, 2.4, 1.2, "Good", "Low", "Good", "Available"),
    ("Community Relief Centre", 86, 1800, 1320, 3.1, 1.8, "Good", "Low", "Available", "Available"),
    ("District Sports Hall", 81, 1200, 900, 4.0, 2.0, "Fair", "Low", "Available", "Available"),
]


def utc_now() -> str:
    """Return an ISO timestamp in UTC for consistent database records."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db() -> sqlite3.Connection:
    """Open a SQLite connection with row objects and foreign-key checks enabled."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def get_db() -> sqlite3.Connection:
    """Get the request-scoped database connection, creating it when needed."""
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(exception: Optional[BaseException] = None) -> None:
    """Close the database connection at the end of each Flask request."""
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def create_schema() -> None:
    """Create all tables used by the prototype."""
    db = connect_db()
    try:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS risks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lat REAL NOT NULL CHECK(lat >= -90 AND lat <= 90),
                lng REAL NOT NULL CHECK(lng >= -180 AND lng <= 180),
                name TEXT NOT NULL UNIQUE,
                score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
                population INTEGER NOT NULL DEFAULT 0 CHECK(population >= 0),
                hazard TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('critical','high','moderate','low')),
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS relocation_sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                safezone_score INTEGER NOT NULL CHECK(safezone_score BETWEEN 0 AND 100),
                capacity INTEGER NOT NULL CHECK(capacity >= 0),
                available INTEGER NOT NULL CHECK(available >= 0),
                distance_km REAL NOT NULL CHECK(distance_km >= 0),
                healthcare_km REAL NOT NULL CHECK(healthcare_km >= 0),
                road_condition TEXT NOT NULL,
                hazard_level TEXT NOT NULL,
                water_status TEXT NOT NULL,
                electricity_status TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                level TEXT NOT NULL CHECK(level IN ('critical','high','moderate','low')),
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','acknowledged','closed')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS relocation_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site_id INTEGER NOT NULL REFERENCES relocation_sites(id),
                people INTEGER NOT NULL CHECK(people > 0),
                status TEXT NOT NULL DEFAULT 'assigned',
                created_at TEXT NOT NULL
            );
            """
        )
        db.commit()
    finally:
        db.close()


def seed_database() -> None:
    """Insert sample risk, relocation, and alert data once on first run."""
    db = connect_db()
    try:
        risk_count = db.execute("SELECT COUNT(*) FROM risks").fetchone()[0]
        if risk_count == 0:
            for lat, lng, name, score, population, hazard, action, level in DEFAULT_RISKS:
                db.execute(
                    """INSERT INTO risks
                    (lat,lng,name,score,population,hazard,recommended_action,level,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (lat, lng, name, score, population, hazard, action, level, utc_now()),
                )

        site_count = db.execute("SELECT COUNT(*) FROM relocation_sites").fetchone()[0]
        if site_count == 0:
            for site in DEFAULT_SITES:
                db.execute(
                    """INSERT INTO relocation_sites
                    (name,safezone_score,capacity,available,distance_km,healthcare_km,
                     road_condition,hazard_level,water_status,electricity_status,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (*site, utc_now()),
                )

        alert_count = db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        if alert_count == 0:
            examples = [
                ("Critical Zone Alert", "critical", "Illustrative flood and landslide risk. Verify with local authorities."),
                ("High Risk Area", "high", "Heavy rainfall monitoring required. Demo alert, not an official warning."),
                ("Moderate Weather Watch", "moderate", "Continue monitoring verified local weather information."),
            ]
            for title, level, message in examples:
                db.execute(
                    """INSERT INTO alerts(title,level,message,status,created_at,updated_at)
                    VALUES(?,?,?,'open',?,?)""",
                    (title, level, message, utc_now(), utc_now()),
                )
        db.commit()
    finally:
        db.close()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row to a regular dictionary."""
    return {key: row[key] for key in row.keys()}


def parse_json_body() -> dict[str, Any]:
    """Parse JSON body safely and reject non-object request payloads."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return data


def clean_text(value: Any, field_name: str, max_length: int = 240) -> str:
    """Validate and normalize a required text field."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text.")
    value = " ".join(value.strip().split())
    if not value:
        raise ValueError(f"{field_name} is required.")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer.")
    return value


def bounded_int(value: Any, field_name: str, minimum: int, maximum: int) -> int:
    """Validate an integer value within inclusive bounds."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer.")
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return parsed


def bounded_float(value: Any, field_name: str, minimum: float, maximum: float) -> float:
    """Validate a numeric value within inclusive bounds."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number.")
    if not math.isfinite(parsed) or parsed < minimum or parsed > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}.")
    return parsed


def score_to_level(score: int) -> str:
    """Map a numerical risk score to the application's risk category."""
    if score >= 85:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 45:
        return "moderate"
    return "low"


def level_to_action(level: str, hazard: str) -> str:
    """Return a generic demo recommendation based on the risk category."""
    actions = {
        "critical": "Immediate Attention — verify with emergency authorities",
        "high": "Prepare for Relocation — follow official guidance",
        "moderate": "Monitor Conditions — check verified updates",
        "low": "Routine Monitoring — maintain preparedness",
    }
    return actions[level]


def calculate_risk_score(
    hazard_intensity: float,
    exposed_population: float,
    vulnerability: float,
    infrastructure: float,
    evacuation_access: float,
) -> int:
    """
    Calculate a simple transparent demo score from five inputs.

    Each input is expected on a 0..100 scale. The weights sum to 100%.
    This is an educational heuristic, not a validated scientific model.
    """
    values = [
        hazard_intensity,
        exposed_population,
        vulnerability,
        infrastructure,
        evacuation_access,
    ]
    if any(not math.isfinite(float(value)) or value < 0 or value > 100 for value in values):
        raise ValueError("All risk factors must be between 0 and 100.")
    weighted = (
        hazard_intensity * 0.35
        + exposed_population * 0.25
        + vulnerability * 0.20
        + infrastructure * 0.10
        + evacuation_access * 0.10
    )
    return max(0, min(100, round(weighted)))


def risk_summary(rows: list[sqlite3.Row]) -> dict[str, Any]:
    """Summarize risk rows into counts and population totals."""
    counts = {level: 0 for level in RISK_LEVELS}
    total_population = 0
    score_total = 0
    for row in rows:
        level = row["level"]
        if level in counts:
            counts[level] += 1
        total_population += int(row["population"])
        score_total += int(row["score"])
    overall = round(score_total / len(rows)) if rows else 0
    return {
        "overall_risk": overall,
        "zone_counts": counts,
        "monitored_locations": len(rows),
        "population_in_monitored_zones": total_population,
    }


def get_risks(
    level: Optional[str] = None,
    query: Optional[str] = None,
    minimum_score: Optional[int] = None,
) -> list[sqlite3.Row]:
    """Query risks with optional category, name/hazard search, and score filter."""
    db = get_db()
    sql = "SELECT * FROM risks WHERE 1=1"
    params: list[Any] = []
    if level:
        if level not in RISK_LEVELS:
            raise ValueError("level must be critical, high, moderate, or low.")
        sql += " AND level = ?"
        params.append(level)
    if query:
        sql += " AND (LOWER(name) LIKE ? OR LOWER(hazard) LIKE ?)"
        pattern = f"%{query.lower()}%"
        params.extend([pattern, pattern])
    if minimum_score is not None:
        sql += " AND score >= ?"
        params.append(minimum_score)
    sql += " ORDER BY score DESC, name ASC"
    return db.execute(sql, params).fetchall()


def get_risk_by_id(risk_id: int) -> Optional[sqlite3.Row]:
    """Fetch one risk record by its primary key."""
    return get_db().execute("SELECT * FROM risks WHERE id=?", (risk_id,)).fetchone()


def get_site_by_id(site_id: int) -> Optional[sqlite3.Row]:
    """Fetch one relocation site by its primary key."""
    return get_db().execute("SELECT * FROM relocation_sites WHERE id=?", (site_id,)).fetchone()


def get_alert_by_id(alert_id: int) -> Optional[sqlite3.Row]:
    """Fetch one alert by its primary key."""
    return get_db().execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()


def create_alert_record(title: str, level: str, message: str) -> int:
    """Create an alert record and return its database ID."""
    if level not in RISK_LEVELS:
        raise ValueError("level must be critical, high, moderate, or low.")
    now = utc_now()
    cursor = get_db().execute(
        """INSERT INTO alerts(title,level,message,status,created_at,updated_at)
        VALUES(?,?,?,'open',?,?)""",
        (title, level, message, now, now),
    )
    get_db().commit()
    return int(cursor.lastrowid)


def set_alert_status(alert_id: int, status: str) -> bool:
    """Update an alert status; return False when the alert does not exist."""
    if status not in ("open", "acknowledged", "closed"):
        raise ValueError("status must be open, acknowledged, or closed.")
    cursor = get_db().execute(
        "UPDATE alerts SET status=?, updated_at=? WHERE id=?",
        (status, utc_now(), alert_id),
    )
    get_db().commit()
    return cursor.rowcount > 0


def assign_people_to_site(site_id: int, people: int) -> dict[str, Any]:
    """Assign a demo number of people to a site if enough capacity is available."""
    if people < 1:
        raise ValueError("people must be at least 1.")
    db = get_db()
    site = get_site_by_id(site_id)
    if site is None:
        raise LookupError("Relocation site not found.")
    if int(site["available"]) < people:
        raise ValueError(f"Only {site['available']} places are currently available.")
    db.execute(
        "INSERT INTO relocation_assignments(site_id,people,status,created_at) VALUES(?,?,'assigned',?)",
        (site_id, people, utc_now()),
    )
    db.execute(
        "UPDATE relocation_sites SET available=available-?, updated_at=? WHERE id=?",
        (people, utc_now(), site_id),
    )
    db.commit()
    return {"site": site["name"], "people": people, "remaining": int(site["available"]) - people}


def error_response(message: str, status_code: int = 400):
    """Create a consistent JSON error response."""
    return jsonify({"ok": False, "error": message}), status_code


@app.errorhandler(404)
def not_found(_error):
    """Return JSON for unknown API paths and a simple response for other paths."""
    if request.path.startswith("/api/"):
        return error_response("API endpoint not found.", 404)
    return "Page not found", 404


@app.errorhandler(413)
def request_too_large(_error):
    """Return a helpful response when a request exceeds the configured size."""
    return error_response("Request body is too large.", 413)


@app.errorhandler(500)
def server_error(error):
    """Log unexpected server errors without exposing internal details."""
    logger.exception("Unhandled server error: %s", error)
    return error_response("Unexpected server error. Check the server log.", 500)


@app.get("/")
def home():
    """Render the dashboard."""
    return render_template("index.html")


@app.get("/health")
def health():
    """Simple health-check endpoint."""
    return jsonify({
        "ok": True,
        "service": "SafeZone AI Flask backend",
        "time": utc_now(),
        "demo_data": True,
    })


@app.get("/api/dashboard")
def api_dashboard():
    """Return dashboard metrics and risk counts."""
    rows = get_db().execute("SELECT * FROM risks").fetchall()
    summary = risk_summary(rows)
    summary["ok"] = True
    summary["data_mode"] = "illustrative_demo_data"
    return jsonify(summary)


@app.get("/api/risks")
def api_risks():
    """List risks; optional query params: level, q, min_score."""
    try:
        level = request.args.get("level") or None
        query = request.args.get("q", "").strip() or None
        minimum = request.args.get("min_score")
        minimum_score = bounded_int(minimum, "min_score", 0, 100) if minimum is not None else None
        rows = get_risks(level, query, minimum_score)
        return jsonify({"ok": True, "count": len(rows), "items": [row_to_dict(row) for row in rows]})
    except ValueError as exc:
        return error_response(str(exc))


@app.get("/api/risks/<int:risk_id>")
def api_risk_detail(risk_id: int):
    """Return one risk location and its details."""
    row = get_risk_by_id(risk_id)
    if row is None:
        return error_response("Risk location not found.", 404)
    return jsonify({"ok": True, "item": row_to_dict(row)})


@app.post("/api/risks")
def api_create_risk():
    """Create a risk location from validated JSON."""
    try:
        data = parse_json_body()
        name = clean_text(data.get("name"), "name", 120)
        hazard = clean_text(data.get("hazard"), "hazard", 200)
        lat = bounded_float(data.get("lat"), "lat", -90, 90)
        lng = bounded_float(data.get("lng"), "lng", -180, 180)
        score = bounded_int(data.get("score"), "score", 0, 100)
        population = bounded_int(data.get("population", 0), "population", 0, 1000000000)
        level = score_to_level(score)
        action = level_to_action(level, hazard)
        now = utc_now()
        cursor = get_db().execute(
            """INSERT INTO risks(lat,lng,name,score,population,hazard,recommended_action,level,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (lat, lng, name, score, population, hazard, action, level, now),
        )
        get_db().commit()
        row = get_risk_by_id(int(cursor.lastrowid))
        return jsonify({"ok": True, "message": "Risk location created.", "item": row_to_dict(row)}), 201
    except ValueError as exc:
        return error_response(str(exc))
    except sqlite3.IntegrityError:
        return error_response("A risk location with that name already exists.")


@app.put("/api/risks/<int:risk_id>")
def api_update_risk(risk_id: int):
    """Update editable fields on a risk location."""
    try:
        data = parse_json_body()
        existing = get_risk_by_id(risk_id)
        if existing is None:
            return error_response("Risk location not found.", 404)
        name = clean_text(data.get("name", existing["name"]), "name", 120)
        hazard = clean_text(data.get("hazard", existing["hazard"]), "hazard", 200)
        lat = bounded_float(data.get("lat", existing["lat"]), "lat", -90, 90)
        lng = bounded_float(data.get("lng", existing["lng"]), "lng", -180, 180)
        score = bounded_int(data.get("score", existing["score"]), "score", 0, 100)
        population = bounded_int(data.get("population", existing["population"]), "population", 0, 1000000000)
        level = score_to_level(score)
        action = level_to_action(level, hazard)
        get_db().execute(
            """UPDATE risks SET lat=?,lng=?,name=?,score=?,population=?,hazard=?,
            recommended_action=?,level=?,updated_at=? WHERE id=?""",
            (lat, lng, name, score, population, hazard, action, level, utc_now(), risk_id),
        )
        get_db().commit()
        return jsonify({"ok": True, "item": row_to_dict(get_risk_by_id(risk_id))})
    except ValueError as exc:
        return error_response(str(exc))
    except sqlite3.IntegrityError:
        return error_response("A risk location with that name already exists.")


@app.delete("/api/risks/<int:risk_id>")
def api_delete_risk(risk_id: int):
    """Delete a risk location by ID."""
    cursor = get_db().execute("DELETE FROM risks WHERE id=?", (risk_id,))
    get_db().commit()
    if cursor.rowcount == 0:
        return error_response("Risk location not found.", 404)
    return jsonify({"ok": True, "message": "Risk location deleted."})


@app.get("/api/relocation-sites")
def api_relocation_sites():
    """List relocation sites ordered by SafeZone score."""
    rows = get_db().execute(
        "SELECT * FROM relocation_sites ORDER BY safezone_score DESC, name"
    ).fetchall()
    return jsonify({"ok": True, "count": len(rows), "items": [row_to_dict(row) for row in rows]})


@app.get("/api/relocation-sites/<int:site_id>")
def api_relocation_site_detail(site_id: int):
    """Get the details of one relocation site."""
    row = get_site_by_id(site_id)
    if row is None:
        return error_response("Relocation site not found.", 404)
    return jsonify({"ok": True, "item": row_to_dict(row)})


@app.post("/api/relocation-sites")
def api_create_relocation_site():
    """Add a new relocation site."""
    try:
        data = parse_json_body()
        name = clean_text(data.get("name"), "name", 150)
        score = bounded_int(data.get("safezone_score"), "safezone_score", 0, 100)
        capacity = bounded_int(data.get("capacity"), "capacity", 0, 10000000)
        available = bounded_int(data.get("available", capacity), "available", 0, capacity)
        distance = bounded_float(data.get("distance_km", 0), "distance_km", 0, 100000)
        healthcare = bounded_float(data.get("healthcare_km", 0), "healthcare_km", 0, 100000)
        road = clean_text(data.get("road_condition", "Unknown"), "road_condition", 60)
        hazard = clean_text(data.get("hazard_level", "Unknown"), "hazard_level", 60)
        water = clean_text(data.get("water_status", "Unknown"), "water_status", 60)
        electricity = clean_text(data.get("electricity_status", "Unknown"), "electricity_status", 60)
        cursor = get_db().execute(
            """INSERT INTO relocation_sites
            (name,safezone_score,capacity,available,distance_km,healthcare_km,road_condition,
             hazard_level,water_status,electricity_status,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (name, score, capacity, available, distance, healthcare, road, hazard, water, electricity, utc_now()),
        )
        get_db().commit()
        return jsonify({"ok": True, "item": row_to_dict(get_site_by_id(int(cursor.lastrowid)))}), 201
    except ValueError as exc:
        return error_response(str(exc))
    except sqlite3.IntegrityError:
        return error_response("A relocation site with that name already exists.")


@app.post("/api/relocation-assignments")
def api_assign_relocation():
    """Assign a number of people to a relocation site."""
    try:
        data = parse_json_body()
        site_id = bounded_int(data.get("site_id"), "site_id", 1, 2147483647)
        people = bounded_int(data.get("people", 1), "people", 1, 1000000)
        result = assign_people_to_site(site_id, people)
        return jsonify({
            "ok": True,
            "message": f"Assigned {people} person(s) to {result['site']}. Remaining capacity: {result['remaining']}.",
            "assignment": result,
        }), 201
    except ValueError as exc:
        return error_response(str(exc))
    except LookupError as exc:
        return error_response(str(exc), 404)


@app.get("/api/relocation-assignments")
def api_list_assignments():
    """List recent relocation assignments."""
    rows = get_db().execute(
        """SELECT a.id,a.site_id,s.name AS site_name,a.people,a.status,a.created_at
        FROM relocation_assignments a JOIN relocation_sites s ON s.id=a.site_id
        ORDER BY a.id DESC"""
    ).fetchall()
    return jsonify({"ok": True, "items": [row_to_dict(row) for row in rows]})


@app.get("/api/alerts")
def api_alerts():
    """List alerts, optionally filtered by status or level."""
    status = request.args.get("status")
    level = request.args.get("level")
    if status and status not in ("open", "acknowledged", "closed"):
        return error_response("status must be open, acknowledged, or closed.")
    if level and level not in RISK_LEVELS:
        return error_response("level must be critical, high, moderate, or low.")
    sql = "SELECT * FROM alerts WHERE 1=1"
    params: list[Any] = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if level:
        sql += " AND level=?"
        params.append(level)
    sql += " ORDER BY CASE level WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'moderate' THEN 2 ELSE 3 END, id DESC"
    rows = get_db().execute(sql, params).fetchall()
    return jsonify({"ok": True, "count": len(rows), "items": [row_to_dict(row) for row in rows]})


@app.post("/api/alerts")
def api_create_alert():
    """Create an alert record."""
    try:
        data = parse_json_body()
        title = clean_text(data.get("title"), "title", 160)
        message = clean_text(data.get("message"), "message", 1000)
        level = clean_text(data.get("level", "moderate"), "level", 20).lower()
        alert_id = create_alert_record(title, level, message)
        row = get_alert_by_id(alert_id)
        return jsonify({"ok": True, "message": "Alert record created in the local database.", "item": row_to_dict(row)}), 201
    except ValueError as exc:
        return error_response(str(exc))


@app.patch("/api/alerts/<int:alert_id>")
def api_update_alert(alert_id: int):
    """Change an alert status to open, acknowledged, or closed."""
    try:
        data = parse_json_body()
        status = clean_text(data.get("status"), "status", 20).lower()
        if not set_alert_status(alert_id, status):
            return error_response("Alert not found.", 404)
        return jsonify({"ok": True, "item": row_to_dict(get_alert_by_id(alert_id))})
    except ValueError as exc:
        return error_response(str(exc))


@app.get("/api/analytics")
def api_analytics():
    """Return category, average-score, and population summaries."""
    db = get_db()
    categories = db.execute(
        "SELECT level,COUNT(*) AS count,ROUND(AVG(score),1) AS average_score,SUM(population) AS population "
        "FROM risks GROUP BY level"
    ).fetchall()
    top = db.execute(
        "SELECT id,name,score,population,hazard,level FROM risks ORDER BY score DESC LIMIT 5"
    ).fetchall()
    return jsonify({
        "ok": True,
        "by_level": [row_to_dict(row) for row in categories],
        "top_risk_locations": [row_to_dict(row) for row in top],
        "generated_at": utc_now(),
    })


@app.get("/api/search")
def api_search():
    """Search risk locations by name or hazard."""
    query = request.args.get("q", "").strip()
    if not query:
        return error_response("Provide a search term using ?q=...")
    if len(query) > 120:
        return error_response("Search term must be 120 characters or fewer.")
    rows = get_risks(query=query)
    return jsonify({"ok": True, "query": query, "count": len(rows), "items": [row_to_dict(row) for row in rows]})


@app.post("/api/calculate-risk")
def api_calculate_risk():
    """Calculate a weighted illustrative risk score from five 0..100 factors."""
    try:
        data = parse_json_body()
        names = ("hazard_intensity", "exposed_population", "vulnerability", "infrastructure", "evacuation_access")
        values = [bounded_float(data.get(name), name, 0, 100) for name in names]
        score = calculate_risk_score(*values)
        level = score_to_level(score)
        return jsonify({
            "ok": True,
            "score": score,
            "level": level,
            "recommended_action": level_to_action(level, "General hazard"),
            "weights": {
                "hazard_intensity": 0.35,
                "exposed_population": 0.25,
                "vulnerability": 0.20,
                "infrastructure": 0.10,
                "evacuation_access": 0.10,
            },
            "note": "Illustrative educational calculation, not an official warning.",
        })
    except ValueError as exc:
        return error_response(str(exc))


@app.get("/api/meta")
def api_meta():
    """Expose basic project metadata for the frontend and viva explanation."""
    return jsonify({
        "ok": True,
        "project": "SafeZone AI — Disaster Rescue Intelligence",
        "backend": "Python Flask",
        "database": "SQLite",
        "mapping_library": "Leaflet.js",
        "map_tiles": "OpenStreetMap",
        "risk_data": "Illustrative demo data",
        "features": [
            "Dashboard metrics",
            "Risk location search and filtering",
            "Weighted risk-score calculation",
            "Relocation-site inventory",
            "Relocation capacity assignments",
            "Emergency alert records",
            "Analytics summaries",
        ],
    })


def initialize_app() -> None:
    """Initialize database schema and sample data before serving requests."""
    create_schema()
    seed_database()


# Initialize on import so Flask development server and test clients are ready.
initialize_app()


if __name__ == "__main__":
    logger.info("Starting SafeZone AI at http://%s:%s", HOST, PORT)
    logger.warning("Demo data is illustrative and is not an official emergency alert feed.")
    app.run(host=HOST, port=PORT, debug=os.environ.get("FLASK_DEBUG") == "1")
