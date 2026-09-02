# SkillSwap — AI-Powered Peer-to-Peer Skill Exchange Platform

<div align="center">

**Exchange skills, not money.** SkillSwap connects people who can teach each other — powered by AI semantic matching, real-time WebRTC communication, and a trust-based credit economy.

**Python 3.10+** | **FastAPI** | **LangGraph AI Agent** | **WebRTC P2P Calling** | **Groq Llama 3.1 & Whisper**

</div>

---

## 🎯 What is SkillSwap?

SkillSwap is a full-stack web application that enables **zero-cost skill exchanges** between community members. Instead of paying for courses or tutors, users list what they can teach and what they want to learn — and the platform's **AI agent** finds the perfect two-way matches.

**Think of it as Tinder for Skills** — but instead of swiping, an AI does the heavy lifting by semantically understanding your skills, validating mutual benefit, and connecting you with the right people nearby.

### Why SkillSwap Stands Out

| Aspect | Traditional Platforms | SkillSwap |
|---|---|---|
| **Matching** | Keyword-based search | AI Semantic Matching (ChromaDB + LLM) |
| **Validation** | No exchange verification | Strict two-way mutual exchange validation |
| **Location** | City-level filtering | Hyperlocal GPS (Haversine distance in KM) |
| **Trust** | Star ratings only | AI-computed Trust Score + Credit Wallet |
| **Communication** | Basic text chat | Real-time Chat, Voice Notes, WebRTC Audio/Video Calls, AI Translation |
| **Cost** | Paid services or subscriptions | Completely free — purely skill-based exchange |

---

## 🏗️ System Architecture

```
┌──────────────────┐        ┌──────────────────────────────────────────────┐
│     Frontend     │        │              Backend (FastAPI)               │
│   (HTML/CSS/JS)  │◄──────►│                                              │
│                  │        │   ┌──────────────────────────────────────┐   │
│  • Auth Pages    │        │   │     AI Agent (LangGraph — 5 Nodes)   │   │
│  • Dashboard     │        │   │                                      │   │
│  • AI Matching   │        │   │  1. Fetch User Profile               │   │
│  • Chat + Calls  │        │   │  2. ChromaDB Semantic Matching       │   │
│  • File Sharing  │        │   │  3. Mutual Exchange Validation ★     │   │
│                  │        │   │  4. LLM Compatibility Scoring        │   │
│                  │        │   │  5. Finalize Top 5 Recommendations   │   │
│                  │        │   └──────────────────────────────────────┘   │
└──────────────────┘        │                    │                          │
                            │   ┌────────────────▼─────────────────────┐   │
        WebSocket ◄─────────│   │           Data Layer                 │   │
        Signaling           │   │  • SQLite (WAL) — Relational Data    │   │
                            │   │  • ChromaDB — Vector Embeddings      │   │
                            │   └──────────────────────────────────────┘   │
                            └──────────────────────────────────────────────┘
                                              │
                                    ┌─────────▼─────────┐
                                    │    Groq Cloud AI   │
                                    │  • Llama 3.1 8B    │
                                    │  • Whisper v3 STT  │
                                    └───────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | FastAPI (Python) | REST APIs, JWT Authentication, Business Logic |
| **AI Agent** | LangGraph + LangChain | 5-node stateful AI pipeline for intelligent matchmaking |
| **LLM** | Groq (GPT-OSS-120b / Llama 3) | Compatibility scoring, AI reasoning, and real-time translation |
| **Speech-to-Text** | Groq (Whisper-large-v3) | Voice message transcription with high accuracy |
| **Vector Database** | ChromaDB | Semantic skill search using sentence embeddings |
| **Relational Database** | SQLite (WAL Mode) | Users, Skills, Matches, Messages, Calls, Credits |
| **Real-Time Comm** | WebSockets + WebRTC | P2P Audio/Video calling with signaling server |
| **Authentication** | JWT + Bcrypt | Secure token-based sessions with hashed passwords |
| **Frontend** | HTML, CSS, JavaScript (SPA) | Premium glassmorphism UI with micro-animations |
| **File Storage** | Server-side (Base64 upload) | PDF, DOCX, PPTX, and Image sharing in chat |

---

## ✨ Key Features

### 1. 🔐 Secure Authentication System
- User registration with name, email, city, GPS coordinates, skills offered, and skills needed.
- Passwords securely hashed using **Bcrypt**.
- JWT token-based sessions with 24-hour expiry.
- On registration, all user skills are **embedded into ChromaDB** as vectors for AI-powered semantic search.

### 1.5. ✨ AI-Guided Skill Profiling
- Simple keyword inputs (e.g., "Python") are intercepted and enriched by the **Groq LLM**.
- AI automatically generates a 1-2 sentence descriptive context (e.g., "I can teach backend Python, FastAPI, and REST API design") and categorizes the skill.
- This dramatically improves the density of the ChromaDB embeddings, leading to significantly higher quality semantic matches.

### 2. 🧠 AI-Powered Matchmaking Engine (5-Node LangGraph Pipeline)

This is the core intelligence of the platform — a **5-node LangGraph state machine** that goes far beyond simple keyword matching:

| Node | What It Does |
|---|---|
| **Fetch User Profile** | Loads the current user's GPS coordinates and complete skill profile from SQLite |
| **Semantic Matching** | Queries ChromaDB to find users whose *offered* skills semantically match what the current user *needs* (e.g., "Python" matches "Backend Development") |
| **Mutual Exchange Validation** ★ | **Strictly validates a true two-way skill exchange** — the matched user must offer what you need AND need what you offer. One-sided matches are automatically penalized and bypass LLM scoring entirely. |
| **Compatibility Scoring** | For validated mutual matches, the **Groq LLM (Llama 3.1)** generates a 0–100% compatibility score and a 1-sentence AI reasoning emphasizing the mutual benefit |
| **Finalize Recommendations** | Sorts all candidates by score and returns the **Top 5** best matches |

**Result:** Every match card shows two columns — *"They can teach you"* and *"Your skills useful for them"* — so users instantly see the value of the exchange.

### 3. 📍 Hyperlocal Distance Calculation
- Uses the **Haversine formula** to calculate real-world distance (in KM) between two GPS coordinates.
- Each match card displays proximity: `📍 2.3 km away`.
- Encourages local, in-person knowledge exchange.

### 4. 🪙 Credit-Based Trust Economy
- Every new user starts with **10 credits**.
- When an exchange is accepted, **5 credits** transfer from requester to acceptor.
- Prevents abuse and ensures both parties are committed to the exchange.

### 5. ⭐ Trust Score & Ratings
- After completing an exchange, both users rate each other (1–5 stars).
- **Trust score** = average of all ratings received.
- Higher trust = better visibility in future matchmaking results.

### 6. 💬 Real-Time Communication Suite (WebSockets & WebRTC)

A full-featured communication system built directly into the platform:

| Feature | Technology | Description |
|---|---|---|
| **Text Chat** | Polling-based messaging | Instant messaging with 3-second auto-refresh |
| **Audio/Video Calling** | WebRTC + WebSocket Signaling | WhatsApp-style P2P calls with Accept/Reject/End controls |
| **Voice Messaging** | MediaRecorder API | Record and send voice notes directly in the browser |
| **AI Transcription** | Groq Whisper (large-v3) | Automatic speech-to-text for every voice message |
| **AI Translation** | Groq Llama 3.1 | On-the-fly translation if sender and receiver speak different languages |
| **YouTube Previews** | OEmbed API | Automatic rich link cards with thumbnails for shared YouTube URLs |
| **Call History** | SQLite Logging | Persistent call logs (duration, missed/rejected) merged into chat feed |

### 7. 📎 File & Document Sharing
- Share **PDFs, DOCX, PPTX, Images (JPG/PNG)** and more via the `+` button in chat.
- Files uploaded as **Base64**, stored server-side, and displayed with file-type icons.
- Image files render an **inline preview** directly inside the chat bubble.

### 8. 🔔 Smart Notification System
- Receive notifications when someone sends you a match request.
- Get notified with credit transfer details when someone accepts your exchange.

---

## 🔄 How It Works — Complete User Flow

```
Step 1: Registration
   ├── User signs up with name, email, city, GPS, skills offered & needed
   └── Skills are vectorized and stored in ChromaDB for semantic search

Step 2: AI Matchmaking
   ├── User searches: "I need Python, I offer UI Design"
   ├── ChromaDB finds semantically similar skill providers
   ├── LangGraph validates STRICT two-way mutual exchange ★
   ├── LLM scores validated candidates (0-100%) with AI reasoning
   └── Top 5 results shown with "They teach you" & "You help them" breakdown

Step 3: Exchange Request
   ├── User sends a request to a matched partner
   └── Partner receives an in-app notification

Step 4: Exchange Accepted
   ├── Match status → "accepted"
   ├── 5 credits transfer from requester → acceptor
   └── Private chat room is unlocked

Step 5: Communicate & Learn
   ├── Text chat, voice messages, file sharing
   ├── Audio/Video calls via WebRTC
   └── AI auto-translates voice messages across languages

Step 6: Rate & Build Trust
   └── Both users rate the exchange → Trust score updates
```

---

## 🗃️ Database Schema

### SQLite Tables

| Table | Key Columns | Purpose |
|---|---|---|
| **Users** | id, name, email, password_hash, city, lat, lon, trust_score, wallet_balance | User profiles & credentials |
| **Skills** | id, user_id, skill_name, type (offered/needed) | Skill listings for matching |
| **Matches** | id, user1_id, user2_id, compatibility_score, ai_reasoning, status | Match tracking & AI scores |
| **Messages** | id, match_id, sender_id, content, is_flagged | Chat messages & file metadata |
| **VoiceMessages** | id, match_id, sender_id, filename, translated_text | Voice notes with AI transcription |
| **YoutubeLinks** | id, match_id, url, title, thumbnail | Rich YouTube link previews |
| **Calls** | id, match_id, caller_id, call_type, status, duration | WebRTC audio/video call history |
| **ExchangeHistory** | id, match_id, credits_transferred, completed_at | Completed exchange records |
| **Ratings** | id, exchange_id, reviewer_id, reviewee_id, rating, review_text | Trust score ratings |
| **Notifications** | id, user_id, content, is_read | User notification feed |

### ChromaDB Vector Collections

| Collection | Content | Purpose |
|---|---|---|
| **skills** | Skill names as document vectors with user_id metadata | Semantic skill matching via embeddings |
| **profiles** | User profile embeddings | Reserved for future expansion |

---

## 🌐 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register user + embed skills into ChromaDB |
| `POST` | `/api/auth/login` | Authenticate and receive JWT token |
| `GET` | `/api/dashboard` | Fetch user profile, trust score, wallet, skills |
| `POST` | `/api/matches` | Trigger full AI matchmaking pipeline (LangGraph) |
| `POST` | `/api/exchange/request` | Send a skill exchange request |
| `POST` | `/api/exchange/accept/{id}` | Accept request + auto-transfer credits |
| `GET` | `/api/exchange/pending` | List pending incoming requests |
| `GET` | `/api/exchange/history` | View completed exchange history |
| `GET` | `/api/chat/rooms` | List all active chat rooms |
| `GET` | `/api/chat/{id}/messages` | Get full chat message history (text + voice + calls) |
| `POST` | `/api/chat/{id}/send` | Send a text message (auto-detects YouTube links) |
| `POST` | `/api/chat/{id}/upload` | Upload a file (PDF, DOCX, Image) |
| `POST` | `/api/chat/{id}/voice` | Send a voice note (triggers Whisper STT + Llama Translation) |
| `WS` | `/api/ws/calls/{user_id}` | WebSocket for WebRTC call signaling |
| `POST` | `/api/calls/log` | Log call history (duration, status) to database |
| `GET` | `/api/files/{filename}` | Download a shared file |
| `GET` | `/api/notifications` | Fetch user notifications |

---

## 📂 Project Structure

```
skillswap/
├── main.py                  # FastAPI server — all API routes + WebSocket signaling
├── agent/
│   ├── workflow.py          # LangGraph 5-node AI matchmaking pipeline
│   ├── tools.py             # LangChain tools (Haversine, ChromaDB search, Moderation)
│   └── memory.py            # SQLite + ChromaDB initialization & query helpers
├── frontend/
│   └── index.html           # Full SPA (Auth, Dashboard, Matchmaking, Chat, Calls)
├── data/
│   ├── hyperlocal.db        # SQLite database (auto-created)
│   ├── chroma_db/           # ChromaDB persistent vector store
│   └── uploads/             # Shared files (PDFs, images, audio, docs)
├── .env                     # Environment variables (GROQ_API_KEY, SECRET_KEY)
└── requirements.txt         # Python dependencies
```

---

## 🚀 Getting Started

```bash
# 1. Clone the repository
git clone https://github.com/viveka-13/SkillSwap.git
cd SkillSwap

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
# Create a .env file with:
GROQ_API_KEY=your_groq_api_key
SECRET_KEY=your_secret_key

# 5. Start the server
python main.py

# 6. Open in browser
# Visit http://localhost:8000
```

---

## 🧪 Testing the Platform

1. **Register two users** with complementary skills (e.g., User A offers "Python" and needs "UI Design"; User B offers "UI Design" and needs "Python").
2. **Search for matches** from either account — the AI will validate the mutual exchange and score it 90–100%.
3. **Accept the exchange** and watch the credit transfer happen automatically.
4. **Open the chat room** — try sending text messages, voice notes, files, and YouTube links.
5. **Make a call** — click the 📞 or 🎥 button to test WebRTC audio/video calling.
6. **Rate the exchange** — both users can rate each other to build their trust score.

---

<div align="center">

**Built with ❤️ using FastAPI, LangGraph, Groq AI, ChromaDB, and WebRTC**

</div>
