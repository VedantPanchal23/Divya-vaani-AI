# 🙏 Divya Vaani AI - Spiritual AI Assistant

**Voice-enabled spiritual guidance powered by AI.**

Upload pravachans → Get transcripts → Ask questions → Listen to answers.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **🔊 Text-to-Speech** | Edge TTS (primary) + gTTS fallback with LRU cache |
| **📝 Transcription** | Fast transcription via Groq Whisper API |
| **💬 Q&A** | RAG-powered answers from discourse transcripts |
| **🔍 Semantic Search** | FAISS + E5 multilingual embeddings for accurate retrieval |
| **📖 Bhagavad Gita** | Verse search integrated into Q&A context |
| **🌐 Bilingual** | Hindi (primary) + English support |
| **🎙️ Voice Input** | Browser speech recognition (Chrome/Edge) |

---

## 🚀 Quick Start

### 1. Get API Keys (Free)
- **Groq**: https://console.groq.com/keys (transcription + Q&A)
- **Gemini**: https://aistudio.google.com/apikey (summaries + explanations)

### 2. Setup Backend

**Windows:**
```bash
cd backend
py -3.11 -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

**Linux / macOS:**
```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Then create your `.env`:
```bash
# Windows
copy ..\.env.example .env

# Linux / macOS
cp ../.env.example .env
```

Edit `.env` and set:
```
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
ADMIN_API_KEY=your_admin_key_here
```

Start the server:
```bash
python run.py
```

### 3. Setup Frontend
```bash
cd frontend
npm install
npm run dev
```

### 4. Open
- Frontend: http://localhost:5173
- API Docs: http://localhost:8000/docs

### 5. Docker (optional)
```bash
docker build -t divya-vaani-ai .
docker run -p 8000:8000 --env-file backend/.env divya-vaani-ai
```

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Frontend** | Vite + React 18 |
| **Backend** | FastAPI (Python 3.11) |
| **Transcription** | Groq Whisper API |
| **LLM** | Groq LLaMA 3.3 70B + Gemini 2.0 Flash |
| **Embeddings** | intfloat/multilingual-e5-small (384d) |
| **Vector DB** | FAISS (thread-safe) |
| **TTS** | Edge TTS (primary) / gTTS (fallback) |
| **CI** | GitHub Actions (lint + test + build) |

---

## 📁 Project Structure

```
├── backend/
│   ├── run.py              # FastAPI server + middleware
│   ├── config.py           # Pydantic settings (SecretStr keys)
│   ├── api/
│   │   ├── __init__.py     # Combines sub-routers
│   │   ├── _helpers.py     # Shared utilities
│   │   ├── upload_routes.py
│   │   ├── video_routes.py
│   │   ├── chat_routes.py
│   │   └── tts_routes.py
│   ├── core/
│   │   ├── transcriber.py  # Groq Whisper
│   │   ├── tts_engine.py   # TTS (Edge + gTTS)
│   │   ├── rag_engine.py   # FAISS search (thread-safe)
│   │   └── llm_engine.py   # Groq / Gemini LLM
│   ├── data/               # Indexes, audio, transcripts
│   └── tests/              # pytest suite
│
├── frontend/
│   └── src/
│       ├── App.jsx          # Router + pagination
│       ├── api.js           # API client
│       └── components/      # React components
│
├── yt-downloader.py         # CLI YouTube downloader
├── Dockerfile               # Multi-stage Docker build
├── railway.toml             # Railway deployment config
└── .github/workflows/ci.yml # CI pipeline
```

---

## ⚠️ Disclaimer

This is an **AI-generated spiritual assistant**.  
All responses are AI-generated based on uploaded discourses only.

---

## 📄 License

Private - All Rights Reserved
