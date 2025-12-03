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
from ..tools.common import DataReporter
from .base_crawler import BaseDyShareCrawler
from .utils import DyShareUtils


class ConcreteDyShareCrawler(BaseDyShareCrawler):
    """抖音自动化具体实现类"""

    def __init__(self):
        """初始化具体实现"""
        super().__init__()
        from ..tools.config import config
        self.config = config
        self.utils = DyShareUtils()
        self.license_manager = LicenseManager()
        self.ws_client = None
        self.ws_thread = None  # WebSocket 运行线程
        self.ws_loop = None  # WebSocket 事件循环
        # 心跳相关属性（保留用于重连机制）
        self.max_reconnect_attempts = 3  # 最大重连次数
        self.reconnect_delay = 3  # 重连延迟（秒）
        # DataReporter 实例字典，每个浏览器ID对应一个实例
        self.data_reporters = {}

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
            log.info("使用数据库模式")
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

        # 发送包含设备码和版本号的新WebSocket消息
        self._send_ws_message({
            "cmd": "LoginReq",
            "id": self.config.DEVICE_CODE,
            "mode": "pc",
            "version": self.config.VERSION
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

                    # 为每个浏览器实例创建 DataReporter
                    self._output_browser_start_event(browser_id)
                    # 获取该浏览器的 DataReporter 实例
                    reporter = self.data_reporters.get(browser_id)
                    
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
                        reporter,  # 传入 DataReporter 实例
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
                                log.error("卡密验证失败，程序终止")
                                raise
                            except Exception as e:
                                log.error(f"线程执行出错: {e}")
                        futures = list(not_done)

                        # 检查是否收到停止信号
                        if self._check_stop_signal():
                            log.info("=" * 50)
                            log.info("主循环检测到停止信号，正在尝试关闭所有线程...")
                            log.info("=" * 50)
                            # 确保停止标志已设置
                            self.utils._stop_flag.set()
                            log.info(f"✓ 已确认设置 _stop_flag")
                            # 取消所有未完成的任务
                            for future in futures:
                                future.cancel()
                            log.info(f"✓ 已取消 {len(futures)} 个任务")
                            break
                    except KeyboardInterrupt:
                        log.info("收到停止信号，正在关闭所有线程...")
                        self.utils._stop_flag.set()
                        for future in futures:
                            future.cancel()
                        import sys
                        sys.exit(0)
        except LicenseException:
            log.error("卡密验证失败，程序终止")
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
                    log.warning(f"无效的抖音链接，已跳过: {url}")

        self.config.URLS = cleaned_urls
        if invalid_count > 0:
            if self.config.DEBUG:
                log.warning(f"URLS列表中有 {invalid_count} 个无效链接已跳过")

        if self.config.DEBUG:
            log.info(f"使用列表模式，共 {len(self.config.URLS)} 个有效URL")
        self.utils.reset_url_list_index()

    def _output_browser_start_event(self, browser_id: str) -> None:
        """为浏览器创建 DataReporter 实例（已删除旧输出格式）"""
        # 为每个浏览器创建 DataReporter 实例
        reporter = DataReporter(
            device_code=self.config.DEVICE_CODE,
            browser_id=browser_id,
            send_ws_message_func=self._send_ws_message_for_reporter
        )
        self.data_reporters[browser_id] = reporter

    def _start_websocket_client(self):
        """启动WebSocket客户端（在单独的线程中运行）"""
        # 使用公共方法创建和启动WebSocket客户端
        from ..tools.ws import create_websocket_client, start_websocket_client_in_thread

        # 创建WebSocket客户端
        self.ws_client = create_websocket_client(self.config)
        
        # 设置外部发送函数，用于处理 TypeStopReq 指令时发送响应
        if self.ws_client:
            self.ws_client.set_external_send_func(self._send_ws_message)
            # 设置配置更新处理器
            self.ws_client.set_config_update_handler(self._handle_config_update)

        # 在独立线程中启动WebSocket客户端
        self.ws_thread = start_websocket_client_in_thread(
            self.ws_client,
            self._on_stop_signal_received
        )

        # 注册指令处理器
        self.ws_client.register_command_handler("LoginRes", self._handle_login_res_command)
        # 注册配置更新指令处理器
        self.ws_client.register_command_handler("ConfigUpdate", self._handle_config_update_command)

        # 等待 WebSocket 线程启动并创建事件循环
        # 从客户端获取正确的事件循环引用（WebSocket 线程中的事件循环）
        max_wait_time = 5  # 最多等待5秒
        wait_interval = 0.1  # 每次等待0.1秒
        waited_time = 0
        while waited_time < max_wait_time:
            if self.ws_client.event_loop is not None:
                self.ws_loop = self.ws_client.event_loop
                log.info("✓ 已获取 WebSocket 事件循环引用")
                break
            time.sleep(wait_interval)
            waited_time += wait_interval
        else:
            log.warning("⚠ 等待 WebSocket 事件循环超时，消息发送可能失败")
            self.ws_loop = None

    def _stop_websocket_client(self):
        """停止WebSocket客户端"""
        try:
            if self.ws_client:
                # 设置停止标志
                self.ws_client.stop_requested = True

                # 获取正确的事件循环（优先使用客户端的事件循环引用）
                event_loop = self.ws_client.event_loop
                if event_loop is None:
                    event_loop = self.ws_loop

                # 如果事件循环在运行，关闭连接
                if event_loop is not None and event_loop.is_running():
                    # 在事件循环中关闭连接
                    asyncio.run_coroutine_threadsafe(self.ws_client.close(), event_loop)

            # 等待 WebSocket 线程结束（最多等待2秒）
            if self.ws_thread is not None and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=2.0)

            log.info("WebSocket客户端已关闭")
        except Exception as e:
            log.error(f"关闭WebSocket客户端时出错: {e}")

    def _send_ws_message(self, message_dict):
        """发送WebSocket消息（线程安全）"""
        # 构造符合服务器要求的格式: {"cmd":"mock","id":"12","data":{原始消息}}
        # id 从配置中获取第一个浏览器ID
        browser_id = self.config.BIT_BROWSER_IDS[0] if self.config.BIT_BROWSER_IDS else "unknown"

        wrapped_message = {
            "cmd": "mock",
            "id": browser_id,
            "data": message_dict
        }

        # 打印将要发送到服务器的消息
        log.info(f"发送到服务器的消息: {json.dumps(wrapped_message, ensure_ascii=False, indent=2)}")
        
        # 检查WebSocket客户端是否存在
        if not self.ws_client:
            log.warning("WebSocket客户端未准备好，无法发送消息（ws_client 为 None）")
            return
        
        # 检查客户端状态
        if self.ws_client.stop_requested:
            log.warning("WebSocket客户端已请求停止，无法发送消息")
            return
        
        if not self.ws_client._running:
            log.warning("WebSocket客户端未运行，无法发送消息")
            return
        
        # 检查WebSocket连接状态
        if not (hasattr(self.ws_client, 'ws') and self.ws_client.ws):
            log.warning("WebSocket连接对象不存在，无法发送消息")
            return
        
        # 获取正确的事件循环（优先使用客户端的事件循环引用）
        event_loop = self.ws_client.event_loop
        if event_loop is None:
            # 如果客户端的事件循环为None，尝试使用保存的引用
            event_loop = self.ws_loop
        
        if event_loop is None:
            log.warning("WebSocket事件循环未准备好，无法发送消息")
            return
        
        if not event_loop.is_running():
            log.warning(f"WebSocket事件循环未运行，无法发送消息")
            return
        
        # 使用正确的事件循环发送消息
        try:
            # 直接将消息放入发送队列，而不是等待future完成
            # 这样可以避免阻塞和超时问题
            asyncio.run_coroutine_threadsafe(
                self.ws_client.send_queue.put(json.dumps(wrapped_message, ensure_ascii=False)),
                event_loop
            )
            log.info("✓ 消息已放入发送队列")
        except Exception as e:
            log.error(f"发送WebSocket消息失败: {e}", exc_info=True)
    
    def _send_ws_message_for_reporter(self, message_dict):
        """
        供 DataReporter 调用的 WebSocket 消息发送方法
        使用与 LoginReq 完全相同的发送逻辑（直接调用 _send_ws_message）
        """
        # 直接使用 _send_ws_message 方法，确保发送逻辑完全一致
        self._send_ws_message(message_dict)

    def _check_stop_signal(self):
        """检查是否收到停止信号"""

        # 检查WebSocket客户端是否收到了停止信号
        if self.ws_client and self.ws_client.stop_requested:
            log.info("_check_stop_signal() 检测到停止信号")
            return True
        # 也检查 _stop_flag（双重检查）
        if self.utils._stop_flag.is_set():
            log.info("_check_stop_signal() 检测到 _stop_flag 已设置")
            return True
        return False

    def _on_stop_signal_received(self):
        """当收到停止信号时的回调函数"""

        log.info("=" * 50)
        log.info("收到WebSocket停止信号，设置停止标志...")
        log.info("=" * 50)
        # 设置停止标志，所有浏览器线程会检测到这个标志并退出
        self.utils._stop_flag.set()
        log.info(f"✓ 已设置 _stop_flag，当前状态: {self.utils._stop_flag.is_set()}")
        log.info(f"✓ WebSocket stop_requested 状态: {self.ws_client.stop_requested if self.ws_client else 'N/A'}")

    def _handle_login_res_command(self, data: dict):
        """处理 LoginRes 指令"""
        # 这里可以处理其他 LoginRes 指令（非 stop）
        log.debug(f"收到 LoginRes 指令: {data}")
        # 可以根据 data 中的内容执行不同的操作

    def _handle_config_update_command(self, data: dict):
        """处理 ConfigUpdate 指令"""
        # 从指令中提取配置数据
        config_data = data.get("data", {})
        # 调用配置更新处理方法
        self._handle_config_update(config_data)

    def _handle_config_update(self, config_data: dict):
        """处理配置更新"""
        from ..tools import log
        try:
            log.info(f"收到配置更新: {config_data}")
            # 更新全局配置对象
            from ..tools.config import config
            config.update_from_dict(config_data)
            log.info("配置已更新")
            # 打印更新后的配置摘要
            config.print_config_summary()
        except Exception as e:
            log.error(f"配置更新失败: {e}")

    def _reconnect_websocket(self):
        """重新连接WebSocket"""

        for attempt in range(self.max_reconnect_attempts):
            try:
                log.info(f"尝试重新连接WebSocket (第 {attempt + 1}/{self.max_reconnect_attempts} 次)")

                # 关闭现有连接
                self._stop_websocket_client()

                # 等待一段时间再重连
                time.sleep(self.reconnect_delay)

                # 重新启动WebSocket客户端
                self._start_websocket_client()

                # 检查连接是否成功
                if self.ws_client:
                    log.info("WebSocket重新连接成功")
                    return True

            except Exception as e:
                log.error(f"重新连接失败 (尝试 {attempt + 1}/{self.max_reconnect_attempts}): {e}")

        log.error("达到最大重连次数，无法重新连接")
        return False