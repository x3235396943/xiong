"""
快手模块 WebSocket 管理器
用于集成 WebSocket 功能到快手浏览器集群中
"""

import asyncio
import json
import threading
import time
from typing import Dict, Callable, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor

from ..tools.ws_client import WebsocketsWSClient, create_websocket_client, start_websocket_client_in_thread
from ..tools import log as logger
from .browser_cluster import BrowserCluster, cluster
from .selenium_browser import SeleniumBrowser
from ..tools.config import env


class KuaishouWSManager:
    """快手模块的WebSocket管理器"""
    
    def __init__(self, config=None):
        self.config = config
        self.ws_client: Optional[WebsocketsWSClient] = None
        self.ws_thread = None
        self.browser_cluster = cluster
        self._running = False
        self.command_handlers: Dict[str, Callable] = {}
        self.browser_ws_handlers: Dict[str, Dict] = {}  # 存储浏览器相关的WebSocket处理器
        self.license_manager = None  # 用于更新LicenseManager配置
        self.heartbeat_task = None
        self.heartbeat_timeout_count = 0
        self.max_heartbeat_timeouts = 3
        self.pong_received = asyncio.Event()
        self.ws_loop = None

    def init_websocket(self):
        """初始化WebSocket客户端"""
        try:
            if not self.config or not hasattr(self.config, 'WS_URL'):
                logger.error("WebSocket 配置缺失，无法初始化")
                return False

            self.ws_client = create_websocket_client(self.config)
            logger.info("WebSocket 客户端初始化成功")

            # 注册默认命令处理器
            self._register_default_handlers()
            
            # 设置停止信号处理器
            def on_stop_received():
                logger.info("收到停止信号，正在关闭快手模块...")
                self._running = False
                # 可以在这里添加停止浏览器任务的逻辑
                self.stop_all_browsers()
                
            self.ws_thread = start_websocket_client_in_thread(self.ws_client, on_stop_received)
            logger.info("WebSocket 客户端线程已启动")
            self._running = True
            
            # 发送版本信息到服务器
            self._send_login_req()
            self._start_heartbeat_if_ready()
             
            return True
            
        except Exception as e:
            logger.error(f"初始化WebSocket失败: {e}")
            return False

    def _register_default_handlers(self):
        """注册默认的命令处理器"""
        # 浏览器控制命令
        self.ws_client.register_command_handler("start_browsers", self._handle_start_browsers)
        self.ws_client.register_command_handler("stop_browsers", self._handle_stop_browsers)
        self.ws_client.register_command_handler("execute_command", self._handle_execute_command)
        self.ws_client.register_command_handler("get_status", self._handle_get_status)
        self.ws_client.register_command_handler("update_config", self._handle_update_config)
        # 配置更新命令
        self.ws_client.register_command_handler("LoginRes", self._handle_login_res_command)
        self.ws_client.register_command_handler("HeartbeatRes", self._handle_heartbeat_response)

    def _send_heartbeat(self):
        try:
            from datetime import datetime
            device_id = (self.ws_client.device_id if self.ws_client else None) or getattr(self.config, "DEVICE_CODE", "")
            message = {
                "cmd": "HeartbeatReq",
                "id": device_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            try:
                logger.info(f"发送到服务器的消息: {json.dumps(message, ensure_ascii=False, indent=2)}")
            except Exception:
                pass
            if self.ws_client and self.ws_client.event_loop:
                asyncio.run_coroutine_threadsafe(self.ws_client.send(message), self.ws_client.event_loop)
        except Exception as e:
            logger.error(f"发送心跳包时出错: {e}")

    def _handle_heartbeat_response(self, data: Dict[str, Any]):
        try:
            if isinstance(data, dict) and data.get("cmd") == "HeartbeatRes":
                self.pong_received.set()
                self.heartbeat_timeout_count = 0
                logger.info(f"收到心跳响应")
        except Exception as e:
            logger.error(f"处理心跳响应失败: {e}")

    async def _heartbeat_task(self):
        while self._running and self.ws_client and not self.ws_client.is_stop_requested():
            try:
                self._send_heartbeat()
                try:
                    await asyncio.wait_for(self.pong_received.wait(), timeout=5.0)
                    self.heartbeat_timeout_count = 0
                    self.pong_received.clear()
                except asyncio.TimeoutError:
                    logger.warning("心跳响应超时")
                    self.heartbeat_timeout_count += 1
                    if self.heartbeat_timeout_count >= self.max_heartbeat_timeouts:
                        logger.error(f"心跳连续 {self.max_heartbeat_timeouts} 次超时，准备停止程序")
                        self._running = False
                        if self.ws_client:
                            self.ws_client.stop_requested = True
                        self.stop_all_browsers()
                        break
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳任务出错: {e}")
                break

    def _start_heartbeat_if_ready(self):
        try:
            max_wait_time = 5
            wait_interval = 0.1
            waited_time = 0
            while waited_time < max_wait_time:
                if self.ws_client and self.ws_client.event_loop is not None:
                    self.ws_loop = self.ws_client.event_loop
                    break
                time.sleep(wait_interval)
                waited_time += wait_interval
            if self.ws_loop and self.ws_loop.is_running():
                self.heartbeat_task = asyncio.run_coroutine_threadsafe(self._heartbeat_task(), self.ws_loop)
                logger.info("心跳任务已启动")
        except Exception as e:
            logger.error(f"启动心跳任务失败: {e}")


    def _send_login_req(self):
        """发送登录请求（包含版本信息）到服务器"""
        try:
            from urllib.parse import parse_qs, urlparse
            
            # 从WebSocket URL中提取设备ID
            parsed_url = urlparse(self.config.WS_URL)
            query_params = parse_qs(parsed_url.query)
            device_id = query_params.get("id", [self.config.DEVICE_CODE])[0]
            
            # 发送登录请求，包含版本信息
            message = {
                "cmd": "LoginReq",
                "id": device_id,
                "mode": "pc",
                "version": env.VERSION or getattr(self.config, 'VERSION', '1.3.5'),  # 使用配置中的版本号或默认值
            }
            try:
                logger.info(f"发送到服务器的消息: {json.dumps(message, ensure_ascii=False, indent=2)}")
            except Exception:
                pass
            
            if self.ws_client:
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(message),
                    self.ws_client.event_loop
                )
                logger.info(f"已发送版本信息到服务器: {message['version']}")
                
        except Exception as e:
            logger.error(f"发送版本信息到服务器失败: {e}")

    def send_run_state_req(self, browser_id: str):
        """发送浏览器运行状态请求到服务器
        
        Args:
            browser_id: 浏览器ID
        """
        try:
            # 根据浏览器ID长度判断状态（参考抖音模块）
            state = "running" if len(browser_id) == 32 else "error"
            
            message = {
                "browserId": browser_id,
                "cmd": "RunStateReq",
                "id": self.config.DEVICE_CODE,
                "state": state,
            }
            try:
                logger.info(f"发送到服务器的消息: {json.dumps(message, ensure_ascii=False, indent=2)}")
            except Exception:
                pass
            
            if self.ws_client:
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(message),
                    self.ws_client.event_loop
                )
                logger.info(f"已发送浏览器运行状态到服务器: {browser_id}, 状态: {state}")
                
        except Exception as e:
            logger.error(f"发送浏览器运行状态到服务器失败: {e}")
            

    def _handle_start_browsers(self, data: Dict[str, Any]):
        """处理启动浏览器命令"""
        try:
            browser_ids = data.get("data", {}).get("browser_ids", [])
            logger.info(f"收到启动浏览器命令，浏览器ID: {browser_ids}")
            
            if browser_ids:
                results = self.browser_cluster.init_browsers_by_ids(browser_ids)
                response = {
                    "cmd": "start_browsers_response",
                    "data": results,
                    "success": all(r.get('success', False) for r in results.values())
                }
            else:
                # 启动默认浏览器
                selenium_browser = SeleniumBrowser()
                result = selenium_browser._open_control()
                if result.get('driver'):
                    browser_name = "single_browser_fallback"
                    added = self.browser_cluster.add_browser(browser_name, selenium_browser, display_name=browser_name)
                    response = {
                        "cmd": "start_browsers_response", 
                        "data": {browser_name: {"success": added, "message": result.get('message', '')}},
                        "success": added
                    }
                else:
                    response = {
                        "cmd": "start_browsers_response",
                        "data": {"error": result.get('message', '无法启动浏览器')},
                        "success": False
                    }
            
            # 发送响应
            if self.ws_client:
                try:
                    logger.info(f"发送到服务器的消息: {json.dumps(response, ensure_ascii=False, indent=2)}")
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(response), 
                    self.ws_client.event_loop
                )
                
        except Exception as e:
            logger.error(f"处理启动浏览器命令失败: {e}")

    def _handle_stop_browsers(self, data: Dict[str, Any]):
        """处理停止浏览器命令"""
        try:
            browser_ids = data.get("data", {}).get("browser_ids", [])
            logger.info(f"收到停止浏览器命令，浏览器ID: {browser_ids}")
            
            if browser_ids:
                for browser_id in browser_ids:
                    browser = self.browser_cluster.get_browser(browser_id)
                    if browser and browser.driver:
                        try:
                            browser._close_control(browser.id)
                            self.browser_cluster.remove_browser(browser_id, close_browser=False)
                        except Exception as e:
                            logger.error(f"关闭浏览器 {browser_id} 失败: {e}")
            else:
                # 停止所有浏览器
                self.stop_all_browsers()
            
            response = {
                "cmd": "stop_browsers_response",
                "data": {"message": "浏览器已停止"},
                "success": True
            }
            
            if self.ws_client:
                try:
                    logger.info(f"发送到服务器的消息: {json.dumps(response, ensure_ascii=False, indent=2)}")
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(response),
                    self.ws_client.event_loop
                )
                
        except Exception as e:
            logger.error(f"处理停止浏览器命令失败: {e}")

    def _handle_execute_command(self, data: Dict[str, Any]):
        """处理执行命令命令"""
        try:
            command = data.get("data", {}).get("command", "")
            browser_id = data.get("data", {}).get("browser_id", "")
            params = data.get("data", {}).get("params", {})
            
            logger.info(f"收到执行命令: {command}, 浏览器: {browser_id}, 参数: {params}")
            
            # 根据命令类型执行不同的操作
            result = None
            success = False
            
            if command == "navigate_to":
                # 导航到指定URL
                url = params.get("url", "")
                browser = self.browser_cluster.get_browser(browser_id)
                if browser and browser.driver:
                    try:
                        browser.driver.get(url)
                        result = {"message": f"成功导航到 {url}"}
                        success = True
                    except Exception as e:
                        result = {"error": f"导航失败: {e}"}
                else:
                    result = {"error": f"浏览器 {browser_id} 不存在或未启动"}
            elif command == "get_current_url":
                # 获取当前URL
                browser = self.browser_cluster.get_browser(browser_id)
                if browser and browser.driver:
                    try:
                        current_url = browser.driver.current_url
                        result = {"current_url": current_url}
                        success = True
                    except Exception as e:
                        result = {"error": f"获取URL失败: {e}"}
                else:
                    result = {"error": f"浏览器 {browser_id} 不存在或未启动"}
            elif command == "get_browser_list":
                # 获取浏览器列表
                browser_list = self.browser_cluster.list_browsers()
                result = {"browser_list": browser_list}
                success = True
            else:
                result = {"error": f"未知命令: {command}"}
            
            response = {
                "cmd": "execute_command_response",
                "data": result,
                "success": success
            }
            
            if self.ws_client:
                try:
                    logger.info(f"发送到服务器的消息: {json.dumps(response, ensure_ascii=False, indent=2)}")
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(response),
                    self.ws_client.event_loop
                )
                
        except Exception as e:
            logger.error(f"处理执行命令失败: {e}")

    def _handle_get_status(self, data: Dict[str, Any]):
        """处理获取状态命令"""
        try:
            logger.info("收到获取状态命令")
            
            status = {
                "browser_cluster_status": self.browser_cluster.get_status(),
                "websocket_status": {
                    "is_connected": self.ws_client and not self.ws_client.is_stop_requested(),
                    "device_id": self.ws_client.device_id if self.ws_client else "unknown"
                },
                "running": self._running
            }
            
            response = {
                "cmd": "get_status_response",
                "data": status,
                "success": True
            }
            
            if self.ws_client:
                try:
                    logger.info(f"发送到服务器的消息: {json.dumps(response, ensure_ascii=False, indent=2)}")
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(response),
                    self.ws_client.event_loop
                )
                
        except Exception as e:
            logger.error(f"处理获取状态命令失败: {e}")

    def _handle_update_config(self, data: Dict[str, Any]):
        """处理更新配置命令"""
        try:
            new_config = data.get("data", {}).get("config", {})
            logger.info(f"收到更新配置命令: {new_config}")
            
            # 这里可以实现配置更新逻辑
            # 可能需要重新初始化某些组件
            response = {
                "cmd": "update_config_response",
                "data": {"message": "配置更新功能待实现"},
                "success": True
            }
            
            if self.ws_client:
                try:
                    logger.info(f"发送到服务器的消息: {json.dumps(response, ensure_ascii=False, indent=2)}")
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(response),
                    self.ws_client.event_loop
                )
                
        except Exception as e:
            logger.error(f"处理更新配置命令失败: {e}")

    def _handle_login_res_command(self, data: Dict[str, Any]):
        """处理登录响应命令（配置更新）"""
        try:
            logger.info(f"收到登录响应命令，准备更新配置")
            
            if isinstance(data, dict) and "data" in data:
                config_data = data.get("data", {})
                if config_data:
                    self._handle_config_update(config_data)
            
            response = {
                "cmd": "login_res_response",
                "data": {"message": "配置更新成功"},
                "success": True
            }
            
            if self.ws_client:
                try:
                    logger.info(f"发送到服务器的消息: {json.dumps(response, ensure_ascii=False, indent=2)}")
                except Exception:
                    pass
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(response),
                    self.ws_client.event_loop
                )
                
        except Exception as e:
            logger.error(f"处理登录响应命令失败: {e}")

    def _handle_config_update(self, config_data: Dict[str, Any]):
        """处理配置更新"""
        try:
            from ..tools.config import get_config
            from ..tools.license import LicenseManager
            
            # 获取全局配置实例并更新
            cfg = get_config()
            cfg.update_from_dict(config_data)
            
            # 如果LicenseManager已经存在，也更新其配置
            if hasattr(self, 'license_manager') and self.license_manager:
                if "SIBERIAN_URL" in config_data:
                    self.license_manager.url = config_data["SIBERIAN_URL"]
                if "SIBERIAN_KEY" in config_data:
                    self.license_manager.key = config_data["SIBERIAN_KEY"]
                if "DEVICE_CODE" in config_data:
                    self.license_manager.code = config_data["DEVICE_CODE"]
            
            logger.info("配置已更新")
            cfg.print_config_summary()
        except Exception as e:
            logger.error(f"配置更新失败: {e}")


    def send_browser_event(self, browser_id: str, event_type: str, data: Dict[str, Any]):
        """发送浏览器事件到WebSocket服务器"""
        try:
            if not self.ws_client:
                return False
                
            event_data = {
                "cmd": "browser_event",
                "data": {
                    "browser_id": browser_id,
                    "event_type": event_type,
                    "event_data": data,
                    "timestamp": time.time()
                }
            }
            
            try:
                logger.info(f"发送到服务器的消息: {json.dumps(event_data, ensure_ascii=False, indent=2)}")
            except Exception:
                pass
            asyncio.run_coroutine_threadsafe(
                self.ws_client.send(event_data),
                self.ws_client.event_loop
            )
            return True
            
        except Exception as e:
            logger.error(f"发送浏览器事件失败: {e}")
            return False

    def stop_all_browsers(self):
        """停止所有浏览器"""
        logger.info("正在停止所有浏览器...")
        try:
            browser_list = self.browser_cluster.list_browsers()
            for browser_id in browser_list:
                browser = self.browser_cluster.get_browser(browser_id)
                if browser and browser.driver and browser.id:
                    try:
                        browser._close_control(browser.id)
                    except Exception as e:
                        logger.error(f"关闭浏览器 {browser_id} 失败: {e}")
            
            # 从集群中移除所有浏览器
            for browser_id in browser_list:
                self.browser_cluster.remove_browser(browser_id, close_browser=False)
                
            logger.info("所有浏览器已停止")
        except Exception as e:
            logger.error(f"停止浏览器过程中出错: {e}")

    def is_running(self) -> bool:
        """检查管理器是否正在运行"""
        return self._running and self.ws_client and not self.ws_client.is_stop_requested()

    def stop(self):
        """停止WebSocket管理器"""
        logger.info("正在停止快手WebSocket管理器...")
        self._running = False
        
        if self.ws_client:
            # 发送停止请求
            self.ws_client.stop_requested = True
            
        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=5)  # 等待最多5秒
        
        # 停止所有浏览器
        self.stop_all_browsers()
        logger.info("快手WebSocket管理器已停止")


# 全局WebSocket管理器实例
_ws_manager: Optional[KuaishouWSManager] = None


def get_ws_manager() -> Optional[KuaishouWSManager]:
    """获取快手WebSocket管理器实例"""
    return _ws_manager


def init_ws_manager(config, license_manager=None) -> bool:
    """初始化快手WebSocket管理器"""
    global _ws_manager
    try:
        _ws_manager = KuaishouWSManager(config)
        # 设置LicenseManager以便更新配置
        if license_manager:
            _ws_manager.license_manager = license_manager
        success = _ws_manager.init_websocket()
        if success:
            _ws_manager._running = True
            logger.info("快手WebSocket管理器初始化成功")
        else:
            logger.error("快手WebSocket管理器初始化失败")
        return success
    except Exception as e:
        logger.error(f"初始化快手WebSocket管理器时出错: {e}")
        return False


def stop_ws_manager():
    """停止快手WebSocket管理器"""
    global _ws_manager
    if _ws_manager:
        _ws_manager.stop()
        _ws_manager = None
