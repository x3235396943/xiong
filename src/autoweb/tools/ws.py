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
        # 指令处理回调字典：{cmd: handler_function}
        self.command_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        # 停止信号回调
        self.stop_signal_handler: Optional[Callable[[], None]] = None

    async def connect(self):
        """连接WebSocket服务器（使用上下文管理器方式）"""
        print(f"[WebSocket] 正在连接 WebSocket 服务器: {self.url}")
        log.info(f"正在连接 WebSocket 服务器: {self.url}")
        try:
            # 使用 async with 方式连接（这是可以工作的方式）
            self.ws = await websockets.connect(self.url).__aenter__()
            print(f"[WebSocket] ✓ WebSocket 连接成功，URL: {self.url}")
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
        print("[WebSocket] 接收器已启动，开始监听消息...")
        message_count = 0
        try:
            # 使用 async for 方式接收消息（与 main.py 中可工作的方式相同）
            async for message in websocket:
                message_count += 1
                if not self._running or self.stop_requested:
                    print(f"[WebSocket] 接收器检测到停止标志，退出循环（已接收 {message_count} 条消息）")
                    break
                
                msg = message
                # 添加时间戳，确认消息接收时间
                import datetime
                timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"[WebSocket] [{timestamp}] 收到第 {message_count} 条服务器消息: {msg}")
                log.info(f"收到服务器消息: {msg}")
                
                try:
                    data = json.loads(msg)
                    print(f"[WebSocket] 解析后的消息: {data}")
                    log.info(f"解析后的消息: {data}")
                    
                    # 更新上次收到消息的时间
                    self.last_message_time = asyncio.get_event_loop().time()
                    
                    # 处理指令
                    if isinstance(data, dict):
                        cmd = data.get("cmd")
                        data_value = data.get("data")
                        
                        print(f"[WebSocket] 指令: cmd={cmd}, data={data_value}")
                        log.info(f"指令: cmd={cmd}, data={data_value}")
                        
                        # 检查是否是停止信号（支持多种格式）
                        is_stop_signal = False
                        if cmd == "LoginRes" and data_value == "stop":
                            is_stop_signal = True
                        elif cmd == "stop" or data_value == "stop":
                            # 也支持 cmd="stop" 或 data="stop" 的格式
                            is_stop_signal = True
                        
                        if is_stop_signal:
                            print("=" * 60)
                            print("[WebSocket] ✓ 检测到停止信号: cmd={}, data={}".format(cmd, data_value))
                            print("=" * 60)
                            log.info("✓ 检测到停止信号: cmd={}, data={}".format(cmd, data_value))
                            self.stop_requested = True
                            print("[WebSocket] ✓ 已设置 stop_requested = True")
                            log.info("✓ 已设置 stop_requested = True")
                            # 通知应用程序需要停止
                            print("[WebSocket] ✓ 正在调用停止信号处理器...")
                            log.info("✓ 正在调用停止信号处理器...")
                            self._handle_stop_signal()
                            print("[WebSocket] ✓ 停止信号处理器已调用")
                            log.info("✓ 停止信号处理器已调用")
                            # 退出接收循环
                            break
                        else:
                            # 查找并调用对应的指令处理器
                            if cmd and cmd in self.command_handlers:
                                try:
                                    handler = self.command_handlers[cmd]
                                    print(f"[WebSocket] 调用指令处理器: {cmd}")
                                    log.info(f"调用指令处理器: {cmd}")
                                    # 在事件循环中调用处理器（可能是同步函数）
                                    handler(data)
                                except Exception as e:
                                    print(f"[WebSocket] ❌ 处理指令 {cmd} 时出错: {e}")
                                    log.error(f"处理指令 {cmd} 时出错: {e}")
                            else:
                                # 如果没有注册的处理器，记录日志
                                print(f"[WebSocket] 收到未处理的指令: cmd={cmd}, data={data_value}")
                                log.info(f"收到未处理的指令: cmd={cmd}, data={data_value}")
                except json.JSONDecodeError:
                    print(f"[WebSocket] ⚠️ 收到非JSON消息: {msg}")
                    log.warning(f"收到非JSON消息: {msg}")
                except Exception as e:
                    print(f"[WebSocket] ❌ 处理消息时出错: {e}")
                    log.error(f"处理消息时出错: {e}")
        except Exception as e:
            if self._running and not self.stop_requested:
                print(f"[WebSocket] ❌ 接收消息时出错: {e}")
                log.error(f"接收消息时出错: {e}")
                # 连接断开，触发停止信号
                self._handle_connection_lost(f"接收消息失败: {e}")

    async def run(self):
        """运行WebSocket客户端（使用可以工作的方式）"""
        print("[WebSocket] 开始运行 WebSocket 客户端...")
        self._running = True
        self.stop_requested = False
        self.last_message_time = asyncio.get_event_loop().time()  # 初始化时间
        
        try:
            # 使用 async with 方式连接（这是可以工作的方式）
            print(f"[WebSocket] 正在连接到服务器: {self.url}")
            async with websockets.connect(self.url) as websocket:
                self.ws = websocket
                print("[WebSocket] ✓ WebSocket 连接成功!")
                log.info("WebSocket 连接成功")
                
                # 发送初始连接消息
                try:
                    welcome_msg = {"type": "client_connected", "message": "客户端已连接"}
                    await websocket.send(json.dumps(welcome_msg, ensure_ascii=False))
                    print("[WebSocket] 已发送初始消息")
                    log.info("已发送初始连接消息")
                except Exception as e:
                    print(f"[WebSocket] ⚠️ 发送初始消息失败: {e}")
                    log.warning(f"发送初始消息失败: {e}")
                
                print("[WebSocket] 开始监听消息...")
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
            print("[WebSocket] 服务器连接已关闭")
            log.warning("服务器连接已关闭")
            if self._running and not self.stop_requested:
                self._handle_connection_lost("服务器连接已关闭")
        except Exception as e:
            print(f"[WebSocket] ❌ 运行出错: {e}")
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
        log.debug(f"已注册指令处理器: {cmd}")
    
    def register_stop_signal_handler(self, handler: Callable[[], None]):
        """
        注册停止信号处理器
        
        Args:
            handler: 处理函数，无参数
        """
        self.stop_signal_handler = handler
        log.debug("已注册停止信号处理器")
    
    def _handle_stop_signal(self):
        """处理停止信号"""
        print("[WebSocket] _handle_stop_signal() 被调用")
        log.info("_handle_stop_signal() 被调用")
        if self.stop_signal_handler:
            print(f"[WebSocket] 停止信号处理器存在: {self.stop_signal_handler}")
            log.info(f"停止信号处理器存在: {self.stop_signal_handler}")
            try:
                print("[WebSocket] 正在执行停止信号处理器...")
                log.info("正在执行停止信号处理器...")
                self.stop_signal_handler()
                print("[WebSocket] 停止信号处理器执行完成")
                log.info("停止信号处理器执行完成")
            except Exception as e:
                print(f"[WebSocket] ❌ 执行停止信号处理器时出错: {e}")
                log.error(f"执行停止信号处理器时出错: {e}", exc_info=True)
        else:
            print("[WebSocket] ⚠️ 停止信号处理器未注册！")
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