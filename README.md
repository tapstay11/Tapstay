# TapStay — Smart Hospitality & Property Management Operating System (PMS)

**TapStay** is a modern, full-stack smart hospitality software suite and Property Management System (PMS) designed for boutique hotels, heritage properties, resorts, and homestays.

It replaces expensive legacy desktop software and fragmented tools with a single unified platform: a luxury guest-facing website with direct bookings, contactless Smart QR dining, in-room digital concierge, automated review capture, and a real-time administrative operations portal.

---

## 🌟 Key Features

### 🏨 1. Public Guest Website & Direct Booking Engine (`index.html`)
- **Heritage Luxury Aesthetic**: Deep-green (`#1B4332`) and gold (`#C9A227`) design with smooth scroll reveals and responsive layouts.
- **Direct Online Reservations**: Working booking flow with dynamic date picker, automatic night calculations, guest dossiers, and instant confirmation references (`TS-XXXXXX`).
- **Live Inventory Ticker**: Real-time room availability ticker synced directly with the database.
- **Dining & Gallery Showcase**: Interactive lightbox photo gallery, signature dishes menu, and property highlights.

### 🛏️ 2. Property Management System (PMS) & Admin Portal (`admin.html` & `login.html`)
- **Executive Operations Dashboard**: Real-time tracking of Occupancy %, Total Revenue, Today's Check-ins & Check-outs, Active Kitchen Orders, and Pending Service Requests.
- **24-Room Visual Status Grid**: Interactive matrix covering all rooms across 2 floors with 5 real-time states:
  - 🟢 **Available (Clean)**
  - 🔴 **Occupied** (with guest name & stay duration)
  - 🟡 **Reserved** (for today's arrivals)
  - 🟠 **Needs Cleaning** (automatically triggered on checkout)
  - ⚪ **Maintenance / Out of Order**
- **1-Click Room Status & Price Editor**: Update room states or nightly rates dynamically from the dashboard.
- **Reservations & Front Desk Hub**: Searchable bookings ledger with filter tabs, guest contact details, 1-click Check-in / Check-out, and a **"+ Walk-In Booking"** creator.

### 🍳 3. Kitchen Display System (KDS / KOT) & Smart QR Dining (`order.html`)
- **Contactless Table & In-Room QR Menu**: Guests scan a tabletop QR code on their phone to browse categories, customize orders, and pay via simulated UPI or Card.
- **Live 4-Stage Kitchen Pipeline**:
  `New Orders` ➔ `In Preparation` ➔ `Ready to Serve` ➔ `Delivered & Settled`
- Real-time order cards with item breakdown, quantities, taxes (GST), and special chef notes.

### 🛎️ 4. In-Room Digital Concierge Desk (`concierge.html`)
- Self-service requests from guest smartphones:
  - 🧹 Housekeeping & trash pickup
  - 🛁 Fresh bath & hand towels
  - 👔 Laundry & dry cleaning
  - 🔑 Late check-out requests
  - 🔧 AC, plumbing, and electrical maintenance
- Urgent priority flags and staff resolution tracking.

### ⭐ 5. Guest Reviews & Reputation Hub (`review.html`)
- Touchless 5-star rating collection across Cleanliness, Food, Staff, and Room quality.
- **"Feature on Public Website"** toggle to curate verified testimonials.

### 📱 6. Smart QR Standee Studio
- Generates high-resolution, branded printable tabletop QR standees for any Table (1–14) or Room (101–212).
- Formatted with `@media print` for 1-click printing on office printers or acrylic stand fabrication.

---

## 🚀 Quick Start — How to Run

TapStay runs with **zero external dependencies** using the Python 3.12 standard library.

### 1. Start the Unified Server
```bash
python3 server.py
```

### 2. Access the Applications
| Interface | Local URL | Default Credentials |
|---|---|---|
| **Public Hotel Website** | [http://localhost:8080](http://localhost:8080) | Public Access |
| **Staff & Admin Login** | [http://localhost:8080/login.html](http://localhost:8080/login.html) | `admin` / `tapstay123`<br>`frontdesk` / `frontdesk123`<br>`kitchen` / `kitchen123` |
| **Operations Dashboard** | [http://localhost:8080/admin.html](http://localhost:8080/admin.html) | Requires Staff Login |
| **QR Table Ordering** | [http://localhost:8080/order.html?table=7](http://localhost:8080/order.html?table=7) | Sample Table 7 |
| **In-Room Concierge** | [http://localhost:8080/concierge.html?room=204](http://localhost:8080/concierge.html?room=204) | Sample Room 204 |
| **Guest Review Form** | [http://localhost:8080/review.html](http://localhost:8080/review.html) | Public Access |

---

## 🏗️ Technical Stack & Architecture

- **Backend**: Python 3.12 `http.server`, `sqlite3`, `hashlib` (PBKDF2-SHA256), `json`, `secrets`.
- **Database**: SQLite3 (`tapstay.db`) with WAL mode and foreign key constraints.
- **Frontend**: Vanilla HTML5, Modern CSS3 (Glassmorphism, CSS Grid, Flexbox, Custom Properties), JavaScript (ES6+).
- **QR Generation**: Embedded `qrcode.min.js` generating dynamic URLs based on client Wi-Fi / domain.

---

## 📡 REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/login` | `POST` | Authenticate staff member and receive session token |
| `/api/auth/logout` | `POST` | Invalidate active session |
| `/api/stats` | `GET` | Live occupancy, revenue, check-in, and ticket counters |
| `/api/rooms` | `GET` | Complete 24-room inventory with current statuses |
| `/api/rooms/<id>/status` | `PUT` | Update room status (available, occupied, reserved, dirty, maintenance) |
| `/api/bookings` | `GET` / `POST` | List bookings or create direct/walk-in reservation |
| `/api/bookings/<id>/status` | `PUT` | Update booking status (check-in, check-out, cancel) |
| `/api/orders` | `GET` / `POST` | Fetch orders or submit new dining order from QR menu |
| `/api/orders/<id>/status` | `PUT` | Advance KOT order stage (`new` ➔ `preparing` ➔ `ready` ➔ `delivered`) |
| `/api/concierge` | `GET` / `POST` | List or submit in-room service requests |
| `/api/concierge/<id>/status` | `PUT` | Resolve or assign concierge tickets |
| `/api/reviews` | `GET` / `POST` | List or submit guest feedback |
| `/api/reviews/<id>/feature` | `PUT` | Toggle review visibility on public website |

---

## 💼 Business & SaaS Commercialization

TapStay is designed as a high-margin B2B SaaS for independent hospitality operators:
- **Starter Plan** (Homestays / Boutique under 12 rooms): ₹1,999 / month.
- **Growth Plan** (12–35 room hotels): ₹3,999 / month.
- **Resort Plan** (35+ rooms & multiple dining outlets): ₹6,999 / month.
- **Hardware Kit Add-on**: ₹4,999 for 25 laser-cut acrylic tabletop QR standees.

---

## 👥 Built by TapStay Founders
**Hardik, Vaibhav Saxena, Arush, Vaibhav Pandey** — Hospitality-Tech Startup, Dehradun.
