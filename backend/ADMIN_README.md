# Divya Vaani Admin Tools

Tools for uploading and managing pre-processed video content.

## Two Options

### Option 1: Web Admin Panel (Recommended)
Easy drag-and-drop interface for uploading videos.

```bash
cd backend
.\venv\Scripts\activate
python admin_web.py
```

Then open http://localhost:8001 in your browser.

Features:
- 📤 Drag & drop file upload
- 📊 Real-time processing progress
- 📚 View all uploaded videos
- 🔄 Regenerate summaries/explanations
- 🗑️ Delete videos

### Option 2: Command Line Tool
For batch processing or automation.

```bash
cd backend
.\venv\Scripts\activate

# Upload single video
python admin_upload.py path/to/video.mp4

# Upload with audio generation
python admin_upload.py path/to/video.mp4 --audio

# Process all files in a folder
python admin_upload.py --folder path/to/videos/

# List all videos
python admin_upload.py --list

# Regenerate summary for a video
python admin_upload.py --regenerate <video_id>

# Delete a video
python admin_upload.py --delete <video_id>
```

## Supported File Formats
- MP3, MP4, WAV, M4A, WebM, OGG, FLAC

## Processing Steps
When you upload a video, the system:
1. **Transcribes** the audio (using Whisper)
2. **Generates Hindi Summary** (using Gemini/Groq)
3. **Generates English Summary**
4. **Generates Hindi Explanation**
5. **Generates English Explanation**
6. **Indexes** content for RAG-based Q&A search

All content is stored in `backend/data/videos_content.json`.

## Notes
- Make sure the main backend server is NOT running when using admin tools
- Large files may take several minutes to process
- API keys (Groq, Gemini) must be configured in `.env`
