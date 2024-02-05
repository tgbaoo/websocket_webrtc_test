from fastapi import FastAPI, UploadFile, File, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, MediaStreamTrack, RTCConfiguration, RTCIceServer
import uvicorn
from aiortc.contrib.media import MediaPlayer
import cv2
import shutil
from pathlib import Path
import json

app = FastAPI()

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VIDEO_DIR = "temp_videos"
Path(VIDEO_DIR).mkdir(parents=True, exist_ok=True)

pcs = {}

@app.post("/uploadfile/{video_id}")
async def upload_file(video_id: str, file: UploadFile = File(...)):
    file_location = Path(VIDEO_DIR) / f"{video_id}_{file.filename}"
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"filename": file.filename}

@app.websocket("/ws/signaling/{video_id}")
async def websocket_signaling(websocket: WebSocket, video_id: str):
    await websocket.accept()
    pc = RTCPeerConnection()
    pcs[video_id] = pc
    data_channel = pc.createDataChannel("frames")

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        print(f"ICE Connection State has changed to {pc.iceConnectionState}")
        if pc.iceConnectionState == "failed":
            await pc.close()
            pcs.pop(video_id, None)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if 'type' in msg and msg['type'] == 'offer' and 'sdp' in msg:
                offer = RTCSessionDescription(sdp=msg['sdp'], type='offer')
                await pc.setRemoteDescription(offer)

                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                await websocket.send_json({'type': 'answer', 'sdp': pc.localDescription.sdp})

                # Start sending frames after the connection is established
                await send_frames(video_id, data_channel)
            else:
                print("Invalid message format received:", msg)
    except Exception as e:
        print(f"WebSocket connection closed with error: {e}")
    finally:
        await pc.close()
        pcs.pop(video_id, None)

async def send_frames(video_id, data_channel):
    video_path = Path(VIDEO_DIR) / f"{video_id}.mp4"
    cap = cv2.VideoCapture(str(video_path))
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        _, buffer = cv2.imencode('.jpg', frame)
        data_channel.send(buffer.tobytes())
        # await asyncio.sleep(1/30)  # Assuming 30 fps


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
