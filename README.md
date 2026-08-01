# Hyperlocal Skill Swap & Community Exchange Platform

## 📋 Problem Statement

Many individuals have valuable skills but lack financial resources to access services they need. There is no easy way for people in local communities to discover, connect with, and exchange skills without using money. Existing platforms are either monetized or lack intelligent matchmaking.

**Challenge:** Build a community platform where users can list skills they offer (coding, tutoring, cooking, repairs) and exchange them without money. The platform should include trust ratings, matchmaking algorithms, and safe communication channels.

---

## 💡 Our Solution — SkillSwap

**SkillSwap** is an AI-powered hyperlocal platform that enables community members to exchange skills without money. It uses **semantic AI matchmaking** to connect people whose skills complement each other, a **credit-based trust economy** to ensure fairness, and **secure chat with file sharing** for safe knowledge exchange.

### What Makes It Unique?
| Feature | Traditional Platforms | SkillSwap |
|---|---|---|
| Matching | Keyword-based search | AI Semantic Matching (ChromaDB + LLM) |
| Location | City-level | Hyperlocal (Haversine distance in KM) |
| Trust | Star ratings only | AI-computed Trust Score + Credit Wallet |
| Communication | Basic text chat | Chat, File Sharing, AI Voice Translations, & WebRTC Calling |
| Cost | Paid services | Zero money — purely skill-based exchange |

---

## 🏗️ System Architecture

```
┌──────────────┐      ┌──────────────────────────────────────┐
│   Frontend   │      │            Backend (FastAPI)          │
│  (HTML/CSS/  │◄────►│                                      │
│  JavaScript) │      │  ┌──────────────────────────────┐    │
│              │      │  │    AI Agent (LangGraph)       │    │
│  - Auth View │      │  │                              │    │
│  - Dashboard │      │  │  Node 1: Fetch User Profile  │    │
│  - AI Match  │      │  │  Node 2: Semantic Matching   │    │
│  - Chat Room │      │  │  Node 3: LLM Scoring         │    │
│  - File Share│      │  │  Node 4: Finalize Top 5      │    │
│              │      │  └──────────┬───────────────────┘    │
└──────────────┘      │             │                         │
                      │  ┌──────────▼───────────────────┐    │
                      │  │      Data Layer               │    │
                      │  │  SQLite (Users, Skills,       │    │
                      │  │   Matches, Messages, Ratings) │    │
                      │  │  ChromaDB (Vector Embeddings) │    │
                      │  └──────────────────────────────┘    │
                      └──────────────────────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │   Groq Cloud     │
                              │  (Llama 3.1 8B)  │
                              └─────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | FastAPI (Python) | REST APIs, Authentication, Business Logic |
| **Real-Time Comm** | WebSockets & WebRTC | Zero-latency P2P Audio/Video calling & signaling |
| **AI Framework** | LangGraph + LangChain | Multi-step AI agent workflow for matchmaking |
| **LLM** | Groq (Llama 3.1 8B Instant) | Compatibility scoring, translation, & AI reasoning |
| **STT** | Groq (Whisper-large-v3) | Fast, accurate voice message transcription |
| **Vector Database** | ChromaDB | Semantic skill search via embeddings |
| **Relational Database** | SQLite (WAL Mode) | Users, Skills, Matches, Messages, Calls, Credits |
| **Authentication** | JWT + Bcrypt | Secure login with hashed passwords |
| **Frontend** | HTML, CSS, JavaScript (SPA) | Premium UI with glassmorphism & animations |
| **File Storage** | Server-side (Base64 upload) | PDF, DOCX, Image sharing in chat |

---

## ✨ Key Features

### 1. 🔐 Secure Registration & Login
- Users register with their name, email, city, GPS coordinates, skills offered, and skills needed.
- Passwords are hashed using **Bcrypt** before storing.
- Sessions use **JWT tokens** with 24-hour expiry.
- Upon registration, skills are **embedded into ChromaDB** as vectors for semantic search.

### 2. 🧠 AI-Powered Matchmaking (LangGraph Pipeline)
The matchmaking engine is a **5-node LangGraph state machine**:

| Node | What It Does |
|---|---|
| **Fetch User Profile** | Loads the current user's location (lat/lon) and full skill profile from SQLite |
| **Semantic Matching** | Queries ChromaDB to find users whose *offered* skills semantically match what the current user *needs*. |
| **Mutual Exchange Validation** | Strictly validates a two-way skill exchange (they offer what you need AND you offer what they need). Bypasses LLM scoring for one-sided matches. |
| **Compatibility Scoring** | For valid matches, the **Groq LLM (Llama 3.1)** generates a 0-100% compatibility score and a 1-sentence AI reasoning emphasizing the mutual exchange |
| **Finalize Recommendations** | Sorts by score and returns the **Top 5** matches |

### 3. 📍 Hyperlocal Distance Calculation
- Uses the **Haversine formula** to calculate the real-world distance (in KM) between two GPS coordinates.
- Matches display distance like: `📍 2.3 km away`.

### 4. 🪙 Credit-Based Trust Economy
- Every new user starts with **10 credits**.
- When an exchange is accepted, **5 credits** transfer from the requester to the acceptor.
- This ensures accountability and prevents abuse.

### 5. ⭐ Trust Score & Ratings
- After exchanges, users rate each other (1-5 stars).
- The **trust score** is the average of all ratings received.
- Higher trust = better visibility in matchmaking.

### 6. 💬 Advanced Communication Channel (WebSockets & WebRTC)
- Once a match is **accepted**, a private **Chat Room** is created between both users.
- **📞 Real-Time Audio & Video Calling**: Features native WhatsApp-style peer-to-peer (P2P) calling using **WebRTC** for zero-latency communication. **FastAPI WebSockets** act as the signaling server to instantly route connection offers.
- **🎤 Native Voice Messaging**: Users can record and send voice notes directly in the browser using the `MediaRecorder` API.
- **🌐 AI Auto-Translation**: Voice messages are transcribed using **Groq Whisper** and translated on-the-fly using **Llama 3.1** if the sender and receiver have different preferred languages.
- **🎥 YouTube Rich Previews**: Automatically detects YouTube links in messages and fetches video metadata/thumbnails via OEmbed for beautiful inline preview cards.
- **📜 Persistent Call History**: Audio and Video call logs (including duration, missed/rejected states) are merged seamlessly into the chat feed.

### 7. 📎 File & Document Sharing
- Users can share **PDFs, DOCX, PPTX, Images (JPG/PNG)**, and more via the `+` button in chat.
- Files are uploaded as **Base64**, saved on the server, and displayed with icons and download links.
- Image files show an **inline preview** directly in the chat bubble.

### 8. 🔔 Notification System
- When someone sends you a match request, you get a notification.
- When someone accepts your request, you're notified with credit transfer details.

---

## 🔄 Complete User Flow

```
Step 1: User A Registers
   ├── Name, Email, Password, City, Lat/Lon
   ├── Skills Offered: ["Python", "Machine Learning"]
   └── Skills Needed: ["Cooking", "Graphic Design"]
        └── Skills embedded into ChromaDB as vectors

Step 2: User A Searches for Matches
   ├── Enters: "I need Cooking, I offer Python"
   ├── ChromaDB finds users who OFFER "Cooking" (semantic match)
   ├── LangGraph validates a strict TWO-WAY mutual skill exchange
   ├── LLM scores each validated candidate (0-100%)
   └── Returns Top 5 matches with a breakdown of "They can teach you" & "Your skills useful for them"

Step 3: User A Sends Exchange Request to User B
   ├── Match record created in SQLite (status: "pending")
   └── Notification sent to User B

Step 4: User B Accepts the Request
   ├── Match status → "accepted"
   ├── 5 credits: User A → User B
   ├── Exchange logged in ExchangeHistory
   └── Chat room unlocked

Step 5: Both Users Chat & Share Files
   ├── Text messages stored in Messages table
   ├── Files (PDF, DOCX, Images) uploaded via Base64
   └── Both can download shared resources

Step 6: Users Rate Each Other
   └── Trust score updated as average of all ratings
```

---

## 🗃️ Database Schema

### SQLite Tables

| Table | Key Columns | Purpose |
|---|---|---|
| **Users** | id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance | User profiles |
| **Skills** | id, user_id, skill_name, type (offered/needed) | Skill listings |
| **Matches** | id, user1_id, user2_id, compatibility_score, ai_reasoning, status | Match tracking |
| **Messages** | id, match_id, sender_id, content, is_flagged | Chat messages & file metadata |
| **VoiceMessages**| id, match_id, sender_id, filename, translated_text | Audio voice notes |
| **YoutubeLinks**| id, match_id, url, title, thumbnail | Rich YouTube previews |
| **Calls** | id, match_id, caller_id, call_type, status, duration | WebRTC call history |
| **ExchangeHistory** | id, match_id, credits_transferred, completed_at | Completed exchanges |
| **Ratings** | id, exchange_id, reviewer_id, reviewee_id, rating, review_text | Trust ratings |
| **Notifications** | id, user_id, content, is_read | User notifications |

### ChromaDB Collections

| Collection | Content | Purpose |
|---|---|---|
| **skills** | Skill names as document vectors with user_id metadata | Semantic skill matching |
| **profiles** | User profile embeddings | (Reserved for future use) |

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register user + embed skills in ChromaDB |
| `POST` | `/api/auth/login` | Login and receive JWT token |
| `GET` | `/api/dashboard` | Get user profile, trust score, wallet, skills |
| `POST` | `/api/matches` | AI matchmaking pipeline (LangGraph) |
| `POST` | `/api/exchange/request` | Send exchange request |
| `POST` | `/api/exchange/accept/{id}` | Accept request + transfer credits |
| `GET` | `/api/exchange/pending` | Pending incoming requests |
| `GET` | `/api/exchange/history` | Completed exchange history |
| `GET` | `/api/chat/rooms` | List active chat rooms |
| `GET` | `/api/chat/{id}/messages` | Get chat message history |
| `POST` | `/api/chat/{id}/send` | Send a text message (auto-detects YouTube links) |
| `POST` | `/api/chat/{id}/upload` | Upload a file (PDF, DOCX, Image) |
| `POST` | `/api/chat/{id}/voice` | Upload a voice note (triggers Whisper STT + Llama Translation) |
| `WS` | `/api/ws/calls/{user_id}` | WebSocket endpoint for WebRTC signaling |
| `POST` | `/api/calls/log` | Log WebRTC call history to database |
| `GET` | `/api/files/{filename}` | Download a shared file |
| `GET` | `/api/notifications` | Get user notifications |

---

## 📂 Project Structure

```
Autostartup_Ai/
├── main.py                  # FastAPI server — all API routes
├── agent/
│   ├── workflow.py          # LangGraph 4-node matchmaking pipeline
│   ├── tools.py             # LangChain tools (Haversine, ChromaDB search, Moderation)
│   └── memory.py            # SQLite + ChromaDB initialization & helpers
├── frontend/
│   └── index.html           # Full SPA (Auth, Dashboard, Matchmaking, Chat)
├── data/
│   ├── hyperlocal.db        # SQLite database
│   ├── chroma_db/           # ChromaDB persistent vector store
│   └── uploads/             # Shared files (PDFs, images, docs)
├── .env                     # Environment variables (GROQ_API_KEY, SECRET_KEY)
└── requirements.txt         # Python dependencies
```

---

## 🚀 How to Run

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate it
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables (.env)
GROQ_API_KEY=your_groq_api_key
SECRET_KEY=your_secret_key

# 5. Run the server
python main.py

# 6. Open browser
http://localhost:8000
```
