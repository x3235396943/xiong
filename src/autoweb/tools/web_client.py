import asyncio
from asyncio import sleep
from . import log, env, PcConfig
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType


class NotBack(Exception):
    pass


class WSClient:
    session: ClientSession
    ws: ClientWebSocketResponse

    def __init__(self, url: str):
        self.url = url
        self._running = False
        self.send_queue = asyncio.Queue()
        self.ready_event = asyncio.Event()
        self.is_back = asyncio.Event()
        self.config: PcConfig | None = None
        self.cmd = ""
        self.device_data = {
            "cmd": "PcDataReq",
            "data": {
                "comment": 0,
                "deviceType": "pc",
                "follow": 0,
                "isCompleted": False,
                "keywords": "",
                "like": 0,
                "video": 0,
                "videoComment": 0,
            },
        }

    async def connect(self):
        log.debug(f"{self.url}...")
        self._running = True
        if not hasattr(self, "session") or self.session.closed:
            self.session = ClientSession()
        self.ws = await self.session.ws_connect(self.url)
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
            msg["id"] = env.DEVICE_CODE
            if msg["cmd"] != "HeartbeatReq":
                log.debug(f"_sender: {msg}")
            await self.ws.send_json(msg)

            if msg["cmd"].endswith("Req"):
                self.cmd = msg["cmd"][0:-1] + "s"
                for i in range(3):
                    try:
                        async with asyncio.timeout(5):
                            await self.is_back.wait()
                        self.is_back.clear()
                        break
                    except TimeoutError:
                        log.error(f"响应超时5秒，{i + 1}/3 次重试中...")
                else:
                    raise NotBack("响应没有返回...")
            elif msg["cmd"] == "StopRes":
                return

            await sleep(1)

    async def _receiver(self):
        async for msg in self.ws:
            if msg.type == WSMsgType.TEXT:
                data = msg.json()
                if data["cmd"] != "HeartbeatRes":
                    log.debug(f"_receiver: {data}")

                cmd = data.get("cmd")
                if not cmd:
                    return

                if cmd.endswith("Res") and data["CONNECT_KEY"] != env.CONNECT_KEY:
                    log.debug(
                        f"_receiver: env connect_key: {env.CONNECT_KEY}, data connect_key: {data['CONNECT_KEY']}"
                    )
                    return

                if cmd == self.cmd:
                    self.is_back.set()
                if cmd == "LoginRes":
                    self.config = PcConfig(**data["data"])
                    self.ready_event.set()
                elif cmd == "StopReq":
                    await self.send({"cmd": "StopRes"})
                elif cmd == "StopPubForce":
                    return
        raise Exception("断开链接...")

    async def _heartbeat(self):
        """自定义心跳任务，可以携带额外参数"""
        while self._running:
            await asyncio.sleep(10)
            await self.send({"cmd": "HeartbeatReq"})

    async def updateState(self, state: str):
        await self.send({"cmd": "RunStateReq", "state": state})

    async def push(self, **kwargs):
        params = self.device_data["data"]
        for k, v in kwargs.items():
            if type(params[k]) is int:
                params[k] += v
            else:
                params[k] = v
        await self.send(self.device_data)

    async def run(self):
        retry = 1
        retry_times = 3
        while True:
            try:
                log.debug(f"启动WS服务（第 {retry} 次）")
                await self.connect()
                retry = 1

                if not self.config:
                    await self.send(
                        {
                            "cmd": "LoginReq",
                            "mode": "pc",
                            "version": env.VERSION,
                        }
                    )

                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(self._heartbeat()),
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
            except NotBack:
                raise
            except Exception as e:
                self._running = False
                if retry <= retry_times:
                    log.error(
                        f"连接异常：{e}，{retry}/{retry_times} 次重试中...",
                        exc_info=True,
                    )
                    retry_interval = 9
                    log.debug(f"{retry_interval} 秒后尝试重连")
                    await sleep(retry_interval)
                else:
                    log.error("重试次数已用尽，WS客户端关闭")
                    raise
            retry += 1
