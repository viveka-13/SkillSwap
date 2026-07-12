import os
import json
import asyncio
import uuid
from datetime import datetime, timedelta
import base64
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import jwt
import bcrypt

from agent.workflow import run_matchmaking
from agent.memory import run_query, fetch_query, skills_collection

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-hackathon-key")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

class UserRegister(BaseModel):
    name: str
    email: str
    password: str
    city: str
    lat: float
    lon: float
    bio: str
    skills_offered: list[str]
    skills_needed: list[str]

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
    hashed_pwd = hash_password(user.password)
    user_id = str(uuid.uuid4())
    try:
        run_query(
            "INSERT INTO Users (id, name, email, password_hash, city, lat, lon, bio) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, user.name, user.email, hashed_pwd, user.city, user.lat, user.lon, user.bio)
        )
        
        for skill in user.skills_offered:
            skill_id = str(uuid.uuid4())
            run_query("INSERT INTO Skills (id, user_id, skill_name, type) VALUES (?, ?, ?, 'offered')", (skill_id, user_id, skill))
            skills_collection.add(documents=[skill], metadatas=[{"user_id": user_id, "type": "offered", "skill_name": skill}], ids=[skill_id])
            
        for skill in user.skills_needed:
            skill_id = str(uuid.uuid4())
            run_query("INSERT INTO Skills (id, user_id, skill_name, type) VALUES (?, ?, ?, 'needed')", (skill_id, user_id, skill))
            skills_collection.add(documents=[skill], metadatas=[{"user_id": user_id, "type": "needed", "skill_name": skill}], ids=[skill_id])
            
        return {"status": "success", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login")
async def login(creds: UserLogin):
    rows = fetch_query("SELECT * FROM Users WHERE email = ?", (creds.email,))
    if not rows or not verify_password(creds.password, rows[0]["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = jwt.encode({"sub": rows[0]["id"], "exp": datetime.utcnow() + timedelta(days=1)}, SECRET_KEY, algorithm="HS256")
    return {"token": token, "user": {"id": rows[0]["id"], "name": rows[0]["name"]}}

@app.post("/api/matches")
async def get_matches(req: MatchRequest, user_id: str = Depends(get_current_user_id)):
    matches = await run_matchmaking(user_id, req.needed_skill, req.offered_skill)
    return {"matches": matches}

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
    """Accept an exchange request — transfers credits and logs history."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND user2_id = ?", (match_id, user_id))
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match[0]["status"] != "pending":
        raise HTTPException(status_code=400, detail="Already processed")
    
    run_query("UPDATE Matches SET status = 'accepted' WHERE id = ?", (match_id,))
    # Transfer credits
    run_query("UPDATE Users SET wallet_balance = wallet_balance - 5 WHERE id = ?", (match[0]["user1_id"],))
    run_query("UPDATE Users SET wallet_balance = wallet_balance + 5 WHERE id = ?", (match[0]["user2_id"],))
    # Log exchange
    ex_id = str(uuid.uuid4())
    run_query("INSERT INTO ExchangeHistory (id, match_id, credits_transferred) VALUES (?, ?, 5)", (ex_id, match_id))
    # Notify requester
    notif_id = str(uuid.uuid4())
    acceptor = fetch_query("SELECT name FROM Users WHERE id = ?", (user_id,))
    acceptor_name = acceptor[0]["name"] if acceptor else "Someone"
    run_query(
        "INSERT INTO Notifications (id, user_id, content) VALUES (?, ?, ?)",
        (notif_id, match[0]["user1_id"], f"✅ {acceptor_name} accepted your exchange request! 5 credits transferred.")
    )
    return {"status": "accepted", "credits_transferred": 5}

@app.get("/api/notifications")
async def get_notifications(user_id: str = Depends(get_current_user_id)):
    """Get all notifications for the current user."""
    notifs = fetch_query("SELECT * FROM Notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (user_id,))
    return {"notifications": notifs}

@app.get("/api/exchange/pending")
async def get_pending_requests(user_id: str = Depends(get_current_user_id)):
    """Get pending exchange requests sent TO this user."""
    pending = fetch_query(
        """SELECT m.id, m.compatibility_score, m.ai_reasoning, m.created_at, u.name as requester_name
           FROM Matches m JOIN Users u ON m.user1_id = u.id
           WHERE m.user2_id = ? AND m.status = 'pending' ORDER BY m.created_at DESC""",
        (user_id,)
    )
    return {"pending": pending}

@app.get("/api/exchange/history")
async def get_exchange_history(user_id: str = Depends(get_current_user_id)):
    """Get completed exchanges."""
    history = fetch_query(
        """SELECT eh.id, eh.completed_at, eh.credits_transferred, m.compatibility_score, m.ai_reasoning,
                  u1.name as user1_name, u2.name as user2_name
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
    """Get all accepted matches to act as chat rooms."""
    rooms = fetch_query(
        """SELECT m.id as match_id, u.id as other_user_id, u.name as other_user_name, m.compatibility_score 
           FROM Matches m JOIN Users u ON (m.user1_id = u.id OR m.user2_id = u.id)
           WHERE (m.user1_id = ? OR m.user2_id = ?) AND u.id != ? AND m.status = 'accepted'
           ORDER BY m.created_at DESC""",
        (user_id, user_id, user_id)
    )
    return {"rooms": rooms}

@app.get("/api/chat/{match_id}/messages")
async def get_chat_messages(match_id: str, user_id: str = Depends(get_current_user_id)):
    """Get all messages for a specific match/chat room."""
    # Verify user is part of the match
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
        
    messages = fetch_query("SELECT * FROM Messages WHERE match_id = ? ORDER BY created_at ASC", (match_id,))
    return {"messages": messages}

@app.post("/api/chat/{match_id}/send")
async def send_chat_message(match_id: str, req: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """Send a message to a chat room."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    if match[0]["status"] != "accepted":
        raise HTTPException(status_code=400, detail="Match not accepted yet")
        
    msg_id = str(uuid.uuid4())
    run_query(
        "INSERT INTO Messages (id, match_id, sender_id, content) VALUES (?, ?, ?, ?)",
        (msg_id, match_id, user_id, req.content)
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
    if match[0]["status"] != "accepted":
        raise HTTPException(status_code=400, detail="Match not accepted yet")
    
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
