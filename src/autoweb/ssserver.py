import asyncio
import json

from websockets.asyncio.server import serve

from .tools import config


class WebSocketServer:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port

    async def send_json(self, ws, data: dict):
        """统一 JSON 发送出口"""
        try:
            await ws.send(json.dumps(data, ensure_ascii=False))
        except Exception as e:
            print("发送失败:", e)

    async def push_message(self, ws):
        pass
        # await asyncio.sleep(8)
        # await self.send_json(ws, {"cmd": "StopReq", "id": config.ANDROID_SERIAL})

    async def handle_message(self, ws, message):
        print(message)
        res = json.loads(message)

        if res.get("cmd") == "LoginReq":
            await self.send_json(ws, {"cmd": "LoginRes", "data": config.model_dump()})

    async def echo(self, ws):
        # 启动推送任务
        push_task = asyncio.create_task(self.push_message(ws))

        try:
            async for message in ws:
                await self.handle_message(ws, message)

        except Exception as e:
            print("连接断开:", e)

        finally:
            push_task.cancel()
            await asyncio.sleep(0)  # 让 cancel 生效

    async def start(self):
        print(f"WebSocket server running at ws://{self.host}:{self.port}")
        async with serve(self.echo, self.host, self.port):
            await asyncio.Future()  # 永久运行


if __name__ == "__main__":
    server = WebSocketServer()
    asyncio.run(server.start())
