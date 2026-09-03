import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import os

from .pipeline import run_pipeline

logger = logging.getLogger("nostradamus.server")

app = FastAPI(title="Nostradamus API")

# Manejador de conexion WS activo (solo permitimos 1 cliente a la vez por simplicidad)
class ConnectionManager:
    def __init__(self):
        self.active_connection: Optional[WebSocket] = None
        self.is_running = False

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connection = websocket

    def disconnect(self, websocket: WebSocket):
        if self.active_connection == websocket:
            self.active_connection = None

    async def send_json(self, data: dict):
        if self.active_connection:
            try:
                await self.active_connection.send_json(data)
            except Exception as e:
                logger.error(f"Error sending WS data: {e}")

manager = ConnectionManager()


@app.websocket("/ws/pipeline")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Esperar comando de inicio
            data = await websocket.receive_text()
            if data == "start" and not manager.is_running:
                manager.is_running = True
                
                # Definir callbacks que envian datos via WebSocket
                def on_log(msg: str, level: str):
                    # No usar await directamente en callbacks sincronos, asi que agendamos
                    asyncio.create_task(manager.send_json({
                        "type": "log",
                        "msg": msg,
                        "level": level
                    }))

                def on_step(num: int, status: str):
                    asyncio.create_task(manager.send_json({
                        "type": "step",
                        "num": num,
                        "status": status
                    }))

                # Correr pipeline
                try:
                    result = await run_pipeline(on_log=on_log, on_step=on_step)
                    await manager.send_json({
                        "type": "result",
                        "data": result if result else {"error": "Pipeline abortado"}
                    })
                except Exception as e:
                    await manager.send_json({
                        "type": "error",
                        "msg": str(e)
                    })
                finally:
                    manager.is_running = False

    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Servir archivos estaticos (Frontend)
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
