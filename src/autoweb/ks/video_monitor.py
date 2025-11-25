"""
视频状态监控模块：在等待视频切换的间隙实时检测视频状态，并在异常时触发暂停
"""
import asyncio
import threading
import time
import logging
import platform
import psutil
from typing import Optional, Dict, Callable
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    WebDriverException,
    TimeoutException,
    StaleElementReferenceException
)

logger = logging.getLogger(__name__)


class VideoStatusMonitor:
    """
    视频状态监控器：在等待期间检测视频状态，异常时触发暂停
    """
    
    def __init__(
        self,
        browser_id: str,
        driver,
        check_interval: float = 1.0,
        paused_threshold: float = 3.0,
        progress_stall_threshold: float = 5.0
    ):
        """
        初始化视频状态监控器
        
        Args:
            browser_id: 浏览器名称
            driver: Selenium WebDriver 对象
            check_interval: 检测间隔（秒），默认1秒
            paused_threshold: 视频暂停阈值（秒），持续暂停超过此时间视为异常
            progress_stall_threshold: 播放进度停滞阈值（秒），进度未更新超过此时间视为卡住
        """
        self.browser_id = browser_id
        self.driver = driver
        self.check_interval = check_interval
        self.paused_threshold = paused_threshold
        self.progress_stall_threshold = progress_stall_threshold
        
        # 线程安全的状态标志
        self._pause_event = threading.Event()  # 暂停标志
        self._monitoring_event = threading.Event()  # 监控激活标志
        self._stop_event = threading.Event()  # 停止监控标志
        
        # 监控线程
        self._monitor_thread: Optional[threading.Thread] = None
        
        # 状态记录
        self._last_video_time: Optional[float] = None  # 上次检测到的视频播放时间
        self._last_video_time_timestamp: Optional[float] = None  # 上次检测时间戳
        self._paused_start_time: Optional[float] = None  # 视频暂停开始时间
        self._last_check_time: Optional[float] = None  # 上次检测时间
        
        # 异常信息
        self._last_exception: Optional[str] = None
        self._exception_count = 0
        self._normal_count = 0  # 连续无异常计数
        
        # 浏览器进程ID（用于检测浏览器是否存活）
        self._browser_pid: Optional[int] = None
        self._update_browser_pid()
    
    def _update_browser_pid(self):
        """更新浏览器进程ID"""
        try:
            if self.driver and hasattr(self.driver, 'service') and hasattr(self.driver.service, 'process'):
                if self.driver.service.process:
                    self._browser_pid = self.driver.service.process.pid
        except Exception as e:
            logger.debug(f"[{self.browser_id}][monitor] 获取浏览器进程ID失败: {e}")
    
    def start_monitoring(self):
        """启动监控（已废弃，使用全局监控线程，此方法保留以兼容旧代码）"""
        # 不再使用每个监控器独立的线程，改为使用全局监控线程
        # 这个方法保留是为了兼容性，实际功能由全局 start_monitoring 函数处理
        self._monitoring_event.set()
        logger.debug(f"[{self.browser_id}][monitor] 监控已激活（使用全局监控线程）")
    
    def stop_monitoring(self):
        """停止监控（停用该浏览器的监控）"""
        self._monitoring_event.clear()
        logger.info(f"[{self.browser_id}][monitor] 监控已停用")
    
    def is_paused(self) -> bool:
        """检查是否已触发暂停"""
        return self._pause_event.is_set()
    
    def clear_pause(self):
        """清除暂停标志"""
        self._pause_event.clear()
        self._last_exception = None
        self._exception_count = 0
        logger.info(f"[{self.browser_id}][monitor] 暂停标志已清除")
    
    def wait_for_resume(self, timeout: Optional[float] = None) -> bool:
        """
        等待暂停标志被清除（恢复）
        
        Args:
            timeout: 超时时间（秒），None表示无限等待
        
        Returns:
            是否已恢复（True=已恢复，False=超时）
        """
        if not self.is_paused():
            return True
        
        logger.info(f"[{self.browser_id}][monitor] 等待恢复（超时: {timeout}秒）...")
        if timeout is None:
            # 无限等待，直到恢复
            self._pause_event.wait()
            return True
        else:
            # 等待指定时间，如果超时返回False，如果恢复返回True
            # _pause_event.wait(timeout) 返回True表示事件被设置（仍在暂停），False表示超时
            # 我们需要等待事件被清除（恢复），所以需要轮询检查
            start_time = time.time()
            while time.time() - start_time < timeout:
                if not self.is_paused():
                    return True
                time.sleep(0.1)  # 每0.1秒检查一次
            # 超时
            return False
    
    def _check_video_element_status(self) -> Dict[str, any]:
        """
        检查视频元素状态
        
        Returns:
            包含视频状态的字典: {
                'exists': bool,  # 视频元素是否存在
                'paused': bool,  # 是否暂停
                'ended': bool,   # 是否播放完成
                'current_time': float,  # 当前播放时间
                'duration': float,  # 视频总时长
                'ready_state': int  # 视频就绪状态
            }
        """
        try:
            # 使用JavaScript检查视频元素状态
            status = self.driver.execute_script("""
                try {
                    const video = document.querySelector('video');
                    if (!video) {
                        return {
                            exists: false,
                            paused: null,
                            ended: null,
                            current_time: null,
                            duration: null,
                            ready_state: null
                        };
                    }
                    return {
                        exists: true,
                        paused: video.paused,
                        ended: video.ended,
                        current_time: video.currentTime,
                        duration: video.duration,
                        ready_state: video.readyState
                    };
                } catch (e) {
                    return {
                        exists: false,
                        error: e.toString()
                    };
                }
            """)
            return status
        except Exception as e:
            logger.debug(f"[{self.browser_id}][monitor] 检查视频元素状态失败: {e}")
            return {'exists': False, 'error': str(e)}
    
    def _check_page_status(self) -> Dict[str, any]:
        """
        检查页面状态
        
        Returns:
            包含页面状态的字典: {
                'url': str,  # 当前URL
                'is_video_page': bool,  # 是否在视频页面
                'has_error': bool,  # 是否有错误页面
                'title': str  # 页面标题
            }
        """
        try:
            current_url = self.driver.current_url
            page_title = self.driver.title
            
            # 检查是否在视频页面
            is_video_page = 'short-video' in current_url
            
            # 检查是否有异常页面（验证码、封号提示等）
            has_error = False
            error_indicators = [
                'verify', 'captcha', '验证', '封禁', 'ban', 'block',
                'error', '异常', '403', '404', '500'
            ]
            url_lower = current_url.lower()
            title_lower = page_title.lower()
            for indicator in error_indicators:
                if indicator in url_lower or indicator in title_lower:
                    has_error = True
                    break
            
            return {
                'url': current_url,
                'is_video_page': is_video_page,
                'has_error': has_error,
                'title': page_title
            }
        except Exception as e:
            logger.debug(f"[{self.browser_id}][monitor] 检查页面状态失败: {e}")
            return {
                'url': None,
                'is_video_page': False,
                'has_error': True,
                'error': str(e)
            }
    
    def _check_browser_status(self) -> Dict[str, any]:
        """
        检查浏览器进程状态
        
        Returns:
            包含浏览器状态的字典: {
                'alive': bool,  # 浏览器进程是否存活
                'pid': int  # 进程ID
            }
        """
        try:
            # 如果无法获取进程ID，尝试更新
            if self._browser_pid is None:
                self._update_browser_pid()
            
            if self._browser_pid is None:
                # 无法获取进程ID，尝试通过driver检查
                try:
                    self.driver.current_url
                    return {'alive': True, 'pid': None, 'method': 'driver_check'}
                except Exception:
                    return {'alive': False, 'pid': None, 'error': '无法检查进程状态'}
            
            # 检查进程是否存活
            try:
                process = psutil.Process(self._browser_pid)
                is_alive = process.is_running()
                return {'alive': is_alive, 'pid': self._browser_pid}
            except psutil.NoSuchProcess:
                return {'alive': False, 'pid': self._browser_pid, 'error': '进程不存在'}
            except Exception as e:
                return {'alive': False, 'pid': self._browser_pid, 'error': str(e)}
        except Exception as e:
            logger.debug(f"[{self.browser_id}][monitor] 检查浏览器状态失败: {e}")
            # 回退到driver检查
            try:
                self.driver.current_url
                return {'alive': True, 'pid': None, 'method': 'driver_fallback'}
            except Exception:
                return {'alive': False, 'pid': None, 'error': str(e)}
    
    def _detect_abnormalities(self) -> Optional[str]:
        """
        检测异常情况
        
        Returns:
            异常描述字符串，如果无异常返回None
        """
        try:
            # 1. 检查浏览器状态
            browser_status = self._check_browser_status()
            if not browser_status.get('alive', False):
                return f"浏览器进程异常: {browser_status.get('error', '进程不存在或已崩溃')}"
            
            # 2. 检查页面状态
            # page_status = self._check_page_status()
            # if page_status.get('has_error', False):
            #     return f"页面异常: URL={page_status.get('url', 'Unknown')}, Title={page_status.get('title', 'Unknown')}"
            
            # if not page_status.get('is_video_page', False):
            #     # 不在视频页面，但不一定是异常（可能是正常跳转，比如查看个人信息页面）
            #     # 这里只记录，不触发暂停，直接返回None表示无异常
            #     logger.debug(f"[{self.browser_id}][monitor] 当前不在视频页面: {page_status.get('url', 'Unknown')}，跳过视频状态检测")
            #     return None
            
            # 3. 检查视频元素状态（仅在视频页面检测）
            video_status = self._check_video_element_status()
            if not video_status.get('exists', False):
                # 视频元素不存在，可能是页面加载中、已切换或不在视频页面
                # 这种情况不视为异常，返回None
                logger.debug(f"[{self.browser_id}][monitor] 视频元素不存在，可能页面加载中或已切换")
                return None
            
            # 检查视频是否意外暂停
            if video_status.get('paused', False):
                current_time = time.time()
                if self._paused_start_time is None:
                    self._paused_start_time = current_time
                else:
                    paused_duration = current_time - self._paused_start_time
                    if paused_duration > self.paused_threshold:
                        return f"视频持续暂停超过阈值: {paused_duration:.1f}秒 > {self.paused_threshold}秒"
            else:
                # 视频在播放，重置暂停开始时间
                self._paused_start_time = None
                
                # 检查播放进度是否停滞
                current_video_time = video_status.get('current_time')
                if current_video_time is not None:
                    current_check_time = time.time()
                    if self._last_video_time is not None and self._last_video_time == current_video_time:
                        # 播放时间未更新
                        if self._last_video_time_timestamp is not None:
                            stall_duration = current_check_time - self._last_video_time_timestamp
                            if stall_duration > self.progress_stall_threshold:
                                return f"视频播放进度停滞: {stall_duration:.1f}秒 > {self.progress_stall_threshold}秒"
                    else:
                        # 播放时间有更新，重置记录
                        self._last_video_time = current_video_time
                        self._last_video_time_timestamp = current_check_time
            
            return None
            
        except WebDriverException as e:
            # WebDriver异常（如session失效）
            return f"WebDriver异常: {str(e)}"
        except Exception as e:
            logger.error(f"[{self.browser_id}][monitor] 检测异常时发生错误: {e}")
            return f"检测过程异常: {str(e)}"
    
    
    def get_status(self) -> Dict[str, any]:
        """获取当前监控状态"""
        return {
            'is_paused': self.is_paused(),
            'is_monitoring': self._monitoring_event.is_set(),
            'last_exception': self._last_exception,
            'exception_count': self._exception_count,
            'browser_pid': self._browser_pid
        }


# 全局监控器字典：browser_id -> VideoStatusMonitor
_global_monitors: Dict[str, VideoStatusMonitor] = {}
_monitors_lock = threading.Lock()

# 全局监控线程（所有浏览器共享一个监控线程）
_global_monitor_thread: Optional[threading.Thread] = None
_global_monitor_stop_event = threading.Event()
_global_monitor_active = threading.Event()

# 监控器引用计数：browser_id -> 引用计数（用于跟踪有多少浏览器正在使用该监控器）
_monitor_ref_counts: Dict[str, int] = {}
_ref_counts_lock = threading.Lock()


def get_monitor(browser_id: str) -> Optional[VideoStatusMonitor]:
    """获取指定浏览器的监控器"""
    with _monitors_lock:
        return _global_monitors.get(browser_id)


def create_monitor(
    browser_name: str,
    browser_id: str,
    driver,
    check_interval: float = 1.0,
    paused_threshold: float = 3.0,
    progress_stall_threshold: float = 5.0
) -> VideoStatusMonitor:
    """
    创建并注册监控器（增加引用计数）
    
    Args:
        browser_name: 浏览器名称
        browser_id: 浏览器ID
        driver: Selenium WebDriver 对象
        check_interval: 检测间隔（秒）
        paused_threshold: 视频暂停阈值（秒）
        progress_stall_threshold: 播放进度停滞阈值（秒）
    
    Returns:
        VideoStatusMonitor 实例
    """
    with _monitors_lock:
        # 如果已存在，增加引用计数
        if browser_id in _global_monitors:
            with _ref_counts_lock:
                _monitor_ref_counts[browser_id] = _monitor_ref_counts.get(browser_id, 0) + 1
                logger.info(f"[{browser_id}][monitor] 监控器已存在，引用计数+1，当前引用计数: {_monitor_ref_counts[browser_id]}")
            return _global_monitors[browser_id]
        
        # 创建新监控器
        monitor = VideoStatusMonitor(
            browser_id=browser_id,
            driver=driver,
            check_interval=check_interval,
            paused_threshold=paused_threshold,
            progress_stall_threshold=progress_stall_threshold
        )
        _global_monitors[browser_id] = monitor
        with _ref_counts_lock:
            _monitor_ref_counts[browser_id] = 1
        logger.info(f"[{browser_id}][monitor] 监控器已创建，引用计数: 1")
        return monitor


def remove_monitor(browser_id: str):
    """移除监控器（只有当引用计数为0时才真正移除）"""
    with _ref_counts_lock:
        if browser_id in _monitor_ref_counts:
            _monitor_ref_counts[browser_id] -= 1
            ref_count = _monitor_ref_counts[browser_id]
            
            if ref_count <= 0:
                # 引用计数为0，真正移除监控器
                del _monitor_ref_counts[browser_id]
                with _monitors_lock:
                    if browser_id in _global_monitors:
                        monitor = _global_monitors[browser_id]
                        monitor.stop_monitoring()
                        del _global_monitors[browser_id]
                        logger.info(f"[{browser_id}][monitor] 监控器已移除（引用计数为0）")
                    else:
                        logger.debug(f"[{browser_id}][monitor] 监控器不存在，无需移除")
            else:
                logger.debug(f"[{browser_id}][monitor] 监控器引用计数减1，当前引用计数: {ref_count}，不移除监控器")
        else:
            # 如果没有引用计数记录，直接尝试移除（兼容旧代码）
            with _monitors_lock:
                if browser_id in _global_monitors:
                    monitor = _global_monitors[browser_id]
                    monitor.stop_monitoring()
                    del _global_monitors[browser_id]
                    logger.info(f"[{browser_id}][monitor] 监控器已移除（无引用计数记录，直接移除）")
                else:
                    logger.debug(f"[{browser_id}][monitor] 监控器不存在，无需移除")


def _global_monitor_worker():
    """全局监控工作线程：轮询所有浏览器的监控器"""
    logger.info("[global_monitor] 全局监控线程已启动")
    
    while not _global_monitor_stop_event.is_set():
        try:
            # 等待监控激活
            if not _global_monitor_active.wait(timeout=0.5):
                continue
            
            # 轮询所有监控器
            with _monitors_lock:
                monitors = list(_global_monitors.values())
            
            # 如果没有监控器了，停止全局监控线程
            if not monitors:
                logger.info("[global_monitor] 没有监控器了，停止全局监控线程")
                _global_monitor_active.clear()
                break
            
            for monitor in monitors:
                try:
                    # 只监控已激活的监控器
                    if monitor._monitoring_event.is_set():
                        abnormality = monitor._detect_abnormalities()
                        
                        if abnormality:
                            monitor._exception_count += 1
                            monitor._last_exception = abnormality
                            
                            # 触发暂停
                            if not monitor._pause_event.is_set():
                                monitor._pause_event.set()
                                logger.warning(
                                    f"[{monitor.browser_id}][monitor] ⚠ 检测到异常，触发暂停: {abnormality} "
                                    f"(异常计数: {monitor._exception_count})"
                                )
                        else:
                            # 无异常，如果之前有异常记录，连续3次无异常后自动清除暂停标志
                            if monitor._exception_count > 0:
                                if not hasattr(monitor, '_normal_count'):
                                    monitor._normal_count = 0
                                monitor._normal_count += 1
                                
                                # 连续3次检测无异常，自动清除暂停标志
                                if monitor._normal_count >= 3 and monitor._pause_event.is_set():
                                    monitor._pause_event.clear()
                                    logger.info(
                                        f"[{monitor.browser_id}][monitor] ✓ 连续{monitor._normal_count}次检测无异常，自动清除暂停标志"
                                    )
                                    monitor._exception_count = 0
                                    monitor._normal_count = 0
                                    monitor._last_exception = None
                            else:
                                if hasattr(monitor, '_normal_count'):
                                    monitor._normal_count = 0
                except Exception as e:
                    logger.error(f"[{monitor.browser_id}][monitor] 监控异常: {e}")
            
            # 等待检测间隔（使用第一个监控器的间隔，或默认1秒）
            check_interval = 1.0
            if monitors:
                check_interval = monitors[0].check_interval
            time.sleep(check_interval)
            
        except Exception as e:
            logger.error(f"[global_monitor] 全局监控线程异常: {e}")
            time.sleep(1.0)
    
    logger.info("[global_monitor] 全局监控线程已退出")


def start_monitoring(browser_id: str):
    """启动指定浏览器的监控（激活监控，如果全局监控线程未启动则启动它）"""
    global _global_monitor_thread
    
    monitor = get_monitor(browser_id)
    if not monitor:
        logger.warning(f"[{browser_id}][monitor] 监控器不存在，无法启动")
        return
    
    # 激活该浏览器的监控
    monitor._monitoring_event.set()
    
    # 如果全局监控线程未启动，启动它
    if _global_monitor_thread is None or not _global_monitor_thread.is_alive():
        _global_monitor_stop_event.clear()
        _global_monitor_active.set()
        _global_monitor_thread = threading.Thread(
            target=_global_monitor_worker,
            daemon=True,
            name="GlobalVideoMonitor"
        )
        _global_monitor_thread.start()
        logger.info(f"[global_monitor] 全局监控线程已启动（为 {browser_id} 启动）")
    else:
        logger.debug(f"[{browser_id}][monitor] 监控已激活（使用全局监控线程）")


def stop_monitoring(browser_id: str):
    """停止指定浏览器的监控"""
    monitor = get_monitor(browser_id)
    if monitor:
        monitor.stop_monitoring()
    else:
        logger.warning(f"[{browser_id}][monitor] 监控器不存在，无法停止")


def is_paused(browser_id: str) -> bool:
    """检查指定浏览器是否已暂停"""
    monitor = get_monitor(browser_id)
    if monitor:
        return monitor.is_paused()
    return False


def clear_pause(browser_id: str):
    """清除指定浏览器的暂停标志"""
    monitor = get_monitor(browser_id)
    if monitor:
        monitor.clear_pause()
    else:
        logger.warning(f"[{browser_id}][monitor] 监控器不存在，无法清除暂停")


def wait_for_resume(browser_id: str, timeout: Optional[float] = None) -> bool:
    """等待指定浏览器恢复"""
    monitor = get_monitor(browser_id)
    if monitor:
        return monitor.wait_for_resume(timeout)
    return True  # 如果监控器不存在，认为已恢复

