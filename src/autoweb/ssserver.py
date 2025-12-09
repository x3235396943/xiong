from aiohttp import web, WSMsgType
from aiohttp.web import WebSocketResponse

from .tools import KuSettings


class WebSocketServer:
    ws: WebSocketResponse

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port

    async def _send_json(self, data: dict) -> None:
        """发送JSON数据到WebSocket客户端"""
        data["CONNECT_KEY"] = "test"
        await self.ws.send_json(data)

    async def _handle_login_request(self) -> None:
        """处理登录请求"""
        config = KuSettings()
        await self._send_json({"cmd": "LoginRes", "data": config.model_dump()})

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

    def start(self):
        """启动WebSocket服务器"""
        app = web.Application()
        app.add_routes([web.get("/", self._websocket_handler)])
        web.run_app(app, host=self.host, port=self.port)
        print(f"WebSocket服务器运行在 ws://{self.host}:{self.port}")


if __name__ == "__main__":
    server = WebSocketServer()
    server.start()
