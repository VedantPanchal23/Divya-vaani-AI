# 🙏 Divya Vaani AI - Spiritual AI Assistant

**Voice-enabled spiritual guidance in Premanand Govind Sharan Maharaj's voice.**

Upload pravachans → Get transcripts → Ask questions → Listen to answers in Maharaj's voice.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **🔊 Text-to-Speech** | gTTS + Edge TTS (custom person-specific TTS model coming soon) |
| **📝 Transcription** | Fast transcription via Groq Whisper API |
| **💬 Q&A** | Ask questions, get answers from the discourse |
| **🔍 Semantic Search** | FAISS + E5 multilingual embeddings for accurate retrieval |
| **🌐 Bilingual** | Hindi (primary) + English support |

---

## 🚀 Quick Start

### 1. Get API Keys (Free)
- **Groq**: https://console.groq.com/keys (transcription + Q&A)
- **Gemini**: https://aistudio.google.com/apikey (summaries + explanations)

### 2. Setup Backend
```bash
cd backend

# Create virtual environment
py -3.11 -m venv venv
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env from example
copy ..\.env.example .env
# Edit .env and add:
# GROQ_API_KEY=your_key_here
# GEMINI_API_KEY=your_key_here

# Run server
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

---

## ️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Frontend** | Vite + React |
| **Backend** | FastAPI (Python 3.11) |
| **Transcription** | Groq Whisper API |
| **LLM** | Groq LLaMA 3.3 70B + Gemini 2.0 Flash |
| **Embeddings** | intfloat/multilingual-e5-small (384d) |
| **Vector DB** | FAISS |
| **TTS** | gTTS (primary) / Edge TTS (fallback) — custom TTS model planned |

---

## 📁 Project Structure

```
├── backend/
│   ├── run.py           # FastAPI server
│   ├── config.py        # Configuration
│   ├── api/routes.py    # API endpoints
│   ├── core/
│   │   ├── transcriber.py   # Groq Whisper
│   │   ├── tts_engine.py    # Text-to-Speech (gTTS + Edge TTS)
│   │   ├── rag_engine.py    # FAISS search
│   │   └── llm_engine.py    # Groq LLM
│   └── data/            # Indexes, audio files
│
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── api.js
│       └── components/  # React components
│
├── Input/               # Voice samples & test files
│   ├── maharaj_audio.mp3
│   └── test.mp4
│
└── .env.example         # Environment template
```

---

## ⚠️ Disclaimer

This is an **AI-generated spiritual assistant**.  
All responses are AI-generated based on uploaded discourses only.

---

## 📄 License

Private - All Rights Reserved
