#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音分享爬虫具体实现类
继承抽象基类并实现所有抽象方法
"""

import sys
import json
import time
import random
import concurrent.futures
import asyncio
import threading
from ..tools.config import KuSettings
from ..tools.verify import LicenseException, LicenseManager
from ..tools.ws import WSClient
from ..tools import log
from .base_crawler import BaseDyShareCrawler
from .utils import DyShareUtils


class ConcreteDyShareCrawler(BaseDyShareCrawler):
    """抖音分享爬虫具体实现类"""

    def __init__(self):
        """初始化具体爬虫实现"""
        super().__init__()
        self.config = KuSettings()
        self.utils = DyShareUtils()
        self.license_manager = LicenseManager()
        self.ws_client = None
        self.ws_thread = None  # WebSocket 运行线程
        self.ws_loop = None  # WebSocket 事件循环
        # 心跳相关属性
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 3  # 3秒心跳间隔
        self.max_reconnect_attempts = 3  # 最大重连次数
        self.reconnect_delay = 3  # 重连延迟（秒）

    def initialize_config(self) -> None:
        """初始化配置"""
        # 配置已在__init__中初始化
        pass

    def validate_license(self) -> bool:
        """验证卡密"""
        return self.license_manager.verify_license()

    def prepare_environment(self) -> None:
        """准备运行环境"""
        # 启动WebSocket客户端
        self._start_websocket_client()
        
        # 启动定期验证线程
        self.license_manager.start_periodic_check()
        
        # 开启防休眠
        self.utils.set_keep_awake(True)
        
        # 如果启用了调试模式，打印所有配置参数
        if self.config.DEBUG:
            self.utils.print_config_debug()

    def setup_database(self) -> None:
        """设置数据库"""
        # 判断使用列表模式还是数据库模式
        use_list_mode = self.config.URLS and len(self.config.URLS) > 0

        if use_list_mode:
            self._prepare_url_list_mode()
        else:
            print("使用数据库模式")
            # 添加0.2秒延迟
            time.sleep(0.2)
            self.utils.init_database()

        if not self.config.BIT_BROWSER_IDS:
            raise Exception("请在代码中的 BIT_BROWSER_IDS 列表中配置浏览器ID")

    def output_version_info(self) -> None:
        """输出版本信息"""
        # 输出版本信息
        version_info = {"code": 0, "data": {"type": "version", "version": f"pc.{self.config.VERSION}"}}
        output = json.dumps(version_info, ensure_ascii=False)
        print(output)
        
        # 发送WebSocket消息
        self._send_ws_message({
            "type": "system_status",
            "status": "started",
            "message": f"抖音分享爬虫已启动，版本: {self.config.VERSION}"
        })
        
        # 添加0.2秒延迟
        time.sleep(0.2)

    def process_urls_with_thread_pool(self) -> None:
        """使用线程池处理URL"""
        MAX_WORKERS_USED = len(self.config.BIT_BROWSER_IDS)
        WAIT_TIME_USED = self.config.WAIT_TIME
        LIKE_PROBABILITY_USED = self.config.LIKE_PROBABILITY
        VISIT_PROFILE_PROBABILITY_USED = self.config.VISIT_ENABLE
        PROFILE_FOLLOW_PROBABILITY_USED = self.config.PROFILE_FOLLOW_PROBABILITY
        MIN_FOLLOWS_PER_VIDEO_USED = self.config.MIN_FOLLOWS_PER_VIDEO
        MAX_FOLLOWS_PER_VIDEO_USED = self.config.MAX_FOLLOWS_PER_VIDEO
        MIN_LIKES_PER_VIDEO_USED = self.config.COMMENT_LIKE_COUNT_MIN
        MAX_LIKES_PER_VIDEO_USED = self.config.COMMENT_LIKE_COUNT_MAX

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_USED) as executor:
                futures = []
                for i in range(MAX_WORKERS_USED):
                    browser_id = self.config.BIT_BROWSER_IDS[i % len(self.config.BIT_BROWSER_IDS)]

                    # 为每个浏览器实例单独输出start事件
                    self._output_browser_start_event(browser_id)
                    # 添加0.2秒延迟
                    time.sleep(0.2)

                    future = executor.submit(
                        self.utils.continuous_processing_loop,
                        browser_id,
                        WAIT_TIME_USED,
                        LIKE_PROBABILITY_USED,
                        VISIT_PROFILE_PROBABILITY_USED,
                        PROFILE_FOLLOW_PROBABILITY_USED,
                        MIN_FOLLOWS_PER_VIDEO_USED,
                        MAX_FOLLOWS_PER_VIDEO_USED,
                        MIN_LIKES_PER_VIDEO_USED,
                        MAX_LIKES_PER_VIDEO_USED,
                        i + 1,
                    )
                    futures.append(future)

                    if i < MAX_WORKERS_USED - 1:
                        time.sleep(2.5)

                while futures:
                    try:
                        done, not_done = concurrent.futures.wait(futures, timeout=1)
                        for future in done:
                            try:
                                future.result()
                            except LicenseException:
                                print("卡密验证失败，程序终止")
                                raise
                            except Exception as e:
                                print(f"线程执行出错: {e}")
                        futures = list(not_done)
                        
                        # 检查是否收到停止信号
                        if self._check_stop_signal():
                            print("=" * 50)
                            print("主循环检测到停止信号，正在尝试关闭所有线程...")
                            print("=" * 50)
                            # 确保停止标志已设置
                            self.utils._stop_flag.set()
                            print(f"✓ 已确认设置 _stop_flag")
                            # 取消所有未完成的任务
                            for future in futures:
                                future.cancel()
                            print(f"✓ 已取消 {len(futures)} 个任务")
                            break
                    except KeyboardInterrupt:
                        print("收到停止信号，正在关闭所有线程...")
                        self.utils._stop_flag.set()
                        for future in futures:
                            future.cancel()
                        import sys
                        sys.exit(0)
        except LicenseException:
            print("卡密验证失败，程序终止")
            raise

    def cleanup_resources(self) -> None:
        """清理资源"""
        # 关闭WebSocket客户端
        self._stop_websocket_client()
        
        # 关闭防休眠
        self.utils.set_keep_awake(False)
        # 停止卡密检查
        self.license_manager.stop_periodic_check()

    def handle_add_command(self) -> None:
        """处理添加链接命令"""
        self.utils.add_links_cli()

    def handle_look_command(self) -> None:
        """处理查看链接命令"""
        self.utils.view_links_in_db()

    def handle_clear_command(self) -> None:
        """处理清除数据库命令"""
        if len(sys.argv) > 2:
            self.utils.clear_database(status=sys.argv[2])
        else:
            self.utils.clear_database()

    def show_help(self) -> None:
        """显示帮助信息"""
        print("使用方法: python DY_ku.py [run|add|look|clear]")

    def _prepare_url_list_mode(self) -> None:
        """准备URL列表模式"""
        cleaned_urls = []
        invalid_count = 0
        for url in self.config.URLS:
            cleaned_url = self.utils.extract_douyin_link(url)
            if cleaned_url:
                cleaned_urls.append(cleaned_url)
            else:
                invalid_count += 1
                if self.config.DEBUG:
                    print(f"无效的抖音链接，已跳过: {url}")

        self.config.URLS = cleaned_urls
        if invalid_count > 0:
            if self.config.DEBUG:
                print(f"URLS列表中有 {invalid_count} 个无效链接已跳过")

        if self.config.DEBUG:
            print(f"使用列表模式，共 {len(self.config.URLS)} 个有效URL")
        self.utils.reset_url_list_index()

    def _output_browser_start_event(self, browser_id: str) -> None:
        """输出单个浏览器的start事件"""
        result = {"code": 0, "data": {"type": "start", "id": browser_id}}
        output = json.dumps(result, ensure_ascii=False)
        print(output)
        
        # 发送WebSocket消息
        self._send_ws_message({
            "type": "browser_status",
            "browser": browser_id,
            "status": "started",
            "message": f"浏览器 {browser_id} 已启动"
        })

    def _start_websocket_client(self):
        """启动WebSocket客户端（在单独的线程中运行）"""
        # 获取设备码
        device_code = getattr(self.config, 'DEVICE_CODE', '111222')
        
        # 构建 WebSocket URL
        ws_url = self.config.WEBSOCKET_URL
        if not ws_url or ws_url == "ws://localhost:8000":
            # 如果没有配置或使用默认值，使用 DEVICE_CODE 构建 URL
            ws_url = f"ws://192.168.2.9:11221/ws/?id={device_code}"
        else:
            # 确保 URL 中的 id 参数使用当前的 DEVICE_CODE
            if '?id=' in ws_url:
                base_url = ws_url.split('?id=')[0]
                ws_url = f"{base_url}?id={device_code}"
            elif '?id=' not in ws_url:
                separator = '&' if '?' in ws_url else '?'
                ws_url = f"{ws_url}{separator}id={device_code}"
        
        print(f"[WebSocket] 准备连接到: {ws_url}")
        
        if not ws_url:
            print("❌ WebSocket URL 未配置，程序无法启动")
            raise Exception("WebSocket URL 未配置，请检查配置文件")
        
        # 创建 WebSocket 客户端
        self.ws_client = WSClient(ws_url)
        
        # 注册停止信号处理器
        self.ws_client.register_stop_signal_handler(self._on_stop_signal_received)
        
        # 注册其他指令处理器（可扩展）
        self.ws_client.register_command_handler("LoginRes", self._handle_login_res_command)
        
        # 在单独的线程中运行 WebSocket 客户端
        def run_ws_in_thread():
            """在独立线程中运行事件循环"""
            # 创建新的事件循环（确保独立运行）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if self.ws_client:
                    # 在新的事件循环中运行
                    loop.run_until_complete(self.ws_client.run())
            except Exception as e:
                print(f"[WebSocket线程] 运行出错: {e}")
            finally:
                loop.close()
        
        # 启动后台线程（设置为非 daemon，确保能正常运行）
        self.ws_thread = threading.Thread(target=run_ws_in_thread, daemon=False, name="WebSocketThread")
        self.ws_thread.start()
        
        # 等待 WebSocket 连接建立（给一点时间）
        time.sleep(2)
        
        print(f"✓ WebSocket 客户端已启动，连接到: {ws_url}")
        self.last_heartbeat = time.time()

    def _stop_websocket_client(self):
        """停止WebSocket客户端"""
        try:
            if self.ws_client:
                # 设置停止标志
                self.ws_client.stop_requested = True
                
                # 如果事件循环在运行，关闭连接
                if self.ws_loop is not None and self.ws_loop.is_running():
                    # 在事件循环中关闭连接
                    asyncio.run_coroutine_threadsafe(self.ws_client.close(), self.ws_loop)
            
            # 等待 WebSocket 线程结束（最多等待2秒）
            if self.ws_thread is not None and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=2.0)
            
            print("WebSocket客户端已关闭")
        except Exception as e:
            print(f"关闭WebSocket客户端时出错: {e}")

    def _send_ws_message(self, message_dict):
        """发送WebSocket消息（线程安全）"""
        if self.ws_client and self.ws_loop is not None and self.ws_loop.is_running():
            try:
                # 在 WebSocket 线程的事件循环中发送消息
                asyncio.run_coroutine_threadsafe(
                    self.ws_client.send(message_dict),
                    self.ws_loop
                )
            except Exception as e:
                print(f"发送WebSocket消息失败: {e}")

    def _check_stop_signal(self):
        """检查是否收到停止信号"""
        # 检查WebSocket客户端是否收到了停止信号
        if self.ws_client and self.ws_client.stop_requested:
            print("_check_stop_signal() 检测到停止信号")
            return True
        # 也检查 _stop_flag（双重检查）
        if self.utils._stop_flag.is_set():
            print("_check_stop_signal() 检测到 _stop_flag 已设置")
            return True
        return False
    
    def _on_stop_signal_received(self):
        """当收到停止信号时的回调函数"""
        print("=" * 50)
        print("收到WebSocket停止信号，设置停止标志...")
        print("=" * 50)
        # 设置停止标志，所有浏览器线程会检测到这个标志并退出
        self.utils._stop_flag.set()
        print(f"✓ 已设置 _stop_flag，当前状态: {self.utils._stop_flag.is_set()}")
        print(f"✓ WebSocket stop_requested 状态: {self.ws_client.stop_requested if self.ws_client else 'N/A'}")
    
    def _handle_login_res_command(self, data: dict):
        """处理 LoginRes 指令"""
        # 这里可以处理其他 LoginRes 指令（非 stop）
        log.debug(f"收到 LoginRes 指令: {data}")
        # 可以根据 data 中的内容执行不同的操作

    def _reconnect_websocket(self):
        """重新连接WebSocket"""
        for attempt in range(self.max_reconnect_attempts):
            try:
                print(f"尝试重新连接WebSocket (第 {attempt + 1}/{self.max_reconnect_attempts} 次)")
                
                # 关闭现有连接
                self._stop_websocket_client()
                
                # 等待一段时间再重连
                time.sleep(self.reconnect_delay)
                
                # 重新启动WebSocket客户端
                self._start_websocket_client()
                
                # 检查连接是否成功
                if self.ws_client:
                    print("WebSocket重新连接成功")
                    return True
                    
            except Exception as e:
                print(f"重新连接失败 (尝试 {attempt + 1}/{self.max_reconnect_attempts}): {e}")
                
        print("达到最大重连次数，无法重新连接")
        return False