import asyncio
from asyncio import sleep
import json
from . import log, config, ApkConfig
from websockets import connect
from websockets.asyncio.client import ClientConnection


class WSClient:
    ws: ClientConnection

    def __init__(self, url: str):
        self.url = url
        self.send_queue = asyncio.Queue()
        self._running = False
        self.ready_event = asyncio.Event()

    async def connect(self):
        log.debug(f"连接中...{self.url}")
        self.ws = await connect(self.url)
        log.debug("连接成功...")

    async def close(self):
        self._running = False
        if self.ws:
            await self.ws.close()

    async def send(self, data: dict):
        await self.send_queue.put(json.dumps(data))

    async def _sender(self):
        while self._running:
            msg = await self.send_queue.get()
            await self.ws.send(msg)
            await sleep(1)

    async def _receiver(self):
        async for msg in self.ws:
            print("1收到:", msg)
            data = json.loads(msg)
            print("2收到:", data)
            # if data.get("type") == "ready":
            #     global config
            #     config = ApkConfig(**data)
            #     self.ready_event.set()

    async def run(self):
        self._running = True
        await self.connect()
        await asyncio.gather(self._sender(), self._receiver())
