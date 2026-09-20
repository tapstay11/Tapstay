#!/usr/bin/env python3
"""
TapStay — Smart Hospitality & Property Management System (PMS)
Unified Backend Server (Python 3.12 Standard Library)
Zero external dependencies: uses built-in http.server, sqlite3, json, hashlib.
"""

import http.server
import socketserver
import sqlite3
import json
import os
import sys
import mimetypes
import hashlib
import secrets
import time
from urllib.parse import urlparse, parse_qs
from datetime import datetime, date, timedelta

PORT = 8080
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tapstay.db")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

# Active sessions: token -> {user_id, username, role, full_name, expires_at}
SESSIONS = {}

# Active SSE client queues or event listeners
EVENT_LISTENERS = []

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"{salt}:{hashed}"

def verify_password(password, stored_hash):
    try:
        salt, hashed = stored_hash.split(":")
        test_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
        return secrets.compare_digest(hashed, test_hash)
    except Exception:
        return False

def broadcast_event(event_type, data):
    payload = json.dumps({"type": event_type, "data": data, "timestamp": time.time()})
    for queue in list(EVENT_LISTENERS):
        try:
            queue.append(payload)
        except Exception:
            EVENT_LISTENERS.remove(queue)

def init_database():
    conn = get_db()
    c = conn.cursor()

    # Users table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin', -- 'admin', 'frontdesk', 'kitchen', 'housekeeping'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Room Types table
    c.execute("""
    CREATE TABLE IF NOT EXISTS room_types (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        base_price REAL NOT NULL,
        capacity INTEGER NOT NULL DEFAULT 2,
        description TEXT,
        image_url TEXT
    )
    """)

    # Rooms table (24 rooms across 4 categories)
    c.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT UNIQUE NOT NULL,
        floor INTEGER NOT NULL,
        room_type_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'available', -- 'available', 'occupied', 'reserved', 'dirty', 'maintenance'
        assigned_guest TEXT,
        assigned_booking_id TEXT,
        cleaning_notes TEXT,
        FOREIGN KEY (room_type_id) REFERENCES room_types(id)
    )
    """)

    # Bookings table
    c.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ref_number TEXT UNIQUE NOT NULL,
        guest_name TEXT NOT NULL,
        guest_phone TEXT NOT NULL,
        guest_email TEXT NOT NULL,
        room_type_id TEXT NOT NULL,
        room_number TEXT,
        checkin_date TEXT NOT NULL,
        checkout_date TEXT NOT NULL,
        guests_count INTEGER NOT NULL DEFAULT 2,
        total_amount REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'confirmed', -- 'confirmed', 'checked_in', 'checked_out', 'cancelled'
        payment_status TEXT NOT NULL DEFAULT 'pay_at_hotel', -- 'paid', 'deposit', 'pay_at_hotel'
        special_requests TEXT,
        source TEXT NOT NULL DEFAULT 'website', -- 'website', 'walk_in', 'phone'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Food & Beverage Orders table (from order.html)
    c.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_ref TEXT UNIQUE NOT NULL,
        source_type TEXT NOT NULL, -- 'table', 'room'
        source_number TEXT NOT NULL, -- e.g. '7' for Table 7, or '204' for Room 204
        items_json TEXT NOT NULL,
        subtotal REAL NOT NULL,
        tax REAL NOT NULL,
        total REAL NOT NULL,
        payment_method TEXT NOT NULL DEFAULT 'upi', -- 'upi', 'card', 'room_bill', 'cash'
        payment_status TEXT NOT NULL DEFAULT 'completed', -- 'completed', 'pending'
        order_status TEXT NOT NULL DEFAULT 'new', -- 'new', 'preparing', 'ready', 'delivered'
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Concierge & Housekeeping Requests table (from concierge.html)
    c.execute("""
    CREATE TABLE IF NOT EXISTS concierge_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT NOT NULL,
        request_type TEXT NOT NULL, -- 'towels', 'cleaning', 'laundry', 'late_checkout', 'maintenance', 'wifi', 'other'
        details TEXT,
        priority TEXT NOT NULL DEFAULT 'normal', -- 'normal', 'urgent'
        status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'in_progress', 'resolved'
        assigned_to TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP
    )
    """)

    # Reviews table (from review.html)
    c.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guest_name TEXT NOT NULL,
        room_number TEXT,
        overall_rating INTEGER NOT NULL,
        room_rating INTEGER DEFAULT 5,
        clean_rating INTEGER DEFAULT 5,
        food_rating INTEGER DEFAULT 5,
        staff_rating INTEGER DEFAULT 5,
        comment TEXT,
        is_featured INTEGER DEFAULT 0, -- 1 to show on public website
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Hotel & TapStay Settings table
    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # Seed Initial Data if empty
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        # Default Admin Credentials: admin / tapstay123
        admin_pass = hash_password("tapstay123")
        c.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                  ("admin", admin_pass, "Vaibhav Pandey (General Manager)", "admin"))
        
        reception_pass = hash_password("frontdesk123")
        c.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                  ("frontdesk", reception_pass, "Arush (Front Office)", "frontdesk"))

        kitchen_pass = hash_password("kitchen123")
        c.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                  ("kitchen", kitchen_pass, "Chef Hardik (Grand Kitchen)", "kitchen"))

    # Seed Room Types
    c.execute("SELECT COUNT(*) FROM room_types")
    if c.fetchone()[0] == 0:
        types = [
            ("deluxe", "Heritage Deluxe Room", 3499.0, 2, "Timeless elegance with high ceilings, teakwood furnishings, and modern comforts.", "images/gallery-room.jpg"),
            ("garden", "Premium Garden View", 4499.0, 2, "Tranquil retreat with private balcony overlooking the verdant Doon Valley gardens.", "images/gallery-suite.jpg"),
            ("suite", "Grand Suite", 6999.0, 4, "Spacious luxury suite with a separate heritage sitting parlour and grand king bedroom.", "images/gallery-suite2.jpg"),
            ("executive", "Executive Heritage Room", 5499.0, 2, "Refined workspace and bespoke lounge chair for discerning business & leisure travellers.", "images/gallery-room2.jpg"),
        ]
        c.executemany("INSERT INTO room_types (id, name, base_price, capacity, description, image_url) VALUES (?, ?, ?, ?, ?, ?)", types)

    # Seed 24 Rooms
    c.execute("SELECT COUNT(*) FROM rooms")
    if c.fetchone()[0] == 0:
        rooms_data = [
            # Floor 1 (101 - 112)
            ("101", 1, "deluxe", "occupied", "A. Sharma", "TS-829104", "Cleaned at 11 AM"),
            ("102", 1, "deluxe", "dirty", None, None, "Guest checked out at 10:30 AM — needs fresh sheets"),
            ("103", 1, "deluxe", "available", None, None, "Inspected & ready"),
            ("104", 1, "garden", "occupied", "Vikram Malhotra", "TS-481920", None),
            ("105", 1, "garden", "reserved", "Sunita Verma", "TS-918234", "Arriving 3 PM today"),
            ("106", 1, "garden", "available", None, None, "Ready"),
            ("107", 1, "deluxe", "available", None, None, "Ready"),
            ("108", 1, "deluxe", "maintenance", None, None, "AC thermostat calibration"),
            ("109", 1, "executive", "occupied", "Rajeev Singhania", "TS-628401", None),
            ("110", 1, "executive", "available", None, None, "Ready"),
            ("111", 1, "suite", "occupied", "Capt. K. Rawat", "TS-551029", "VIP Guest"),
            ("112", 1, "suite", "available", None, None, "Ready"),

            # Floor 2 (201 - 212)
            ("201", 2, "deluxe", "available", None, None, "Ready"),
            ("202", 2, "deluxe", "occupied", "Meera Sen", "TS-339182", None),
            ("203", 2, "deluxe", "available", None, None, "Ready"),
            ("204", 2, "garden", "occupied", "Deepak Saxena", "TS-771290", "Concierge active"),
            ("205", 2, "garden", "available", None, None, "Ready"),
            ("206", 2, "garden", "reserved", "Pooja Hegde", "TS-229103", "Evening arrival"),
            ("207", 2, "executive", "available", None, None, "Ready"),
            ("208", 2, "executive", "occupied", "Anand Joshi", "TS-882310", None),
            ("209", 2, "deluxe", "available", None, None, "Ready"),
            ("210", 2, "deluxe", "dirty", None, None, "Needs bathroom sanitization"),
            ("211", 2, "suite", "available", None, None, "Ready"),
            ("212", 2, "suite", "occupied", "Dr. S. Mukherjee", "TS-119283", None),
        ]
        c.executemany("INSERT INTO rooms (room_number, floor, room_type_id, status, assigned_guest, assigned_booking_id, cleaning_notes) VALUES (?, ?, ?, ?, ?, ?, ?)", rooms_data)

    # Seed Sample Bookings
    c.execute("SELECT COUNT(*) FROM bookings")
    if c.fetchone()[0] == 0:
        today_str = date.today().isoformat()
        tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
        day_after_str = (date.today() + timedelta(days=2)).isoformat()
        sample_bookings = [
            ("TS-829104", "A. Sharma", "+91 98765 43210", "asharma@example.com", "deluxe", "101", today_str, tomorrow_str, 2, 3499.0, "checked_in", "paid", "Quiet room requested", "website"),
            ("TS-481920", "Vikram Malhotra", "+91 98221 12345", "vikram.m@example.com", "garden", "104", today_str, day_after_str, 2, 8998.0, "checked_in", "paid", "Balcony view preferred", "website"),
            ("TS-918234", "Sunita Verma", "+91 94120 56789", "sverma@example.com", "garden", "105", today_str, tomorrow_str, 2, 4499.0, "confirmed", "pay_at_hotel", "Late check-in expected around 4 PM", "website"),
            ("TS-628401", "Rajeev Singhania", "+91 98100 99887", "singhania@corp.in", "executive", "109", today_str, day_after_str, 1, 10998.0, "checked_in", "paid", "Business invoice required", "walk_in"),
            ("TS-551029", "Capt. K. Rawat", "+91 97600 11223", "krawat@armydoon.org", "suite", "111", today_str, tomorrow_str, 3, 6999.0, "checked_in", "paid", "Extra pillow set", "phone"),
            ("TS-771290", "Deepak Saxena", "+91 98970 44556", "dsaxena@techdoon.com", "garden", "204", today_str, day_after_str, 2, 8998.0, "checked_in", "paid", "Anniversary celebration", "website"),
            ("TS-229103", "Pooja Hegde", "+91 99887 76655", "pooja.h@travelindia.com", "garden", "206", today_str, day_after_str, 2, 8998.0, "confirmed", "deposit", "Ground or 2nd floor", "website"),
        ]
        c.executemany("INSERT INTO bookings (ref_number, guest_name, guest_phone, guest_email, room_type_id, room_number, checkin_date, checkout_date, guests_count, total_amount, status, payment_status, special_requests, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", sample_bookings)

    # Seed Sample KOT Orders
    c.execute("SELECT COUNT(*) FROM orders")
    if c.fetchone()[0] == 0:
        sample_orders = [
            ("KOT-101", "table", "7", json.dumps([{"name": "Garhwali Paneer Tikka", "qty": 2, "price": 380}, {"name": "Butter Naan", "qty": 4, "price": 60}]), 1000.0, 50.0, 1050.0, "upi", "completed", "preparing", "Medium spicy for table 7"),
            ("KOT-102", "room", "204", json.dumps([{"name": "Kadhai Murgh", "qty": 1, "price": 480}, {"name": "Jeera Rice", "qty": 1, "price": 180}, {"name": "Gulab Jamun", "qty": 2, "price": 120}]), 900.0, 45.0, 945.0, "card", "completed", "new", "Send with 2 sets of cutlery"),
            ("KOT-103", "table", "3", json.dumps([{"name": "Doon Masala Chai", "qty": 3, "price": 90}, {"name": "Crispy Corn Fritters", "qty": 1, "price": 240}]), 510.0, 25.5, 535.5, "upi", "completed", "delivered", "Served on terrace"),
        ]
        c.executemany("INSERT INTO orders (order_ref, source_type, source_number, items_json, subtotal, tax, total, payment_method, payment_status, order_status, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", sample_orders)

    # Seed Sample Concierge Requests
    c.execute("SELECT COUNT(*) FROM concierge_requests")
    if c.fetchone()[0] == 0:
        sample_concierge = [
            ("204", "towels", "2 extra bath towels and bathrobes please", "normal", "pending", None),
            ("109", "cleaning", "Tidy up desk and empty trash bin before evening meeting", "normal", "in_progress", "Housekeeping Team A"),
            ("108", "maintenance", "Air conditioner makes a slight humming noise on low fan", "urgent", "in_progress", "Manoj (Electrician)"),
            ("111", "late_checkout", "Request check-out extension to 2:00 PM tomorrow due to late afternoon flight", "normal", "resolved", "Front Desk"),
        ]
        c.executemany("INSERT INTO concierge_requests (room_number, request_type, details, priority, status, assigned_to) VALUES (?, ?, ?, ?, ?, ?)", sample_concierge)

    # Seed Sample Reviews
    c.execute("SELECT COUNT(*) FROM reviews")
    if c.fetchone()[0] == 0:
        sample_reviews = [
            ("Aditya Sharma", "101", 5, 5, 5, 5, 5, "Remarkable heritage ambiance with courteous staff! The in-room QR service was lightning fast.", 1),
            ("Priya & Rahul Kapoor", "204", 5, 5, 5, 5, 5, "Loved our anniversary stay. The garden view room was immaculate, and dining on the terrace was heavenly.", 1),
            ("Rohit Varma", "109", 4, 4, 4, 5, 5, "Extremely convenient location in Dehradun with comfortable heritage work desks. High-speed Wi-Fi worked great.", 1),
            ("Sonalika Sen", "112", 5, 5, 5, 5, 5, "The food at The Grand Kitchen is easily the best North Indian food in Dehradun. The QR ordering was very slick!", 1),
        ]
        c.executemany("INSERT INTO reviews (guest_name, room_number, overall_rating, room_rating, clean_rating, food_rating, staff_rating, comment, is_featured) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", sample_reviews)

    # Seed Settings
    c.execute("SELECT COUNT(*) FROM settings")
    if c.fetchone()[0] == 0:
        settings_data = [
            ("hotel_name", "HOTEL"),
            ("tagline", "Heritage Hospitality & Smart QR Hospitality"),
            ("location", "Dehradun, Uttarakhand, India"),
            ("phone", "+91 135 271 2345"),
            ("email", "stay@hotel-dehradun.com"),
            ("wifi_ssid", "HOTEL_Heritage_Guest"),
            ("wifi_pass", "DoonValley2026"),
            ("checkout_time", "11:00 AM"),
            ("company_brand", "TapStay"),
            ("company_tagline", "The Smart Hospitality Operating System"),
        ]
        c.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", settings_data)

    conn.commit()
    conn.close()
    print("✓ TapStay Database initialized and seeded successfully.")


class TapStayRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP Request Handler supporting REST APIs & static assets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def send_json(self, data, status_code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status_code=400):
        self.send_json({"error": message, "success": False}, status_code)

    def get_auth_user(self):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            session = SESSIONS.get(token)
            if session and session["expires_at"] > time.time():
                return session
        return None

    def read_json_body(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return {}
            raw_body = self.rfile.read(content_length).decode("utf-8")
            return json.loads(raw_body)
        except Exception as e:
            return None

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # ==================== GET HANDLER ====================
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Redirect clean routes
        if path in ("/thank-you", "/thank-you/", "/thankyou", "/thankyou/"):
            self.send_response(302)
            self.send_header("Location", "/thankyou.html")
            self.end_headers()
            return
        if path == "/hotel" or path == "/hotel/":
            self.send_response(302)
            self.send_header("Location", "/hotel.html")
            self.end_headers()
            return
        if path == "/admin" or path == "/admin/":
            self.send_response(302)
            self.send_header("Location", "/admin.html")
            self.end_headers()
            return
        if path == "/login" or path == "/login/":
            self.send_response(302)
            self.send_header("Location", "/login.html")
            self.end_headers()
            return

        # API Routes
        if path.startswith("/api/"):
            self.handle_api_get(path, query)
            return

        # Default static file serving
        return super().do_GET()

    def handle_api_get(self, path, query):
        conn = get_db()
        c = conn.cursor()

        try:
            # Check active session
            if path == "/api/auth/me":
                user = self.get_auth_user()
                if user:
                    self.send_json({"success": True, "user": user})
                else:
                    self.send_error_json("Unauthorized", 401)
                return

            # Comprehensive Hotel & TapStay Stats
            if path == "/api/stats":
                # Occupancy
                c.execute("SELECT status, COUNT(*) as cnt FROM rooms GROUP BY status")
                room_counts = {row["status"]: row["cnt"] for row in c.fetchall()}
                total_rooms = 24
                occupied_count = room_counts.get("occupied", 0)
                available_count = room_counts.get("available", 0)
                reserved_count = room_counts.get("reserved", 0)
                dirty_count = room_counts.get("dirty", 0)
                maintenance_count = room_counts.get("maintenance", 0)
                occupancy_pct = round((occupied_count / total_rooms) * 100)

                # Today's check-ins & check-outs
                today_str = date.today().isoformat()
                c.execute("SELECT COUNT(*) FROM bookings WHERE checkin_date = ? AND status IN ('confirmed', 'checked_in')", (today_str,))
                checkins_today = c.fetchone()[0]

                c.execute("SELECT COUNT(*) FROM bookings WHERE checkout_date = ? AND status = 'checked_in'", (today_str,))
                checkouts_today = c.fetchone()[0]

                # Revenue stats
                c.execute("SELECT SUM(total_amount) FROM bookings WHERE status != 'cancelled'")
                room_rev = c.fetchone()[0] or 0.0

                c.execute("SELECT SUM(total) FROM orders WHERE payment_status = 'completed'")
                food_rev = c.fetchone()[0] or 0.0

                # Active counts
                c.execute("SELECT COUNT(*) FROM orders WHERE order_status IN ('new', 'preparing')")
                active_orders = c.fetchone()[0]

                c.execute("SELECT COUNT(*) FROM concierge_requests WHERE status IN ('pending', 'in_progress')")
                pending_concierge = c.fetchone()[0]

                c.execute("SELECT AVG(overall_rating), COUNT(*) FROM reviews")
                avg_row = c.fetchone()
                avg_rating = round(avg_row[0] or 5.0, 1)
                total_reviews = avg_row[1]

                self.send_json({
                    "success": True,
                    "stats": {
                        "total_rooms": total_rooms,
                        "occupied_count": occupied_count,
                        "available_count": available_count,
                        "reserved_count": reserved_count,
                        "dirty_count": dirty_count,
                        "maintenance_count": maintenance_count,
                        "occupancy_pct": occupancy_pct,
                        "checkins_today": checkins_today,
                        "checkouts_today": checkouts_today,
                        "room_revenue": room_rev,
                        "food_revenue": food_rev,
                        "total_revenue": room_rev + food_rev,
                        "active_orders": active_orders,
                        "pending_concierge": pending_concierge,
                        "avg_rating": avg_rating,
                        "total_reviews": total_reviews
                    }
                })
                return

            # Rooms list
            if path == "/api/rooms":
                c.execute("""
                    SELECT r.*, rt.name as type_name, rt.base_price, rt.capacity, rt.image_url 
                    FROM rooms r
                    JOIN room_types rt ON r.room_type_id = rt.id
                    ORDER BY r.floor ASC, r.room_number ASC
                """)
                rooms = [dict(row) for row in c.fetchall()]
                self.send_json({"success": True, "rooms": rooms})
                return

            # Room availability summary (public website ticker)
            if path == "/api/rooms/summary":
                c.execute("""
                    SELECT r.room_type_id, rt.name, rt.base_price,
                           COUNT(CASE WHEN r.status = 'available' THEN 1 END) as available_count,
                           COUNT(*) as total_count
                    FROM rooms r
                    JOIN room_types rt ON r.room_type_id = rt.id
                    GROUP BY r.room_type_id
                """)
                summary = [dict(row) for row in c.fetchall()]
                
                c.execute("SELECT COUNT(*) FROM rooms WHERE status = 'available'")
                total_avail = c.fetchone()[0]

                self.send_json({"success": True, "total_available": total_avail, "categories": summary})
                return

            # Bookings list
            if path == "/api/bookings":
                status_filter = query.get("status", [None])[0]
                sql = """
                    SELECT b.*, rt.name as room_type_name
                    FROM bookings b
                    JOIN room_types rt ON b.room_type_id = rt.id
                """
                params = []
                if status_filter and status_filter != "all":
                    sql += " WHERE b.status = ?"
                    params.append(status_filter)
                sql += " ORDER BY b.id DESC LIMIT 100"

                c.execute(sql, params)
                bookings = [dict(row) for row in c.fetchall()]
                self.send_json({"success": True, "bookings": bookings})
                return

            # Orders list
            if path == "/api/orders":
                status_filter = query.get("status", [None])[0]
                sql = "SELECT * FROM orders"
                params = []
                if status_filter and status_filter != "all":
                    sql += " WHERE order_status = ?"
                    params.append(status_filter)
                sql += " ORDER BY id DESC LIMIT 100"

                c.execute(sql, params)
                orders = []
                for row in c.fetchall():
                    item = dict(row)
                    try:
                        item["items"] = json.loads(item["items_json"])
                    except Exception:
                        item["items"] = []
                    orders.append(item)
                self.send_json({"success": True, "orders": orders})
                return

            # Concierge requests list
            if path == "/api/concierge":
                status_filter = query.get("status", [None])[0]
                sql = "SELECT * FROM concierge_requests"
                params = []
                if status_filter and status_filter != "all":
                    sql += " WHERE status = ?"
                    params.append(status_filter)
                sql += " ORDER BY id DESC LIMIT 100"

                c.execute(sql, params)
                requests = [dict(row) for row in c.fetchall()]
                self.send_json({"success": True, "requests": requests})
                return

            # Reviews list
            if path == "/api/reviews":
                featured_only = query.get("featured", ["false"])[0].lower() == "true"
                sql = "SELECT * FROM reviews"
                if featured_only:
                    sql += " WHERE is_featured = 1"
                sql += " ORDER BY id DESC LIMIT 50"

                c.execute(sql)
                reviews = [dict(row) for row in c.fetchall()]
                self.send_json({"success": True, "reviews": reviews})
                return

            # Settings
            if path == "/api/settings":
                c.execute("SELECT key, value FROM settings")
                settings = {row["key"]: row["value"] for row in c.fetchall()}
                self.send_json({"success": True, "settings": settings})
                return

            self.send_error_json("API route not found", 404)

        finally:
            conn.close()

    # ==================== POST HANDLER ====================
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()

        if body is None:
            self.send_error_json("Invalid JSON body", 400)
            return

        conn = get_db()
        c = conn.cursor()

        try:
            # Login
            if path == "/api/auth/login":
                username = body.get("username", "").strip()
                password = body.get("password", "").strip()

                if not username or not password:
                    self.send_error_json("Username and password required", 400)
                    return

                c.execute("SELECT * FROM users WHERE username = ?", (username,))
                user = c.fetchone()
                if not user or not verify_password(password, user["password_hash"]):
                    self.send_error_json("Invalid username or password", 401)
                    return

                token = secrets.token_hex(32)
                session = {
                    "user_id": user["id"],
                    "username": user["username"],
                    "full_name": user["full_name"],
                    "role": user["role"],
                    "expires_at": time.time() + (86400 * 7) # 7 days
                }
                SESSIONS[token] = session
                self.send_json({
                    "success": True,
                    "token": token,
                    "user": session
                })
                return

            # Logout
            if path == "/api/auth/logout":
                auth_header = self.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:].strip()
                    SESSIONS.pop(token, None)
                self.send_json({"success": True, "message": "Logged out"})
                return

            # Create Direct Booking (from website or walk-in)
            if path == "/api/bookings":
                guest_name = body.get("guest_name", "").strip()
                guest_phone = body.get("guest_phone", "").strip()
                guest_email = body.get("guest_email", "").strip()
                room_type_id = body.get("room_type_id", "deluxe")
                checkin_date = body.get("checkin_date", date.today().isoformat())
                checkout_date = body.get("checkout_date", (date.today() + timedelta(days=1)).isoformat())
                guests_count = int(body.get("guests_count", 2))
                source = body.get("source", "website")
                special_requests = body.get("special_requests", "")

                if not guest_name or not guest_phone:
                    self.send_error_json("Guest name and phone number are required", 400)
                    return

                # Calculate nights and total amount
                try:
                    d1 = datetime.strptime(checkin_date, "%Y-%m-%d").date()
                    d2 = datetime.strptime(checkout_date, "%Y-%m-%d").date()
                    nights = max(1, (d2 - d1).days)
                except Exception:
                    nights = 1

                c.execute("SELECT base_price FROM room_types WHERE id = ?", (room_type_id,))
                rt = c.fetchone()
                base_price = rt["base_price"] if rt else 3499.0
                total_amount = base_price * nights

                # Generate reference number
                ref_number = "TS-" + str(secrets.randbelow(900000) + 100000)

                # Find an available room of this type and assign/reserve it
                c.execute("SELECT room_number FROM rooms WHERE room_type_id = ? AND status = 'available' LIMIT 1", (room_type_id,))
                avail_room = c.fetchone()
                assigned_room = avail_room["room_number"] if avail_room else None

                c.execute("""
                    INSERT INTO bookings (ref_number, guest_name, guest_phone, guest_email, room_type_id, room_number, checkin_date, checkout_date, guests_count, total_amount, status, payment_status, special_requests, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed', 'pay_at_hotel', ?, ?)
                """, (ref_number, guest_name, guest_phone, guest_email, room_type_id, assigned_room, checkin_date, checkout_date, guests_count, total_amount, special_requests, source))
                booking_id = c.lastrowid

                # If room assigned, mark as reserved
                if assigned_room:
                    c.execute("UPDATE rooms SET status = 'reserved', assigned_guest = ?, assigned_booking_id = ? WHERE room_number = ?",
                              (guest_name, ref_number, assigned_room))

                conn.commit()

                broadcast_event("new_booking", {
                    "ref": ref_number,
                    "guest": guest_name,
                    "room_type": room_type_id,
                    "room_number": assigned_room,
                    "total": total_amount
                })

                self.send_json({
                    "success": True,
                    "ref_number": ref_number,
                    "booking_id": booking_id,
                    "assigned_room": assigned_room,
                    "total_amount": total_amount,
                    "nights": nights,
                    "message": "Booking confirmed! TapStay has notified the front desk."
                }, 201)
                return

            # Create Food Order (from order.html)
            if path == "/api/orders":
                source_type = body.get("source_type", "table")
                source_number = str(body.get("source_number", "7"))
                items = body.get("items", [])
                subtotal = float(body.get("subtotal", 0.0))
                tax = float(body.get("tax", 0.0))
                total = float(body.get("total", 0.0))
                payment_method = body.get("payment_method", "upi")
                notes = body.get("notes", "")

                if not items:
                    self.send_error_json("Order must contain at least 1 item", 400)
                    return

                order_ref = "KOT-" + str(secrets.randbelow(9000) + 1000)

                c.execute("""
                    INSERT INTO orders (order_ref, source_type, source_number, items_json, subtotal, tax, total, payment_method, payment_status, order_status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', 'new', ?)
                """, (order_ref, source_type, source_number, json.dumps(items), subtotal, tax, total, payment_method, notes))
                order_id = c.lastrowid
                conn.commit()

                broadcast_event("new_order", {
                    "ref": order_ref,
                    "source": f"{source_type.title()} {source_number}",
                    "total": total,
                    "item_count": len(items)
                })

                self.send_json({
                    "success": True,
                    "order_ref": order_ref,
                    "order_id": order_id,
                    "message": f"Order received for {source_type.title()} {source_number}! Sent to kitchen."
                }, 201)
                return

            # Create Concierge Request (from concierge.html)
            if path == "/api/concierge":
                room_number = str(body.get("room_number", "204")).strip()
                request_type = body.get("request_type", "towels")
                details = body.get("details", "")
                priority = body.get("priority", "normal")

                if not room_number:
                    self.send_error_json("Room number is required", 400)
                    return

                c.execute("""
                    INSERT INTO concierge_requests (room_number, request_type, details, priority, status)
                    VALUES (?, ?, ?, ?, 'pending')
                """, (room_number, request_type, details, priority))
                req_id = c.lastrowid
                conn.commit()

                broadcast_event("new_concierge", {
                    "id": req_id,
                    "room": room_number,
                    "type": request_type,
                    "details": details
                })

                self.send_json({
                    "success": True,
                    "request_id": req_id,
                    "message": f"Service request logged for Room {room_number}! Front desk notified."
                }, 201)
                return

            # Submit Guest Review (from review.html)
            if path == "/api/reviews":
                guest_name = body.get("guest_name", "Valued Guest").strip()
                room_number = str(body.get("room_number", "")).strip()
                overall_rating = int(body.get("overall_rating", 5))
                room_rating = int(body.get("room_rating", 5))
                clean_rating = int(body.get("clean_rating", 5))
                food_rating = int(body.get("food_rating", 5))
                staff_rating = int(body.get("staff_rating", 5))
                comment = body.get("comment", "")

                # Automatically feature 5-star reviews
                is_featured = 1 if overall_rating >= 5 else 0

                c.execute("""
                    INSERT INTO reviews (guest_name, room_number, overall_rating, room_rating, clean_rating, food_rating, staff_rating, comment, is_featured)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (guest_name, room_number, overall_rating, room_rating, clean_rating, food_rating, staff_rating, comment, is_featured))
                review_id = c.lastrowid
                conn.commit()

                broadcast_event("new_review", {
                    "id": review_id,
                    "guest": guest_name,
                    "rating": overall_rating,
                    "comment": comment
                })

                self.send_json({
                    "success": True,
                    "review_id": review_id,
                    "message": "Thank you for your feedback! It helps us improve."
                }, 201)
                return

            self.send_error_json("API route not found", 404)

        finally:
            conn.close()

    # ==================== PUT HANDLER ====================
    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()

        if body is None:
            self.send_error_json("Invalid JSON body", 400)
            return

        conn = get_db()
        c = conn.cursor()

        try:
            # Update Room Status & Cleaning Notes
            # e.g. /api/rooms/101/status
            if path.startswith("/api/rooms/") and path.endswith("/status"):
                room_num = path.split("/")[3]
                new_status = body.get("status")
                cleaning_notes = body.get("cleaning_notes")

                if new_status not in ["available", "occupied", "reserved", "dirty", "maintenance"]:
                    self.send_error_json("Invalid room status", 400)
                    return

                if new_status == "available":
                    # Clear guest when room becomes available
                    c.execute("UPDATE rooms SET status = ?, assigned_guest = NULL, assigned_booking_id = NULL, cleaning_notes = ? WHERE room_number = ?",
                              (new_status, cleaning_notes or "Inspected & clean", room_num))
                else:
                    c.execute("UPDATE rooms SET status = ?, cleaning_notes = COALESCE(?, cleaning_notes) WHERE room_number = ?",
                              (new_status, cleaning_notes, room_num))

                conn.commit()
                self.send_json({"success": True, "room_number": room_num, "status": new_status})
                return

            # Update Room Type Pricing
            # /api/room-types/deluxe/price
            if path.startswith("/api/room-types/") and path.endswith("/price"):
                type_id = path.split("/")[3]
                new_price = float(body.get("price", 0.0))
                if new_price <= 0:
                    self.send_error_json("Invalid price", 400)
                    return
                c.execute("UPDATE room_types SET base_price = ? WHERE id = ?", (new_price, type_id))
                conn.commit()
                self.send_json({"success": True, "room_type": type_id, "price": new_price})
                return

            # Update Booking Status (Check-in, Check-out, Cancel)
            # /api/bookings/1/status
            if path.startswith("/api/bookings/") and path.endswith("/status"):
                booking_id = int(path.split("/")[3])
                new_status = body.get("status")
                assigned_room = body.get("room_number")

                c.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
                booking = c.fetchone()
                if not booking:
                    self.send_error_json("Booking not found", 404)
                    return

                room_to_use = assigned_room or booking["room_number"]

                if new_status == "checked_in":
                    # Room becomes occupied
                    if room_to_use:
                        c.execute("UPDATE rooms SET status = 'occupied', assigned_guest = ?, assigned_booking_id = ? WHERE room_number = ?",
                                  (booking["guest_name"], booking["ref_number"], room_to_use))
                    c.execute("UPDATE bookings SET status = 'checked_in', room_number = ? WHERE id = ?", (room_to_use, booking_id))

                elif new_status == "checked_out":
                    # Room becomes dirty (needs cleaning)
                    if room_to_use:
                        c.execute("UPDATE rooms SET status = 'dirty', cleaning_notes = 'Guest checked out, requires fresh linens' WHERE room_number = ?", (room_to_use,))
                    c.execute("UPDATE bookings SET status = 'checked_out' WHERE id = ?", (booking_id,))

                elif new_status == "cancelled":
                    # Room becomes available if it was reserved
                    if room_to_use:
                        c.execute("UPDATE rooms SET status = 'available', assigned_guest = NULL, assigned_booking_id = NULL WHERE room_number = ?", (room_to_use,))
                    c.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
                else:
                    c.execute("UPDATE bookings SET status = ? WHERE id = ?", (new_status, booking_id))

                conn.commit()
                self.send_json({"success": True, "booking_id": booking_id, "status": new_status, "room": room_to_use})
                return

            # Update KOT Order Status (new -> preparing -> ready -> delivered)
            # /api/orders/1/status
            if path.startswith("/api/orders/") and path.endswith("/status"):
                order_id = int(path.split("/")[3])
                new_status = body.get("status")
                if new_status not in ["new", "preparing", "ready", "delivered"]:
                    self.send_error_json("Invalid order status", 400)
                    return
                c.execute("UPDATE orders SET order_status = ? WHERE id = ?", (new_status, order_id))
                conn.commit()
                self.send_json({"success": True, "order_id": order_id, "status": new_status})
                return

            # Update Concierge Request Status (pending -> in_progress -> resolved)
            # /api/concierge/1/status
            if path.startswith("/api/concierge/") and path.endswith("/status"):
                req_id = int(path.split("/")[3])
                new_status = body.get("status")
                assigned_to = body.get("assigned_to")

                resolved_time = datetime.now().isoformat() if new_status == "resolved" else None
                c.execute("""
                    UPDATE concierge_requests 
                    SET status = ?, assigned_to = COALESCE(?, assigned_to), resolved_at = COALESCE(?, resolved_at)
                    WHERE id = ?
                """, (new_status, assigned_to, resolved_time, req_id))
                conn.commit()
                self.send_json({"success": True, "request_id": req_id, "status": new_status})
                return

            # Toggle Review Featured Status
            # /api/reviews/1/feature
            if path.startswith("/api/reviews/") and path.endswith("/feature"):
                review_id = int(path.split("/")[3])
                is_featured = 1 if body.get("is_featured", False) else 0
                c.execute("UPDATE reviews SET is_featured = ? WHERE id = ?", (is_featured, review_id))
                conn.commit()
                self.send_json({"success": True, "review_id": review_id, "is_featured": bool(is_featured)})
                return

            self.send_error_json("API route not found", 404)

        finally:
            conn.close()


def run_server():
    init_database()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), TapStayRequestHandler) as httpd:
        print("=" * 65)
        print("  ✦ TapStay — Smart Hospitality & Property Management System ✦")
        print(f"  Server running locally at:   http://localhost:{PORT}")
        print(f"  Admin & PMS Portal at:       http://localhost:{PORT}/admin.html")
        print(f"  Default Admin Login:         admin  /  tapstay123")
        print(f"  Frontdesk Login:             frontdesk  /  frontdesk123")
        print(f"  Kitchen Login:               kitchen  /  kitchen123")
        print("=" * 65)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down TapStay server.")
            httpd.server_close()

if __name__ == "__main__":
    run_server()
