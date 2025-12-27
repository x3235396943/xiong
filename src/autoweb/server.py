from aiohttp import web, WSMsgType
from aiohttp.web import WebSocketResponse

from .tools import PcConfig


class WebSocketServer:
    ws: WebSocketResponse

    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port

    async def _send_json(self, data: dict) -> None:
        """发送JSON数据到WebSocket客户端"""
        data["CONNECT_KEY"] = "key-6584"
        await self.ws.send_json(data)

    async def _handle_login_request(self) -> None:
        """处理登录请求"""
        config = PcConfig(
            SIBERIAN_URL="http://127.0.0.1:8765/api/siberianNitraria/verifyActivate",
            SIBERIAN_KEY="Li/HbEihAYOLKDSYZAqJ/8d2tN0SC81ROxOFJ4Yokuk=",
            # 搜索关键字
            KEYWORDS=[
                "猫咪",
                "日本美女",
                "俄罗斯美女",
                "韩国美女",
                "台湾美女",
                "欧美美女",
                "港台美女",
                "素人美女",
                "黑人美女",
                "阿拉伯美女",
            ],
            VIDEO_COMMENTS="|".join(["6"]),
            COMMENT_REPLIES="|".join(["6"]),
            COMMENT_FILTER_KEYWORDS=["美女"],
            BIT_BROWSER_IDS=["4bbbe30c084a495796aaaff8a7082fda","57bd9953b5364d3db5c4ac7cfbb9a1b3"],
            # ShareConfig 中的参数
            LIKE_PROBABILITY=10,
            VISIT_ENABLE=10,
            PROFILE_FOLLOW_PROBABILITY=10,
            ENABLE_FOLLOW=True,
            ENABLE_PROFILE_VISIT=True,
            ENABLE_LIKE=True,
            ENABLE_SEARCH_KEYWORDS=True,
            ENABLE_COMMENT_REPLY=True,
            ENABLE_VIDEO_COMMENT=True,
            ENABLE_COMMENT_TEMPLATES=True,
            COMMENT_REPLY_PROBABILITY=10,
            VIDEO_REPLY_RATE=10,
            MIN_FOLLOWS_PER_VIDEO=5,
            MAX_FOLLOWS_PER_VIDEO=15,
            COMMENT_LIKE_COUNT_MIN=5,
            COMMENT_LIKE_COUNT_MAX=15,
            LIKE_WAIT_MIN=4,
            LIKE_WAIT_MAX=10,
            VISIT_MIN=2,
            VISIT_MAX=5,
            VIDEO_REPLY_WAIT_MIN=5,
            VIDEO_REPLY_WAIT_MAX=8,
            COMMENT_WAIT_MIN=5,
            COMMENT_WAIT_MAX=8,
            MAX_SCROLL_VIDEO=[10, 20],
            MAX_COMMENT=[2, 15]
        )
        config_data = config.model_dump()
        print("发送的配置数据:", config_data)
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
        elif cmd == "PcDataReq":
            await self._send_json({"cmd": "PcDataRes", "data": {}})
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
