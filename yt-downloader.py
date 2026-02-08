import yt_dlp

url = "https://www.youtube.com/watch?v=yed25ZsyClU"

ydl_opts = {
    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "outtmpl": "%(title)s.%(ext)s",

    # 🔧 network stability fixes
    "retries": 10,
    "fragment_retries": 10,
    "socket_timeout": 30,
    "http_chunk_size": 1048576,  # 1MB chunks
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([url])
