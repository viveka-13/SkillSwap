import os
import json
from pywebpush import webpush, WebPushException
from agent.memory import fetch_query, run_query

def send_push_to_user(user_id: str, title: str, body: str, data: dict = None):
    """
    Sends a push notification to all active subscriptions of a user.
    Never raises an exception to the caller.
    """
    try:
        public_key = os.getenv("VAPID_PUBLIC_KEY")
        private_key = os.getenv("VAPID_PRIVATE_KEY")
        claims_email = os.getenv("VAPID_CLAIMS_EMAIL")

        if not public_key or not private_key or not claims_email:
            # Silently skip if not configured
            return

        subs = fetch_query("SELECT id, endpoint, p256dh_key, auth_key FROM PushSubscriptions WHERE user_id = ?", (user_id,))
        if not subs:
            return
            
        payload = {
            "title": title,
            "body": body,
            "data": data or {}
        }
        payload_data = json.dumps(payload)

        for sub in subs:
            sub_info = {
                "endpoint": sub["endpoint"],
                "keys": {
                    "p256dh": sub["p256dh_key"],
                    "auth": sub["auth_key"]
                }
            }
            try:
                webpush(
                    subscription_info=sub_info,
                    data=payload_data,
                    vapid_private_key=private_key,
                    vapid_claims={"sub": f"mailto:{claims_email}"}
                )
            except WebPushException as e:
                # If subscription is expired or invalid (404/410), delete it
                if e.response is not None and e.response.status_code in [404, 410]:
                    run_query("DELETE FROM PushSubscriptions WHERE id = ?", (sub["id"],))
                else:
                    print(f"Push delivery failed for sub {sub['id']}: {e}")
            except Exception as e:
                print(f"Unexpected error sending push to sub {sub['id']}: {e}")
                
    except Exception as e:
        print(f"Failed to process push sending for user {user_id}: {e}")
