import os
import json
import asyncio
import uuid
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import base64
from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import jwt
import bcrypt

from agent.workflow import run_matchmaking
from agent.memory import run_query, fetch_query, skills_collection

import logging
logger = logging.getLogger(__name__)

# Fraud detection imports (lazy to avoid circular imports at module level)
def _get_fraud_module():
    from agent.fraud import detect_ghosting_pattern, detect_credit_cycling
    return detect_ghosting_pattern, detect_credit_cycling

def groq_whisper_transcribe(audio_bytes: bytes, filename: str = 'audio.webm', default_lang: str = 'English') -> tuple[str, str]:
    """
    Transcribes audio using Groq's Whisper API.
    Returns a tuple of (transcribed_text, detected_language_code).
    """
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return "[Transcription unavailable: No API Key]", default_lang
        
    try:
        import http.client
        import json
        import uuid
        
        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
        
        body = b""
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        body += b'Content-Type: audio/webm\r\n\r\n'
        body += audio_bytes
        body += b'\r\n'
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += b'whisper-large-v3\r\n'
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="response_format"\r\n\r\n'
        body += b'verbose_json\r\n'
        body += f"--{boundary}--\r\n".encode()
        
        conn = http.client.HTTPSConnection("api.groq.com")
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
        conn.request("POST", "/openai/v1/audio/transcriptions", body=body, headers=headers)
        resp = conn.getresponse()
        resp_data = json.loads(resp.read().decode())
        conn.close()
        
        original_text = resp_data.get("text", "")
        language_code = resp_data.get("language", default_lang)
        return original_text, language_code
        
    except Exception as e:
        print(f"Whisper transcription failed: {e}")
        return "[Transcription unavailable]", default_lang


load_dotenv()
app = FastAPI()

# Seed gamification badges at startup
try:
    from agent.gamification import seed_badges
    seed_badges()
except Exception as e:
    print(f'Badge seeding failed (non-critical): {e}')


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_text(message)
            except Exception:
                self.disconnect(user_id)

call_manager = ConnectionManager()

@app.websocket("/api/ws/calls/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await call_manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                
                if msg.get("type") == "notes_update":
                    match_id = msg.get("match_id")
                    content = msg.get("content")
                    q = "SELECT user1_id, user2_id FROM Matches WHERE id = ?"
                    match = fetch_query(q, (match_id,))
                    if match and user_id in (match[0]['user1_id'], match[0]['user2_id']):
                        run_query(
                            "INSERT INTO SharedNotes (id, match_id, content, last_edited_by, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET content=excluded.content, last_edited_by=excluded.last_edited_by, updated_at=CURRENT_TIMESTAMP",
                            (match_id, match_id, content, user_id)
                        )
                        target_id = match[0]['user2_id'] if match[0]['user1_id'] == user_id else match[0]['user1_id']
                        msg["sender"] = user_id
                        await call_manager.send_personal_message(json.dumps(msg), target_id)
                    continue

                target_id = msg.get("target")
                if target_id:
                    msg["sender"] = user_id
                    await call_manager.send_personal_message(json.dumps(msg), target_id)
            except Exception as e:
                print(f"WS Msg Error: {e}")
    except WebSocketDisconnect:
        call_manager.disconnect(user_id)

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-hackathon-key")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

class SkillEntry(BaseModel):
    skill_name: str
    description: str | None = None
    level: str = "beginner"
    category: str | None = None

class StructureSuggestionRequest(BaseModel):
    skill_name: str
    type: str = "offered"  # 'offered' or 'needed'

class UserRegister(BaseModel):
    name: str
    email: str
    password: str
    city: str
    lat: float
    lon: float
    bio: str
    skills_offered: list  # list[SkillEntry] or list[str] for backward compat
    offered_level: str = "beginner"
    skills_needed: list   # list[SkillEntry] or list[str] for backward compat
    needed_level: str = "beginner"
    preferred_language: str = "English"

class UserLogin(BaseModel):
    email: str
    password: str

class MatchRequest(BaseModel):
    needed_skill: str
    offered_skill: str

class ExchangeRequest(BaseModel):
    matched_user_id: str
    compatibility_score: float
    ai_reasoning: str

class ChatRequest(BaseModel):
    content: str

class FileUploadRequest(BaseModel):
    filename: str
    data: str  # base64-encoded file content

class VoiceUploadRequest(BaseModel):
    data: str  # base64-encoded audio content
    duration: float = 0.0

class DeleteMessageRequest(BaseModel):
    mode: str  # "for_me" or "for_everyone"

# WhatsApp-style: allow "delete for everyone" within this window only
DELETE_FOR_EVERYONE_WINDOW_MINUTES = 30

def get_current_user_id(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload.get("sub")
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/")
async def root():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.post("/api/auth/register")
async def register(user: UserRegister):
    # Basic validation
    if not user.email or not user.password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    email = user.email.strip().lower()
    hashed_pwd = hash_password(user.password)
    user_id = str(uuid.uuid4())
    try:
        run_query(
            "INSERT INTO Users (id, name, email, password_hash, city, lat, lon, bio, preferred_language) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, user.name, email, hashed_pwd, user.city, user.lat, user.lon, user.bio, user.preferred_language)
        )
        
        # --- Guided Skill Entry: save structured skill data ---
        def _normalize_skill(raw, fallback_level):
            """Accept either a dict/SkillEntry or a plain string for backward compat."""
            if isinstance(raw, dict):
                return {
                    "skill_name": raw.get("skill_name", ""),
                    "description": raw.get("description") or None,
                    "level": raw.get("level", fallback_level),
                    "category": raw.get("category") or None,
                }
            # Plain string (old format)
            return {"skill_name": str(raw), "description": None, "level": fallback_level, "category": None}

        def _embed_text(skill_name, description):
            """Build the text to embed into ChromaDB — richer than skill_name alone."""
            if description:
                return f"{skill_name}: {description}"
            return skill_name

        for raw_skill in user.skills_offered:
            s = _normalize_skill(raw_skill, user.offered_level)
            skill_id = str(uuid.uuid4())
            run_query(
                "INSERT INTO Skills (id, user_id, skill_name, type, level, description, category) VALUES (?, ?, ?, 'offered', ?, ?, ?)",
                (skill_id, user_id, s["skill_name"], s["level"], s["description"], s["category"])
            )
            embed_doc = _embed_text(s["skill_name"], s["description"])
            meta = {"user_id": user_id, "type": "offered", "skill_name": s["skill_name"], "level": s["level"]}
            if s["category"]:
                meta["category"] = s["category"]
            skills_collection.add(documents=[embed_doc], metadatas=[meta], ids=[skill_id])

        for raw_skill in user.skills_needed:
            s = _normalize_skill(raw_skill, user.needed_level)
            skill_id = str(uuid.uuid4())
            run_query(
                "INSERT INTO Skills (id, user_id, skill_name, type, level, description, category) VALUES (?, ?, ?, 'needed', ?, ?, ?)",
                (skill_id, user_id, s["skill_name"], s["level"], s["description"], s["category"])
            )
            embed_doc = _embed_text(s["skill_name"], s["description"])
            meta = {"user_id": user_id, "type": "needed", "skill_name": s["skill_name"], "level": s["level"]}
            if s["category"]:
                meta["category"] = s["category"]
            skills_collection.add(documents=[embed_doc], metadatas=[meta], ids=[skill_id])
            
        return {"status": "success", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/skills/structure-suggestion")
async def skill_structure_suggestion(req: StructureSuggestionRequest):
    """AI-assisted skill structuring: suggests category, description, and clarifying question."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        return {"suggested_category": None, "suggested_description": None, "clarifying_question": None}

    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model_name="openai/gpt-oss-120b", groq_api_key=groq_api_key)

        skill_type_label = "teach/offer" if req.type == "offered" else "learn/need"
        prompt = f"""You are a skill-matching assistant. A user wants to {skill_type_label} the skill: "{req.skill_name}".

Return ONLY valid JSON (no markdown, no explanation) with exactly these keys:
{{
  "suggested_category": "one of: Programming, Design, Music, Languages, Cooking, Fitness, Business, Science, Writing, Photography, Other",
  "suggested_description": "a natural 1-2 sentence elaboration the user can edit, e.g. 'I can teach {req.skill_name}, focused on ___'",
  "clarifying_question": "a short optional question to help the user be more specific, or null if the skill name is already specific enough"
}}"""

        response = llm.invoke(prompt)
        import json as json_mod
        # Try to parse JSON from the response
        text = response.content.strip()
        # Handle potential markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json_mod.loads(text)
        return {
            "suggested_category": result.get("suggested_category"),
            "suggested_description": result.get("suggested_description"),
            "clarifying_question": result.get("clarifying_question"),
        }
    except Exception as e:
        print(f"Skill suggestion failed (graceful fallback): {e}")
        return {"suggested_category": None, "suggested_description": None, "clarifying_question": None}

@app.post("/api/auth/login")
async def login(creds: UserLogin):
    email = creds.email.strip().lower()
    rows = fetch_query("SELECT * FROM Users WHERE LOWER(email) = ?", (email,))
    if not rows or not verify_password(creds.password, rows[0]["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = jwt.encode({"sub": rows[0]["id"], "exp": datetime.utcnow() + timedelta(days=1)}, SECRET_KEY, algorithm="HS256")
    return {"token": token, "user": {"id": rows[0]["id"], "name": rows[0]["name"]}}

@app.post("/api/matches")
async def get_matches(req: MatchRequest, user_id: str = Depends(get_current_user_id)):
    matches = await run_matchmaking(user_id, req.needed_skill, req.offered_skill)
    return {"matches": matches}

# ---------------------------------------------------------------------------
# Admin API Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/admin/fraud-flags")
async def get_fraud_flags(user_id: str = Depends(get_current_user_id)):
    """Get all unresolved fraud flags.
    TODO: Add proper Role-Based Access Control (RBAC).
    Currently any authenticated user can technically hit this if they know the URL,
    which is a known gap to be fixed later."""
    flags = fetch_query(
        "SELECT f.*, u.name as user_name FROM FraudFlags f JOIN Users u ON f.user_id = u.id WHERE f.resolved_at IS NULL ORDER BY f.created_at DESC"
    )
    return {"flags": flags}

@app.post("/api/admin/fraud-flags/{flag_id}/resolve")
async def resolve_fraud_flag(flag_id: str, user_id: str = Depends(get_current_user_id)):
    """Resolve a fraud flag and recalculate user status.
    TODO: Add proper RBAC."""
    flag = fetch_query("SELECT user_id FROM FraudFlags WHERE id = ?", (flag_id,))
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
        
    target_user_id = flag[0]["user_id"]
    now = datetime.utcnow().isoformat()
    
    run_query(
        "UPDATE FraudFlags SET resolved_at = ?, resolved_by = ? WHERE id = ?",
        (now, user_id, flag_id)
    )
    
    # Recalculate user's overall fraud status
    try:
        from agent.fraud import recalculate_user_fraud_status
        recalculate_user_fraud_status(target_user_id)
    except Exception:
        logger.exception("Failed to recalculate fraud status for user %s", target_user_id)
        
    return {"status": "resolved"}

@app.get("/api/dashboard")
async def get_dashboard(user_id: str = Depends(get_current_user_id)):
    rows = fetch_query("SELECT id, name, email, city, lat, lon, bio, trust_score, wallet_balance FROM Users WHERE id = ?", (user_id,))
    if not rows: raise HTTPException(404)
    user = rows[0]
    
    offered = fetch_query("SELECT skill_name FROM Skills WHERE user_id = ? AND type = 'offered'", (user_id,))
    needed = fetch_query("SELECT skill_name FROM Skills WHERE user_id = ? AND type = 'needed'", (user_id,))
    
    return {
        "user": user,
        "skills_offered": [s["skill_name"] for s in offered],
        "skills_needed": [s["skill_name"] for s in needed]
    }


@app.post("/api/exchange/request")
async def send_exchange_request(req: ExchangeRequest, user_id: str = Depends(get_current_user_id)):
    """Send a skill exchange request to another user."""
    # Fraud check: restricted users cannot create new exchange requests
    user_row = fetch_query("SELECT fraud_flag FROM Users WHERE id = ?", (user_id,))
    if user_row and user_row[0].get("fraud_flag") == "restricted":
        raise HTTPException(
            status_code=403,
            detail="New exchange requests are temporarily restricted because your account has been flagged for repeated incomplete exchanges. Please wait for review."
        )

    match_id = str(uuid.uuid4())
    run_query(
        "INSERT INTO Matches (id, user1_id, user2_id, compatibility_score, ai_reasoning, status) VALUES (?, ?, ?, ?, ?, 'pending')",
        (match_id, user_id, req.matched_user_id, req.compatibility_score, req.ai_reasoning)
    )
    # Get sender name
    sender = fetch_query("SELECT name FROM Users WHERE id = ?", (user_id,))
    sender_name = sender[0]["name"] if sender else "Someone"
    # Notify the matched user
    notif_id = str(uuid.uuid4())
    run_query(
        "INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)",
        (notif_id, req.matched_user_id, f"🤝 {sender_name} wants to exchange skills with you! (Match: {req.compatibility_score}%)")
    )
    return {"status": "sent", "match_id": match_id}

@app.post("/api/exchange/accept/{match_id}")
async def accept_exchange(match_id: str, user_id: str = Depends(get_current_user_id)):
    """Accept an exchange request - holds credits in escrow."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND user2_id = ?", (match_id, user_id))
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match[0]["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already processed")
    
    # Check requester wallet balance
    requester = fetch_query("SELECT wallet_balance FROM Users WHERE id = ?", (match[0]["user1_id"],))
    if not requester or requester[0]["wallet_balance"] < 5:
        raise HTTPException(status_code=400, detail="Requester does not have enough credits to start exchange.")

    # Deduct from requester and update match to in_progress with escrow
    run_query("UPDATE Users SET wallet_balance = wallet_balance - 5 WHERE id = ?", (match[0]["user1_id"],))
    run_query("UPDATE Matches SET status = 'in_progress', credits_held = 5, escrow_created_at = CURRENT_TIMESTAMP WHERE id = ?", (match_id,))
    
    # Notify requester
    notif_id = str(uuid.uuid4())
    acceptor = fetch_query("SELECT name FROM Users WHERE id = ?", (user_id,))
    acceptor_name = acceptor[0]["name"] if acceptor else "Someone"
    run_query(
        "INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)",
        (notif_id, match[0]["user1_id"], f"✅ {acceptor_name} accepted your exchange! 5 credits are now held in escrow.")
    )
    return {"status": "in_progress", "credits_held": 5}

@app.post("/api/exchange/{match_id}/confirm")
async def confirm_exchange(match_id: str, user_id: str = Depends(get_current_user_id)):
    """Confirm the exchange is completed to release escrow credits."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match = match[0]
    
    if match["status"] != "in_progress":
        if match["status"] == "completed":
            return {"status": "completed", "message": "Exchange already completed."}
        raise HTTPException(status_code=400, detail=f"Cannot confirm exchange in status: {match['status']}")
        
    is_requester = user_id == match["user1_id"]
    
    # Update confirmation flag
    if is_requester:
        run_query("UPDATE Matches SET requester_confirmed = 1 WHERE id = ?", (match_id,))
        match = fetch_query("SELECT * FROM Matches WHERE id = ?", (match_id,))[0]
    else:
        run_query("UPDATE Matches SET acceptor_confirmed = 1 WHERE id = ?", (match_id,))
        match = fetch_query("SELECT * FROM Matches WHERE id = ?", (match_id,))[0]
        
    if match["requester_confirmed"] and match["acceptor_confirmed"]:
        # Both confirmed! Release credits
        run_query("UPDATE Matches SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE id = ?", (match_id,))
        run_query("UPDATE Users SET wallet_balance = wallet_balance + ? WHERE id = ?", (match["credits_held"], match["user2_id"]))
        
        # Log to ExchangeHistory
        ex_id = str(uuid.uuid4())
        run_query("INSERT INTO ExchangeHistory (id, match_id, credits_transferred) VALUES (?, ?, ?)", (ex_id, match_id, match["credits_held"]))
        
        # Notify both
        run_query("INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)", (str(uuid.uuid4()), match["user1_id"], "🎉 Exchange completed! Credits released."))
        run_query("INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)", (str(uuid.uuid4()), match["user2_id"], f"🎉 Exchange completed! You received {match['credits_held']} credits."))
        
        # Fraud detection: credit cycling check (non-blocking)
        try:
            detect_ghosting, detect_cycling = _get_fraud_module()
            detect_cycling(match["user1_id"])
            detect_cycling(match["user2_id"])
        except Exception:
            logger.exception("Credit cycling detection failed for match %s", match_id)

        # Gamification hooks (non-blocking — failure must never block exchange completion)
        try:
            from agent.gamification import update_streak, check_and_award_badges
            update_streak(match["user1_id"])
            update_streak(match["user2_id"])
            check_and_award_badges(match["user1_id"])
            check_and_award_badges(match["user2_id"])
        except Exception:
            logger.exception("Gamification hook failed for match %s", match_id)
        
        return {"status": "completed", "message": "Exchange completed, credits released."}
    else:
        # Notify the other party
        other_user = match["user2_id"] if is_requester else match["user1_id"]
        confirmer = fetch_query("SELECT name FROM Users WHERE id = ?", (user_id,))
        confirmer_name = confirmer[0]["name"] if confirmer else "Someone"
        run_query("INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)", (str(uuid.uuid4()), other_user, f"⏳ {confirmer_name} confirmed the exchange. Please confirm your side!"))
        
        return {"status": "waiting", "message": "Waiting on the other party to confirm."}

@app.post("/api/exchange/{match_id}/cancel")
async def cancel_exchange(match_id: str, user_id: str = Depends(get_current_user_id)):
    """Cancel an in-progress exchange and refund credits."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match = match[0]
    
    if match["status"] == "completed":
        raise HTTPException(status_code=409, detail="Cannot cancel an already completed exchange.")
    if match["status"] != "in_progress":
        raise HTTPException(status_code=400, detail="Cannot cancel exchange in this state.")
        
    # Refund requester
    run_query("UPDATE Users SET wallet_balance = wallet_balance + ? WHERE id = ?", (match["credits_held"], match["user1_id"]))
    run_query("UPDATE Matches SET status = 'cancelled', credits_held = 0, cancelled_by = ? WHERE id = ?", (user_id, match_id))
    
    # Notify both
    canceller = fetch_query("SELECT name FROM Users WHERE id = ?", (user_id,))
    canceller_name = canceller[0]["name"] if canceller else "Someone"
    
    run_query("INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)", (str(uuid.uuid4()), match["user1_id"], f"🚫 {canceller_name} cancelled the exchange. {match['credits_held']} credits refunded."))
    run_query("INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)", (str(uuid.uuid4()), match["user2_id"], f"🚫 {canceller_name} cancelled the exchange."))
    
    # Fraud detection: ghosting check on the OTHER user (non-blocking)
    try:
        detect_ghosting, detect_cycling = _get_fraud_module()
        other_user_id = match["user2_id"] if user_id == match["user1_id"] else match["user1_id"]
        detect_ghosting(other_user_id)
    except Exception:
        logger.exception("Ghosting detection failed for cancel on match %s", match_id)
    
    return {"status": "cancelled", "message": "Exchange cancelled, credits refunded."}

    return {"notifications": notifs}

@app.get("/api/exchange/pending")
async def get_pending_requests(user_id: str = Depends(get_current_user_id)):
    """Get pending and in_progress exchange requests for this user."""
    pending = fetch_query(
        """SELECT m.id, m.compatibility_score, m.ai_reasoning, m.created_at, m.status,
                  m.credits_held, m.requester_confirmed, m.acceptor_confirmed, m.user1_id, m.user2_id,
                  u1.name as requester_name, u2.name as acceptor_name
           FROM Matches m 
           JOIN Users u1 ON m.user1_id = u1.id
           JOIN Users u2 ON m.user2_id = u2.id
           WHERE (m.user1_id = ? OR m.user2_id = ?) AND m.status IN ('pending', 'in_progress')
           ORDER BY m.created_at DESC""",
        (user_id, user_id)
    )
    return {"pending": pending}

@app.get("/api/exchange/history")
async def get_exchange_history(user_id: str = Depends(get_current_user_id)):
    """Get completed exchanges."""
    history = fetch_query(
        """SELECT eh.id, eh.completed_at, eh.credits_transferred, m.compatibility_score, m.ai_reasoning,
                  u1.name as user1_name, u2.name as user2_name, m.status
           FROM ExchangeHistory eh
           JOIN Matches m ON eh.match_id = m.id
           JOIN Users u1 ON m.user1_id = u1.id
           JOIN Users u2 ON m.user2_id = u2.id
           WHERE m.user1_id = ? OR m.user2_id = ?
           ORDER BY eh.completed_at DESC""",
        (user_id, user_id)
    )
    return {"history": history}

@app.get("/api/chat/rooms")
async def get_chat_rooms(user_id: str = Depends(get_current_user_id)):
    """Get all in_progress or completed matches to act as chat rooms."""
    rooms = fetch_query(
        """SELECT m.id as match_id, u.id as other_user_id, u.name as other_user_name, m.compatibility_score, m.status 
           FROM Matches m JOIN Users u ON (m.user1_id = u.id OR m.user2_id = u.id)
           WHERE (m.user1_id = ? OR m.user2_id = ?) AND u.id != ? AND m.status IN ('accepted', 'in_progress', 'completed')
           ORDER BY m.created_at DESC""",
        (user_id, user_id, user_id)
    )
    return {"rooms": rooms}

@app.get("/api/chat/{match_id}/messages")
async def get_chat_messages(match_id: str, user_id: str = Depends(get_current_user_id)):
    """Get all messages (text, file, voice, youtube) for a chat room, merged chronologically."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    
    # Text + File messages
    text_msgs = fetch_query("SELECT id, match_id, sender_id, content, created_at, deleted_for_everyone, deleted_for_everyone_at, deleted_for_sender, deleted_for_recipient FROM Messages WHERE match_id = ? ORDER BY created_at ASC", (match_id,))
    for m in text_msgs:
        m["msg_type"] = "text"  # will be overridden by JS if content is JSON file meta
    
    # Voice messages
    voice_msgs = fetch_query("SELECT id, match_id, sender_id, filename, duration, original_text, translated_text, language_code, translation_status, created_at, deleted_for_everyone, deleted_for_everyone_at, deleted_for_sender, deleted_for_recipient FROM VoiceMessages WHERE match_id = ? ORDER BY created_at ASC", (match_id,))
    for v in voice_msgs:
        v["msg_type"] = "voice"
        v["content"] = ""  # placeholder for unified rendering
    
    # YouTube links
    yt_msgs = fetch_query("SELECT id, match_id, sender_id, url, video_id, title, thumbnail, channel, duration, created_at, deleted_for_everyone, deleted_for_everyone_at, deleted_for_sender, deleted_for_recipient FROM YoutubeLinks WHERE match_id = ? ORDER BY created_at ASC", (match_id,))
    for y in yt_msgs:
        y["msg_type"] = "youtube"
        y["content"] = ""  # placeholder
    
    # Calls
    call_msgs = fetch_query("SELECT id, match_id, caller_id, receiver_id, call_type, status, duration, created_at FROM Calls WHERE match_id = ? ORDER BY created_at ASC", (match_id,))
    for c in call_msgs:
        c["msg_type"] = "call_log"
        c["sender_id"] = c["caller_id"]  # Normalize for frontend rendering
        c["content"] = ""

    # Merge and sort all messages by created_at
    all_msgs = text_msgs + voice_msgs + yt_msgs + call_msgs
    all_msgs.sort(key=lambda x: x.get("created_at", ""))
    
    # Apply WhatsApp-style deletion visibility filtering
    filtered = []
    for msg in all_msgs:
        # Call logs are never deletable — pass through
        if msg.get("msg_type") == "call_log":
            filtered.append(msg)
            continue
        
        is_sender = msg.get("sender_id") == user_id
        
        # "Delete for me" — omit entirely for the user who deleted it
        if is_sender and msg.get("deleted_for_sender"):
            continue
        if not is_sender and msg.get("deleted_for_recipient"):
            continue
        
        # "Delete for everyone" — show placeholder
        if msg.get("deleted_for_everyone"):
            filtered.append({
                "id": msg["id"],
                "match_id": msg["match_id"],
                "sender_id": msg["sender_id"],
                "content": None,
                "created_at": msg["created_at"],
                "msg_type": "deleted",
                "deleted": True,
                "deleted_scope": "everyone"
            })
            continue
        
        # Normal message — strip deletion metadata from response
        for key in ["deleted_for_everyone", "deleted_for_everyone_at", "deleted_for_sender", "deleted_for_recipient"]:
            msg.pop(key, None)
        filtered.append(msg)
    
    return {"messages": filtered}



# ========== MESSAGE DELETION (WhatsApp-style) ==========

@app.post("/api/chat/{match_id}/messages/{message_id}/delete")
async def delete_message(match_id: str, message_id: str, req: DeleteMessageRequest, user_id: str = Depends(get_current_user_id)):
    """Delete a message: 'for_me' hides it for requester only; 'for_everyone' shows placeholder to both."""
    # Verify user is participant
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    
    if req.mode not in ("for_me", "for_everyone"):
        raise HTTPException(status_code=400, detail="Mode must be 'for_me' or 'for_everyone'")
    
    # Find the message across all message tables
    msg = None
    table = None
    for tbl in ["Messages", "VoiceMessages", "YoutubeLinks"]:
        rows = fetch_query(f"SELECT id, sender_id, created_at FROM {tbl} WHERE id = ? AND match_id = ?", (message_id, match_id))
        if rows:
            msg = rows[0]
            table = tbl
            break
    
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    is_sender = msg["sender_id"] == user_id
    
    if req.mode == "for_me":
        if is_sender:
            run_query(f"UPDATE {table} SET deleted_for_sender = 1 WHERE id = ?", (message_id,))
        else:
            run_query(f"UPDATE {table} SET deleted_for_recipient = 1 WHERE id = ?", (message_id,))
        return {"status": "deleted", "mode": "for_me"}
    
    # for_everyone
    if not is_sender:
        raise HTTPException(status_code=403, detail="Only the sender can delete a message for everyone")
    
    # Time window check
    try:
        created = datetime.fromisoformat(str(msg["created_at"]).replace("Z", "+00:00"))
    except:
        created = datetime.strptime(str(msg["created_at"]), "%Y-%m-%d %H:%M:%S")
    
    now = datetime.utcnow()
    age_minutes = (now - created.replace(tzinfo=None)).total_seconds() / 60
    
    if age_minutes > DELETE_FOR_EVERYONE_WINDOW_MINUTES:
        raise HTTPException(
            status_code=400,
            detail=f"This message is too old to delete for everyone (sent {int(age_minutes)} min ago, limit is {DELETE_FOR_EVERYONE_WINDOW_MINUTES} min). You can still delete it for yourself."
        )
    
    run_query(f"UPDATE {table} SET deleted_for_everyone = 1, deleted_for_everyone_at = CURRENT_TIMESTAMP WHERE id = ?", (message_id,))
    return {"status": "deleted", "mode": "for_everyone"}


@app.post("/api/chat/{match_id}/clear")
async def clear_chat(match_id: str, user_id: str = Depends(get_current_user_id)):
    """Clear all messages in a chat for the requesting user only (bulk 'delete for me')."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    
    # For each table: set deleted_for_sender where user is sender, deleted_for_recipient where user is recipient
    for table in ["Messages", "VoiceMessages", "YoutubeLinks"]:
        run_query(f"UPDATE {table} SET deleted_for_sender = 1 WHERE match_id = ? AND sender_id = ?", (match_id, user_id))
        run_query(f"UPDATE {table} SET deleted_for_recipient = 1 WHERE match_id = ? AND sender_id != ?", (match_id, user_id))
    
    return {"status": "cleared"}

class CallLogRequest(BaseModel):
    call_id: str
    match_id: str
    receiver_id: str
    call_type: str
    status: str
    duration: int

@app.post("/api/calls/log")
async def log_call(req: CallLogRequest, user_id: str = Depends(get_current_user_id)):
    run_query(
        "INSERT INTO Calls (id, match_id, caller_id, receiver_id, call_type, status, duration) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (req.call_id, req.match_id, user_id, req.receiver_id, req.call_type, req.status, req.duration)
    )
    return {"status": "logged"}

@app.post("/api/chat/{match_id}/send")
async def send_chat_message(match_id: str, req: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """Send a message. Auto-detects YouTube links and stores rich metadata."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    if match[0]["status"] not in ("accepted", "in_progress", "completed"):
        raise HTTPException(status_code=400, detail="Exchange not active yet")
    
    content = req.content.strip()
    
    # Detect YouTube URLs
    yt_pattern = r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w-]{11})[^\s]*)'
    yt_matches = re.findall(yt_pattern, content)
    
    if yt_matches:
        for yt_url, video_id in yt_matches:
            yt_id = str(uuid.uuid4())
            title, thumbnail, channel, duration = "", "", "", ""
            # Fetch metadata via YouTube OEmbed (no API key needed)
            try:
                oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
                oembed_req = urllib.request.Request(oembed_url, headers={"User-Agent": "SkillSwap/1.0"})
                with urllib.request.urlopen(oembed_req, timeout=5) as resp:
                    oembed_data = json.loads(resp.read().decode())
                    title = oembed_data.get("title", "YouTube Video")
                    channel = oembed_data.get("author_name", "")
                thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            except:
                title = "YouTube Video"
                thumbnail = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            
            run_query(
                "INSERT INTO YoutubeLinks (id, match_id, sender_id, url, video_id, title, thumbnail, channel, duration) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (yt_id, match_id, user_id, yt_url, video_id, title, thumbnail, channel, duration)
            )
        return {"status": "sent", "type": "youtube", "count": len(yt_matches)}
    
    # Normal text message
    msg_id = str(uuid.uuid4())
    run_query(
        "INSERT INTO Messages (id, match_id, sender_id, content) VALUES (?, ?, ?, ?)",
        (msg_id, match_id, user_id, content)
    )
    
    return {"status": "sent", "message_id": msg_id}

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/chat/{match_id}/upload")
async def upload_file_to_chat(match_id: str, req: FileUploadRequest, user_id: str = Depends(get_current_user_id)):
    """Upload a file (doc, pdf, image) to a chat room via base64."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    if match[0]["status"] not in ("accepted", "in_progress", "completed"):
        raise HTTPException(status_code=400, detail="Exchange not active yet")
    
    # Validate file type
    allowed = [".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".txt", ".pptx", ".xlsx"]
    ext = os.path.splitext(req.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"File type {ext} not allowed")
    
    file_id = str(uuid.uuid4())
    safe_filename = f"{file_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    contents = base64.b64decode(req.data)
    with open(file_path, "wb") as f:
        f.write(contents)
    
    msg_id = str(uuid.uuid4())
    file_meta = json.dumps({"type": "file", "filename": req.filename, "stored_as": safe_filename, "size": len(contents), "ext": ext})
    run_query(
        "INSERT INTO Messages (id, match_id, sender_id, content) VALUES (?, ?, ?, ?)",
        (msg_id, match_id, user_id, file_meta)
    )
    return {"status": "uploaded", "message_id": msg_id, "filename": req.filename}

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

@app.post("/api/chat/{match_id}/voice")
async def upload_voice_message(match_id: str, req: VoiceUploadRequest, user_id: str = Depends(get_current_user_id)):
    """Upload a voice message. Transcribes via Groq Whisper and translates if needed."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    if match[0]["status"] not in ("accepted", "in_progress", "completed"):
        raise HTTPException(status_code=400, detail="Exchange not active yet")
    
    # Validate size (15MB max)
    audio_bytes = base64.b64decode(req.data)
    if len(audio_bytes) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large. Max 15MB.")
    
    # Save audio file
    voice_id = str(uuid.uuid4())
    filename = f"{voice_id}.webm"
    file_path = os.path.join(AUDIO_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(audio_bytes)
    
    # Determine receiver's preferred language
    m = match[0]
    receiver_id = m["user2_id"] if m["user1_id"] == user_id else m["user1_id"]
    receiver = fetch_query("SELECT preferred_language FROM Users WHERE id = ?", (receiver_id,))
    receiver_lang = receiver[0]["preferred_language"] if receiver else "English"
    sender = fetch_query("SELECT preferred_language FROM Users WHERE id = ?", (user_id,))
    sender_lang = sender[0]["preferred_language"] if sender else "English"
    
    original_text = ""
    translated_text = ""
    language_code = sender_lang
    translation_status = "none"
    
    # Speech-to-Text via Groq Whisper API
    original_text, language_code = groq_whisper_transcribe(audio_bytes, filename=filename, default_lang=sender_lang)
    
    # Translation if languages differ
    if original_text and original_text != "[Transcription unavailable]" and receiver_lang.lower() != sender_lang.lower() and language_code.lower() != receiver_lang.lower():
        try:
            from langchain_groq import ChatGroq
            from langchain_core.messages import HumanMessage
            
            llm = ChatGroq(model_name="openai/gpt-oss-120b", groq_api_key=groq_api_key)
            translate_prompt = f"""Translate the following text to {receiver_lang}. 
Rules:
- Do NOT translate URLs, code snippets, email addresses, or file names.
- Keep the translation natural and conversational.
- Return ONLY the translated text, nothing else.

Text: {original_text}"""
            response = llm.invoke([HumanMessage(content=translate_prompt)])
            translated_text = response.content.strip()
            translation_status = "completed"
        except Exception as e:
            print(f"Translation failed: {e}")
            translated_text = original_text
            translation_status = "failed"
    else:
        translated_text = original_text
        translation_status = "same_language"
    
    # Save to database
    run_query(
        "INSERT INTO VoiceMessages (id, match_id, sender_id, filename, duration, original_text, translated_text, language_code, translation_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (voice_id, match_id, user_id, filename, req.duration, original_text, translated_text, language_code, translation_status)
    )
    
    return {
        "status": "uploaded",
        "voice_id": voice_id,
        "original_text": original_text,
        "translated_text": translated_text,
        "translation_status": translation_status
    }

@app.get("/api/audio/{filename}")
async def serve_audio(filename: str):
    """Serve an uploaded audio file."""
    file_path = os.path.join(AUDIO_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(file_path, media_type="audio/webm", filename=filename)

@app.get("/api/files/{filename}")
async def download_file(filename: str):
    """Download a shared file."""
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)

@app.get("/api/notifications/stream")
async def notification_stream(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps({'type': 'ping'})}\\n\\n"
            await asyncio.sleep(10)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

from fastapi import UploadFile, File

CALLS_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads", "calls")
os.makedirs(CALLS_AUDIO_DIR, exist_ok=True)

# Temporary memory to store partial call transcripts
call_transcripts_in_memory = {}

async def process_call_summary(call_id: str, is_partial: bool = False):
    try:
        run_query("UPDATE Calls SET summary_status = 'processing' WHERE id = ?", (call_id,))
        
        call_info = fetch_query("SELECT caller_id FROM Calls WHERE id = ?", (call_id,))
        caller_id = call_info[0]["caller_id"] if call_info else None
        
        merged_text = ""
        if call_id in call_transcripts_in_memory:
            for speaker_id, text in call_transcripts_in_memory[call_id].items():
                label = "Caller" if speaker_id == caller_id else "Receiver"
                merged_text += f"[{label}]: {text}\n\n"
                
        if not merged_text.strip():
            run_query("UPDATE Calls SET summary_status = 'failed' WHERE id = ?", (call_id,))
            return

        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            run_query("UPDATE Calls SET summary_status = 'failed' WHERE id = ?", (call_id,))
            return
            
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage
        llm = ChatGroq(model_name="openai/gpt-oss-20b", groq_api_key=groq_api_key)
        
        partial_str = "true" if is_partial else "false"
        prompt = f"""You are an AI assistant analyzing a call transcript between two users.
Here is the transcript:
{merged_text}

Provide a summary in STRICT JSON format with the following keys exactly:
{{
  "summary": "2-3 sentence overview of what was discussed",
  "key_points": ["point 1", "point 2"],
  "action_items": ["action 1", "action 2"],
  "is_partial": {partial_str}
}}
Return ONLY the raw JSON string, nothing else. Do not use markdown code blocks.
"""
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        # Validate json
        json.loads(content)
        
        run_query("UPDATE Calls SET transcript = ?, summary = ?, summary_status = 'ready' WHERE id = ?", (merged_text, content, call_id))
        
        # Cleanup
        if call_id in call_transcripts_in_memory:
            del call_transcripts_in_memory[call_id]
            
    except Exception as e:
        print(f"Summary failed: {e}")
        run_query("UPDATE Calls SET summary_status = 'failed' WHERE id = ?", (call_id,))

@app.post("/api/calls/{call_id}/recording")
async def upload_call_recording(call_id: str, file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    # Note: We do not check if the call exists yet, because the receiver might upload 
    # the recording before the initiator successfully logs the call via /api/calls/log.
    
    audio_bytes = await file.read()
    
    file_path = os.path.join(CALLS_AUDIO_DIR, f"{call_id}_{user_id}.webm")
    with open(file_path, "wb") as f:
        f.write(audio_bytes)
        
    transcript_text, _ = groq_whisper_transcribe(audio_bytes, filename=file.filename)
    
    if call_id not in call_transcripts_in_memory:
        call_transcripts_in_memory[call_id] = {}
        
    call_transcripts_in_memory[call_id][user_id] = transcript_text
    
    # Check if both have uploaded
    if len(call_transcripts_in_memory[call_id]) == 2:
        asyncio.create_task(process_call_summary(call_id, is_partial=False))
    else:
        # Schedule timeout task to process as partial if second upload doesn't arrive
        async def wait_and_process():
            await asyncio.sleep(120)  # 2 minutes timeout
            if call_id in call_transcripts_in_memory and len(call_transcripts_in_memory[call_id]) == 1:
                await process_call_summary(call_id, is_partial=True)
                
        asyncio.create_task(wait_and_process())
        
    return {"status": "uploaded", "transcript": transcript_text}

@app.get("/api/calls/{call_id}/summary")
async def get_call_summary(call_id: str, user_id: str = Depends(get_current_user_id)):
    call = fetch_query("SELECT * FROM Calls WHERE id = ? AND (caller_id = ? OR receiver_id = ?)", (call_id, user_id, user_id))
    if not call:
        raise HTTPException(status_code=403, detail="Not part of this call")
        
    status = call[0].get("summary_status", "none")
    summary = call[0].get("summary", None)
    
    if summary:
        try:
            summary = json.loads(summary)
        except:
            summary = {"error": "Invalid JSON"}
            
    return {"summary_status": status, "summary": summary}

@app.get("/api/matches/{match_id}/learning-path")
async def get_learning_path(match_id: str, request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    rows = fetch_query("SELECT * FROM LearningPaths WHERE match_id = ?", (match_id,))
    if not rows:
        return {"status": "success", "paths": []}
    return {"status": "success", "paths": rows}

@app.post("/api/matches/{match_id}/learning-path")
async def generate_learning_path(match_id: str, request: Request):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    match_rows = fetch_query("SELECT * FROM Matches WHERE id = ?", (match_id,))
    if not match_rows:
        raise HTTPException(status_code=404, detail="Match not found")
    
    match = match_rows[0]
    if match['user1_id'] != user_id and match['user2_id'] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    existing = fetch_query("SELECT id FROM LearningPaths WHERE match_id = ?", (match_id,))
    if existing:
        return {"status": "success", "message": "Already generated", "paths": fetch_query("SELECT * FROM LearningPaths WHERE match_id = ?", (match_id,))}

    u1 = match['user1_id']
    u2 = match['user2_id']
    
    u1_skills = fetch_query("SELECT * FROM Skills WHERE user_id = ?", (u1,))
    u2_skills = fetch_query("SELECT * FROM Skills WHERE user_id = ?", (u2,))
    
    u1_offered = [{"name": s['skill_name'], "level": s['level']} for s in u1_skills if s['type'] == 'offered']
    u1_needed = [{"name": s['skill_name'], "level": s['level']} for s in u1_skills if s['type'] == 'needed']
    
    u2_offered = [{"name": s['skill_name'], "level": s['level']} for s in u2_skills if s['type'] == 'offered']
    u2_needed = [{"name": s['skill_name'], "level": s['level']} for s in u2_skills if s['type'] == 'needed']
    
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise HTTPException(status_code=500, detail="LLM configuration missing")
        
    from langchain_groq import ChatGroq
    from langchain_core.messages import HumanMessage
    
    try:
        llm = ChatGroq(model_name="openai/gpt-oss-20b", groq_api_key=groq_api_key)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to init LLM")
        
    schema_instructions = '''
    Return ONLY valid JSON shaped exactly like this, with no markdown formatting or extra text:
    {
      "skill": "skill_name",
      "learner_level": "level",
      "estimated_sessions": 4,
      "sessions": [
        {
          "session_number": 1,
          "title": "...",
          "objectives": ["...", "..."],
          "suggested_duration_minutes": 45
        }
      ],
      "milestones": ["...", "..."]
    }
    '''

    def generate_for_direction(learner_id, teacher_id, learner_needs, teacher_offers, ai_reasoning):
        prompt = f"""
        You are an expert curriculum designer. Generate a learning path session plan for a user learning a skill from a peer.
        The matchmaking reasoning for these users was: {ai_reasoning}
        The learner wants to learn: {json.dumps(learner_needs)}
        The teacher can teach: {json.dumps(teacher_offers)}
        
        Figure out the best skill for the teacher to teach the learner, and generate a session plan based on the learner's level.
        
        {schema_instructions}
        """
        try:
            res = llm.invoke([HumanMessage(content=prompt)])
            text = res.content.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            return json.loads(text)
        except Exception as e:
            try:
                res = llm.invoke([HumanMessage(content=prompt + "\n\nFAILED PREVIOUSLY. YOU MUST RETURN ONLY RAW VALID JSON.")])
                text = res.content.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                return json.loads(text)
            except Exception as e2:
                return None
                
    plan_u1_learns_from_u2 = generate_for_direction(u1, u2, u1_needed, u2_offered, match['ai_reasoning'])
    plan_u2_learns_from_u1 = generate_for_direction(u2, u1, u2_needed, u1_offered, match['ai_reasoning'])
    
    if not plan_u1_learns_from_u2 and not plan_u2_learns_from_u1:
        raise HTTPException(status_code=502, detail="Failed to generate valid learning paths")
        
    if plan_u1_learns_from_u2:
        run_query("INSERT INTO LearningPaths (id, match_id, generated_for_user_id, skill_name, plan_json) VALUES (?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), match_id, u1, plan_u1_learns_from_u2.get('skill', 'Unknown'), json.dumps(plan_u1_learns_from_u2)))
    if plan_u2_learns_from_u1:
        run_query("INSERT INTO LearningPaths (id, match_id, generated_for_user_id, skill_name, plan_json) VALUES (?, ?, ?, ?, ?)",
                  (str(uuid.uuid4()), match_id, u2, plan_u2_learns_from_u1.get('skill', 'Unknown'), json.dumps(plan_u2_learns_from_u1)))
                  
    paths = fetch_query("SELECT * FROM LearningPaths WHERE match_id = ?", (match_id,))
    return {"status": "success", "paths": paths}

@app.get("/api/matches/{match_id}/notes")
def get_match_notes(match_id: str, current_user_id: str = Depends(get_current_user_id)):
    q = "SELECT user1_id, user2_id FROM Matches WHERE id = ?"
    match = fetch_query(q, (match_id,))
    if not match or current_user_id not in (match[0]["user1_id"], match[0]["user2_id"]):
        raise HTTPException(status_code=403, detail="Not authorized for this match")
    
    notes = fetch_query("SELECT content, last_edited_by, updated_at FROM SharedNotes WHERE match_id = ?", (match_id,))
    if not notes:
        return {"content": "", "last_edited_by": None, "updated_at": None}
    return notes[0]

class NoteUpdate(BaseModel):
    content: str

@app.post("/api/matches/{match_id}/notes")
def update_match_notes(match_id: str, req: NoteUpdate, current_user_id: str = Depends(get_current_user_id)):
    user_id = current_user_id
    q = "SELECT user1_id, user2_id FROM Matches WHERE id = ?"
    match = fetch_query(q, (match_id,))
    if not match or user_id not in (match[0]["user1_id"], match[0]["user2_id"]):
        raise HTTPException(status_code=403, detail="Not authorized for this match")
    
    run_query(
        "INSERT INTO SharedNotes (id, match_id, content, last_edited_by, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET content=excluded.content, last_edited_by=excluded.last_edited_by, updated_at=CURRENT_TIMESTAMP",
        (match_id, match_id, req.content, user_id)
    )
    return {"status": "ok"}

@app.get("/api/webrtc/ice-config")
def get_ice_config(current_user_id: str = Depends(get_current_user_id)):
    stun_url = os.getenv("STUN_URL", "stun:stun.l.google.com:19302")
    ice_servers = [{"urls": stun_url}]
    
    turn_url = os.getenv("TURN_URL")
    turn_user = os.getenv("TURN_USERNAME")
    turn_pass = os.getenv("TURN_CREDENTIAL")
    
    if turn_url and turn_user and turn_pass:
        ice_servers.append({
            "urls": turn_url,
            "username": turn_user,
            "credential": turn_pass
        })
        
    return {"iceServers": ice_servers}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ══════════════════════════════════════════════════════════════
# GAMIFICATION ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.get("/api/gamification/profile")
async def gamification_profile(user_id: str = Depends(get_current_user_id)):
    """Return the authenticated user's streak data and earned badges."""
    # Streak data
    streak_rows = fetch_query("SELECT * FROM UserStreaks WHERE user_id = ?", (user_id,))
    streak = streak_rows[0] if streak_rows else {"current_streak": 0, "longest_streak": 0, "last_completed_period": None}

    # Earned badges
    badges = fetch_query(
        """SELECT b.id, b.code, b.name, b.description, ub.awarded_at
           FROM UserBadges ub JOIN Badges b ON ub.badge_id = b.id
           WHERE ub.user_id = ?
           ORDER BY ub.awarded_at DESC""",
        (user_id,)
    )

    # Completed exchange count
    completed = fetch_query(
        "SELECT COUNT(*) as cnt FROM Matches WHERE status = 'completed' AND (user1_id = ? OR user2_id = ?)",
        (user_id, user_id)
    )
    completed_count = completed[0]["cnt"] if completed else 0

    return {
        "current_streak": streak["current_streak"],
        "longest_streak": streak["longest_streak"],
        "last_completed_period": streak.get("last_completed_period"),
        "completed_exchanges": completed_count,
        "badges": badges,
    }


@app.get("/api/gamification/leaderboard")
async def gamification_leaderboard(city: str = "", user_id: str = Depends(get_current_user_id)):
    """
    City-level leaderboard ranked by a simple engagement formula.
    
    Ranking formula: completed_exchanges * 2 + trust_score
    This weights actual exchange activity more heavily than passive trust,
    encouraging active participation.
    
    Returns top 20 users. Only includes users with leaderboard_visible = 1.
    If no city is provided, uses the authenticated user's city.
    """
    if not city:
        user_rows = fetch_query("SELECT city FROM Users WHERE id = ?", (user_id,))
        city = user_rows[0]["city"] if user_rows else ""

    if not city:
        return {"leaderboard": [], "city": ""}

    leaderboard = fetch_query(
        """SELECT u.id, u.name, u.city, u.trust_score,
                  COUNT(CASE WHEN m.status = 'completed' THEN 1 END) as completed_exchanges,
                  (COUNT(CASE WHEN m.status = 'completed' THEN 1 END) * 2 + COALESCE(u.trust_score, 0)) as score
           FROM Users u
           LEFT JOIN Matches m ON (m.user1_id = u.id OR m.user2_id = u.id)
           WHERE LOWER(u.city) = LOWER(?) AND u.leaderboard_visible = 1
           GROUP BY u.id
           ORDER BY score DESC
           LIMIT 20""",
        (city,)
    )

    # Add rank numbers and badge counts
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1
        badge_count = fetch_query(
            "SELECT COUNT(*) as cnt FROM UserBadges WHERE user_id = ?",
            (entry["id"],)
        )
        entry["badge_count"] = badge_count[0]["cnt"] if badge_count else 0

    return {"leaderboard": leaderboard, "city": city}
