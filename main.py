import os
import json
import asyncio
import uuid
import re
import urllib.request
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
    """Get all messages (text, file, voice, youtube) for a chat room, merged chronologically."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    
    # Text + File messages
    text_msgs = fetch_query("SELECT id, match_id, sender_id, content, created_at FROM Messages WHERE match_id = ? ORDER BY created_at ASC", (match_id,))
    for m in text_msgs:
        m["msg_type"] = "text"  # will be overridden by JS if content is JSON file meta
    
    # Voice messages
    voice_msgs = fetch_query("SELECT id, match_id, sender_id, filename, duration, original_text, translated_text, language_code, translation_status, created_at FROM VoiceMessages WHERE match_id = ? ORDER BY created_at ASC", (match_id,))
    for v in voice_msgs:
        v["msg_type"] = "voice"
        v["content"] = ""  # placeholder for unified rendering
    
    # YouTube links
    yt_msgs = fetch_query("SELECT id, match_id, sender_id, url, video_id, title, thumbnail, channel, duration, created_at FROM YoutubeLinks WHERE match_id = ? ORDER BY created_at ASC", (match_id,))
    for y in yt_msgs:
        y["msg_type"] = "youtube"
        y["content"] = ""  # placeholder
    
    # Merge and sort all messages by created_at
    all_msgs = text_msgs + voice_msgs + yt_msgs
    all_msgs.sort(key=lambda x: x.get("created_at", ""))
    
    return {"messages": all_msgs}

@app.post("/api/chat/{match_id}/send")
async def send_chat_message(match_id: str, req: ChatRequest, user_id: str = Depends(get_current_user_id)):
    """Send a message. Auto-detects YouTube links and stores rich metadata."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    if match[0]["status"] != "accepted":
        raise HTTPException(status_code=400, detail="Match not accepted yet")
    
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

AUDIO_DIR = os.path.join(os.path.dirname(__file__), "data", "uploads", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

@app.post("/api/chat/{match_id}/voice")
async def upload_voice_message(match_id: str, req: VoiceUploadRequest, user_id: str = Depends(get_current_user_id)):
    """Upload a voice message. Transcribes via Groq Whisper and translates if needed."""
    match = fetch_query("SELECT * FROM Matches WHERE id = ? AND (user1_id = ? OR user2_id = ?)", (match_id, user_id, user_id))
    if not match:
        raise HTTPException(status_code=403, detail="Not part of this match")
    if match[0]["status"] != "accepted":
        raise HTTPException(status_code=400, detail="Match not accepted yet")
    
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
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            import http.client
            import mimetypes
            
            boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
            
            # Build multipart body
            body = b""
            # File field
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
            body += b'Content-Type: audio/webm\r\n\r\n'
            body += audio_bytes
            body += b'\r\n'
            # Model field
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
            body += b'whisper-large-v3\r\n'
            # Language hint (optional)
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
            language_code = resp_data.get("language", sender_lang)
            
        except Exception as e:
            print(f"Whisper transcription failed: {e}")
            original_text = "[Transcription unavailable]"
        
        # Translation if languages differ
        if original_text and receiver_lang.lower() != sender_lang.lower() and language_code.lower() != receiver_lang.lower():
            try:
                from langchain_groq import ChatGroq
                from langchain_core.messages import HumanMessage
                
                llm = ChatGroq(model_name="llama-3.1-8b-instant", groq_api_key=groq_api_key)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

