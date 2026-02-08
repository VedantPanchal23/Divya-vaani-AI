"""
Admin Web UI - Upload and manage video content
Run: python admin_web.py
Open: http://localhost:8001
"""
import os
import sys
import asyncio
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import settings
from data.videos_content import (
    VideoContent, add_video_content, get_all_videos, 
    get_video_detail, update_video_content, delete_video_content
)
from core import transcriber, llm_engine, rag_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Divya Vaani Admin", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Upload directory
UPLOAD_DIR = settings.DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Thumbnail directory
THUMBNAIL_DIR = settings.DATA_DIR / "thumbnails"
THUMBNAIL_DIR.mkdir(exist_ok=True)

# Processing status tracker
processing_status = {}


def generate_thumbnail(video_path: Path, video_id: str) -> bool:
    """Generate thumbnail from video using ffmpeg."""
    try:
        output_path = THUMBNAIL_DIR / f"{video_id}.jpg"
        
        # Extract frame at 5 seconds (or 1 second if video is short)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-ss", "00:00:05",  # Seek to 5 seconds
            "-vframes", "1",    # Extract 1 frame
            "-vf", "scale=480:-1",  # Scale to 480px width
            "-q:v", "3",        # Quality (1-31, lower is better)
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"✅ Generated thumbnail: {output_path}")
            return True
        
        # Try at 1 second if 5 seconds failed
        cmd[5] = "00:00:01"
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"✅ Generated thumbnail (1s): {output_path}")
            return True
            
        logger.warning(f"Failed to generate thumbnail: {result.stderr.decode()[:200]}")
        return False
        
    except Exception as e:
        logger.error(f"Thumbnail generation error: {e}")
        return False


async def process_video_task(file_path: Path, video_id: str, original_filename: str = None):
    """Background task to process uploaded video."""
    try:
        processing_status[video_id] = {"status": "transcribing", "progress": 0}
        
        # Get clean title from original filename (remove extension)
        if original_filename:
            clean_title = Path(original_filename).stem  # Remove extension
            # Clean up common patterns
            clean_title = clean_title.replace("_", " ").replace("-", " ")
        else:
            clean_title = file_path.stem
        
        # Step 1: Transcribe
        def progress_cb(current, total, msg):
            processing_status[video_id] = {
                "status": "transcribing", 
                "progress": int(current/total * 30),
                "message": msg
            }
        
        transcript = await transcriber.transcribe_audio(
            file_id=video_id,
            file_path=file_path,
            filename=file_path.name,
            progress_callback=progress_cb
        )
        
        # Step 2: Generate Summary
        processing_status[video_id] = {"status": "generating_summary", "progress": 40}
        summary_hi = await llm_engine.generate_summary(transcript.full_text, "hi")
        
        processing_status[video_id] = {"status": "generating_summary", "progress": 50}
        summary_en = await llm_engine.generate_summary(transcript.full_text, "en")
        
        # Step 3: Generate Explanation
        processing_status[video_id] = {"status": "generating_explanation", "progress": 60}
        explanation_hi = await llm_engine.generate_explanation(transcript.full_text, "hi")
        
        processing_status[video_id] = {"status": "generating_explanation", "progress": 75}
        explanation_en = await llm_engine.generate_explanation(transcript.full_text, "en")
        
        # Step 4: Generate Themes and Key Teachings
        processing_status[video_id] = {"status": "generating_themes", "progress": 80}
        themes_data = await llm_engine.generate_video_themes(transcript.full_text)
        
        # Step 5: Index for RAG
        processing_status[video_id] = {"status": "indexing", "progress": 90}
        try:
            rag_engine.index_transcript(transcript)
        except Exception as e:
            logger.warning(f"RAG indexing failed: {e}")
        
        # Generate thumbnail from video
        processing_status[video_id] = {"status": "generating_thumbnail", "progress": 85}
        generate_thumbnail(file_path, video_id)
        
        # Create video content - use original filename as title
        title_hi = clean_title  # Use original filename
        title_en = clean_title  # Use original filename
        
        video_content = VideoContent(
            id=transcript.id,
            title=title_en,
            title_hi=title_hi,
            description=f"Spiritual discourse. Duration: {int(transcript.duration/60)} minutes.",
            description_hi="महाराज जी का आध्यात्मिक प्रवचन",
            thumbnail=f"/api/thumbnail/{transcript.id}",
            video_url=f"/api/video/{transcript.id}",  # Serve uploaded video
            duration=transcript.duration,
            transcript=transcript.full_text,
            transcript_chunks=[{
                "id": c.id,
                "text": c.text,
                "start_time": c.start_time,
                "end_time": c.end_time
            } for c in transcript.chunks],
            summary_hi=summary_hi,
            summary_en=summary_en,
            explanation_hi=explanation_hi,
            explanation_en=explanation_en,
            main_topic=themes_data.get("main_topic", ""),
            main_topic_en=themes_data.get("main_topic_en", ""),
            themes=themes_data.get("themes", []),
            themes_en=themes_data.get("themes_en", []),
            key_teachings=themes_data.get("key_teachings", []),
            created_at=datetime.now().isoformat(),
            category="pravachan",
            speaker="Maharaj Ji",
            tags=["spiritual", "pravachan", "hindi"]
        )
        
        add_video_content(video_content)
        
        processing_status[video_id] = {
            "status": "complete", 
            "progress": 100,
            "video_id": video_id
        }
        
    except Exception as e:
        logger.exception(f"Processing failed: {e}")
        processing_status[video_id] = {
            "status": "error", 
            "progress": 0,
            "error": str(e)
        }


@app.get("/", response_class=HTMLResponse)
async def admin_home():
    """Admin dashboard HTML."""
    videos = get_all_videos()
    
    video_rows = ""
    for v in videos:
        vid_id = v['id'][:12]
        detail = get_video_detail(v['id'], 'hi')
        has_summary = "✅" if detail and detail.get('summary_hi') else "❌"
        duration = f"{int(v['duration']/60)}m {int(v['duration']%60)}s"
        title = v.get('title_hi', v.get('title', 'N/A'))[:50]
        
        video_rows += f"""
        <tr>
            <td><code>{vid_id}</code></td>
            <td>{title}</td>
            <td>{duration}</td>
            <td>{has_summary}</td>
            <td>
                <button onclick="regenerate('{v['id']}')" class="btn btn-sm">🔄 Regenerate</button>
                <button onclick="deleteVideo('{v['id']}')" class="btn btn-sm btn-danger">🗑️ Delete</button>
            </td>
        </tr>
        """
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Divya Vaani Admin</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 1200px; margin: 0 auto; padding: 20px;
                background: #f5f5f5;
            }}
            h1 {{ color: #c97b3e; }}
            .card {{ 
                background: white; border-radius: 12px; padding: 24px; 
                margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            .upload-zone {{
                border: 2px dashed #ccc; border-radius: 12px; padding: 40px;
                text-align: center; cursor: pointer; transition: all 0.3s;
            }}
            .upload-zone:hover {{ border-color: #c97b3e; background: #fff9f5; }}
            .upload-zone.dragging {{ border-color: #c97b3e; background: #fff9f5; }}
            input[type="file"] {{ display: none; }}
            .btn {{
                background: #c97b3e; color: white; border: none; padding: 10px 20px;
                border-radius: 8px; cursor: pointer; font-size: 14px;
            }}
            .btn:hover {{ background: #b06a30; }}
            .btn-danger {{ background: #dc3545; }}
            .btn-danger:hover {{ background: #c82333; }}
            .btn-sm {{ padding: 5px 10px; font-size: 12px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
            th {{ background: #f8f9fa; font-weight: 600; }}
            .progress-bar {{
                width: 100%; height: 24px; background: #eee; border-radius: 12px;
                overflow: hidden; margin-top: 10px;
            }}
            .progress-fill {{
                height: 100%; background: linear-gradient(90deg, #c97b3e, #e8a96a);
                transition: width 0.3s;
            }}
            .status {{ 
                margin-top: 10px; padding: 10px; border-radius: 8px;
                background: #f8f9fa;
            }}
            .status.error {{ background: #ffe6e6; color: #dc3545; }}
            .status.complete {{ background: #e6ffe6; color: #28a745; }}
            code {{ 
                background: #f1f1f1; padding: 2px 6px; border-radius: 4px;
                font-family: monospace;
            }}
        </style>
    </head>
    <body>
        <h1>🙏 Divya Vaani Admin</h1>
        
        <div class="card">
            <h2>📤 Upload New Video</h2>
            <div class="upload-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
                <p style="font-size: 48px; margin: 0;">📁</p>
                <p><strong>Click or drag video/audio file here</strong></p>
                <p style="color: #666; font-size: 14px;">Supports: MP3, MP4, WAV, M4A, WebM, OGG, FLAC</p>
            </div>
            <input type="file" id="fileInput" accept=".mp3,.mp4,.wav,.m4a,.webm,.ogg,.flac" onchange="uploadFile(this.files[0])">
            
            <div id="uploadProgress" style="display: none;">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill" style="width: 0%"></div>
                </div>
                <div class="status" id="statusText">Uploading...</div>
            </div>
        </div>
        
        <div class="card">
            <h2>📚 Video Library ({len(videos)} videos)</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Title</th>
                        <th>Duration</th>
                        <th>Summary</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {video_rows if video_rows else '<tr><td colspan="5" style="text-align:center; color:#666;">No videos yet. Upload one above!</td></tr>'}
                </tbody>
            </table>
        </div>
        
        <script>
            const dropZone = document.getElementById('dropZone');
            
            dropZone.addEventListener('dragover', (e) => {{
                e.preventDefault();
                dropZone.classList.add('dragging');
            }});
            
            dropZone.addEventListener('dragleave', () => {{
                dropZone.classList.remove('dragging');
            }});
            
            dropZone.addEventListener('drop', (e) => {{
                e.preventDefault();
                dropZone.classList.remove('dragging');
                const file = e.dataTransfer.files[0];
                if (file) uploadFile(file);
            }});
            
            async function uploadFile(file) {{
                const progressDiv = document.getElementById('uploadProgress');
                const progressFill = document.getElementById('progressFill');
                const statusText = document.getElementById('statusText');
                
                progressDiv.style.display = 'block';
                statusText.textContent = 'Uploading file...';
                statusText.className = 'status';
                progressFill.style.width = '5%';
                
                const formData = new FormData();
                formData.append('file', file);
                
                try {{
                    const response = await fetch('/upload', {{
                        method: 'POST',
                        body: formData
                    }});
                    
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || 'Upload failed');
                    
                    const videoId = data.video_id;
                    statusText.textContent = 'Processing: Transcribing audio...';
                    
                    // Poll for status
                    const pollStatus = async () => {{
                        const statusResponse = await fetch(`/status/${{videoId}}`);
                        const status = await statusResponse.json();
                        
                        progressFill.style.width = status.progress + '%';
                        
                        if (status.status === 'transcribing') {{
                            statusText.textContent = `Transcribing... ${{status.message || ''}}`;
                        }} else if (status.status === 'generating_summary') {{
                            statusText.textContent = 'Generating summary...';
                        }} else if (status.status === 'generating_explanation') {{
                            statusText.textContent = 'Generating explanation...';
                        }} else if (status.status === 'indexing') {{
                            statusText.textContent = 'Indexing for search...';
                        }} else if (status.status === 'complete') {{
                            statusText.textContent = '✅ Complete! Video is ready.';
                            statusText.className = 'status complete';
                            setTimeout(() => location.reload(), 2000);
                            return;
                        }} else if (status.status === 'error') {{
                            statusText.textContent = '❌ Error: ' + status.error;
                            statusText.className = 'status error';
                            return;
                        }}
                        
                        setTimeout(pollStatus, 2000);
                    }};
                    
                    pollStatus();
                    
                }} catch (error) {{
                    statusText.textContent = '❌ Error: ' + error.message;
                    statusText.className = 'status error';
                }}
            }}
            
            async function regenerate(videoId) {{
                if (!confirm('Regenerate summary and explanation for this video?')) return;
                
                const statusText = document.getElementById('statusText');
                const progressDiv = document.getElementById('uploadProgress');
                progressDiv.style.display = 'block';
                statusText.textContent = 'Regenerating content...';
                statusText.className = 'status';
                
                try {{
                    const response = await fetch(`/regenerate/${{videoId}}`, {{ method: 'POST' }});
                    const data = await response.json();
                    
                    if (response.ok) {{
                        statusText.textContent = '✅ ' + data.message;
                        statusText.className = 'status complete';
                        setTimeout(() => location.reload(), 2000);
                    }} else {{
                        throw new Error(data.detail);
                    }}
                }} catch (error) {{
                    statusText.textContent = '❌ Error: ' + error.message;
                    statusText.className = 'status error';
                }}
            }}
            
            async function deleteVideo(videoId) {{
                if (!confirm('Delete this video permanently?')) return;
                
                try {{
                    const response = await fetch(`/delete/${{videoId}}`, {{ method: 'DELETE' }});
                    if (response.ok) {{
                        location.reload();
                    }} else {{
                        const data = await response.json();
                        alert('Error: ' + data.detail);
                    }}
                }} catch (error) {{
                    alert('Error: ' + error.message);
                }}
            }}
        </script>
    </body>
    </html>
    """


@app.post("/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload and process a video file."""
    
    # Validate file type
    valid_extensions = {'.mp3', '.mp4', '.wav', '.m4a', '.webm', '.ogg', '.flac'}
    ext = Path(file.filename).suffix.lower()
    
    if ext not in valid_extensions:
        raise HTTPException(400, f"Invalid file type. Allowed: {', '.join(valid_extensions)}")
    
    # Generate video ID
    import uuid
    video_id = str(uuid.uuid4())[:12]
    
    # Save file
    file_path = UPLOAD_DIR / f"{video_id}{ext}"
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    logger.info(f"📥 Uploaded: {file.filename} -> {file_path}")
    
    # Start background processing - pass original filename for title
    background_tasks.add_task(process_video_task, file_path, video_id, file.filename)
    
    return {"video_id": video_id, "message": "Processing started"}


@app.get("/status/{video_id}")
async def get_processing_status(video_id: str):
    """Get processing status for a video."""
    status = processing_status.get(video_id, {"status": "unknown", "progress": 0})
    return status


@app.post("/regenerate/{video_id}")
async def regenerate_video(video_id: str):
    """Regenerate summary and explanation for existing video."""
    
    video = get_video_detail(video_id, "hi")
    if not video:
        raise HTTPException(404, "Video not found")
    
    transcript = video.get("transcript", "")
    if not transcript:
        raise HTTPException(400, "No transcript available")
    
    # Generate new content
    summary_hi = await llm_engine.generate_summary(transcript, "hi")
    summary_en = await llm_engine.generate_summary(transcript, "en")
    explanation_hi = await llm_engine.generate_explanation(transcript, "hi")
    explanation_en = await llm_engine.generate_explanation(transcript, "en")
    
    # Update
    update_video_content(video_id, {
        "summary_hi": summary_hi,
        "summary_en": summary_en,
        "explanation_hi": explanation_hi,
        "explanation_en": explanation_en,
    })
    
    return {"message": "Content regenerated successfully"}


@app.delete("/delete/{video_id}")
async def delete_video(video_id: str):
    """Delete a video from the content store."""
    
    if not delete_video_content(video_id):
        raise HTTPException(404, "Video not found")
    
    return {"message": "Video deleted"}


@app.get("/api/videos")
async def list_videos():
    """API: List all videos."""
    return get_all_videos()


if __name__ == "__main__":
    print("\n" + "="*50)
    print("🙏 Divya Vaani Admin Panel")
    print("="*50)
    print(f"📂 Upload directory: {UPLOAD_DIR}")
    print(f"🌐 Open: http://localhost:8001")
    print("="*50 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8001)
