from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3, os, json
from datetime import datetime

# ═══════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════
API_KEY  = "MonBotKyste_2024_aBc9xZ"   # même valeur dans bot.py
DB_PATH  = "kyste.db"
PORT     = int(os.environ.get("PORT", 5000))

app = Flask(__name__)
CORS(app)

# ═══════════════════════════════════════════
#  DB INIT
# ═══════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id   TEXT PRIMARY KEY,
                guild_id     TEXT NOT NULL,
                user_id      TEXT NOT NULL,
                number       INTEGER,
                status       TEXT DEFAULT 'open',
                priority     TEXT DEFAULT 'low',
                category     TEXT,
                claimed_by   TEXT,
                closed_by    TEXT,
                panel_id     TEXT,
                opened_at    TEXT,
                closed_at    TEXT,
                last_activity TEXT
            );
            CREATE TABLE IF NOT EXISTS panels (
                panel_id         TEXT PRIMARY KEY,
                guild_id         TEXT NOT NULL,
                name             TEXT,
                emoji            TEXT DEFAULT '🎫',
                color            TEXT DEFAULT '0xDC143C',
                ticket_limit     INTEGER DEFAULT 1,
                inactivity_hours INTEGER DEFAULT 0,
                welcome_message  TEXT,
                created_at       TEXT
            );
            CREATE TABLE IF NOT EXISTS stats (
                guild_id       TEXT NOT NULL,
                user_id        TEXT NOT NULL,
                claimed        INTEGER DEFAULT 0,
                closed         INTEGER DEFAULT 0,
                ratings_sum    INTEGER DEFAULT 0,
                ratings_count  INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS global_stats (
                guild_id      TEXT PRIMARY KEY,
                total_opened  INTEGER DEFAULT 0,
                total_closed  INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS config (
                guild_id      TEXT PRIMARY KEY,
                antispam      TEXT DEFAULT '{}',
                verify        TEXT DEFAULT '{}',
                logs          TEXT DEFAULT '{}'
            );
        """)
    print("✅ DB initialisée")

# ═══════════════════════════════════════════
#  AUTH MIDDLEWARE
# ═══════════════════════════════════════════
def auth():
    return request.headers.get("X-Api-Key") == API_KEY

# ═══════════════════════════════════════════
#  ROUTES BOT → API (écriture, protégées)
# ═══════════════════════════════════════════

@app.route("/bot/ticket/open", methods=["POST"])
def ticket_open():
    if not auth(): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO tickets
            (channel_id, guild_id, user_id, number, status, priority, category, panel_id, opened_at, last_activity)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            data["channel_id"], data["guild_id"], data["user_id"],
            data["number"], "open", "low",
            data.get("category"), data.get("panel_id"),
            data.get("opened_at", datetime.utcnow().isoformat()),
            datetime.utcnow().isoformat()
        ))
        db.execute("""
            INSERT INTO global_stats (guild_id, total_opened, total_closed)
            VALUES (?, 1, 0)
            ON CONFLICT(guild_id) DO UPDATE SET total_opened = total_opened + 1
        """, (data["guild_id"],))
    return jsonify({"ok": True})

@app.route("/bot/ticket/close", methods=["POST"])
def ticket_close():
    if not auth(): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    with get_db() as db:
        db.execute("""
            UPDATE tickets SET status='closed', closed_by=?, closed_at=?
            WHERE channel_id=?
        """, (data.get("closed_by"), datetime.utcnow().isoformat(), data["channel_id"]))
        db.execute("""
            INSERT INTO global_stats (guild_id, total_opened, total_closed)
            VALUES (?, 0, 1)
            ON CONFLICT(guild_id) DO UPDATE SET total_closed = total_closed + 1
        """, (data["guild_id"],))
        staff_id = data.get("staff_id")
        if staff_id:
            db.execute("""
                INSERT INTO stats (guild_id, user_id, closed)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET closed = closed + 1
            """, (data["guild_id"], staff_id))
        rating = data.get("rating")
        if rating and staff_id:
            db.execute("""
                UPDATE stats SET ratings_sum = ratings_sum + ?, ratings_count = ratings_count + 1
                WHERE guild_id=? AND user_id=?
            """, (rating, data["guild_id"], staff_id))
    return jsonify({"ok": True})

@app.route("/bot/ticket/claim", methods=["POST"])
def ticket_claim():
    if not auth(): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    with get_db() as db:
        db.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?",
                   (data["staff_id"], data["channel_id"]))
        db.execute("""
            INSERT INTO stats (guild_id, user_id, claimed)
            VALUES (?, ?, 1)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET claimed = claimed + 1
        """, (data["guild_id"], data["staff_id"]))
    return jsonify({"ok": True})

@app.route("/bot/ticket/activity", methods=["POST"])
def ticket_activity():
    if not auth(): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    with get_db() as db:
        db.execute("UPDATE tickets SET last_activity=? WHERE channel_id=?",
                   (datetime.utcnow().isoformat(), data["channel_id"]))
    return jsonify({"ok": True})

@app.route("/bot/ticket/priority", methods=["POST"])
def ticket_priority():
    if not auth(): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    with get_db() as db:
        db.execute("UPDATE tickets SET priority=? WHERE channel_id=?",
                   (data["priority"], data["channel_id"]))
    return jsonify({"ok": True})

@app.route("/bot/panel/sync", methods=["POST"])
def panel_sync():
    if not auth(): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO panels
            (panel_id, guild_id, name, emoji, color, ticket_limit, inactivity_hours, welcome_message, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            data["panel_id"], data["guild_id"], data["name"],
            data.get("emoji","🎫"), data.get("color","0xDC143C"),
            data.get("ticket_limit",1), data.get("inactivity_hours",0),
            data.get("welcome_message"), data.get("created_at", datetime.utcnow().isoformat())
        ))
    return jsonify({"ok": True})

@app.route("/bot/config/sync", methods=["POST"])
def config_sync():
    if not auth(): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    gid = data["guild_id"]
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO config (guild_id, antispam, verify, logs)
            VALUES (?,?,?,?)
        """, (
            gid,
            json.dumps(data.get("antispam", {})),
            json.dumps(data.get("verify", {})),
            json.dumps(data.get("logs", {})),
        ))
    return jsonify({"ok": True})

# ═══════════════════════════════════════════
#  ROUTES DASHBOARD (lecture publique)
# ═══════════════════════════════════════════

@app.route("/api/stats/<guild_id>")
def api_stats(guild_id):
    with get_db() as db:
        open_count = db.execute(
            "SELECT COUNT(*) as c FROM tickets WHERE guild_id=? AND status='open'", (guild_id,)
        ).fetchone()["c"]
        gs = db.execute(
            "SELECT * FROM global_stats WHERE guild_id=?", (guild_id,)
        ).fetchone()
        panels_count = db.execute(
            "SELECT COUNT(*) as c FROM panels WHERE guild_id=?", (guild_id,)
        ).fetchone()["c"]
        staff_rows = db.execute(
            "SELECT * FROM stats WHERE guild_id=?", (guild_id,)
        ).fetchall()
        cfg = db.execute(
            "SELECT * FROM config WHERE guild_id=?", (guild_id,)
        ).fetchone()

    leaderboard = {}
    for row in staff_rows:
        leaderboard[row["user_id"]] = {
            "claimed":       row["claimed"],
            "closed":        row["closed"],
            "ratings_sum":   row["ratings_sum"],
            "ratings_count": row["ratings_count"],
        }

    antispam = json.loads(cfg["antispam"]) if cfg else {}
    verify   = json.loads(cfg["verify"])   if cfg else {}

    return jsonify({
        "open_tickets":      open_count,
        "total_opened":      gs["total_opened"]  if gs else 0,
        "total_closed":      gs["total_closed"]  if gs else 0,
        "panels":            panels_count,
        "staff_leaderboard": leaderboard,
        "antispam_enabled":  antispam.get("enabled", False),
        "verify_enabled":    verify.get("enabled", False),
    })

@app.route("/api/tickets/<guild_id>")
def api_tickets(guild_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM tickets WHERE guild_id=? ORDER BY number DESC", (guild_id,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/panels/<guild_id>")
def api_panels(guild_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM panels WHERE guild_id=?", (guild_id,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/antispam/<guild_id>")
def api_antispam(guild_id):
    with get_db() as db:
        cfg = db.execute("SELECT antispam FROM config WHERE guild_id=?", (guild_id,)).fetchone()
    return jsonify(json.loads(cfg["antispam"]) if cfg else {})

@app.route("/api/verify/<guild_id>")
def api_verify(guild_id):
    with get_db() as db:
        cfg = db.execute("SELECT verify FROM config WHERE guild_id=?", (guild_id,)).fetchone()
    return jsonify(json.loads(cfg["verify"]) if cfg else {})

@app.route("/api/logs/<guild_id>")
def api_logs(guild_id):
    with get_db() as db:
        cfg = db.execute("SELECT logs FROM config WHERE guild_id=?", (guild_id,)).fetchone()
    return jsonify(json.loads(cfg["logs"]) if cfg else {})

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

# ═══════════════════════════════════════════
#  START
# ═══════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    print(f"🚀 Kyste API — port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
