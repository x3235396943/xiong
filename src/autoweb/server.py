import asyncio
import json
import re

from aiohttp import web, WSMsgType
from aiohttp.web import WebSocketResponse

from .tools import SearchConfig, ShareConfig


class MobileServer:
    ws: WebSocketResponse
    ready_event: asyncio.Event

    def __init__(self):
        self.ready_event = asyncio.Event()

    async def _send_json(self, data: dict) -> None:
        """发送JSON数据到WebSocket客户端"""
        data["CONNECT_KEY"] = "test"
        await self.ws.send_json(data)

    def _load_test_json(self) -> dict:
        with open("test.json", "r", encoding="utf-8") as f:
            return json.load(f)

    def _get_env(self, name) -> str:
        with open(".env", "r", encoding="utf-8") as f:
            return re.search(rf'{name}="(.+)"', f.read()).group(1)

    async def _handle_login_request(self) -> None:
        """处理登录请求"""
        res = await asyncio.to_thread(self._load_test_json)
        mode = await asyncio.to_thread(self._get_env, "RUN_MODE")
        params = res[mode]

        if mode == "search":
            config = SearchConfig(**params)
        else:
            config = ShareConfig(**params)
        await self._send_json({"cmd": "LoginRes", "data": config.model_dump()})
        # self.ready_event.set()

    async def _process_message(self, data: dict) -> None:
        """处理接收到的WebSocket消息"""

        cmd = data.get("cmd")

        if cmd == "LoginReq":
            await self._handle_login_request()
        elif cmd == "HeartbeatReq":
            await self._send_json({"cmd": "HeartbeatRes", "data": {}})
        elif cmd == "RunStateReq":
            await self._send_json({"cmd": "RunStateRes", "data": {}})
        elif cmd == "DeviceDataReq":
            await self._send_json({"cmd": "DeviceDataRes", "data": {}})
        else:
            print(f"未知命令: {cmd}")

    async def _websocket_handler(self, request: web.Request) -> WebSocketResponse:
        """WebSocket连接处理器"""
        self.ws = ws = WebSocketResponse()
        await ws.prepare(request)

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await self._process_message(msg.json())
            elif msg.type == WSMsgType.ERROR:
                print("ws connection closed with exception %s" % ws.exception())

        print("websocket connection closed")

        return ws

    async def active_key(self, _):
        return web.json_response({"code": 200, "data": {}})

    async def timer_task(self, _):
        await self.ready_event.wait()
        await asyncio.sleep(20)
        await self._send_json({"cmd": "StopPubForce", "data": {}})

    async def start_background_tasks(self, app: web.Application):
        app["timer_task"] = asyncio.create_task(self.timer_task(app))

    async def cleanup_background_tasks(self, app: web.Application):
        task = app["timer_task"]
        task.cancel()
        await task

    def start(self):
        """启动服务器"""
        app = web.Application()

        app.on_startup.append(self.start_background_tasks)
        app.on_cleanup.append(self.cleanup_background_tasks)

        app.add_routes([web.get("/", self._websocket_handler)])
        app.add_routes([web.post("/siberianNitraria/activate", self.active_key)])
        app.add_routes(
            [web.post("/api/siberianNitraria/verifyActivate", self.active_key)]
        )

        web.run_app(app, host="localhost", port=8765)
        print("服务器运行在 http://localhost:8765")


if __name__ == "__main__":
    server = MobileServer()
    server.start()
