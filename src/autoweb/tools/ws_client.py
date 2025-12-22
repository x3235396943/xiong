"""
WebSocket 客户端收口模块

- dy（异步模式）使用 aiohttp WebSocket（主事件循环内）
- dyShare（多线程同步主流程）使用 websockets（独立线程事件循环内）

此文件的目标是“减少文件数量 + 消除 WSClient 命名冲突”，不强制统一到底层库。
"""

from __future__ import annotations

import asyncio
import json
from asyncio import sleep
from datetime import datetime
from typing import Any, Callable, Dict

from .core import log
from .config import env, PcConfig

# ----------------------------
# dy: aiohttp 版本（原 web_client.py）
# ----------------------------
from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType


class NotBack(Exception):
    pass


class AiohttpWSClient:
    session: ClientSession
    ws: ClientWebSocketResponse

    def __init__(self, url: str):
        self.url = url
        self._running = False
        self.send_queue: asyncio.Queue[dict] = asyncio.Queue()
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


# dy 现有代码默认使用的 WSClient（保持向后兼容）
WSClient = AiohttpWSClient


# ----------------------------
# dyShare: websockets 版本（原 ws.py）
# ----------------------------
import websockets


class WebsocketsWSClient:
    ws: Any

    def __init__(self, url: str):
        self.url = url
        self.send_queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False
        self.ready_event = asyncio.Event()
        self.stop_requested = False  # 添加停止请求标志
        # 指令处理回调字典：{cmd: handler_function}
        self.command_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        # 停止信号回调
        self.stop_signal_handler: Callable[[], None] | None = None
        # 保存外部发送消息的函数引用
        self.external_send_func: Callable[[Dict], None] | None = None
        # 保存配置更新回调函数
        self.config_update_handler: Callable[[Dict], None] | None = None
        # 事件循环引用
        self.event_loop = None
        # 从URL中提取设备ID
        self.device_id = self._extract_device_id(url)

    def _extract_device_id(self, url: str) -> str:
        """从WebSocket URL中提取设备ID"""
        try:
            from urllib.parse import urlparse, parse_qs

            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            return query_params.get("id", ["unknown"])[0]
        except Exception:
            return "unknown"

    async def connect(self):
        """连接WebSocket服务器（使用上下文管理器方式）"""
        log.info(f"正在连接 WebSocket 服务器: {self.url}")
        try:
            # 使用 async with 方式连接（这是可以工作的方式）
            self.ws = await websockets.connect(self.url).__aenter__()
            log.info("WebSocket 连接成功")
        except Exception as e:
            log.error(f"WebSocket 连接失败: {e}")
            raise  # 重新抛出异常，让调用者知道连接失败

    async def close(self):
        self._running = False
        self.stop_requested = True
        if hasattr(self, "ws") and self.ws:
            await self.ws.close()

    async def send(self, data: dict):
        if not self.stop_requested:
            await self.send_queue.put(json.dumps(data, ensure_ascii=False))

    async def _sender(self):
        while self._running and not self.stop_requested:
            try:
                msg = await asyncio.wait_for(self.send_queue.get(), timeout=1.0)
                await self.ws.send(msg)
                await sleep(0.1)  # 减少发送间隔
            except asyncio.TimeoutError:
                # 超时继续检查循环条件
                continue
            except Exception as e:
                if self._running and not self.stop_requested:
                    log.error(f"发送消息时出错: {e}")
                    # 连接断开，触发停止信号
                    self._handle_connection_lost("发送消息失败")
                break

        # 在退出循环前，确保队列中的关键消息（如 StopRes）被发送
        # 最多等待1秒，确保关键消息能够发送
        if self.stop_requested and not self.send_queue.empty():
            log.info("检测到停止标志，等待队列中的关键消息发送完成...")
            max_wait_time = 1.0  # 最多等待1秒
            wait_interval = 0.1  # 每次检查间隔0.1秒
            waited_time = 0.0

            while waited_time < max_wait_time and not self.send_queue.empty():
                try:
                    # 尝试获取并发送队列中的消息
                    msg = await asyncio.wait_for(
                        self.send_queue.get(), timeout=wait_interval
                    )
                    await self.ws.send(msg)
                    log.info("✓ 已发送队列中的关键消息")
                    waited_time = 0.0  # 重置等待时间，继续处理下一条消息
                except asyncio.TimeoutError:
                    # 超时，增加等待时间
                    waited_time += wait_interval
                    continue
                except Exception as e:
                    log.warning(f"发送队列中的关键消息时出错: {e}")
                    break

            if not self.send_queue.empty():
                log.warning(f"队列中仍有 {self.send_queue.qsize()} 条消息未发送")
            else:
                log.info("✓ 队列中的关键消息已全部发送完成")

    async def _receiver(self, websocket):
        """接收消息（使用 async for 方式，与 main.py 相同）"""
        message_count = 0
        try:
            async for message in websocket:
                message_count += 1
                if not self._running or self.stop_requested:
                    log.info(
                        f"[WebSocket] 接收器检测到停止标志，退出循环（已接收 {message_count} 条消息）"
                    )
                    break

                msg = message
                log.info(f"[WebSocket]收到第 {message_count} 条服务器消息: {msg}")

                try:
                    data = json.loads(msg)

                    # 处理指令
                    if isinstance(data, dict):
                        cmd = data.get("cmd")

                        # 检查是否是停止信号
                        is_stop_signal = False
                        if cmd == "StopReq":
                            is_stop_signal = True
                            self._send_response({"cmd": "StopRes", "id": self.device_id})
                            log.info("等待 StopRes 消息发送完成...")
                            await self._wait_for_message_sent()
                            log.info("✓ StopRes 消息已发送完成")

                        if is_stop_signal:
                            log.info("检测到停止信号: cmd={}".format(cmd))
                            self.stop_requested = True
                            self._handle_stop_signal()
                            break
                        else:
                            if cmd and cmd in self.command_handlers:
                                try:
                                    handler = self.command_handlers[cmd]
                                    handler(data)
                                except Exception as e:
                                    log.error(f"处理指令 {cmd} 时出错: {e}")
                            else:
                                pass
                except json.JSONDecodeError:
                    log.warning(f"收到非JSON消息: {msg}")
                except Exception as e:
                    log.error(f"处理消息时出错: {e}")
        except Exception as e:
            if self._running and not self.stop_requested:
                log.error(f"接收消息时出错: {e}")
                self._handle_connection_lost(f"接收消息失败: {e}")

    def _send_response(self, response_data: dict):
        """使用外部函数发送响应消息"""
        try:
            if self.external_send_func:
                self.external_send_func(response_data)
                log.info(f"已通过外部函数发送响应消息: {response_data}")
            else:
                log.warning("外部发送函数未设置，无法发送响应消息")
        except Exception as e:
            log.error(f"通过外部函数发送响应消息失败: {e}")

    async def _wait_for_message_sent(self, max_wait_time: float = 0.5):
        wait_interval = 0.05
        waited_time = 0.0

        while waited_time < max_wait_time:
            if self.send_queue.empty():
                await asyncio.sleep(0.1)
                log.info("✓ 队列已空，消息应已发送")
                return

            await asyncio.sleep(wait_interval)
            waited_time += wait_interval

        if not self.send_queue.empty():
            log.warning(
                f"等待消息发送超时（{max_wait_time}秒），队列中仍有消息，但继续执行停止流程"
            )

    def _handle_stop_signal(self):
        log.info("_handle_stop_signal() 被调用")
        if self.stop_signal_handler:
            log.info(f"停止信号处理器存在: {self.stop_signal_handler}")
            try:
                log.info("正在执行停止信号处理器...")
                self.stop_signal_handler()
                log.info("停止信号处理器执行完成")
            except Exception as e:
                log.error(f"执行停止信号处理器时出错: {e}", exc_info=True)
        else:
            log.warning("停止信号处理器未注册！")

    def set_external_send_func(self, send_func):
        self.external_send_func = send_func

    def set_config_update_handler(self, handler: Callable[[Dict], None]):
        self.config_update_handler = handler

    async def run(self):
        """运行WebSocket客户端主循环"""
        self._running = True
        while self._running and not self.stop_requested:
            try:
                await self.connect()
                self.ready_event.set()

                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(self._sender()),
                        asyncio.create_task(self._receiver(self.ws)),
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
                if self._running and not self.stop_requested:
                    log.error(f"WebSocket运行异常: {e}")
                    await asyncio.sleep(3)
                else:
                    break

    def register_command_handler(
        self, cmd: str, handler: Callable[[Dict[str, Any]], None]
    ):
        self.command_handlers[cmd] = handler

    def register_stop_signal_handler(self, handler: Callable[[], None]):
        self.stop_signal_handler = handler

    def _handle_connection_lost(self, reason: str):
        log.error(f"WebSocket 连接断开: {reason}")
        self.stop_requested = True
        if self.stop_signal_handler:
            try:
                self.stop_signal_handler()
            except Exception as e:
                log.error(f"执行停止信号处理器时出错: {e}")

    def is_stop_requested(self):
        return self.stop_requested


def create_websocket_client(cfg):
    """
    dyShare 使用：创建 websockets 客户端

    Args:
        cfg: 配置对象，需要包含 WS_URL 属性
    """
    ws_url = cfg.WS_URL
    if not ws_url:
        raise Exception("WebSocket URL 未配置，请检查配置文件")
    ws_client = WebsocketsWSClient(ws_url)
    log.info(f"✓ WebSocket 客户端已创建，连接到: {ws_url}")
    return ws_client


def start_websocket_client_in_thread(ws_client, on_stop_signal_received):
    """
    dyShare 使用：在独立线程中启动 websockets 客户端
    """
    import threading
    import time

    ws_client.register_stop_signal_handler(on_stop_signal_received)

    def run_ws_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ws_client.event_loop = loop
        try:
            loop.run_until_complete(ws_client.run())
        except Exception as e:
            log.error(f"[WebSocket线程] 运行出错: {e}")
        finally:
            loop.close()
            ws_client.event_loop = None

    ws_thread = threading.Thread(
        target=run_ws_in_thread, daemon=False, name="WebSocketThread"
    )
    ws_thread.start()
    time.sleep(2)
    return ws_thread


