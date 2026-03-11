import asyncio
import json
import logging
from typing import List, Dict
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._background_task = None
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: dict):
        text_message = json.dumps(message)
        stale_connections: List[WebSocket] = []
        send_tasks = [connection.send_text(text_message) for connection in list(self.active_connections)]
        results = await asyncio.gather(*send_tasks, return_exceptions=True) if send_tasks else []
        for connection, result in zip(list(self.active_connections), results):
            if isinstance(result, Exception):
                logger.error(f"Error broadcasting to client: {result}")
                stale_connections.append(connection)
        for connection in stale_connections:
            self.disconnect(connection)
                
    async def start_price_broadcaster(self, get_quote_func):
        """
        Background task to periodically broadcast dummy or real prices 
        to all connected WebSocket clients.
        """
        if self._background_task is not None:
            return
            
        async def broadcast_loop():
            # Tickers to monitor (can be made dynamic later)
            tickers = ["NIFTY 50", "RELIANCE.NS", "HDFCBANK.NS", "TCS.NS"]
            while True:
                if self.active_connections:
                    prices = {}
                    for ticker in tickers:
                        try:
                            price = await asyncio.to_thread(get_quote_func, ticker)
                            prices[ticker] = float(price or 0.0)
                        except:
                            pass
                            
                    if prices:
                        payload = {
                            "type": "price_update",
                            "timestamp": datetime.now().isoformat(),
                            "data": prices
                        }
                        await self.broadcast(payload)
                await asyncio.sleep(2.0)  # Broadcast every 2 seconds
                
        self._background_task = asyncio.create_task(broadcast_loop())

manager = ConnectionManager()
