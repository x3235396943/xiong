import asyncio
from asyncio import sleep
import json
from typing import Dict, Callable, Optional, Any
from . import log, config
import websockets
from websockets.asyncio.client import ClientConnection


class WSClient:
    ws: ClientConnection

    def __init__(self, url: str):
        self.url = url
        self.send_queue = asyncio.Queue()
        self._running = False
        self.ready_event = asyncio.Event()
        self.stop_requested = False  # 添加停止请求标志
        self.last_message_time = 0  # 上次收到消息的时间
        self.event_loop = None  # 保存事件循环引用，用于跨线程发送消息
        # 指令处理回调字典：{cmd: handler_function}
        self.command_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        # 停止信号回调
        self.stop_signal_handler: Optional[Callable[[], None]] = None
        # 保存外部发送消息的函数引用
        self.external_send_func: Optional[Callable[[Dict], None]] = None
        # 保存配置更新回调函数
        self.config_update_handler: Optional[Callable[[Dict], None]] = None

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
        if hasattr(self, 'ws') and self.ws:
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

    async def _receiver(self, websocket):
        """接收消息（使用 async for 方式，与 main.py 相同）"""
        # log.info("[WebSocket] 接收器已启动，开始监听消息...")
        message_count = 0
        try:
            # 使用 async for 方式接收消息（与 main.py 中可工作的方式相同）
            async for message in websocket:
                message_count += 1
                if not self._running or self.stop_requested:
                    log.info(f"[WebSocket] 接收器检测到停止标志，退出循环（已接收 {message_count} 条消息）")
                    break

                msg = message
                # 添加时间戳，确认消息接收时间
                import datetime
                timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                log.info(f"[WebSocket]收到第 {message_count} 条服务器消息: {msg}")

                try:
                    data = json.loads(msg)
                    # log.info(f"解析后的消息: {data}")
                    
                    # 更新上次收到消息的时间
                    self.last_message_time = asyncio.get_event_loop().time()
                    
                    # 处理指令
                    if isinstance(data, dict):
                        cmd = data.get("cmd")

                        # 检查是否是停止信号（处理TypeStopReq或LoginRes stop）
                        is_stop_signal = False
                        if cmd == "StopReq":
                            is_stop_signal = True
                            # 当收到 TypeStopReq 时，使用外部函数发送响应
                            self._send_response({"cmd": "StopRes"})
                        
                        if is_stop_signal:
                            log.info("检测到停止信号: cmd={}".format(cmd))
                            self.stop_requested = True
                            self._handle_stop_signal()
                            # 退出接收循环
                            break
                        else:
                            # 查找并调用对应的指令处理器
                            if cmd and cmd in self.command_handlers:
                                try:
                                    handler = self.command_handlers[cmd]
                                    # 在事件循环中调用处理器（可能是同步函数）
                                    handler(data)
                                except Exception as e:
                                    log.error(f"处理指令 {cmd} 时出错: {e}")
                            else:
                                # 如果没有注册的处理器，记录日志
                                pass
                except json.JSONDecodeError:
                    log.warning(f"收到非JSON消息: {msg}")
                except Exception as e:
                    log.error(f"处理消息时出错: {e}")
        except Exception as e:
            if self._running and not self.stop_requested:
                log.error(f"接收消息时出错: {e}")
                # 连接断开，触发停止信号
                self._handle_connection_lost(f"接收消息失败: {e}")

    def _send_response(self, response_data: dict):
        """使用外部函数发送响应消息"""
        try:
            if self.external_send_func:
                # 调用外部发送函数
                self.external_send_func(response_data)
                log.info(f"已通过外部函数发送响应消息: {response_data}")
            else:
                log.warning("外部发送函数未设置，无法发送响应消息")
        except Exception as e:
            log.error(f"通过外部函数发送响应消息失败: {e}")

    def _handle_config_update(self, config_data: dict):
        """处理配置更新指令"""
        try:
            log.info(f"收到配置更新指令: {config_data}")
            if self.config_update_handler:
                log.info("调用配置更新处理器")
                self.config_update_handler(config_data)
                # 发送配置更新确认
                self._send_response({
                    "cmd": "ConfigUpdateAck",
                    "data": {
                        "status": "success",
                        "message": "配置更新已应用"
                    }
                })
                log.info("配置更新确认已发送")
            else:
                log.warning("未注册配置更新处理器")
                # 发送配置更新失败响应
                self._send_response({
                    "cmd": "ConfigUpdateAck",
                    "data": {
                        "status": "failed",
                        "message": "未注册配置更新处理器"
                    }
                })
        except Exception as e:
            log.error(f"处理配置更新时出错: {e}")
            # 发送配置更新失败响应
            self._send_response({
                "cmd": "ConfigUpdateAck",
                "data": {
                    "status": "failed",
                    "message": f"配置更新失败: {str(e)}"
                }
            })

    def set_external_send_func(self, send_func):
        """设置外部发送函数"""
        self.external_send_func = send_func
        log.info("外部发送函数已设置")

    def set_config_update_handler(self, handler: Callable[[Dict], None]):
        """设置配置更新处理器"""
        self.config_update_handler = handler
        log.info("配置更新处理器已设置")

    async def run(self):
        """运行WebSocket客户端（使用可以工作的方式）"""
        # log.info("[WebSocket] 开始运行 WebSocket 客户端...")
        self._running = True
        self.stop_requested = False
        self.last_message_time = asyncio.get_event_loop().time()  # 初始化时间

        try:
            # 使用 async with 方式连接（这是可以工作的方式）
            # log.info(f"[WebSocket] 正在连接到服务器: {self.url}")
            async with websockets.connect(self.url) as websocket:
                self.ws = websocket
                # log.info("WebSocket 连接成功")
                
                # 发送初始连接消息
                try:
                    welcome_msg = {"type": "client_connected", "message": "客户端已连接"}
                    await websocket.send(json.dumps(welcome_msg, ensure_ascii=False))
                except Exception as e:
                    log.warning(f"发送初始消息失败: {e}")

                # log.info("[WebSocket] 开始监听消息...")
                # 运行发送器和接收器（接收器需要传入 websocket 对象）
                # 使用 gather 确保两个任务并行运行
                try:
                    await asyncio.gather(
                        self._sender(), 
                        self._receiver(websocket),
                        return_exceptions=True
                    )
                except Exception as e:
                    log.error(f"WebSocket 任务执行出错: {e}")
                    raise
                
        except websockets.exceptions.ConnectionClosed:
            log.warning("服务器连接已关闭")
            if self._running and not self.stop_requested:
                self._handle_connection_lost("服务器连接已关闭")
        except Exception as e:
            log.error(f"WebSocket 运行出错: {e}")
            # 连接失败或运行时出错，触发停止信号
            if self._running and not self.stop_requested:
                self._handle_connection_lost(f"WebSocket 运行失败: {e}")
            raise  # 重新抛出异常
        
    def register_command_handler(self, cmd: str, handler: Callable[[Dict[str, Any]], None]):
        """
        注册指令处理器
        
        Args:
            cmd: 指令名称（如 "LoginRes"）
            handler: 处理函数，接收指令数据字典作为参数
        """
        self.command_handlers[cmd] = handler
        # log.debug(f"已注册指令处理器: {cmd}")

    def register_stop_signal_handler(self, handler: Callable[[], None]):
        """
        注册停止信号处理器

        Args:
            handler: 处理函数，无参数
        """
        self.stop_signal_handler = handler
        # log.debug("已注册停止信号处理器")

    def _handle_stop_signal(self):
        """处理停止信号"""
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

    def _handle_connection_lost(self, reason: str):
        """处理连接断开"""
        log.error(f"WebSocket 连接断开: {reason}")
        self.stop_requested = True
        # 连接断开时也触发停止信号，停止程序
        if self.stop_signal_handler:
            try:
                self.stop_signal_handler()
            except Exception as e:
                log.error(f"执行停止信号处理器时出错: {e}")

    def is_stop_requested(self):
        """检查是否请求了停止"""
        return self.stop_requested

    def is_heartbeat_timeout(self, timeout=3):
        """检查心跳是否超时"""
        return (asyncio.get_event_loop().time() - self.last_message_time) > timeout


# 公共方法，用于创建和启动WebSocket客户端
def create_websocket_client(config):
    """
    创建WebSocket客户端的公共方法

    Args:
        config: 配置对象，需要包含WEBSOCKET_URL和DEVICE_CODE属性

    Returns:
        WSClient: WebSocket客户端实例
    """
    # 从配置中获取 WebSocket URL 和设备码，并拼接成完整的URL
    ws_url = f"{config.WEBSOCKET_URL}?id={config.DEVICE_CODE}"

    if not ws_url:
        raise Exception("WebSocket URL 未配置，请检查配置文件")

    # 创建 WebSocket 客户端
    ws_client = WSClient(ws_url)

    log.info(f"✓ WebSocket 客户端已创建，连接到: {ws_url}")
    return ws_client


def start_websocket_client_in_thread(ws_client, on_stop_signal_received):
    """
    在独立线程中启动WebSocket客户端的公共方法

    Args:
        ws_client: WebSocket客户端实例
        on_stop_signal_received: 停止信号回调函数

    Returns:
        threading.Thread: WebSocket线程实例
    """
    import threading

    # 注册停止信号处理器
    ws_client.register_stop_signal_handler(on_stop_signal_received)

    # 在单独的线程中运行 WebSocket 客户端
    def run_ws_in_thread():
        """在独立线程中运行事件循环"""
        # 创建新的事件循环（确保独立运行）
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # 保存事件循环引用到客户端实例，供主线程使用
        ws_client.event_loop = loop
        try:
            # 在新的事件循环中运行
            loop.run_until_complete(ws_client.run())
        except Exception as e:
            log.error(f"[WebSocket线程] 运行出错: {e}")
        finally:
            loop.close()
            ws_client.event_loop = None  # 清理引用

    # 启动后台线程（设置为非 daemon，确保能正常运行）
    ws_thread = threading.Thread(target=run_ws_in_thread, daemon=False, name="WebSocketThread")
    ws_thread.start()

    # 等待 WebSocket 连接建立（给一点时间）
    import time
    time.sleep(2)

    # log.info("✓ WebSocket 客户端已在独立线程中启动")
    return ws_thread