"""
Group Skill Events Module

Credit handling summary:
- join: user balance -> held on the participant row
- leave/cancel: held -> back to user
- completion (Part B): held -> host balance
"""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import HTTPException

from agent.memory import SQLITE_PATH, _get_conn, fetch_query, run_query
from agent.tools import haversine, chat_moderation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema Initialization
# ---------------------------------------------------------------------------
def init_events_tables():
    """Ensure Events and EventParticipants tables exist."""
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS Events (
                id TEXT PRIMARY KEY,
                host_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                category TEXT,
                level TEXT DEFAULT 'all',
                mode TEXT NOT NULL,
                city TEXT,
                venue_name TEXT,
                venue_address TEXT,
                lat REAL,
                lon REAL,
                starts_at TIMESTAMP NOT NULL,
                duration_minutes INTEGER DEFAULT 60,
                capacity INTEGER NOT NULL,
                credit_cost INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                cancel_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (host_id) REFERENCES Users(id)
            );
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS EventParticipants (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                credits_held INTEGER DEFAULT 0,
                waitlist_position INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reminder_sent INTEGER DEFAULT 0,
                FOREIGN KEY (event_id) REFERENCES Events(id),
                FOREIGN KEY (user_id) REFERENCES Users(id),
                UNIQUE (event_id, user_id)
            );
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_starts_at ON Events(starts_at);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON Events(status);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_events_host_id ON Events(host_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_event_parts_event ON EventParticipants(event_id, status);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_event_parts_user ON EventParticipants(user_id);")
        conn.commit()
    finally:
        conn.close()


init_events_tables()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_iso_datetime(dt_str: str) -> datetime:
    """Parse ISO string into a timezone-aware UTC datetime."""
    clean_str = dt_str.replace("Z", "+00:00").replace(" ", "T")
    dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def send_event_notification(user_id: str, content: str, title: str = "SkillSwap Events"):
    """Create in-app notification and trigger push alert if available."""
    try:
        notif_id = str(uuid.uuid4())
        run_query("INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)", (notif_id, user_id, content))
    except Exception as e:
        logger.error(f"Failed to insert event notification: {e}")

    try:
        from agent.push import send_push_to_user
        send_push_to_user(user_id, title, content, {"url": "/#events"})
    except Exception as e:
        logger.debug(f"Push notification skipped: {e}")


def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    rows = fetch_query("SELECT id, name, email, city, lat, lon, trust_score, wallet_balance, fraud_flag FROM Users WHERE id = ?", (user_id,))
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Core Event Service Functions
# ---------------------------------------------------------------------------

def create_event(host_id: str, data: dict) -> dict:
    """
    POST /api/events
    Validates input, runs moderation, applies hosting guards, and creates an event.
    """
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    skill_name = (data.get("skill_name") or "").strip()
    category = (data.get("category") or "").strip() or None
    level = (data.get("level") or "all").strip().lower()
    mode = (data.get("mode") or "").strip().lower()
    city = (data.get("city") or "").strip() or None
    venue_name = (data.get("venue_name") or "").strip() or None
    venue_address = (data.get("venue_address") or "").strip() or None
    lat = data.get("lat")
    lon = data.get("lon")
    starts_at_raw = data.get("starts_at")
    duration_minutes = int(data.get("duration_minutes") or 60)
    capacity = int(data.get("capacity") or 0)
    credit_cost = int(data.get("credit_cost") if data.get("credit_cost") is not None else 0)

    # 1. Basic validation
    if not (3 <= len(title) <= 100):
        raise HTTPException(status_code=422, detail="Title must be between 3 and 100 characters.")
    if not (1 <= len(description) <= 1000):
        raise HTTPException(status_code=422, detail="Description is required and must not exceed 1000 characters.")
    if not skill_name:
        raise HTTPException(status_code=422, detail="Skill name is required.")
    if level not in ("beginner", "intermediate", "advanced", "all"):
        raise HTTPException(status_code=422, detail="Level must be beginner, intermediate, advanced, or all.")
    if mode not in ("in_person", "online"):
        raise HTTPException(status_code=422, detail="Mode must be in_person or online.")
    if not (2 <= capacity <= 30):
        raise HTTPException(status_code=422, detail="Capacity must be between 2 and 30 attendees.")
    if not (0 <= credit_cost <= 10):
        raise HTTPException(status_code=422, detail="Credit cost must be between 0 and 10 credits.")
    if duration_minutes < 15:
        raise HTTPException(status_code=422, detail="Duration must be at least 15 minutes.")

    # 2. Starts_at validation (at least 1 hour ahead)
    if not starts_at_raw:
        raise HTTPException(status_code=422, detail="Start time (starts_at) is required.")
    try:
        starts_at_dt = parse_iso_datetime(starts_at_raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid date/time format: {e}")

    now_utc = datetime.now(timezone.utc)
    if (starts_at_dt - now_utc).total_seconds() < 3600:
        raise HTTPException(status_code=422, detail="Event start time must be at least 1 hour in the future.")

    # 3. Host lookup & guards
    host = get_user_profile(host_id)
    if not host:
        raise HTTPException(status_code=404, detail="Host user not found.")
    if host.get("fraud_flag") == "restricted":
        raise HTTPException(status_code=403, detail="Your account is restricted from hosting community events.")

    # In-person mode coordinate resolution
    if mode == "in_person":
        if lat is None or lon is None:
            lat = host.get("lat")
            lon = host.get("lon")
        if lat is None or lon is None:
            raise HTTPException(status_code=422, detail="In-person events require latitude and longitude coordinates. Please provide them or set your profile location.")
        if not city:
            city = host.get("city")
    else:
        # Online mode
        lat = None
        lon = None
        venue_address = None

    # Cap: max 3 open upcoming events per host
    upcoming_events = fetch_query(
        "SELECT id, starts_at FROM Events WHERE host_id = ? AND status = 'open'",
        (host_id,)
    )
    open_count = 0
    for ev in upcoming_events:
        try:
            if parse_iso_datetime(ev["starts_at"]) > now_utc:
                open_count += 1
        except Exception:
            pass
    if open_count >= 3:
        raise HTTPException(status_code=409, detail="Maximum 3 open upcoming events allowed per host. Complete or cancel existing events first.")

    # 4. Moderation check
    try:
        mod_result = chat_moderation(f"{title}\n{description}")
        if mod_result.get("is_flagged"):
            raise HTTPException(status_code=422, detail="Event title or description was flagged by automated content moderation.")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Moderation check skipped or failed: {e}")

    # 5. Insert event
    event_id = str(uuid.uuid4())
    starts_at_iso = starts_at_dt.isoformat()
    now_iso = now_utc.isoformat()

    run_query("""
        INSERT INTO Events (
            id, host_id, title, description, skill_name, category, level, mode,
            city, venue_name, venue_address, lat, lon, starts_at, duration_minutes,
            capacity, credit_cost, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
    """, (
        event_id, host_id, title, description, skill_name, category, level, mode,
        city, venue_name, venue_address, lat, lon, starts_at_iso, duration_minutes,
        capacity, credit_cost, now_iso
    ))

    return {
        "id": event_id,
        "host_id": host_id,
        "title": title,
        "description": description,
        "skill_name": skill_name,
        "category": category,
        "level": level,
        "mode": mode,
        "city": city,
        "venue_name": venue_name,
        "venue_address": venue_address,
        "lat": lat,
        "lon": lon,
        "starts_at": starts_at_iso,
        "duration_minutes": duration_minutes,
        "capacity": capacity,
        "credit_cost": credit_cost,
        "status": "open",
        "created_at": now_iso
    }


def get_events(
    user_id: str,
    city: Optional[str] = None,
    category: Optional[str] = None,
    skill: Optional[str] = None,
    mode: Optional[str] = None,
    max_km: Optional[float] = None,
    free_only: bool = False,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    sort: str = "starts_at",
    limit: int = 20,
    offset: int = 0
) -> Dict[str, Any]:
    """
    GET /api/events
    Returns list of upcoming open/full events matching filters. Privacy rule: venue_address excluded.
    """
    user = get_user_profile(user_id)
    user_lat = user.get("lat") if user else None
    user_lon = user.get("lon") if user else None

    # Fetch all candidate events
    raw_events = fetch_query("""
        SELECT e.*, u.name as host_name, u.trust_score as host_trust_score
        FROM Events e
        JOIN Users u ON e.host_id = u.id
        WHERE e.status IN ('open', 'full')
    """)

    now_utc = datetime.now(timezone.utc)
    filtered = []

    for ev in raw_events:
        # Check starts_at in future
        try:
            ev_dt = parse_iso_datetime(ev["starts_at"])
            if ev_dt <= now_utc:
                continue
        except Exception:
            continue

        # Filters
        if city and ev.get("city") and city.lower() not in ev["city"].lower():
            continue
        if category and ev.get("category") and category.lower() not in ev["category"].lower():
            continue
        if skill:
            skill_q = skill.lower()
            ev_skill = (ev.get("skill_name") or "").lower()
            ev_title = (ev.get("title") or "").lower()
            if skill_q not in ev_skill and skill_q not in ev_title:
                continue
        if mode and ev.get("mode") != mode:
            continue
        if free_only and (ev.get("credit_cost") or 0) > 0:
            continue
        if from_date:
            try:
                if ev_dt < parse_iso_datetime(from_date):
                    continue
            except Exception:
                pass
        if to_date:
            try:
                if ev_dt > parse_iso_datetime(to_date):
                    continue
            except Exception:
                pass

        # Distance calculation
        distance_km = None
        if ev.get("mode") == "in_person" and user_lat is not None and user_lon is not None and ev.get("lat") is not None and ev.get("lon") is not None:
            distance_km = round(haversine(user_lat, user_lon, ev["lat"], ev["lon"]), 2)

        if max_km is not None and ev.get("mode") == "in_person":
            if distance_km is None or distance_km > max_km:
                continue

        # Confirmed attendees & spots left
        c_rows = fetch_query("SELECT COUNT(*) as cnt FROM EventParticipants WHERE event_id = ? AND status = 'confirmed'", (ev["id"],))
        confirmed_count = c_rows[0]["cnt"] if c_rows else 0
        spots_left = max(0, ev["capacity"] - confirmed_count)

        # Current user's status
        p_rows = fetch_query("SELECT status FROM EventParticipants WHERE event_id = ? AND user_id = ?", (ev["id"], user_id))
        my_status = p_rows[0]["status"] if p_rows else None

        filtered.append({
            "id": ev["id"],
            "title": ev["title"],
            "skill_name": ev["skill_name"],
            "category": ev.get("category"),
            "level": ev.get("level", "all"),
            "mode": ev["mode"],
            "city": ev.get("city"),
            "venue_name": ev.get("venue_name"),
            # Privacy rule: venue_address is NEVER included in list responses
            "starts_at": ev["starts_at"],
            "duration_minutes": ev.get("duration_minutes", 60),
            "capacity": ev["capacity"],
            "confirmed_count": confirmed_count,
            "spots_left": spots_left,
            "credit_cost": ev.get("credit_cost", 0),
            "status": ev["status"],
            "host": {
                "id": ev["host_id"],
                "name": ev["host_name"],
                "trust_score": ev.get("host_trust_score", 0.0)
            },
            "distance_km": distance_km,
            "my_status": my_status,
            "_ev_dt": ev_dt
        })

    # Sort
    if sort == "distance":
        # Put items with distance first (sorted asc), then online/unknown distance items sorted by starts_at
        filtered.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0, x["_ev_dt"]))
    else:
        # Default: starts_at ascending
        filtered.sort(key=lambda x: x["_ev_dt"])

    total = len(filtered)
    limit = min(max(1, limit), 50)
    paged = filtered[offset:offset + limit]

    # Clean internal sort helper
    for item in paged:
        item.pop("_ev_dt", None)

    return {
        "events": paged,
        "total": total,
        "limit": limit,
        "offset": offset
    }


def get_recommended_events(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    GET /api/events/recommended
    Ranks upcoming events by overlap between user's NEEDED skills and event text, boosted by proximity.
    """
    user = get_user_profile(user_id)
    user_lat = user.get("lat") if user else None
    user_lon = user.get("lon") if user else None

    # Get user's needed skills
    needed_skills_rows = fetch_query("SELECT skill_name FROM Skills WHERE user_id = ? AND type = 'needed'", (user_id,))
    needed_skills = [row["skill_name"].strip().lower() for row in needed_skills_rows if row.get("skill_name")]

    # Get all upcoming events
    events_data = get_events(user_id, limit=50)["events"]
    if not events_data:
        return []

    scored = []
    for ev in events_data:
        match_score = 0
        matched_skill = None
        ev_text = f"{ev.get('skill_name', '')} {ev.get('title', '')} {ev.get('category', '')}".lower()

        # Keyword overlap with needed skills
        for n_skill in needed_skills:
            if n_skill in ev_text:
                match_score += 15
                if not matched_skill:
                    matched_skill = n_skill

        # Distance bonus
        dist = ev.get("distance_km")
        if dist is not None:
            match_score += max(0, 10 - min(dist, 50) / 5)
        elif ev.get("mode") == "online":
            match_score += 5  # Online accessible

        # Formulate reason
        if matched_skill:
            reason = f"Matches a skill you want to learn: {matched_skill.title()}"
        elif dist is not None:
            reason = f"Upcoming event near you (📍 {dist} km away)"
        else:
            reason = "Popular upcoming skill session"

        ev_copy = dict(ev)
        ev_copy["reason"] = reason
        ev_copy["_rec_score"] = match_score
        scored.append(ev_copy)

    # Sort descending by recommendation score
    scored.sort(key=lambda x: x["_rec_score"], reverse=True)
    top_items = scored[:min(limit, 10)]
    for it in top_items:
        it.pop("_rec_score", None)

    return top_items


def get_event_detail(event_id: str, user_id: str) -> Dict[str, Any]:
    """
    GET /api/events/{id}
    Returns full details. Privacy rule: venue_address only for host and confirmed/attended attendees.
    """
    rows = fetch_query("""
        SELECT e.*, u.name as host_name, u.trust_score as host_trust_score, u.bio as host_bio
        FROM Events e
        JOIN Users u ON e.host_id = u.id
        WHERE e.id = ?
    """, (event_id,))

    if not rows:
        raise HTTPException(status_code=404, detail="Event not found.")
    ev = rows[0]

    # Current user's participant status
    p_rows = fetch_query("SELECT status, credits_held, waitlist_position FROM EventParticipants WHERE event_id = ? AND user_id = ?", (event_id, user_id))
    my_status = p_rows[0]["status"] if p_rows else None
    credits_held = p_rows[0]["credits_held"] if p_rows else 0
    waitlist_position = p_rows[0]["waitlist_position"] if p_rows else None

    is_host = (ev["host_id"] == user_id)

    # Privacy Rule for venue_address
    venue_address = ev.get("venue_address") if (is_host or my_status in ("confirmed", "attended")) else None

    # Attendees list
    all_participants = fetch_query("""
        SELECT p.user_id, u.name, p.status, p.waitlist_position, p.joined_at
        FROM EventParticipants p
        JOIN Users u ON p.user_id = u.id
        WHERE p.event_id = ?
        ORDER BY p.joined_at ASC
    """, (event_id,))

    participants_view = []
    for p in all_participants:
        # Non-hosts only see confirmed and attended participants
        if is_host or p["status"] in ("confirmed", "attended"):
            participants_view.append({
                "user_id": p["user_id"],
                "name": p["name"],
                "status": p["status"],
                "waitlist_position": p["waitlist_position"] if is_host else None
            })

    confirmed_count = len([p for p in all_participants if p["status"] == "confirmed"])
    spots_left = max(0, ev["capacity"] - confirmed_count)

    # Distance calculation
    user = get_user_profile(user_id)
    distance_km = None
    if ev.get("mode") == "in_person" and user and user.get("lat") is not None and user.get("lon") is not None and ev.get("lat") is not None and ev.get("lon") is not None:
        distance_km = round(haversine(user["lat"], user["lon"], ev["lat"], ev["lon"]), 2)

    return {
        "id": ev["id"],
        "title": ev["title"],
        "description": ev["description"],
        "skill_name": ev["skill_name"],
        "category": ev.get("category"),
        "level": ev.get("level", "all"),
        "mode": ev["mode"],
        "city": ev.get("city"),
        "venue_name": ev.get("venue_name"),
        "venue_address": venue_address,
        "lat": ev.get("lat"),
        "lon": ev.get("lon"),
        "starts_at": ev["starts_at"],
        "duration_minutes": ev.get("duration_minutes", 60),
        "capacity": ev["capacity"],
        "confirmed_count": confirmed_count,
        "spots_left": spots_left,
        "credit_cost": ev.get("credit_cost", 0),
        "status": ev["status"],
        "cancel_reason": ev.get("cancel_reason"),
        "created_at": ev.get("created_at"),
        "completed_at": ev.get("completed_at"),
        "host": {
            "id": ev["host_id"],
            "name": ev["host_name"],
            "trust_score": ev.get("host_trust_score", 0.0),
            "bio": ev.get("host_bio")
        },
        "distance_km": distance_km,
        "my_status": my_status,
        "my_credits_held": credits_held,
        "my_waitlist_position": waitlist_position,
        "is_host": is_host,
        "participants": participants_view
    }


def join_event(event_id: str, user_id: str) -> Dict[str, Any]:
    """
    POST /api/events/{id}/join
    Runs in a single BEGIN IMMEDIATE transaction to prevent race conditions on seats.
    """
    user = get_user_profile(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.get("fraud_flag") == "restricted":
        raise HTTPException(status_code=403, detail="Your account is restricted from joining events.")

    conn = _get_conn()
    conn.isolation_level = None  # Autocommit off for explicit BEGIN IMMEDIATE
    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()

        # 1. Fetch Event
        c.execute("SELECT * FROM Events WHERE id = ?", (event_id,))
        ev_row = c.fetchone()
        if not ev_row:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=404, detail="Event not found.")

        # Convert to dict
        columns = [desc[0] for desc in c.description]
        event = dict(zip(columns, ev_row))

        # Guards
        if event["host_id"] == user_id:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=403, detail="Host cannot join their own event.")

        if event["status"] in ("cancelled", "completed"):
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=409, detail=f"Cannot join an event that is {event['status']}.")

        now_utc = datetime.now(timezone.utc)
        try:
            ev_starts = parse_iso_datetime(event["starts_at"])
            if ev_starts <= now_utc:
                conn.execute("ROLLBACK")
                raise HTTPException(status_code=409, detail="Event has already started.")
        except HTTPException:
            raise
        except Exception:
            pass

        # 2. Check existing active participation
        c.execute("SELECT status FROM EventParticipants WHERE event_id = ? AND user_id = ?", (event_id, user_id))
        existing_part = c.fetchone()
        if existing_part and existing_part[0] in ("confirmed", "waitlisted"):
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=409, detail="You are already joined or waitlisted for this event.")

        # 3. Check capacity & confirmed seats
        c.execute("SELECT COUNT(*) FROM EventParticipants WHERE event_id = ? AND status = 'confirmed'", (event_id,))
        confirmed_count = c.fetchone()[0]
        capacity = event["capacity"]
        credit_cost = event["credit_cost"] or 0

        # Check current user available wallet balance
        c.execute("SELECT wallet_balance FROM Users WHERE id = ?", (user_id,))
        user_balance = c.fetchone()[0]

        if confirmed_count < capacity:
            # Confirmed seat available!
            if credit_cost > 0:
                if user_balance < credit_cost:
                    conn.execute("ROLLBACK")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient credits. You need {credit_cost} credits to join (Available balance: {user_balance})."
                    )
                # Deduct credits from user
                c.execute("UPDATE Users SET wallet_balance = wallet_balance - ? WHERE id = ?", (credit_cost, user_id))

            # Upsert participant row as confirmed
            part_id = str(uuid.uuid4())
            c.execute("""
                INSERT INTO EventParticipants (id, event_id, user_id, status, credits_held, waitlist_position, joined_at)
                VALUES (?, ?, ?, 'confirmed', ?, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(event_id, user_id) DO UPDATE SET
                    status = 'confirmed',
                    credits_held = excluded.credits_held,
                    waitlist_position = NULL,
                    joined_at = CURRENT_TIMESTAMP
            """, (part_id, event_id, user_id, credit_cost))

            # If capacity is now full, update event status
            if confirmed_count + 1 >= capacity:
                c.execute("UPDATE Events SET status = 'full' WHERE id = ?", (event_id,))

            conn.execute("COMMIT")
            status_res = "confirmed"
            waitlist_pos = None
            held_res = credit_cost
        else:
            # Event is full: add to Waitlist (do not take credits yet!)
            c.execute("SELECT COALESCE(MAX(waitlist_position), 0) + 1 FROM EventParticipants WHERE event_id = ? AND status = 'waitlisted'", (event_id,))
            next_pos = c.fetchone()[0]

            part_id = str(uuid.uuid4())
            c.execute("""
                INSERT INTO EventParticipants (id, event_id, user_id, status, credits_held, waitlist_position, joined_at)
                VALUES (?, ?, ?, 'waitlisted', 0, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(event_id, user_id) DO UPDATE SET
                    status = 'waitlisted',
                    credits_held = 0,
                    waitlist_position = excluded.waitlist_position,
                    joined_at = CURRENT_TIMESTAMP
            """, (part_id, event_id, user_id, next_pos))

            # Ensure event status is marked full
            c.execute("UPDATE Events SET status = 'full' WHERE id = ?", (event_id,))

            conn.execute("COMMIT")
            status_res = "waitlisted"
            waitlist_pos = next_pos
            held_res = 0

    except HTTPException:
        raise
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        logger.error(f"Error in join_event: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to join event: {str(e)}")
    finally:
        conn.close()

    # Post-transaction notification
    host_id = event["host_id"]
    user_name = user.get("name", "An attendee")
    if status_res == "confirmed":
        msg = f"👤 {user_name} joined your event: '{event['title']}'."
    else:
        msg = f"⏳ {user_name} joined the waitlist (#{waitlist_pos}) for your event: '{event['title']}'."
    send_event_notification(host_id, msg)

    return {
        "status": status_res,
        "event_id": event_id,
        "credits_held": held_res,
        "waitlist_position": waitlist_pos
    }


def leave_event(event_id: str, user_id: str) -> Dict[str, Any]:
    """
    POST /api/events/{id}/leave
    Attendee cancels spot. Allowed until 2 hours before starts_at.
    Refunds held credits and promotes earliest eligible waitlisted user in one transaction.
    """
    conn = _get_conn()
    conn.isolation_level = None
    promoted_user_id = None
    skipped_user_ids = []
    refunded_credits = 0

    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()

        # 1. Fetch Event
        c.execute("SELECT * FROM Events WHERE id = ?", (event_id,))
        ev_row = c.fetchone()
        if not ev_row:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=404, detail="Event not found.")

        columns = [desc[0] for desc in c.description]
        event = dict(zip(columns, ev_row))

        # Check 2-hour cutoff rule
        now_utc = datetime.now(timezone.utc)
        ev_starts = parse_iso_datetime(event["starts_at"])
        if (ev_starts - now_utc).total_seconds() < 2 * 3600:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=409, detail="Cannot leave an event within 2 hours of start time.")

        # 2. Check participant row
        c.execute("SELECT id, status, credits_held FROM EventParticipants WHERE event_id = ? AND user_id = ?", (event_id, user_id))
        part_row = c.fetchone()
        if not part_row or part_row[1] not in ("confirmed", "waitlisted"):
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=409, detail="You are not an active participant in this event.")

        part_id, part_status, credits_held = part_row

        if part_status == "confirmed":
            # Refund attendee's held credits
            if credits_held > 0:
                c.execute("UPDATE Users SET wallet_balance = wallet_balance + ? WHERE id = ?", (credits_held, user_id))
                refunded_credits = credits_held

            # Mark row as cancelled
            c.execute("UPDATE EventParticipants SET status = 'cancelled', credits_held = 0, waitlist_position = NULL WHERE id = ?", (part_id,))

            # Promote earliest eligible waitlisted user
            credit_cost = event["credit_cost"] or 0
            c.execute("""
                SELECT p.id, p.user_id, u.wallet_balance
                FROM EventParticipants p
                JOIN Users u ON p.user_id = u.id
                WHERE p.event_id = ? AND p.status = 'waitlisted'
                ORDER BY p.waitlist_position ASC
            """, (event_id,))
            waitlist_entries = c.fetchall()

            seat_filled = False
            for wl_id, wl_user_id, wl_balance in waitlist_entries:
                if credit_cost > 0 and wl_balance < credit_cost:
                    # Cannot afford: skip and mark waitlist entry cancelled
                    c.execute("UPDATE EventParticipants SET status = 'cancelled', waitlist_position = NULL WHERE id = ?", (wl_id,))
                    skipped_user_ids.append(wl_user_id)
                else:
                    # Promote!
                    if credit_cost > 0:
                        c.execute("UPDATE Users SET wallet_balance = wallet_balance - ? WHERE id = ?", (credit_cost, wl_user_id))
                    c.execute("UPDATE EventParticipants SET status = 'confirmed', credits_held = ?, waitlist_position = NULL WHERE id = ?", (credit_cost, wl_id))
                    promoted_user_id = wl_user_id
                    seat_filled = True
                    break

            # Renumber remaining waitlist
            c.execute("SELECT id FROM EventParticipants WHERE event_id = ? AND status = 'waitlisted' ORDER BY waitlist_position ASC", (event_id,))
            rem_wl = c.fetchall()
            for idx, (rw_id,) in enumerate(rem_wl):
                c.execute("UPDATE EventParticipants SET waitlist_position = ? WHERE id = ?", (idx + 1, rw_id))

            # If no waitlist candidate filled the seat, set event status back to open
            if not seat_filled:
                c.execute("UPDATE Events SET status = 'open' WHERE id = ?", (event_id,))

        else:
            # Waitlisted user leaves
            c.execute("UPDATE EventParticipants SET status = 'cancelled', credits_held = 0, waitlist_position = NULL WHERE id = ?", (part_id,))
            # Renumber remaining waitlist
            c.execute("SELECT id FROM EventParticipants WHERE event_id = ? AND status = 'waitlisted' ORDER BY waitlist_position ASC", (event_id,))
            rem_wl = c.fetchall()
            for idx, (rw_id,) in enumerate(rem_wl):
                c.execute("UPDATE EventParticipants SET waitlist_position = ? WHERE id = ?", (idx + 1, rw_id))

        conn.execute("COMMIT")

    except HTTPException:
        raise
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        logger.error(f"Error in leave_event: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to leave event: {str(e)}")
    finally:
        conn.close()

    # Post-transaction notifications
    if promoted_user_id:
        send_event_notification(
            promoted_user_id,
            f"🎉 Great news! A spot opened up and you are now confirmed for '{event['title']}'!"
        )
    for skipped_id in skipped_user_ids:
        send_event_notification(
            skipped_id,
            f"A spot opened up for '{event['title']}', but you had insufficient credits to claim it."
        )

    send_event_notification(event["host_id"], f"An attendee left your event: '{event['title']}'.")

    return {
        "status": "cancelled",
        "refunded_credits": refunded_credits,
        "promoted_user_id": promoted_user_id
    }


def cancel_event(event_id: str, host_id: str, cancel_reason: str) -> Dict[str, Any]:
    """
    POST /api/events/{id}/cancel (Host only)
    Refunds all confirmed attendees, marks event cancelled, notifies all members.
    """
    cancel_reason = (cancel_reason or "").strip()
    if len(cancel_reason) < 3:
        raise HTTPException(status_code=422, detail="A valid cancellation reason is required (at least 3 characters).")

    conn = _get_conn()
    conn.isolation_level = None
    affected_user_ids = []

    try:
        conn.execute("BEGIN IMMEDIATE")
        c = conn.cursor()

        # Fetch event
        c.execute("SELECT * FROM Events WHERE id = ?", (event_id,))
        ev_row = c.fetchone()
        if not ev_row:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=404, detail="Event not found.")

        columns = [desc[0] for desc in c.description]
        event = dict(zip(columns, ev_row))

        if event["host_id"] != host_id:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=403, detail="Only the event host can cancel this event.")

        if event["status"] in ("completed", "cancelled"):
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=409, detail=f"Cannot cancel an event that is already {event['status']}.")

        # Fetch all active participants
        c.execute("SELECT user_id, status, credits_held FROM EventParticipants WHERE event_id = ? AND status IN ('confirmed', 'waitlisted')", (event_id,))
        active_parts = c.fetchall()

        for u_id, p_status, credits_held in active_parts:
            affected_user_ids.append(u_id)
            if p_status == "confirmed" and credits_held > 0:
                c.execute("UPDATE Users SET wallet_balance = wallet_balance + ? WHERE id = ?", (credits_held, u_id))

        # Mark all participants cancelled
        c.execute("""
            UPDATE EventParticipants
            SET status = 'cancelled', credits_held = 0, waitlist_position = NULL
            WHERE event_id = ? AND status IN ('confirmed', 'waitlisted')
        """, (event_id,))

        # Update event status
        c.execute("UPDATE Events SET status = 'cancelled', cancel_reason = ? WHERE id = ?", (cancel_reason, event_id))

        conn.execute("COMMIT")

    except HTTPException:
        raise
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        logger.error(f"Error in cancel_event: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel event: {str(e)}")
    finally:
        conn.close()

    # Notify all attendees
    for uid in affected_user_ids:
        send_event_notification(
            uid,
            f"⚠️ Event '{event['title']}' was cancelled by the host. Reason: {cancel_reason}. Any held credits have been refunded."
        )

    return {
        "status": "cancelled",
        "cancel_reason": cancel_reason,
        "affected_attendees_count": len(affected_user_ids)
    }


def get_my_events(user_id: str) -> Dict[str, Any]:
    """
    GET /api/events/mine
    Returns hosted and joined events split into upcoming and past.
    """
    now_utc = datetime.now(timezone.utc)

    # 1. Hosted events
    hosted_rows = fetch_query("""
        SELECT e.*, u.name as host_name, u.trust_score as host_trust_score
        FROM Events e
        JOIN Users u ON e.host_id = u.id
        WHERE e.host_id = ?
        ORDER BY e.starts_at ASC
    """, (user_id,))

    hosted_upcoming = []
    hosted_past = []

    for ev in hosted_rows:
        # Confirmed count
        c_cnt = fetch_query("SELECT COUNT(*) as cnt FROM EventParticipants WHERE event_id = ? AND status = 'confirmed'", (ev["id"],))[0]["cnt"]
        spots_left = max(0, ev["capacity"] - c_cnt)
        item = {
            "id": ev["id"],
            "title": ev["title"],
            "skill_name": ev["skill_name"],
            "category": ev.get("category"),
            "level": ev.get("level", "all"),
            "mode": ev["mode"],
            "city": ev.get("city"),
            "venue_name": ev.get("venue_name"),
            "venue_address": ev.get("venue_address"),  # Host always sees address
            "starts_at": ev["starts_at"],
            "duration_minutes": ev.get("duration_minutes", 60),
            "capacity": ev["capacity"],
            "confirmed_count": c_cnt,
            "spots_left": spots_left,
            "credit_cost": ev.get("credit_cost", 0),
            "status": ev["status"],
            "cancel_reason": ev.get("cancel_reason"),
            "is_host": True
        }
        try:
            ev_dt = parse_iso_datetime(ev["starts_at"])
            if ev["status"] == "open" or (ev["status"] == "full" and ev_dt > now_utc):
                hosted_upcoming.append(item)
            else:
                hosted_past.append(item)
        except Exception:
            hosted_past.append(item)

    # 2. Joined events
    joined_rows = fetch_query("""
        SELECT e.*, u.name as host_name, u.trust_score as host_trust_score,
               p.status as my_status, p.credits_held as my_credits_held, p.waitlist_position as my_waitlist_position
        FROM EventParticipants p
        JOIN Events e ON p.event_id = e.id
        JOIN Users u ON e.host_id = u.id
        WHERE p.user_id = ?
        ORDER BY e.starts_at ASC
    """, (user_id,))

    joined_upcoming = []
    joined_past = []

    for ev in joined_rows:
        c_cnt = fetch_query("SELECT COUNT(*) as cnt FROM EventParticipants WHERE event_id = ? AND status = 'confirmed'", (ev["id"],))[0]["cnt"]
        spots_left = max(0, ev["capacity"] - c_cnt)
        my_status = ev["my_status"]
        venue_address = ev.get("venue_address") if my_status in ("confirmed", "attended") else None

        item = {
            "id": ev["id"],
            "title": ev["title"],
            "skill_name": ev["skill_name"],
            "category": ev.get("category"),
            "level": ev.get("level", "all"),
            "mode": ev["mode"],
            "city": ev.get("city"),
            "venue_name": ev.get("venue_name"),
            "venue_address": venue_address,
            "starts_at": ev["starts_at"],
            "duration_minutes": ev.get("duration_minutes", 60),
            "capacity": ev["capacity"],
            "confirmed_count": c_cnt,
            "spots_left": spots_left,
            "credit_cost": ev.get("credit_cost", 0),
            "status": ev["status"],
            "my_status": my_status,
            "my_credits_held": ev["my_credits_held"],
            "my_waitlist_position": ev["my_waitlist_position"],
            "host": {
                "id": ev["host_id"],
                "name": ev["host_name"],
                "trust_score": ev.get("host_trust_score", 0.0)
            },
            "is_host": False
        }

        try:
            ev_dt = parse_iso_datetime(ev["starts_at"])
            if ev["status"] in ("open", "full") and ev_dt > now_utc and my_status in ("confirmed", "waitlisted"):
                joined_upcoming.append(item)
            else:
                joined_past.append(item)
        except Exception:
            joined_past.append(item)

    return {
        "hosted": {
            "upcoming": hosted_upcoming,
            "past": hosted_past
        },
        "joined": {
            "upcoming": joined_upcoming,
            "past": joined_past
        }
    }
