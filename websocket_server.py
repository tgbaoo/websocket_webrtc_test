from fastapi import FastAPI, WebSocket, UploadFile, File
import cv2
import base64
import asyncio
import uvicorn
import time
import shutil
import json  # Import the JSON module
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Dict

app = FastAPI()

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Allow only the specific client origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Directory for storing uploaded videos
VIDEO_DIR = "temp_videos"
Path(VIDEO_DIR).mkdir(parents=True, exist_ok=True)

# Dictionary to store paths of uploaded videos
uploaded_videos = {}

@app.post("/uploadfile/{video_id}")
async def create_upload_file(video_id: str, file: UploadFile = File(...)):
    file_location = Path(VIDEO_DIR) / f"{video_id}_{file.filename}"
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    uploaded_videos[video_id] = str(file_location)
    return {"filename": file.filename}

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, video_id: str):
        await websocket.accept()
        self.active_connections[video_id] = websocket

    def disconnect(self, video_id: str):
        del self.active_connections[video_id]

    async def send_video(self, video_id: str, data: bytes):
        websocket = self.active_connections.get(video_id)
        if websocket:
            await websocket.send_bytes(data)

manager = ConnectionManager()

async def stream_video(video_path, websocket: WebSocket):
    cap = cv2.VideoCapture(video_path)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        await websocket.send_bytes(buffer.tobytes())
        # You can adjust the sleep time to control the frame rate
        # await asyncio.sleep(0.033)  # Around 30 frames per second
    cap.release()

@app.websocket("/ws/video/{video_id}")
async def websocket_endpoint(websocket: WebSocket, video_id: str):
    await manager.connect(websocket, video_id)
    try:
        video_path = uploaded_videos.get(video_id)
        if not video_path:
            await websocket.close(code=1003, reason="Video file not uploaded")
            return
        await stream_video(video_path, websocket)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        manager.disconnect(video_id)

if __name__ == "__main__":
    config = uvicorn.Config(
        app,
        reload=True,
        host="127.0.0.1",
        port=8000,
        log_level="trace"
    )
    server = uvicorn.Server(config)
    server.run()