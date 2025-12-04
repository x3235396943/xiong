import asyncio
from asyncio import sleep
import json
from . import log, config, KuSettings
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType


class WSClient:
    session: ClientSession
    ws: ClientWebSocketResponse

    def __init__(self, url: str, retry_times=3, retry_interval=9):
        self.url = url
        self.retry_times = retry_times
        self.retry_interval = retry_interval
        self.retry = 0

        self.send_queue = asyncio.Queue()
        self._running = False
        self.ready_event = asyncio.Event()

    async def connect(self):
        log.debug(f"{self.url}...")
        if not hasattr(self, "session") or self.session.closed:
            self.session = ClientSession()
        self.ws = await self.session.ws_connect(
            self.url,
            heartbeat=10,  # 心跳间隔
        )
        log.debug("连接成功")

    async def close(self):
        self._running = False
        if hasattr(self, "ws") and not self.ws.closed:
            await self.ws.close()

        if hasattr(self, "session") and not self.session.closed:
            await self.session.close()

    async def send(self, data: dict):
        await self.send_queue.put(data)

    async def _sender(self):
        while self._running:
            msg = await self.send_queue.get()
            log.debug(f"_sender: {msg}")
            await self.ws.send_json(msg)
            await sleep(1)

    async def _receiver(self):
        async for msg in self.ws:
            log.debug(f"_receiver: {msg}")
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("cmd") == "LoginRes":
                    global config
                    config = KuSettings(**data["data"])
                    self.ready_event.set()
                elif data.get("cmd") == "StopReq":
                    await self.send({"cmd": "StopRes", "id": config.BIT_BROWSER_IDS[0]})
                    return
            else:
                log.debug("WSMsgType:", msg.type)
        raise Exception("断开链接...")

    async def push(self, data: dict):
        await self.send(
            {
                "cmd": "PcDataReq",
                "data": {
                    "browserId": "",
                    "comment": 0,
                    "deviceType": "pc",
                    "follow": 0,
                    "id": config.BIT_BROWSER_IDS[0],
                    "isCompleted": False,
                    "keywords": "",
                    "like": 0,
                    "urlFail": 0,
                    "urlIndex": 0,
                    "urlOk": 0,
                    "video": 0,
                    "videoComment": 0,
                    **data,
                },
                "id": config.BIT_BROWSER_IDS[0],
            }
        )

    async def run(self):
        while self.retry < self.retry_times:
            try:
                log.debug(f"启动WS服务（第 {self.retry + 1} 次）")
                self._running = True
                await self.connect()
                self.retry = 0
                await self.send(
                    {
                        "cmd": "LoginReq",
                        "mode": "pc",
                        "id": config.BIT_BROWSER_IDS[0],
                        "version": config.VERSION,
                    }
                )

                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(self._sender()),
                        asyncio.create_task(self._receiver()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()

                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc
                break
            except Exception as e:
                self.retry += 1
                self._running = False

                if self.retry < self.retry_times:
                    log.error(
                        f"连接异常：{e}，{self.retry}/{self.retry_times} 次重试中...",
                        exc_info=True,
                    )
                    log.debug(f"{self.retry_interval} 秒后尝试重连")
                    await sleep(self.retry_interval)
                else:
                    log.error("重试次数已用尽，WS客户端关闭")
                    await self.close()
                    raise
