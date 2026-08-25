"""
Fraud Detection & Abuse Prevention Module

Detects two abuse patterns:
1. Ghosting: Users repeatedly accept exchanges but fail to complete them.
2. Credit Cycling: Two accounts repeatedly exchange credits back and forth.

All detection is heuristic-based, explicit, and explainable.
Detection failures must NEVER block normal exchange operations.
"""

import uuid
import logging
from datetime import datetime, timedelta
from agent.memory import run_query, fetch_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GHOSTING_MIN_EXCHANGES = 3        # Minimum accepted exchanges before ghosting check
GHOSTING_RECENT_WINDOW = 5        # Number of recent exchanges to evaluate
GHOSTING_INACTIVITY_DAYS = 7      # Days before an in_progress exchange is considered stale
GHOSTING_THRESHOLD = 0.50         # Fraction of ghosts required to trigger flag

CYCLING_WINDOW_DAYS = 14          # Time window for credit cycling detection
CYCLING_MIN_EXCHANGES = 3         # Minimum exchanges between a pair to trigger check
CYCLING_NET_FLOW_THRESHOLD = 0.20 # |net| / total <= this -> suspicious


# ---------------------------------------------------------------------------
# Helper: get unresolved flags for a user
# ---------------------------------------------------------------------------
def get_unresolved_flags(user_id: str, flag_type: str = None) -> list:
    """Return unresolved FraudFlags for a user, optionally filtered by type."""
    if flag_type:
        return fetch_query(
            "SELECT * FROM FraudFlags WHERE user_id = ? AND flag_type = ? AND resolved_at IS NULL",
            (user_id, flag_type)
        )
    return fetch_query(
        "SELECT * FROM FraudFlags WHERE user_id = ? AND resolved_at IS NULL",
        (user_id,)
    )


# ---------------------------------------------------------------------------
# Helper: set user fraud status columns
# ---------------------------------------------------------------------------
def set_user_fraud_status(user_id: str, flag: str, reason: str, timestamp: str):
    """Update the Users table fraud columns."""
    run_query(
        "UPDATE Users SET fraud_flag = ?, fraud_flag_reason = ?, fraud_flagged_at = ? WHERE id = ?",
        (flag, reason, timestamp, user_id)
    )


# ---------------------------------------------------------------------------
# Helper: recalculate user fraud status from remaining unresolved flags
# ---------------------------------------------------------------------------
def recalculate_user_fraud_status(user_id: str):
    """After resolving a flag, recalculate the user's active fraud state
    from any remaining unresolved flags. Picks the highest severity."""
    unresolved = fetch_query(
        "SELECT * FROM FraudFlags WHERE user_id = ? AND resolved_at IS NULL ORDER BY created_at DESC",
        (user_id,)
    )
    if not unresolved:
        # Clear fraud status
        set_user_fraud_status(user_id, None, None, None)
        return

    # Pick the most severe unresolved flag
    severity_order = {"restricted": 2, "watch": 1}
    worst = max(unresolved, key=lambda f: severity_order.get(f["severity"], 0))
    set_user_fraud_status(user_id, worst["severity"], worst["detail"], worst["created_at"])


# ---------------------------------------------------------------------------
# Helper: create a fraud flag (with dedup)
# ---------------------------------------------------------------------------
def create_fraud_flag(user_id: str, flag_type: str, detail: str, severity: str):
    """Create a FraudFlags audit record and update the user's current fraud status.
    Avoids creating duplicate identical active flags."""
    # Check for existing unresolved flag of same type
    existing = get_unresolved_flags(user_id, flag_type)
    if existing:
        # Don't create duplicate -- already flagged for this type
        logger.info("Skipping duplicate %s flag for user %s", flag_type, user_id)
        return existing[0]["id"]

    flag_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    run_query(
        "INSERT INTO FraudFlags (id, user_id, flag_type, detail, severity, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (flag_id, user_id, flag_type, detail, severity, now)
    )

    # Update user's current fraud status (use highest severity among unresolved)
    user = fetch_query("SELECT fraud_flag FROM Users WHERE id = ?", (user_id,))
    current_flag = user[0]["fraud_flag"] if user else None

    severity_order = {"restricted": 2, "watch": 1}
    if severity_order.get(severity, 0) >= severity_order.get(current_flag, 0):
        set_user_fraud_status(user_id, severity, detail, now)

    return flag_id


# ---------------------------------------------------------------------------
# Ghosting Detection
# ---------------------------------------------------------------------------
def detect_ghosting_pattern(user_id: str):
    """Inspect a user's exchange history for ghosting patterns.

    Ghosting: user accepts exchanges but fails to complete them, leaving the
    other party to eventually cancel.

    Rules:
    - Only evaluate if user has >= GHOSTING_MIN_EXCHANGES accepted exchanges
    - Look at last GHOSTING_RECENT_WINDOW accepted exchanges
    - A "ghost" is an exchange where:
      a) status='cancelled' AND cancelled_by != user_id (other party cancelled)
      b) status='in_progress' AND escrow_created_at > GHOSTING_INACTIVITY_DAYS ago
    - If ghost_count / qualifying_count > GHOSTING_THRESHOLD -> flag

    Severity:
    - First detection: 'watch'
    - If previous ghosting flag exists (resolved or unresolved): 'restricted'
    """
    # Get all exchanges where this user participated and that reached at least in_progress
    exchanges = fetch_query(
        """SELECT id, user1_id, user2_id, status, cancelled_by, escrow_created_at, completed_at
           FROM Matches
           WHERE (user1_id = ? OR user2_id = ?)
             AND status IN ('in_progress', 'completed', 'cancelled')
           ORDER BY created_at DESC""",
        (user_id, user_id)
    )

    # Sample-size guard: must have at least GHOSTING_MIN_EXCHANGES
    if len(exchanges) < GHOSTING_MIN_EXCHANGES:
        return

    # Take the most recent GHOSTING_RECENT_WINDOW
    recent = exchanges[:GHOSTING_RECENT_WINDOW]

    ghost_count = 0
    qualifying_count = len(recent)

    now = datetime.utcnow()

    for ex in recent:
        if ex["status"] == "cancelled":
            # Only count as ghosting if someone ELSE cancelled
            # (meaning this user was the inactive party)
            if ex["cancelled_by"] and ex["cancelled_by"] != user_id:
                ghost_count += 1
            # LIMITATION: If cancelled_by is NULL (legacy data before we added the column),
            # we cannot determine who cancelled. We do NOT count these as ghosting
            # to avoid false positives.

        elif ex["status"] == "in_progress":
            # Stuck exchange -- accepted but never completed
            if ex["escrow_created_at"]:
                try:
                    escrow_dt = datetime.fromisoformat(ex["escrow_created_at"].replace("Z", "+00:00").replace("+00:00", ""))
                except (ValueError, AttributeError):
                    try:
                        escrow_dt = datetime.strptime(ex["escrow_created_at"], "%Y-%m-%d %H:%M:%S")
                    except (ValueError, AttributeError):
                        continue
                if (now - escrow_dt).days >= GHOSTING_INACTIVITY_DAYS:
                    ghost_count += 1

    # Check threshold
    if qualifying_count == 0:
        return

    ghost_ratio = ghost_count / qualifying_count
    if ghost_ratio <= GHOSTING_THRESHOLD:
        return

    # Determine severity: check if user has any previous ghosting flags (resolved or not)
    all_ghosting_flags = fetch_query(
        "SELECT * FROM FraudFlags WHERE user_id = ? AND flag_type = 'ghosting'",
        (user_id,)
    )

    if all_ghosting_flags:
        severity = "restricted"
    else:
        severity = "watch"

    detail = (
        f"{ghost_count} of the last {qualifying_count} accepted exchanges were not completed "
        f"after remaining inactive for more than {GHOSTING_INACTIVITY_DAYS} days."
    )

    create_fraud_flag(user_id, "ghosting", detail, severity)
    logger.info("Ghosting flag created for user %s: %s (%s)", user_id, detail, severity)


# ---------------------------------------------------------------------------
# Credit Cycling Detection
# ---------------------------------------------------------------------------
def detect_credit_cycling(user_id: str):
    """Inspect completed exchanges for suspicious bidirectional credit cycling.

    Credit cycling: two accounts repeatedly exchange credits back and forth
    in a short period with near-zero net flow.

    # This heuristic can false-positive on legitimate repeat collaborators.
    # Credit-cycling detection must therefore default to watch severity
    # and must never automatically restrict an account.

    Rules:
    - Look at completed exchanges in the last CYCLING_WINDOW_DAYS days
    - Group by counterpart
    - For pairs with >= CYCLING_MIN_EXCHANGES:
      - Calculate directional credit flows
      - If |net flow| / total flow <= CYCLING_NET_FLOW_THRESHOLD -> suspicious
    - Always severity='watch', never auto-restrict
    - Flag both users in the pair
    """
    cutoff = (datetime.utcnow() - timedelta(days=CYCLING_WINDOW_DAYS)).isoformat()

    # Get completed exchanges involving this user within the window
    completed = fetch_query(
        """SELECT m.id, m.user1_id, m.user2_id, m.credits_held, m.completed_at,
                  eh.credits_transferred
           FROM Matches m
           LEFT JOIN ExchangeHistory eh ON eh.match_id = m.id
           WHERE (m.user1_id = ? OR m.user2_id = ?)
             AND m.status = 'completed'
             AND m.completed_at >= ?
           ORDER BY m.completed_at DESC""",
        (user_id, user_id, cutoff)
    )

    if len(completed) < CYCLING_MIN_EXCHANGES:
        return

    # Group by counterpart
    pairs = {}  # counterpart_id -> list of exchanges
    for ex in completed:
        counterpart = ex["user2_id"] if ex["user1_id"] == user_id else ex["user1_id"]
        if counterpart not in pairs:
            pairs[counterpart] = []
        pairs[counterpart].append(ex)

    for counterpart_id, exchanges in pairs.items():
        if len(exchanges) < CYCLING_MIN_EXCHANGES:
            continue

        # Calculate directional credit flows
        # In the system: user1 pays credits_held, user2 receives them on completion
        flow_to_counterpart = 0   # credits user_id sent to counterpart
        flow_from_counterpart = 0  # credits counterpart sent to user_id

        for ex in exchanges:
            credits = ex["credits_transferred"] or ex["credits_held"] or 0
            if ex["user1_id"] == user_id:
                # user_id was requester (paid credits), counterpart received
                flow_to_counterpart += credits
            else:
                # counterpart was requester (paid credits), user_id received
                flow_from_counterpart += credits

        total_flow = flow_to_counterpart + flow_from_counterpart
        if total_flow == 0:
            continue

        net_flow = abs(flow_to_counterpart - flow_from_counterpart)
        net_ratio = net_flow / total_flow

        if net_ratio > CYCLING_NET_FLOW_THRESHOLD:
            # Net flow is significant -- likely legitimate
            continue

        # Suspicious pattern detected
        detail = (
            f"{len(exchanges)} completed exchanges with the same account occurred within "
            f"{CYCLING_WINDOW_DAYS} days with repeated bidirectional credit transfers "
            f"and near-zero net credit flow (net ratio: {net_ratio:.0%})."
        )

        # Flag this user (if not already flagged for this)
        create_fraud_flag(user_id, "credit_cycling", detail, "watch")

        # Flag the counterpart too
        counterpart_detail = (
            f"{len(exchanges)} completed exchanges with the same account occurred within "
            f"{CYCLING_WINDOW_DAYS} days with repeated bidirectional credit transfers "
            f"and near-zero net credit flow (net ratio: {net_ratio:.0%})."
        )
        create_fraud_flag(counterpart_id, "credit_cycling", counterpart_detail, "watch")

        logger.info(
            "Credit cycling flag created for users %s and %s: %d exchanges, net ratio %.0f%%",
            user_id, counterpart_id, len(exchanges), net_ratio * 100
        )
