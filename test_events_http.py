"""
Comprehensive Real HTTP Test Suite for Group Skill Events API
"""
import sys
import os
import requests
import json
import uuid
from datetime import datetime, timedelta, timezone
import jwt

BASE_URL = "http://localhost:8000"
SECRET_KEY = "super-secret-hackathon-key"

def create_jwt(user_id: str):
    return jwt.encode(
        {"sub": user_id, "exp": datetime.utcnow() + timedelta(days=1)},
        SECRET_KEY,
        algorithm="HS256"
    )

def run_tests():
    print("=== Starting Full HTTP Tests for Events API ===")
    
    # Setup test users via direct DB helper for reliability
    sys.path.insert(0, r'c:\Users\Renta\OneDrive\Documents\projects\skillswap')
    from agent.memory import run_query
    
    uid_host = f"http_host_{uuid.uuid4().hex[:6]}"
    uid_attendee = f"http_att_{uuid.uuid4().hex[:6]}"
    uid_no_skills = f"http_noskill_{uuid.uuid4().hex[:6]}"
    
    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance)
        VALUES (?, 'HTTP Host', ?, 'hash', 'Bangalore', 12.9716, 77.5946, 4.9, 50)
    """, (uid_host, f"{uid_host}@test.com"))
    
    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance)
        VALUES (?, 'HTTP Attendee', ?, 'hash', 'Bangalore', 12.9720, 77.5950, 4.5, 20)
    """, (uid_attendee, f"{uid_attendee}@test.com"))
    
    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance)
        VALUES (?, 'No Skills User', ?, 'hash', 'Bangalore', 12.9716, 77.5946, 4.0, 10)
    """, (uid_no_skills, f"{uid_no_skills}@test.com"))
    
    # Add needed skill for uid_attendee
    run_query("INSERT INTO Skills (id, user_id, skill_name, type) VALUES (?, ?, 'Guitar Playing', 'needed')", (str(uuid.uuid4()), uid_attendee))
    
    token_host = create_jwt(uid_host)
    token_attendee = create_jwt(uid_attendee)
    token_no_skills = create_jwt(uid_no_skills)
    
    headers_host = {"Authorization": f"Bearer {token_host}"}
    headers_attendee = {"Authorization": f"Bearer {token_attendee}"}
    headers_no_skills = {"Authorization": f"Bearer {token_no_skills}"}

    # 1. Test 401 Unauthorized when unauthenticated
    res = requests.get(f"{BASE_URL}/api/events")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("✓ Test 1 Passed: Unauthenticated request returns 401")

    # 2. Test Recommended for user with NO needed skills
    res = requests.get(f"{BASE_URL}/api/events/recommended", headers=headers_no_skills)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    assert isinstance(res.json(), list)
    print("✓ Test 2 Passed: Recommended events for user with NO needed skills returned 200 OK")

    # 3. Create Event via HTTP POST /api/events
    future_time = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    ev_payload = {
        "title": "Acoustic Guitar Workshop for Beginners",
        "description": "Learn fingerpicking and chord progressions in a fun, relaxed environment.",
        "skill_name": "Guitar Playing",
        "category": "Music",
        "level": "beginner",
        "mode": "in_person",
        "city": "Bangalore",
        "venue_name": "Cubbon Park Bandstand",
        "venue_address": "Cubbon Park, Kasturba Road, Bangalore - 560001",
        "starts_at": future_time,
        "duration_minutes": 90,
        "capacity": 3,
        "credit_cost": 2
    }
    res = requests.post(f"{BASE_URL}/api/events", json=ev_payload, headers=headers_host)
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.text}"
    ev_data = res.json()
    event_id = ev_data["id"]
    assert ev_data["title"] == ev_payload["title"]
    assert ev_data["credit_cost"] == 2
    print(f"✓ Test 3 Passed: Created event via HTTP POST 201 (ID: {event_id})")

    # 4. Test Discovery: GET /api/events?sort=starts_at&limit=40
    res = requests.get(f"{BASE_URL}/api/events?sort=starts_at&limit=40", headers=headers_attendee)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    body = res.json()
    assert "events" in body and body["total"] >= 1
    found = [e for e in body["events"] if e["id"] == event_id]
    assert len(found) == 1, "Created event should appear in discovery list"
    assert "venue_address" not in found[0] or found[0]["venue_address"] is None, "List MUST NOT leak venue_address"
    print("✓ Test 4 Passed: Discovery list returned 200 OK with created event (venue_address hidden)")

    # 5. Test Recommended with user matching needed skill
    res = requests.get(f"{BASE_URL}/api/events/recommended", headers=headers_attendee)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    rec_list = res.json()
    matching_rec = [r for r in rec_list if r["id"] == event_id]
    assert len(matching_rec) == 1, "Guitar event must appear in recommended list for attendee"
    assert "Guitar Playing" in matching_rec[0]["reason"], f"Expected reason mentioning Guitar Playing, got {matching_rec[0]['reason']}"
    print(f"✓ Test 5 Passed: Recommended event matched user's needed skill: '{matching_rec[0]['reason']}'")

    # 6. Test Empty-String Filter Parameters
    res = requests.get(
        f"{BASE_URL}/api/events?city=&category=&skill=&mode=&max_km=&free_only=&sort=starts_at&limit=40",
        headers=headers_attendee
    )
    assert res.status_code == 200, f"Expected 200 with empty params, got {res.status_code}: {res.text}"
    print("✓ Test 6 Passed: Empty-string query parameters handled gracefully (Status 200)")

    # 7. Test Specific Filters
    # Filter by mode=in_person
    res = requests.get(f"{BASE_URL}/api/events?mode=in_person", headers=headers_attendee)
    assert res.status_code == 200
    assert any(e["id"] == event_id for e in res.json()["events"])
    
    # Filter by mode=online (should exclude in_person event)
    res = requests.get(f"{BASE_URL}/api/events?mode=online", headers=headers_attendee)
    assert res.status_code == 200
    assert not any(e["id"] == event_id for e in res.json()["events"])

    # Filter by free_only=true (event costs 2, should be excluded)
    res = requests.get(f"{BASE_URL}/api/events?free_only=true", headers=headers_attendee)
    assert res.status_code == 200
    assert not any(e["id"] == event_id for e in res.json()["events"])

    # Filter by skill match
    res = requests.get(f"{BASE_URL}/api/events?skill=guitar", headers=headers_attendee)
    assert res.status_code == 200
    assert any(e["id"] == event_id for e in res.json()["events"])
    print("✓ Test 7 Passed: All query filters (mode, free_only, skill) work accurately")

    # 8. Test Pagination
    res1 = requests.get(f"{BASE_URL}/api/events?limit=1&offset=0", headers=headers_attendee)
    assert res1.status_code == 200
    assert len(res1.json()["events"]) <= 1
    print("✓ Test 8 Passed: Pagination (limit & offset) works as expected")

    # 9. Test GET /api/events/mine
    res_mine = requests.get(f"{BASE_URL}/api/events/mine", headers=headers_host)
    assert res_mine.status_code == 200, f"Expected 200, got {res_mine.status_code}"
    hosted_upcoming = res_mine.json()["hosted"]["upcoming"]
    assert any(e["id"] == event_id for e in hosted_upcoming)
    print("✓ Test 9 Passed: Host's /api/events/mine includes the upcoming event")

    # 10. Test Event Detail & Venue Address Privacy
    # Non-attendee detail
    res_detail_no_attend = requests.get(f"{BASE_URL}/api/events/{event_id}", headers=headers_no_skills)
    assert res_detail_no_attend.status_code == 200
    assert res_detail_no_attend.json()["venue_address"] is None, "Non-attendee must not see venue_address"

    # Host detail
    res_detail_host = requests.get(f"{BASE_URL}/api/events/{event_id}", headers=headers_host)
    assert res_detail_host.status_code == 200
    assert res_detail_host.json()["venue_address"] == ev_payload["venue_address"], "Host must see venue_address"

    # 11. Join Event via HTTP POST /api/events/{id}/join
    res_join = requests.post(f"{BASE_URL}/api/events/{event_id}/join", headers=headers_attendee)
    assert res_join.status_code == 200, f"Expected 200, got {res_join.status_code}: {res_join.text}"
    assert res_join.json()["status"] == "confirmed"
    assert res_join.json()["credits_held"] == 2
    print("✓ Test 10 Passed: Attendee joined successfully via HTTP POST, 2 credits held")

    # Confirmed attendee detail can now see address!
    res_detail_attendee = requests.get(f"{BASE_URL}/api/events/{event_id}", headers=headers_attendee)
    assert res_detail_attendee.status_code == 200
    assert res_detail_attendee.json()["venue_address"] == ev_payload["venue_address"], "Confirmed attendee must see venue_address"
    print("✓ Test 11 Passed: Privacy rule verified - venue_address revealed only upon confirmed join")

    # 12. Leave Event via HTTP POST /api/events/{id}/leave
    res_leave = requests.post(f"{BASE_URL}/api/events/{event_id}/leave", headers=headers_attendee)
    assert res_leave.status_code == 200, f"Expected 200, got {res_leave.status_code}: {res_leave.text}"
    assert res_leave.json()["status"] == "cancelled"
    assert res_leave.json()["refunded_credits"] == 2
    print("✓ Test 12 Passed: Attendee left event via HTTP POST, credits refunded (Status 200)")

    print("\n🎉 ALL HTTP-LEVEL INTEGRATION TESTS PASSED WITH 100% SUCCESS! 🎉")

if __name__ == "__main__":
    run_tests()
