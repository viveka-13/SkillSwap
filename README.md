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
| Communication | Basic text chat | Chat + Document/Image/PDF Sharing |
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
| **AI Framework** | LangGraph + LangChain | Multi-step AI agent workflow for matchmaking |
| **LLM** | Groq (Llama 3.1 8B Instant) | Compatibility scoring & AI reasoning |
| **Vector Database** | ChromaDB | Semantic skill search via embeddings |
| **Relational Database** | SQLite (WAL Mode) | Users, Skills, Matches, Messages, Credits |
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
The matchmaking engine is a **4-node LangGraph state machine**:

| Node | What It Does |
|---|---|
| **Fetch User Profile** | Loads the current user's location (lat/lon) from SQLite |
| **Semantic Matching** | Queries ChromaDB to find users whose *offered* skills semantically match what the current user *needs*. (e.g., "Python" matches "Backend Development") |
| **Compatibility Scoring** | For each candidate, the **Groq LLM (Llama 3.1)** generates a 0-100% compatibility score and a 1-sentence AI reasoning based on skills, distance, and trust |
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

### 6. 💬 Secure Communication Channel
- Once a match is **accepted**, a private **Chat Room** is created between both users.
- Real-time-like messaging with **3-second polling**.
- Messages are stored securely in the **Messages** database table.

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
   ├── LLM scores each candidate (0-100%)
   └── Returns Top 5 matches with AI reasoning

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
| `POST` | `/api/chat/{id}/send` | Send a text message |
| `POST` | `/api/chat/{id}/upload` | Upload a file (PDF, DOCX, Image) |
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
