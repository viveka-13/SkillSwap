"""
Comprehensive Test Suite for Part A: Group Skill Events
"""
import sys
import os
sys.path.insert(0, r'c:\Users\Renta\OneDrive\Documents\projects\skillswap')
os.chdir(r'c:\Users\Renta\OneDrive\Documents\projects\skillswap')

import uuid
import time
import threading
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from agent.memory import run_query, fetch_query
from agent.events import (
    create_event, get_events, get_recommended_events, get_event_detail,
    join_event, leave_event, cancel_event, get_my_events
)

def run_tests():
    print("=== Starting Part A Group Events Tests ===")

    # 1. Setup test users
    uid_host = f"test_host_{uuid.uuid4().hex[:6]}"
    uid_u1 = f"test_user1_{uuid.uuid4().hex[:6]}"
    uid_u2 = f"test_user2_{uuid.uuid4().hex[:6]}"
    uid_u3 = f"test_user3_{uuid.uuid4().hex[:6]}"
    uid_broke = f"test_broke_{uuid.uuid4().hex[:6]}"
    uid_restricted = f"test_restr_{uuid.uuid4().hex[:6]}"

    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance, fraud_flag)
        VALUES (?, 'Host User', ?, 'hash', 'Bangalore', 12.9716, 77.5946, 4.8, 20, NULL)
    """, (uid_host, f"{uid_host}@test.com"))

    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance, fraud_flag)
        VALUES (?, 'Attendee One', ?, 'hash', 'Bangalore', 12.9720, 77.5950, 4.5, 10, NULL)
    """, (uid_u1, f"{uid_u1}@test.com"))

    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance, fraud_flag)
        VALUES (?, 'Attendee Two', ?, 'hash', 'Bangalore', 12.9730, 77.5960, 4.2, 10, NULL)
    """, (uid_u2, f"{uid_u2}@test.com"))

    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance, fraud_flag)
        VALUES (?, 'Attendee Three', ?, 'hash', 'Bangalore', 12.9740, 77.5970, 4.0, 10, NULL)
    """, (uid_u3, f"{uid_u3}@test.com"))

    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance, fraud_flag)
        VALUES (?, 'Broke Attendee', ?, 'hash', 'Bangalore', 12.9716, 77.5946, 3.5, 0, NULL)
    """, (uid_broke, f"{uid_broke}@test.com"))

    run_query("""
        INSERT INTO Users (id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance, fraud_flag)
        VALUES (?, 'Restricted User', ?, 'hash', 'Bangalore', 12.9716, 77.5946, 2.0, 10, 'restricted')
    """, (uid_restricted, f"{uid_restricted}@test.com"))

    # Add needed skill for user1 to test recommendation
    run_query("INSERT INTO Skills (id, user_id, skill_name, type) VALUES (?, ?, 'Italian Cooking', 'needed')", (str(uuid.uuid4()), uid_u1))

    print("Users initialized.")

    # 2. Test Create Event Validation & Restrictions
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    soon_time = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    # Reject past/soon
    try:
        create_event(uid_host, {
            "title": "Cooking Class", "description": "Learn to cook pasta",
            "skill_name": "Italian Cooking", "mode": "in_person",
            "starts_at": soon_time, "capacity": 2, "credit_cost": 2
        })
        assert False, "Should have failed for starts_at < 1hr"
    except HTTPException as e:
        assert e.status_code == 422
        print("✓ Passed: Rejected start time within 1 hour")

    # Reject restricted host
    try:
        create_event(uid_restricted, {
            "title": "Cooking Class", "description": "Learn to cook pasta",
            "skill_name": "Italian Cooking", "mode": "in_person",
            "starts_at": future_time, "capacity": 2, "credit_cost": 2
        })
        assert False, "Should have failed for restricted user"
    except HTTPException as e:
        assert e.status_code == 403
        print("✓ Passed: Rejected restricted user from hosting")

    # Create valid event
    ev1 = create_event(uid_host, {
        "title": "Master Italian Cooking",
        "description": "Authentic handmade pasta and sauces masterclass.",
        "skill_name": "Italian Cooking",
        "category": "Culinary",
        "level": "beginner",
        "mode": "in_person",
        "venue_name": "Community Kitchen Central",
        "venue_address": "123 Secret Kitchen Alley, Suite 4",
        "starts_at": future_time,
        "duration_minutes": 90,
        "capacity": 2,  # Exactly 2 seats!
        "credit_cost": 3
    })
    ev1_id = ev1["id"]
    print(f"✓ Passed: Event created successfully (ID: {ev1_id})")

    # 3. Test Host cannot join own event
    try:
        join_event(ev1_id, uid_host)
        assert False, "Host should not be able to join own event"
    except HTTPException as e:
        assert e.status_code == 403
        print("✓ Passed: Host cannot join own event")

    # 4. Test Insufficient Credits
    try:
        join_event(ev1_id, uid_broke)
        assert False, "Broke user should not be able to join"
    except HTTPException as e:
        assert e.status_code == 400
        # verify balance unchanged
        b = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (uid_broke,))[0]["wallet_balance"]
        assert b == 0
        p = fetch_query("SELECT * FROM EventParticipants WHERE event_id = ? AND user_id = ?", (ev1_id, uid_broke))
        assert len(p) == 0
        print("✓ Passed: Insufficient credits rejected with 400 and no row created")

    # 5. Test Join with Seat Available
    res_u1 = join_event(ev1_id, uid_u1)
    assert res_u1["status"] == "confirmed"
    assert res_u1["credits_held"] == 3
    # check balance deducted from 10 to 7
    bal_u1 = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (uid_u1,))[0]["wallet_balance"]
    assert bal_u1 == 7
    print("✓ Passed: User 1 joined, status=confirmed, 3 credits held, balance=7")

    # 6. Test Duplicate Join
    try:
        join_event(ev1_id, uid_u1)
        assert False, "Duplicate join should fail"
    except HTTPException as e:
        assert e.status_code == 409
        print("✓ Passed: Duplicate join rejected with 409")

    # 7. Test Concurrency / Race Condition on Last Seat
    # Capacity is 2, 1 seat left. Both User 2 and User 3 attempt to join simultaneously!
    results = {}
    errors = {}
    def try_join(uid):
        try:
            results[uid] = join_event(ev1_id, uid)
        except Exception as ex:
            errors[uid] = ex

    t2 = threading.Thread(target=try_join, args=(uid_u2,))
    t3 = threading.Thread(target=try_join, args=(uid_u3,))
    t2.start(); t3.start()
    t2.join(); t3.join()

    # One must be confirmed, one must be waitlisted!
    statuses = [results.get(uid_u2, {}).get("status"), results.get(uid_u3, {}).get("status")]
    assert "confirmed" in statuses, f"Expected one confirmed, got {statuses}"
    assert "waitlisted" in statuses, f"Expected one waitlisted, got {statuses}"
    print(f"✓ Passed: Concurrent race condition handled! Results: {statuses}")

    # Verify event is now marked 'full'
    ev_status = fetch_query("SELECT status FROM Events WHERE id = ?", (ev1_id,))[0]["status"]
    assert ev_status == "full", f"Expected full, got {ev_status}"
    print("✓ Passed: Event status updated to 'full'")

    # 8. Test Privacy Rule for venue_address
    # Non-attendee detail
    det_stranger = get_event_detail(ev1_id, uid_broke)
    assert det_stranger["venue_address"] is None, "Stranger should not see venue_address"
    assert det_stranger["venue_name"] == "Community Kitchen Central"

    # Host detail
    det_host = get_event_detail(ev1_id, uid_host)
    assert det_host["venue_address"] == "123 Secret Kitchen Alley, Suite 4", "Host must see venue_address"

    # Confirmed attendee detail
    det_u1 = get_event_detail(ev1_id, uid_u1)
    assert det_u1["venue_address"] == "123 Secret Kitchen Alley, Suite 4", "Confirmed attendee must see venue_address"

    # List view privacy
    lst = get_events(uid_broke)["events"]
    for ev_item in lst:
        assert "venue_address" not in ev_item or ev_item.get("venue_address") is None, "List view must never expose venue_address"
    print("✓ Passed: Privacy rule for venue_address strictly enforced across list & detail views")

    # 9. Test Recommendations
    recs = get_recommended_events(uid_u1)
    assert len(recs) > 0
    italian_rec = [r for r in recs if r["id"] == ev1_id]
    assert len(italian_rec) > 0
    assert "Italian Cooking" in italian_rec[0]["reason"]
    print(f"✓ Passed: Recommendation engine returned: '{italian_rec[0]['reason']}'")

    # 10. Test Leave with Waitlist Promotion
    # User 1 leaves. The waitlisted user should be promoted and charged 3 credits!
    waitlisted_uid = uid_u2 if results.get(uid_u2, {}).get("status") == "waitlisted" else uid_u3
    confirmed_other_uid = uid_u2 if waitlisted_uid == uid_u3 else uid_u3

    bal_wl_before = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (waitlisted_uid,))[0]["wallet_balance"]
    assert bal_wl_before == 10, "Waitlisted user should not have been charged earlier"

    leave_res = leave_event(ev1_id, uid_u1)
    assert leave_res["status"] == "cancelled"
    assert leave_res["refunded_credits"] == 3
    assert leave_res["promoted_user_id"] == waitlisted_uid

    # Check User 1 refunded
    bal_u1_after = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (uid_u1,))[0]["wallet_balance"]
    assert bal_u1_after == 10, f"User 1 balance should be 10, got {bal_u1_after}"

    # Check waitlisted user promoted & charged
    wl_part = fetch_query("SELECT status, credits_held, waitlist_position FROM EventParticipants WHERE event_id = ? AND user_id = ?", (ev1_id, waitlisted_uid))[0]
    assert wl_part["status"] == "confirmed"
    assert wl_part["credits_held"] == 3
    assert wl_part["waitlist_position"] is None
    bal_wl_after = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (waitlisted_uid,))[0]["wallet_balance"]
    assert bal_wl_after == 7, f"Promoted user should have been charged 3 credits, got {bal_wl_after}"

    # Leave again should return 409
    try:
        leave_event(ev1_id, uid_u1)
        assert False, "Double leave should fail"
    except HTTPException as e:
        assert e.status_code == 409
        print("✓ Passed: User 1 left, refunded once, waitlisted user promoted and charged, double leave rejected with 409")

    # 11. Test Host Cancel Event and Refund All
    # Current confirmed attendees: confirmed_other_uid and waitlisted_uid
    cancel_res = cancel_event(ev1_id, uid_host, "Host family emergency, deeply sorry.")
    assert cancel_res["status"] == "cancelled"

    # Both confirmed attendees refunded
    bal_other = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (confirmed_other_uid,))[0]["wallet_balance"]
    bal_promoted = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (waitlisted_uid,))[0]["wallet_balance"]
    assert bal_other == 10, f"Expected 10, got {bal_other}"
    assert bal_promoted == 10, f"Expected 10, got {bal_promoted}"

    ev_cancelled = fetch_query("SELECT status, cancel_reason FROM Events WHERE id = ?", (ev1_id,))[0]
    assert ev_cancelled["status"] == "cancelled"
    assert ev_cancelled["cancel_reason"] == "Host family emergency, deeply sorry."
    print("✓ Passed: Host cancellation refunded all confirmed attendees and recorded reason")

    # 12. Test Host Event Cap (max 3 open events)
    ev_ids = []
    for i in range(3):
        e = create_event(uid_host, {
            "title": f"Host Event {i+1}", "description": "Description here",
            "skill_name": "Cooking", "mode": "online",
            "starts_at": future_time, "capacity": 5, "credit_cost": 0
        })
        ev_ids.append(e["id"])

    # 4th should fail
    try:
        create_event(uid_host, {
            "title": "Host Event 4", "description": "Description here",
            "skill_name": "Cooking", "mode": "online",
            "starts_at": future_time, "capacity": 5, "credit_cost": 0
        })
        assert False, "4th event should fail with 409"
    except HTTPException as e:
        assert e.status_code == 409
        print("✓ Passed: Host cannot create 4th open event (capped at 3)")

    # 13. Test My Events Endpoint
    my_evs = get_my_events(uid_host)
    assert len(my_evs["hosted"]["upcoming"]) == 3
    assert len(my_evs["hosted"]["past"]) >= 1  # includes cancelled ev1
    print("✓ Passed: get_my_events returns structured hosted & joined views")

    print("\n🎉 ALL PART A BACKEND TESTS PASSED CLEANLY! 🎉")

if __name__ == "__main__":
    run_tests()
