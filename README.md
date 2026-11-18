# SkillSwap — AI-Powered Peer-to-Peer Skill Exchange Platform

<div align="center">

**Exchange skills, not money.** SkillSwap connects people who can teach each other — powered by AI semantic matching, real-time WebRTC communication, automated learning paths, a trust-based escrow economy, and native background push alerts.

**Python 3.10+** | **FastAPI** | **LangGraph AI Agent** | **WebRTC P2P (Audio, Video, Screen Share)** | **Web Push API / PWA** | **Groq Llama 3.1 & Whisper**

</div>

---

## 🎯 What is SkillSwap?

SkillSwap is a full-stack, hyperlocal web application that enables **zero-cost skill exchanges** between community members. Instead of paying for expensive courses or private tutors, users list what they can teach and what they want to learn — and the platform's **LangGraph AI agent** discovers, scores, and validates mutual, two-way exchanges.

**Think of it as Tinder for Skills** — but instead of swiping, an autonomous AI pipeline semantically analyzes your skills, validates mutual benefit, calculates hyperlocal geographic distance, and connects you directly with the right exchange partners nearby.

### Why SkillSwap Stands Out

| Aspect | Traditional Platforms | SkillSwap |
|---|---|---|
| **Matching** | Keyword search or static filters | AI Semantic Matching (ChromaDB Vector Search + LLM reasoning) |
| **Validation** | Unilateral requests (no verification) | Strict two-way mutual exchange validation (prevents one-sided tutoring) |
| **Location** | City or broad postal filtering | Hyperlocal GPS coordinates (Haversine formula in KM) |
| **Trust & Safety** | Star ratings only | Escrow Credit Economy + Multi-Factor Trust Score + Heuristic Fraud Detection |
| **Communication** | Basic text chat | Real-time Chat, Voice Notes with STT, WebRTC Video/Audio/Screen Share, AI Translation |
| **Collaboration** | External tools needed | Live In-Call Shared Notes + AI-Generated Learning Paths & Call Summaries |
| **Notifications** | Polling / Tab-dependent | Web Push API + Service Worker (background alerts even when tab is closed) |
| **Accessibility & Design** | Basic styles | Glassmorphism UI, WCAG AA compliant Light/Dark modes, Keyboard Navigation |
| **Cost** | Subscriptions, paywalls, platform fees | Completely free — pure community skill reciprocity |

---

## 🏗️ System Architecture

```
┌───────────────────────────────────────┐        ┌────────────────────────────────────────────────────────┐
│               Frontend                │        │                   Backend (FastAPI)                    │
│   (HTML5 / Modern CSS / Vanilla JS)   │◄──────►│                                                        │
│                                       │        │   ┌────────────────────────────────────────────────┐   │
│  • Single Page Application (SPA)      │        │   │        AI Agent Pipeline (LangGraph — 5 Nodes) │   │
│  • Accessible Light / Dark Mode       │        │   │                                                │   │
│  • Web Push Service Worker & PWA      │        │   │  1. Fetch User Profile & Preferences           │   │
│  • Real-Time Chat & File Uploads      │        │   │  2. ChromaDB Semantic Vector Search            │   │
│  • WebRTC Calling & Screen Share      │        │   │  3. Mutual Exchange Validation (Strict 2-Way)★ │   │
│  • Live Collaborative Shared Notes    │        │   │  4. LLM Compatibility Scoring & Reasoning      │   │
│  • Gamification & Local Leaderboard   │        │   │  5. Rank & Finalize Top 5 Recommendations      │   │
│  • Dedicated Admin Moderation Panel   │        │   └────────────────────────────────────────────────┘   │
└───────────────────────────────────────┘        │                           │                            │
                     ▲                           │   ┌───────────────────────▼────────────────────────┐   │
                     │                           │   │                  Data Layer                    │   │
                     │ WebSocket Signaling       │   │  • SQLite (WAL Mode) — 18 Relational Tables    │   │
                     │ & Push Subscriptions      │   │  • ChromaDB — Persistent Skill Embeddings      │   │
                     ▼                           │   └────────────────────────────────────────────────┘   │
┌───────────────────────────────────────┐        │                           │                            │
│           Web Push Service            │        │   ┌───────────────────────▼────────────────────────┐   │
│       (Browser Push Endpoints)        │◄───────┤   │             Push & Abuse Modules               │   │
│                                       │        │   │  • pywebpush (VAPID Encryption & Delivery)     │   │
│  • Chrome / Firefox / Safari Push     │        │   │  • agent.fraud (Ghosting & Cycling Detection)  │   │
│  • Multi-Device Endpoint Management   │        │   │  • agent.gamification (Streaks & Badges)       │   │
└───────────────────────────────────────┘        │   └────────────────────────────────────────────────┘   │
                                                 └────────────────────────────────────────────────────────┘
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
| **Backend Framework** | FastAPI (Python 3.10+) | High-performance asynchronous REST APIs & WebSockets |
| **AI Orchestration** | LangGraph + LangChain | 5-node stateful AI matchmaking pipeline and reasoning agent |
| **Large Language Model** | Groq (Llama 3.1 / GPT-OSS-120b) | Compatibility scoring, skill context enrichment, real-time translation, learning paths, and call summaries |
| **Speech-to-Text (STT)** | Groq (Whisper-large-v3) | Audio voice message and recorded call transcription |
| **Vector Database** | ChromaDB | Persistent vector store for semantic skill embedding search |
| **Relational Database** | SQLite (WAL Mode) | Users, skills, matches, messages, calls, escrow, notes, gamification, and push subscriptions |
| **Real-Time Communication**| WebSockets + WebRTC | P2P audio/video calling, screen sharing, and WebSocket signaling |
| **Push Notifications & PWA**| Web Push API (`pywebpush`), Service Worker, VAPID | Native desktop/mobile OS notifications and installable progressive web app |
| **Authentication & Security**| JWT + Bcrypt | Secure token-based sessions with salted password hashing |
| **Abuse Prevention** | Custom Heuristic Engine (`agent/fraud.py`) | Ghosting detection, credit cycling prevention, and severity-tiered admin controls |
| **Frontend Architecture** | Vanilla HTML5, CSS Custom Properties, Modern JS | Ultra-fast SPA with glassmorphism design, zero frontend build step, WCAG AA accessibility |

---

## ✨ Comprehensive Features

### 1. 🔐 Secure Authentication & AI Skill Profiling
- **Registration & Location**: Users register with email, password, city, and GPS coordinates (with browser geolocation support).
- **Security**: Passwords salted and hashed with **Bcrypt**; API protected by **JWT** (24-hour expiry).
- **AI-Guided Skill Profiling (`/api/skills/structure-suggestion`)**:
  - Automatically enriches raw skill names (e.g., "Python") into descriptive, context-rich summaries (e.g., *"Offers backend development with FastAPI, async programming, and REST APIs"*).
  - Categorizes skills and generates high-density embeddings stored in **ChromaDB** for accurate semantic retrieval.

### 2. 🧠 Autonomous AI Matchmaking Engine (5-Node LangGraph Pipeline)
The core matchmaking engine uses a stateful **LangGraph** workflow:
1. **Fetch User Profile**: Pulls current user coordinates and complete offered/needed skill profiles.
2. **Semantic Vector Search**: Queries ChromaDB using cosine distance to discover users whose offered skills match your needed skills.
3. **Mutual Exchange Validation (Strict 2-Way Validation) ★**:
   - Enforces true mutual reciprocity: User A must offer what User B needs **AND** User B must offer what User A needs.
   - One-sided tutoring or unbalanced pairs are automatically penalized and bypass expensive LLM calls.
4. **Compatibility Scoring & Reasoning**: Groq Llama 3.1 evaluates validated pairs to generate a **0–100% score** and an explainable 1-sentence reasoning highlighting reciprocal benefit.
5. **Finalize Top 5 Recommendations**: Sorts and presents top candidates with complementary skill badges highlighted.

### 3. 📍 Hyperlocal Proximity Engine
- Computes exact distance using the spherical **Haversine formula** ($d = 2r rcsin(\dots)$) between GPS points.
- Displays friendly proximity badges (e.g., `📍 2.3 km away`) to encourage local, in-person skill swaps.

### 4. 🪙 Escrow Credit Economy
- Every new user receives **10 starter credits**.
- When an exchange request is accepted, **5 credits** are deducted from the requester and locked safely in **Escrow**.
- Credits are released to the acceptor only after **both parties confirm completion** of the exchange.
- If an exchange is cancelled or the connection is removed, credits in escrow are **automatically refunded** to the requester.

### 5. ⭐ Multi-Factor Trust Score & Reviews
- Following completion, both participants submit ratings (1–5 stars) and detailed reviews.
- The user's public **Trust Score** is dynamically computed from historical ratings and completed exchange volume, directly influencing matchmaking prominence.

### 6. 💬 Real-Time Communication & Collaboration Suite

| Capability | Tech Stack | Highlights |
|---|---|---|
| **Instant Messaging** | REST + Auto-polling | Real-time text messaging with optimistic UI updates |
| **Audio/Video Calls** | WebRTC + WebSocket Signaling | WhatsApp-style call overlay with Accept / Decline / End controls |
| **Screen Sharing** | WebRTC `getDisplayMedia` | One-click screen sharing during video calls for live coding or design reviews |
| **Live Shared Notes** | WebSocket Sync + SQLite | Synchronized collaborative scratchpad for shared code, notes, and session minutes |
| **AI Call Summaries** | Groq Whisper + Llama 3.1 | Post-call audio transcription with auto-generated executive summary and action items |
| **Voice Messaging** | MediaRecorder API | In-browser voice notes with inline audio player and waveform |
| **AI Speech-to-Text** | Groq Whisper-large-v3 | Near-instant transcription automatically attached to voice notes |
| **AI Translation** | Groq Llama 3.1 | Instant on-the-fly message translation across languages |
| **Media & File Sharing**| Base64 Server Storage | Share PDFs, DOCX, PPTX, and images with inline chat previews |
| **YouTube Link Previews**| OEmbed Integration | Rich card previews with titles, thumbnails, and direct playback |
| **WhatsApp-Style Deletion**| Soft-delete flags | **"Delete for Me"** and **"Delete for Everyone"** (30-minute safety window) |
| **Clear Chat History** | Selective user hide | Clears entire chat feed for the requesting user without wiping the other party's history |
| **Call Logging** | SQLite Calls audit | Duration, timestamp, and missed/rejected call badges in chat timeline |

### 7. 🔔 Native Web Push Notifications & Progressive Web App (PWA)
- **True Background Alerts**: Powered by the **Web Push API** and standard **VAPID protocol** (`pywebpush`). Delivers native OS notifications (Windows Action Center, macOS Notification Center, Android notifications) even when the SkillSwap tab is closed or minimized.
- **Service Worker (`/service-worker.js`)**: Root-scoped background worker that listens for incoming push payloads and manages window focusing (`notificationclick` navigation).
- **Multi-Device Support**: Users can subscribe across multiple devices (phone, laptop, desktop); push notifications are dispatched concurrently to all active endpoints.
- **Stale Endpoint Auto-Pruning**: Automatically intercepts HTTP 404 and 410 responses from push services (FCM, Mozilla Autopush) and removes expired subscriptions.
- **Installable PWA (`/manifest.json`)**: Configured with full web app manifest for standalone home screen and desktop installation.

### 8. 🌓 Accessible Dark Mode & UI Themes
- **Accessible Contrast**: Fully compliant with **WCAG AA standards** (minimum 4.5:1 text-to-background contrast ratio) across both Light and Dark themes.
- **CSS Custom Properties**: Structured `--bg-primary`, `--card-bg`, `--text-primary`, `--border`, and `--accent` token system.
- **Persistent Preferences**: Stores user theme selection in `localStorage` and applies it instantly on page reload.
- **Keyboard Navigation**: High-visibility focus indicators and accessible ARIA attributes across all interactive components.

### 9. 🛡️ Heuristic Fraud Detection & Admin Moderation Panel
An autonomous abuse prevention engine (`agent/fraud.py`) running explainable heuristics that never block normal user workflows:
- **Ghosting Detection**: Identifies users who repeatedly accept skill exchange requests but abandon them or remain inactive for over 7 days.
- **Credit Cycling Detection**: Detects collusive pairs of accounts exchanging credits back and forth in closed loops to artificially manipulate streaks or trust scores.
- **Severity Tiers**: Dynamically assigns `watch` or `restricted` statuses to suspicious profiles.
- **Admin Dashboard (`/api/admin/fraud-flags`)**: Comprehensive review console for administrators to inspect flagged users, evaluate automated evidence, and resolve or dismiss flags.

### 10. 🗺️ AI-Powered Learning Path Generator
- **Milestone-Based Curricula**: Generates structured, week-by-week learning paths customized to both partners' specific skill levels and goals.
- **Mutual Syllabi**: Outlines reciprocal learning milestones so both members know exactly what will be taught in each session.
- **Persistent Records**: Stored in `LearningPaths` table and accessible at any time from the chat room.

### 11. 🏆 Gamification & Community Engagement
- **Weekly Streaks**: Tracks consecutive active weeks of completed skill exchanges (`UserStreaks`).
- **Earnable Badges**: Unlocks achievement badges for milestones (e.g., first exchange completed, 5-week streak, top reviewer).
- **Hyperlocal Leaderboard**: Community leaderboard showcasing top contributors in the user's city, fostering local peer learning.

### 12. 🔌 Safe Connection Lifecycle & Escrow Safety
- **Remove Connection**: Either party can safely terminate an exchange at any point via `/api/matches/{id}/remove-connection`.
- **Automatic Escrow Refund**: In-progress escrowed credits are instantly returned to the requester's wallet.
- **Read-Only Archival**: Transitions the chat room into a read-only historical archive, preventing further messaging or calls while preserving records.

---

## 🔄 Complete User Journey Flow

```
1. Profile Setup & Vectorization
   ├── Register with city, GPS coordinates, and skill lists
   └── AI enriches skill descriptions and generates ChromaDB vector embeddings

2. Autonomous AI Matchmaking
   ├── User searches for a skill (e.g., "Need Python, Offer Graphic Design")
   ├── ChromaDB finds semantic nearest neighbors
   ├── LangGraph strictly validates 2-way mutual reciprocity ★
   ├── Groq Llama 3.1 scores validated candidates (0–100%) with AI reasoning
   └── Top 5 matches displayed with complementary skill breakdown and GPS distance

3. Exchange Initiation & Escrow
   ├── Requester sends exchange request
   ├── Recipient receives real-time Web Push notification
   ├── On acceptance: 5 credits deducted from requester into Escrow
   └── Private collaboration room unlocked

4. Real-Time Collaboration & Learning
   ├── Instant messaging, file sharing, and Whisper-transcribed voice notes
   ├── WebRTC P2P Audio / Video calling with Screen Sharing
   ├── Live synchronized Shared Notes during calls
   ├── On-demand AI Learning Path generation for structured milestones
   └── Automatic AI Call Summary generated after session completion

5. Completion, Escrow Release & Gamification
   ├── Both users confirm completion
   ├── Escrowed credits released to provider
   ├── Streak counter increments & badges unlocked
   └── 1–5 star reviews submitted to update public Trust Score
```

---

## 🗃️ Database Schema

### SQLite Relational Tables (18 Tables)

| Table | Key Columns | Purpose |
|---|---|---|
| **Users** | `id`, `name`, `email`, `password_hash`, `city`, `lat`, `lon`, `trust_score`, `wallet_balance`, `fraud_flag`, `fraud_flag_reason` | User account profiles, wallet balances, and fraud status |
| **Skills** | `id`, `user_id`, `skill_name`, `type` (`offered`/`needed`), `description`, `category` | User skill listings for semantic vectorization |
| **Matches** | `id`, `user1_id`, `user2_id`, `compatibility_score`, `ai_reasoning`, `status` | Match records, AI compatibility scores, and active status |
| **Messages** | `id`, `match_id`, `sender_id`, `content`, `deleted_for_all`, `deleted_by_users`, `created_at` | Chat messages with WhatsApp-style soft-deletion support |
| **VoiceMessages** | `id`, `match_id`, `sender_id`, `filename`, `translated_text`, `created_at` | Audio notes with Groq Whisper STT and Llama translation |
| **YoutubeLinks** | `id`, `match_id`, `url`, `title`, `thumbnail`, `created_at` | Rich oEmbed previews for shared YouTube links |
| **Calls** | `id`, `match_id`, `caller_id`, `call_type`, `status`, `duration`, `recording_file`, `summary`, `summary_status` | WebRTC audio/video call logs and AI post-call summaries |
| **SharedNotes** | `id`, `match_id`, `content`, `last_edited_by`, `updated_at` | Live synchronized collaborative scratchpad for exchange pairs |
| **LearningPaths** | `id`, `match_id`, `user1_id`, `user2_id`, `path_data`, `created_at` | Structured AI-generated mutual learning syllabi |
| **ExchangeHistory** | `id`, `match_id`, `credits_transferred`, `completed_at` | Completed exchange audit trail |
| **Ratings** | `id`, `exchange_id`, `reviewer_id`, `reviewee_id`, `rating`, `review_text`, `created_at` | 1–5 star ratings and reviews calculating Trust Score |
| **Notifications** | `id`, `user_id`, `content`, `is_read`, `created_at` | In-app notification feed |
| **PushSubscriptions** | `id`, `user_id`, `endpoint`, `p256dh_key`, `auth_key`, `user_agent`, `created_at` | Web Push API subscription endpoints across all user devices |
| **FraudFlags** | `id`, `user_id`, `flag_type`, `detail`, `severity`, `created_at`, `resolved_at`, `resolved_by` | Heuristic fraud alerts (ghosting, cycling) for admin review |
| **UserStreaks** | `user_id`, `current_streak`, `best_streak`, `last_completed_week` | Weekly exchange streak tracking for gamification |
| **Badges** | `id`, `name`, `description`, `icon`, `criteria` | Catalog of unlockable achievement badges |
| **UserBadges** | `id`, `user_id`, `badge_id`, `earned_at` | User badge awards and achievements |
| **CommunityFeed** | `id`, `user_id`, `content`, `type`, `created_at` | Public community activity feed |

### ChromaDB Vector Collections

| Collection | Content | Purpose |
|---|---|---|
| **skills** | Skill descriptions embedded as dense vectors with `user_id` and `type` metadata | Semantic search matching offered skills to needed skills |
| **profiles** | High-level user profile vectors | Semantic user matching & future recommendation expansion |

---

## 🌐 Complete API Reference

### 🔐 Authentication & Skill Profiling
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Register new account, hash password, and embed skills into ChromaDB |
| `POST` | `/api/auth/login` | Authenticate credentials and return JWT bearer token |
| `POST` | `/api/skills/structure-suggestion` | AI-powered skill structuring, enrichment, and category suggestion |
| `GET` | `/api/dashboard` | Fetch logged-in user profile, wallet balance, trust score, and skills |

### 🧠 AI Matchmaking & Learning Paths
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/matches` | Execute 5-node LangGraph pipeline for mutual exchange matching |
| `GET` | `/api/matches/{id}/learning-path` | Retrieve existing AI learning path for match |
| `POST` | `/api/matches/{id}/learning-path` | Generate a customized milestone learning path using Groq LLM |
| `POST` | `/api/matches/{id}/remove-connection` | Remove connection, refund escrow credits, and set chat to read-only |

### 🪙 Exchanges & Escrow Economy
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/exchange/request` | Send exchange request to a matched user |
| `POST` | `/api/exchange/accept/{id}` | Accept exchange, deduct 5 credits into escrow, unlock chat |
| `POST` | `/api/exchange/{id}/confirm` | Confirm completion of exchange (releases escrowed credits to provider) |
| `POST` | `/api/exchange/{id}/cancel` | Cancel in-progress exchange and refund escrow credits to requester |
| `GET` | `/api/exchange/pending` | List all incoming pending exchange requests |
| `GET` | `/api/exchange/history` | List all completed skill exchanges |

### 💬 Real-Time Messaging & Collaboration
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/chat/rooms` | List all active chat rooms for current user |
| `GET` | `/api/chat/{id}/messages` | Fetch complete chat timeline (messages, voice, files, calls, YouTube) |
| `POST` | `/api/chat/{id}/send` | Send text message (auto-parses YouTube previews & triggers push alerts) |
| `POST` | `/api/chat/{id}/upload` | Upload file/document (PDF, DOCX, PPTX, Images) |
| `POST` | `/api/chat/{id}/voice` | Upload audio voice note for Whisper transcription & Llama translation |
| `POST` | `/api/chat/{id}/messages/{msg_id}/delete` | Delete message (`for_me` or `for_everyone`) |
| `POST` | `/api/chat/{id}/clear` | Clear chat history for the requesting user |
| `GET` | `/api/matches/{id}/notes` | Fetch shared collaborative scratchpad notes |
| `POST` | `/api/matches/{id}/notes` | Update shared collaborative scratchpad notes (syncs in real time) |
| `GET` | `/api/files/{filename}` | Download uploaded chat file |
| `GET` | `/api/audio/{filename}` | Stream voice note audio file |

### 📞 WebRTC Calling, Screen Sharing & Summaries
| Method | Endpoint | Description |
|---|---|---|
| `WS` | `/api/ws/calls/{user_id}` | WebSocket signaling endpoint for WebRTC offer/answer/ICE exchange |
| `GET` | `/api/webrtc/ice-config` | Fetch STUN/TURN ICE server configuration |
| `POST` | `/api/calls/log` | Audit call session (duration, status: completed, missed, rejected) |
| `POST` | `/api/calls/{id}/recording` | Upload call recording audio for transcription |
| `GET` | `/api/calls/{id}/summary` | Retrieve AI-generated executive call summary and action items |

### 🔔 Web Push Notifications & PWA
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/push/vapid-public-key` | Retrieve VAPID public key for browser PushManager subscription |
| `POST` | `/api/push/subscribe` | Register or update a browser push subscription endpoint |
| `POST` | `/api/push/unsubscribe` | De-register push subscription for current user |
| `GET` | `/service-worker.js` | Serve root-scoped Web Push Service Worker |
| `GET` | `/manifest.json` | Serve Progressive Web App (PWA) manifest |
| `GET` | `/api/notifications` | Fetch recent in-app notification records |

### 🏆 Gamification & Community
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/gamification/profile` | Fetch user streaks, completed count, and earned badges |
| `GET` | `/api/gamification/leaderboard` | Fetch hyperlocal city-level leaderboard rankings |

### 🛡️ Admin Moderation & Fraud Detection
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/admin/fraud-flags` | List all unresolved fraud and abuse alerts (ghosting, cycling) |
| `POST` | `/api/admin/fraud-flags/{id}/resolve` | Resolve a fraud alert and recalculate user status |

---

## 📂 Project Structure

```
skillswap/
├── main.py                     # FastAPI application — REST endpoints, WebSocket signaling, PWA routes
├── requirements.txt            # Python dependencies (FastAPI, LangGraph, pywebpush, ChromaDB, etc.)
├── .env                        # Local environment variables (API keys, VAPID credentials)
├── .env.example                # Example template for environment variables
├── agent/
│   ├── workflow.py             # 5-node LangGraph state machine for mutual skill matching
│   ├── tools.py                # LangChain tools (Haversine distance, ChromaDB query, moderation)
│   ├── memory.py               # SQLite schema, WAL mode, CRUD query helpers, ChromaDB client
│   ├── push.py                 # Web Push API dispatcher (pywebpush, VAPID, stale endpoint cleanup)
│   ├── fraud.py                # Heuristic abuse detection (ghosting & credit cycling detection)
│   ├── gamification.py         # Weekly streak tracking, badge calculation, leaderboard queries
│   ├── prompts.py              # LLM system prompts for compatibility scoring & translation
│   └── ppt_generator.py        # Presentation export helper
├── frontend/
│   ├── index.html              # Full single-page application (Auth, Dashboard, Match, Chat, Calls, A11y)
│   ├── service-worker.js       # Background push notification handler & notification click router
│   └── manifest.json           # Progressive Web App (PWA) manifest configuration
└── data/
    ├── hyperlocal.db           # SQLite database with 18 relational tables (auto-generated)
    ├── chroma_db/              # Persistent ChromaDB vector collections for skill embeddings
    └── uploads/                # File storage for shared PDFs, images, docs, and voice recordings
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+**
- **Git**
- A free **Groq Cloud API Key** (for Llama 3.1 and Whisper v3)

### 2. Clone Repository
```bash
git clone https://github.com/viveka-13/SkillSwap.git
cd SkillSwap
```

### 3. Create & Activate Virtual Environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Create a `.env` file in the project root:
```env
# Groq AI Key
GROQ_API_KEY=gsk_your_groq_api_key_here

# JWT Secret
SECRET_KEY=your_super_secret_jwt_key_here

# Web Push VAPID Keys (Generate with pywebpush or web-push generate-vapid-keys)
VAPID_PUBLIC_KEY=your_vapid_public_key_here
VAPID_PRIVATE_KEY=your_vapid_private_key_here
VAPID_CLAIMS_EMAIL=admin@skillswap.local
```

> [!TIP]
> You can generate fresh VAPID keys quickly in Python:
> ```bash
> python -c "from pywebpush import generate_vapid_keys; print(generate_vapid_keys())"
> ```

### 6. Run the Application
```bash
python main.py
```
The server will start at **`http://localhost:8000`**.

---

## 🧪 Testing the New Features

1. **AI Matchmaking & Reciprocity**:
   - Register **User A** (offers *Python*, needs *UI Design*).
   - Register **User B** (offers *UI Design*, needs *Python*).
   - Search for matches: LangGraph will validate mutual reciprocity and return a 90%+ compatibility score with highlighted complementary skills.
2. **Escrow Economy**:
   - Send an exchange request from User A to User B.
   - On acceptance, 5 credits are moved into Escrow.
   - Complete the exchange: both users click **Confirm Completion** to release credits.
3. **Web Push Notifications**:
   - On the Dashboard, click **Enable** under Push Notifications and grant browser permissions.
   - Minimize the tab or browser window.
   - From another browser window or incognito session, send a message or exchange request — a native OS desktop notification will pop up!
4. **WebRTC Calling & Screen Sharing**:
   - Open an active exchange chat room.
   - Click the 📞 (Audio) or 🎥 (Video) call button.
   - Click the **Screen Share** button during a call to share your desktop or code editor.
5. **Live Shared Notes**:
   - Inside the chat room, open the shared notes panel.
   - Type in one browser window — edits synchronize in real time for your exchange partner.
6. **Dark Mode & Accessibility**:
   - Click the **🌓 Dark Mode** button in the sidebar.
   - The theme switches immediately with high-contrast, WCAG AA compliant colors and persists upon page refresh.
7. **Admin Fraud Dashboard**:
   - Navigate to the **Admin Panel** to inspect any detected ghosting or credit cycling flags and resolve them with one click.

---

<div align="center">

**Built with ❤️ using FastAPI, LangGraph, Groq AI, ChromaDB, WebRTC, and Web Push**

</div>
