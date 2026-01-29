# 🙏 Divya Vaani AI - Spiritual AI Assistant

**Voice-enabled spiritual guidance in Premanand Govind Sharan Maharaj's voice.**

Upload pravachans → Get transcripts → Ask questions → Listen to answers in Maharaj's voice.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **🎤 Voice Cloning** | TTS responses in Maharaj Premanand's authentic voice |
| **📝 Transcription** | Fast transcription via Groq Whisper API |
| **💬 Q&A** | Ask questions, get answers from the discourse |
| **🔍 Semantic Search** | FAISS + BGE embeddings for accurate retrieval |
| **🌐 Bilingual** | Hindi (primary) + English support |

---

## 🚀 Quick Start

### 1. Get Groq API Key (Free)
Go to: https://console.groq.com/keys

### 2. Setup Backend
```bash
cd backend

# Create virtual environment
py -3.11 -m venv venv
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# For GPU voice cloning (optional, recommended):
pip install torch --index-url https://download.pytorch.org/whl/cu118

# Create .env from example
copy ..\.env.example .env
# Edit .env and add: GROQ_API_KEY=your_key_here

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

## 🎤 Voice Cloning Setup

The system uses **Coqui XTTS v2** to clone Maharaj Premanand's voice.

### Voice Sample (Already Included)
Voice samples are in the `Input/` folder:
- `maharaj_audio.mp3` - Primary voice sample
- `maharaj-voice.mp3` - Backup sample

The system auto-detects these files. No manual setup required!

### GPU vs CPU
- **With GPU**: Full voice cloning with XTTS v2
- **Without GPU**: Fallback to Edge TTS (high quality Hindi, but not cloned)

---

## 🏗️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Frontend** | Vite + React |
| **Backend** | FastAPI (Python 3.11) |
| **Transcription** | Groq Whisper API |
| **LLM** | Groq LLaMA 3.3 70B |
| **Embeddings** | BGE-m3 / MiniLM |
| **Vector DB** | FAISS |
| **TTS** | Coqui XTTS v2 (voice clone) / Edge TTS (fallback) |

---

## 📁 Project Structure

```
├── backend/
│   ├── run.py           # FastAPI server
│   ├── config.py        # Configuration
│   ├── api/routes.py    # API endpoints
│   ├── core/
│   │   ├── transcriber.py   # Groq Whisper
│   │   ├── tts_engine.py    # Voice cloning
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
