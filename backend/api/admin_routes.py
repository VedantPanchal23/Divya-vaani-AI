import os
import logging
import secrets
from typing import Optional
from html import escape as html_escape

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_db
from db import crud

logger = logging.getLogger(__name__)

router = APIRouter()

def _verify_admin_key(x_admin_key: Optional[str] = Header(None)):
    """Dependency to verify admin API key for protected endpoints."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(403, "Admin access disabled: ADMIN_API_KEY not configured on server.")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(403, "Invalid or missing admin API key. Set X-Admin-Key header.")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    """Admin dashboard HTML."""
    
    db_videos = await crud.get_all_videos_db(db)
    videos = [crud.video_to_card(v) for v in db_videos]
    
    video_rows = ""
    for v in videos:
        vid_id = v['id'][:12]
        has_summary = "✅" if any(vid.summary_hi for vid in db_videos if vid.id == v['id']) else "❌"
        duration = f"{int(v['duration']/60)}m {int(v['duration']%60)}s"
        title = html_escape(v.get('title_hi', v.get('title', 'N/A'))[:50])
        
        video_rows += f"""
        <tr>
            <td><code>{html_escape(vid_id)}</code></td>
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
            
            #loginScreen {{
                position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                background: rgba(0,0,0,0.8); display: flex;
                align-items: center; justify-content: center; z-index: 9999;
            }}
            .login-box {{
                background: white; padding: 30px; border-radius: 12px; width: 400px;
                text-align: center;
            }}
            .login-box input {{
                width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 8px;
            }}
        </style>
    </head>
    <body style="display: none;" id="mainBody">
        
        <div id="loginScreen">
            <div class="login-box">
                <h2>🔐 Admin Login</h2>
                <input type="password" id="adminKeyInput" placeholder="Enter Admin API Key">
                <button onclick="checkAdminKey()" class="btn">Login</button>
            </div>
        </div>
        
        <h1>🙏 Divya Vaani Admin</h1>
        <p>Connected to main server API</p>
        
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
            <h2>📥 Fetch from YouTube</h2>
            <div style="display: flex; gap: 10px; margin-top: 10px;">
                <input type="text" id="youtubeUrl" placeholder="Paste YouTube link here..." style="flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #ccc; font-size: 16px;">
                <button onclick="fetchYouTube()" class="btn">Fetch Video</button>
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
            document.getElementById('mainBody').style.display = 'block';
            let adminKey = sessionStorage.getItem('adminKey');
            
            if (adminKey) {{
                document.getElementById('loginScreen').style.display = 'none';
            }}
            
            function checkAdminKey() {{
                const val = document.getElementById('adminKeyInput').value;
                if(val) {{
                    sessionStorage.setItem('adminKey', val);
                    adminKey = val;
                    document.getElementById('loginScreen').style.display = 'none';
                }}
            }}
            
            function authHeaders() {{
                return {{ 'X-Admin-Key': adminKey || '' }};
            }}
            
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
                    // Update endpoint to point to /api/upload
                    const response = await fetch('/api/upload', {{
                        method: 'POST',
                        body: formData,
                        headers: authHeaders()
                    }});
                    
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || 'Upload failed');
                    
                    const videoId = data.file_id;  // In main API, it's file_id, not video_id
                    statusText.textContent = 'Processing: Transcribing audio...';
                    
                    // Poll for status
                    const pollStatus = async () => {{
                        const statusResponse = await fetch(`/api/transcript/${{videoId}}`);
                        const status = await statusResponse.json();
                        
                        progressFill.style.width = status.progress + '%';
                        
                        if (status.step === 'transcribing') {{
                            statusText.textContent = `Transcribing... ${{status.message || ''}}`;
                        }} else if (status.step === 'summarizing') {{
                            statusText.textContent = 'Generating summary...';
                        }} else if (status.step === 'explaining') {{
                            statusText.textContent = 'Generating explanation...';
                        }} else if (status.step === 'generating_themes') {{
                            statusText.textContent = 'Extracting themes...';
                        }} else if (status.status === 'complete') {{
                            statusText.textContent = '✅ Complete! Video is ready.';
                            statusText.className = 'status complete';
                            setTimeout(() => location.reload(), 2000);
                            return;
                        }} else if (status.status === 'error') {{
                            statusText.textContent = '❌ Error: ' + status.message;
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
            
            async function fetchYouTube() {{
                const url = document.getElementById('youtubeUrl').value.trim();
                if (!url) return alert('Please enter a YouTube URL');
                
                const progressDiv = document.getElementById('uploadProgress');
                const progressFill = document.getElementById('progressFill');
                const statusText = document.getElementById('statusText');
                
                progressDiv.style.display = 'block';
                statusText.textContent = 'Starting YouTube download...';
                statusText.className = 'status';
                progressFill.style.width = '5%';
                
                try {{
                    const response = await fetch('/api/upload/youtube', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            ...authHeaders()
                        }},
                        body: JSON.stringify({{ url: url }})
                    }});
                    
                    const data = await response.json();
                    if (!response.ok) throw new Error(data.detail || 'Failed');
                    
                    const videoId = data.file_id;  // In main API, it's file_id, not video_id
                    
                    // Poll for status using the same logic
                    const pollStatus = async () => {{
                        const statusResponse = await fetch(`/api/transcript/${{videoId}}`);
                        const status = await statusResponse.json();
                        
                        if(status.progress) progressFill.style.width = status.progress + '%';
                        
                        if (status.step === 'transcribing') {{
                            statusText.textContent = `Transcribing... ${{status.message || ''}}`;
                        }} else if (status.step === 'summarizing') {{
                            statusText.textContent = 'Generating summary...';
                        }} else if (status.step === 'explaining') {{
                            statusText.textContent = 'Generating explanation...';
                        }} else if (status.step === 'generating_themes') {{
                            statusText.textContent = 'Extracting themes...';
                        }} else if (status.status === 'complete' || status.step === 'done') {{
                            statusText.textContent = '✅ Complete! Video is ready.';
                            statusText.className = 'status complete';
                            setTimeout(() => location.reload(), 2000);
                            return;
                        }} else if (status.status === 'error' || status.step === 'error') {{
                            statusText.textContent = '❌ Error: ' + status.message;
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
                
                try {{
                    const response = await fetch(`/api/videos/${{videoId}}/generate-summary`, {{ method: 'POST', headers: authHeaders() }});
                    const data = await response.json();
                    
                    if (response.ok) {{
                        alert('✅ ' + data.message + ' (This will take a few minutes in the background)');
                    }} else {{
                        throw new Error(data.detail);
                    }}
                }} catch (error) {{
                    alert('❌ Error: ' + error.message);
                }}
            }}
            
            async function deleteVideo(videoId) {{
                if (!confirm('Delete this video permanently?')) return;
                
                try {{
                    const response = await fetch(`/api/videos/${{videoId}}`, {{ method: 'DELETE', headers: authHeaders() }});
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
