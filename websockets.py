# Logic & Legacy: Day 23 - The WebSocket Switchboard
# This is a production-ready Connection Manager. 
# We don't just 'receive' messages; we manage the lifecycle of the stateful pipe.

import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict

# Setup logging for the war room
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("SocketManager")

class ConnectionManager:
    """
    The Switchboard Operator. 
    In 2026, managing stateful pipes is the difference between a 
    senior architect and a tutorial-copying junior.
    """
    def __init__(self):
        # The Map of State: UserID -> Physical WebSocket Object
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        """Accept the handshake and register the 'Dedicated Line'."""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"[CONNECT] User {user_id} established a persistent pipe.")

    def disconnect(self, user_id: str):
        """Sever the line and free up RAM."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"[DISCONNECT] User {user_id} removed from registry.")

    async def send_private_message(self, message: str, user_id: str):
        """Find the specific pipe in RAM and shove data down it."""
        websocket = self.active_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_text(message)
            except Exception:
                # If the pipe is broken, prune it now.
                self.disconnect(user_id)

    async def broadcast(self, message: str):
        """Yell to everyone currently in the switchboard."""
        # We use list() to avoid dictionary size change errors during iteration
        for user_id in list(self.active_connections.keys()):
            await self.send_private_message(message, user_id)

manager = ConnectionManager()
app = FastAPI()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    # 1. Register the line
    await manager.connect(user_id, websocket)
    
    # 2. Start the Heartbeat (The Silent Killer prevention)
    # We fire a background task to 'ping' the client. 
    # If the client is a 'zombie', the socket will throw an error.
    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(20) # Ping every 20s
                await websocket.send_json({"type": "ping"})
        except Exception:
            manager.disconnect(user_id)

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            # 3. Listen for data (This blocks until a message arrives)
            data = await websocket.receive_text()
            logger.info(f"[DATA] Received from {user_id}: {data}")
            
            # Simple echo broadcast for simulation
            await manager.broadcast(f"User {user_id} says: {data}")
            
    except WebSocketDisconnect:
        # 4. Graceful severance
        manager.disconnect(user_id)
        heartbeat_task.cancel()
    except Exception as e:
        logger.error(f"[ERROR] Pipe failure for {user_id}: {e}")
        manager.disconnect(user_id)
        heartbeat_task.cancel()

# ==========================================
# TEST THIS LOCALLY:
# 1. Run: uvicorn connection_manager:app --reload
# 2. Open two browser consoles: 
#    let ws = new WebSocket("ws://localhost:8000/ws/user_1");
#    ws.onmessage = (e) => console.log(e.data);
# 3. Send data: ws.send("Hello World");
# ==========================================
