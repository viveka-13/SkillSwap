"""
agent/gamification.py — Lightweight gamification for SkillSwap.

Provides:
  - Weekly completion streaks
  - Skill-based badges (seeded at startup)
  - City-level leaderboard scoring

All gamification data is DISPLAY-ONLY and never affects matchmaking,
credit balances, or trust scores.
"""
import uuid
import json
from datetime import datetime, timedelta
from agent.memory import run_query, fetch_query


# ──────────────────────────────────────────────
# Badge Definitions (seeded at startup)
# ──────────────────────────────────────────────
INITIAL_BADGES = [
    {
        "code": "first_exchange",
        "name": "First Exchange",
        "description": "Completed your very first skill exchange!",
        "criteria_type": "total_completions",
        "criteria_value": json.dumps({"count": 1}),
    },
    {
        "code": "five_exchanges",
        "name": "Five Exchanges",
        "description": "Completed 5 skill exchanges — you're on a roll!",
        "criteria_type": "total_completions",
        "criteria_value": json.dumps({"count": 5}),
    },
    {
        "code": "highly_rated",
        "name": "Highly Rated",
        "description": "Maintained an average rating of 4.5+ with at least 3 reviews.",
        "criteria_type": "rating_threshold",
        "criteria_value": json.dumps({"min_avg": 4.5, "min_count": 3}),
    },
    {
        "code": "streak_3",
        "name": "On Fire",
        "description": "Maintained a 3-week completion streak!",
        "criteria_type": "streak",
        "criteria_value": json.dumps({"weeks": 3}),
    },
    {
        "code": "streak_5",
        "name": "Unstoppable",
        "description": "Maintained a 5-week completion streak!",
        "criteria_type": "streak",
        "criteria_value": json.dumps({"weeks": 5}),
    },
]


def seed_badges():
    """Insert badge definitions if they don't already exist. Safe to call repeatedly."""
    for badge in INITIAL_BADGES:
        existing = fetch_query("SELECT id FROM Badges WHERE code = ?", (badge["code"],))
        if not existing:
            run_query(
                "INSERT INTO Badges (id, code, name, description, criteria_type, criteria_value) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), badge["code"], badge["name"], badge["description"],
                 badge["criteria_type"], badge["criteria_value"]),
            )


def _iso_week(dt=None):
    """Return ISO week string like '2026-W35' for the given datetime (default: now)."""
    if dt is None:
        dt = datetime.utcnow()
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _next_week(week_str):
    """Given '2026-W35', return '2026-W36'. Handles year boundaries correctly."""
    year, week = int(week_str[:4]), int(week_str.split("W")[1])
    # Find the Monday of the given ISO week, then add 7 days
    jan4 = datetime(year, 1, 4)  # Jan 4 is always in ISO week 1
    start_of_week1 = jan4 - timedelta(days=jan4.weekday())
    monday_of_week = start_of_week1 + timedelta(weeks=week - 1)
    next_monday = monday_of_week + timedelta(weeks=1)
    return _iso_week(next_monday)


def update_streak(user_id: str):
    """
    Update the user's weekly completion streak.
    Called when an exchange reaches 'completed' status.

    Logic:
      - Same week as last completion → no change (already counted this week)
      - Immediately following week → increment current_streak
      - Skipped one or more weeks → reset current_streak to 1
      - Update longest_streak if current exceeds it
    """
    current_week = _iso_week()

    rows = fetch_query("SELECT * FROM UserStreaks WHERE user_id = ?", (user_id,))
    if not rows:
        # First ever completion — initialize streak
        run_query(
            "INSERT INTO UserStreaks (user_id, current_streak, longest_streak, last_completed_period) VALUES (?, 1, 1, ?)",
            (user_id, current_week),
        )
        return

    streak = rows[0]
    last_period = streak["last_completed_period"]

    if last_period == current_week:
        # Already counted this week — no change
        return

    expected_next = _next_week(last_period)
    if current_week == expected_next:
        # Consecutive week — increment
        new_current = streak["current_streak"] + 1
    else:
        # Skipped at least one week — reset
        new_current = 1

    new_longest = max(streak["longest_streak"], new_current)
    run_query(
        "UPDATE UserStreaks SET current_streak = ?, longest_streak = ?, last_completed_period = ? WHERE user_id = ?",
        (new_current, new_longest, current_week, user_id),
    )


def _get_user_completed_count(user_id: str) -> int:
    """Count how many exchanges this user has completed (as either party)."""
    rows = fetch_query(
        "SELECT COUNT(*) as cnt FROM Matches WHERE status = 'completed' AND (user1_id = ? OR user2_id = ?)",
        (user_id, user_id),
    )
    return rows[0]["cnt"] if rows else 0


def _get_user_rating_stats(user_id: str):
    """Return (average_rating, rating_count) for ratings received by this user."""
    rows = fetch_query(
        "SELECT AVG(rating) as avg_rating, COUNT(*) as cnt FROM Ratings WHERE reviewee_id = ?",
        (user_id,),
    )
    if rows and rows[0]["cnt"] > 0:
        return rows[0]["avg_rating"], rows[0]["cnt"]
    return 0.0, 0


def _get_user_streak(user_id: str) -> int:
    """Return the user's current streak."""
    rows = fetch_query("SELECT current_streak FROM UserStreaks WHERE user_id = ?", (user_id,))
    return rows[0]["current_streak"] if rows else 0


def _seed_skill_mentor_badges(user_id: str):
    """
    Dynamically check and award 'Top [Skill] Mentor' badges.

    Limitation (v1): The Ratings table doesn't directly link to which specific
    skill was exchanged. We trace Matches → Skills(type='offered') to determine
    what skills a user was teaching. This uses ALL offered skills of the user
    at match time, not just the one actually exchanged.
    """
    # Get all completed matches where this user was a participant
    completed_matches = fetch_query(
        "SELECT id, user1_id, user2_id FROM Matches WHERE status = 'completed' AND (user1_id = ? OR user2_id = ?)",
        (user_id, user_id),
    )
    if len(completed_matches) < 3:
        return  # Not enough completions for any mentor badge

    # Get this user's offered skills
    offered_skills = fetch_query(
        "SELECT DISTINCT skill_name FROM Skills WHERE user_id = ? AND type = 'offered'",
        (user_id,),
    )

    for skill_row in offered_skills:
        skill_name = skill_row["skill_name"]
        badge_code = f"top_{skill_name.lower().replace(' ', '_')}_mentor"

        # Check if badge already awarded
        existing = fetch_query(
            """SELECT ub.id FROM UserBadges ub
               JOIN Badges b ON ub.badge_id = b.id
               WHERE ub.user_id = ? AND b.code = ?""",
            (user_id, badge_code),
        )
        if existing:
            continue

        # Count completed exchanges where this user was teaching (was a participant)
        teaching_count = len(completed_matches)  # Approximation: all completions count

        if teaching_count < 3:
            continue

        # Check average rating for this user across exchanges
        avg_rating, rating_count = _get_user_rating_stats(user_id)
        if rating_count < 3 or avg_rating < 4.0:
            continue

        # Ensure the badge definition exists
        badge_rows = fetch_query("SELECT id FROM Badges WHERE code = ?", (badge_code,))
        if not badge_rows:
            # Create the badge definition dynamically
            badge_id = str(uuid.uuid4())
            run_query(
                "INSERT INTO Badges (id, code, name, description, criteria_type, criteria_value) VALUES (?, ?, ?, ?, ?, ?)",
                (badge_id, badge_code, f"Top {skill_name} Mentor",
                 f"Completed 3+ exchanges teaching {skill_name} with a 4.0+ rating.",
                 "skill_completions",
                 json.dumps({"skill_name": skill_name, "count": 3})),
            )
        else:
            badge_id = badge_rows[0]["id"]

        # Award it
        run_query(
            "INSERT INTO UserBadges (id, user_id, badge_id, awarded_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (str(uuid.uuid4()), user_id, badge_id),
        )


def check_and_award_badges(user_id: str):
    """
    Check all badge criteria and award any newly earned badges.
    Called when an exchange reaches 'completed' status.
    """
    completed_count = _get_user_completed_count(user_id)
    avg_rating, rating_count = _get_user_rating_stats(user_id)
    current_streak = _get_user_streak(user_id)

    # Get all badge definitions
    all_badges = fetch_query("SELECT * FROM Badges")

    for badge in all_badges:
        # Skip if already awarded
        already = fetch_query(
            "SELECT id FROM UserBadges WHERE user_id = ? AND badge_id = ?",
            (user_id, badge["id"]),
        )
        if already:
            continue

        criteria = json.loads(badge["criteria_value"]) if badge["criteria_value"] else {}
        earned = False

        if badge["criteria_type"] == "total_completions":
            earned = completed_count >= criteria.get("count", 999)

        elif badge["criteria_type"] == "rating_threshold":
            min_avg = criteria.get("min_avg", 5.0)
            min_count = criteria.get("min_count", 1)
            earned = rating_count >= min_count and avg_rating >= min_avg

        elif badge["criteria_type"] == "streak":
            earned = current_streak >= criteria.get("weeks", 999)

        # skill_completions are handled by _seed_skill_mentor_badges
        # (they need per-skill logic)

        if earned:
            try:
                run_query(
                    "INSERT INTO UserBadges (id, user_id, badge_id, awarded_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (str(uuid.uuid4()), user_id, badge["id"]),
                )
            except Exception:
                pass  # Unique constraint — badge already awarded (race condition guard)

    # Check dynamic skill mentor badges
    _seed_skill_mentor_badges(user_id)
