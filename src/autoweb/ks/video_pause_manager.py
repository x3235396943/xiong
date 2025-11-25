"""
视频暂停管理模块：提供统一的“暂停/恢复”控制入口，
并通过后台线程轮询监控列表中的浏览器状态。

外部代码应只通过此模块使用暂停能力，而不直接操作 video_monitor。
"""

import threading
import time
from typing import Dict, Optional, List
from selenium.webdriver.common.by import By
from ..tools import log as logger
from .video_monitor import (
    get_monitor,
    is_paused as _vm_is_paused,
    clear_pause as _vm_clear_pause,
    wait_for_resume as _vm_wait_for_resume,
)
from selenium.common.exceptions import NoSuchElementException


class VideoPauseManager:
    """
    视频暂停管理器：
    - 维护一个需要监控暂停状态的浏览器列表（以浏览器 ID 作为键）
    - 暴露统一的暂停/恢复/查询接口
    - 通过后台线程周期性检查并输出状态日志（可扩展为更多逻辑）
    """

    def __init__(self, check_interval: float = 1.0):
        # key: browser_id
        self._browsers: Dict[str, dict] = {}
        # 需要播放视频的浏览器标记（key: browser_id, value: bool）
        self._need_play: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._play_thread: Optional[threading.Thread] = None
        self._check_interval = check_interval # 检查间隔时间

    # ----------------- 管理浏览器列表 -----------------
    def add_browser(self, browser_id: str):
        """将浏览器加入暂停管理列表（browser_id 建议使用浏览器 ID）"""
        if not browser_id:
            logger.warning("[PauseManager] add_browser 调用缺少 browser_id")
            return
        with self._lock:
            # 确保同一个 ID 不会同时存在于播放列表
            if browser_id in self._need_play:
                del self._need_play[browser_id]
            if browser_id in self._browsers:
                return
            self._browsers[browser_id] = {"id": browser_id}
            logger.info(f"[PauseManager] 已加入浏览器到暂停列表: {browser_id}")
            self._ensure_thread_started()

    def remove_browser(self, browser_id: str):
        """将浏览器从暂停管理列表中移除（通过浏览器 ID）"""
        with self._lock:
            if browser_id in self._browsers:
                del self._browsers[browser_id]
                logger.info(f"[PauseManager] 已从暂停列表移除浏览器: {browser_id}")

    def list_browsers(self) -> List[str]:
        """返回当前管理的浏览器 ID 列表"""
        with self._lock:
            return list(self._browsers.keys())

    # ----------------- 暂停控制接口 -----------------
    def pause(self, browser_id: str, reason: str = "") -> bool:
        """
        对指定浏览器触发暂停标志（供外部主动调用）。
        实现方式：利用监控器的暂停事件。
        """
        monitor = get_monitor(browser_id)
        if not monitor:
            logger.warning(f"[PauseManager] 暂停失败，监控器不存在: {browser_id}")
            return False
        if not monitor._pause_event.is_set():
            monitor._pause_event.set()
            if reason:
                logger.warning(f"[PauseManager] 已为 {browser_id} 触发暂停 | 原因: {reason}")
            else:
                logger.warning(f"[PauseManager] 已为 {browser_id} 触发暂停")
        return True

    def resume(self, browser_id: str) -> bool:
        """清除指定浏览器的暂停标志"""
        monitor = get_monitor(browser_id)
        if not monitor:
            logger.warning(f"[PauseManager] 恢复失败，监控器不存在: {browser_id}")
            return False
        _vm_clear_pause(browser_id)
        logger.info(f"[PauseManager] 已清除 {browser_id} 的暂停标志")
        return True

    def pause_all(self, reason: str = ""):
        """对当前管理列表中的所有浏览器触发暂停"""
        for name in self.list_browsers():
            self.pause(name, reason=reason)

    def resume_all(self):
        """恢复当前管理列表中的所有浏览器"""
        for name in self.list_browsers():
            self.resume(name)

    # ----------------- 查询辅助 -----------------
    def is_paused(self, browser_id: str) -> bool:
        """查询指定浏览器是否处于暂停状态"""
        if self._browsers.get(browser_id, {}):
            return True
        else:
            return False
    
    def is_need_play(self, browser_id: str) -> bool:
        """查询指定浏览器是否处于播放视频状态"""
        return self._need_play.get(browser_id, False)

    def wait_for_resume(self, browser_id: str, timeout: Optional[float] = None) -> bool:
        """等待指定浏览器从暂停状态恢复"""
        return _vm_wait_for_resume(browser_id, timeout=timeout)

    

    # ----------------- 播放控制接口 -----------------
    def mark_need_play(self, browser_id: str):
        """标记指定浏览器需要播放视频"""
        if not browser_id:
            logger.warning("[PauseManager] mark_need_play 调用缺少 browser_id")
            return
        with self._lock:
            # 需要播放时，确保不在暂停列表
            if browser_id in self._browsers:
                del self._browsers[browser_id]
            if browser_id in self._need_play:
                return
            self._need_play[browser_id] = True
            logger.debug(f"[PauseManager] 已标记 {browser_id} 需要播放视频")
            self._ensure_thread_started()

    def clear_need_play(self, browser_id: str):
        """清除指定浏览器的播放标记"""
        if not browser_id:
            return
        with self._lock:
            if browser_id in self._need_play:
                del self._need_play[browser_id]
                logger.debug(f"[PauseManager] 已清除 {browser_id} 的播放标记")

    # ----------------- 后台线程 -----------------
    def _ensure_thread_started(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker,
                daemon=True,
                name="VideoPauseManagerThread",
            )
            self._thread.start()
            logger.info("[PauseManager] 后台线程已启动")
        
        # 同时启动视频播放检测线程
        if self._play_thread is None or not self._play_thread.is_alive():
            self._play_thread = threading.Thread(
                target=self._play_worker,
                daemon=True,
                name="VideoPlayMonitorThread",
            )
            self._play_thread.start()
            logger.info("[PauseManager] 视频播放检测线程已启动")

    def _worker(self):
        """后台线程：周期性检查并记录各浏览器的暂停/监控状态"""
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    ids = list(self._browsers.keys())
                for browser_id in ids:
                    monitor = get_monitor(browser_id)
                    if not monitor:
                        # 没有监控器，跳过（也可以选择自动移除）
                        time.sleep(0.5)
                        continue
                    status = monitor.get_status()
                    try:
                        if 'short-video' not in monitor.driver.current_url:
                            continue
                    except Exception as e:
                        logger.debug(f"[PauseManager] {browser_id} | 浏览器变动，如果浏览器关闭，请检查浏览器进程")
                        continue
                    
                    try:
                        play_icon = monitor.driver.find_element(By.XPATH, "//span[@class='play-icon']")
                        div_class = play_icon.find_element(By.XPATH, ".//div").get_attribute('class')
                        if div_class == "pause-icon":
                            logger.debug(f"[PauseManager] {browser_id} | 视频正在播放 | div class: {div_class}")
                            try:
                                logger.debug(f"[PauseManager] {browser_id} | 正在查找视频交互区域元素...")
                                video_interactive_area = monitor.driver.find_element(By.CLASS_NAME, 'video-interactive-area')
                                if video_interactive_area:
                                    logger.debug(f"[PauseManager] {browser_id} | 找到视频交互区域，执行点击操作")
                                    video_interactive_area.click()
                                    logger.info(f"[PauseManager] {browser_id} | 暂停视频操作成功")
                                    continue
                            except NoSuchElementException:
                                logger.debug(f"[PauseManager] {browser_id} | 未找到视频交互区域元素")
                                time.sleep(self._check_interval)
                        elif div_class == "play-icon":
                            time.sleep(self._check_interval)
                        else:
                            logger.debug(f"[PauseManager] {browser_id} | 无法检查播放状态: {div_class}")
                            time.sleep(self._check_interval)
                    except Exception as e:
                        logger.debug(f"[PauseManager] {browser_id} | 无法检查播放状态: {e}")
                    # 这里只做轻量级日志，可根据需要扩展逻辑
                    logger.debug(
                        f"[PauseManager] {browser_id} | paused={status['is_paused']} | "
                        f"monitoring={status['is_monitoring']} | "
                        f"exceptions={status['exception_count']}"
                    )
            except Exception as e:
                if get_monitor(browser_id):
                    logger.error(f"[PauseManager] {browser_id} | 后台线程异常: {e}")
                else:
                    logger.debug(f"[PauseManager] {browser_id} | 已从暂停列表移除，跳过检查")
                time.sleep(0.5)

    def _play_worker(self):
        """视频播放检测线程：周期性检查并执行视频播放操作"""
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    ids = list(self._need_play.keys())
                
                for browser_id in ids:
                    monitor = get_monitor(browser_id)
                    if not monitor:
                        # 没有监控器，跳过（也可以选择自动移除）
                        time.sleep(self._check_interval)
                        continue
                    
                    status = monitor.get_status()
                    if 'short-video' not in monitor.driver.current_url:
                        time.sleep(self._check_interval)
                        continue
                    else:
                        try:
                            play_icon = monitor.driver.find_element(By.XPATH, "//span[@class='play-icon']")
                            div_class = play_icon.find_element(By.XPATH, ".//div").get_attribute('class')
                            
                            if div_class == "pause-icon":
                                # 视频正在播放
                                logger.debug(f"[PlayMonitor] {browser_id} | 视频正在播放 | div class: {div_class}")

                            elif div_class == "play-icon":
                                # 视频未播放
                                logger.debug(f"[PlayMonitor] {browser_id} | 视频未播放")
                                try:
                                    logger.debug(f"[PlayMonitor] {browser_id} | 正在查找视频交互区域元素...")
                                    video_interactive_area = monitor.driver.find_element(By.CLASS_NAME, 'video-interactive-area')
                                    if video_interactive_area:
                                        logger.debug(f"[PlayMonitor] {browser_id} | 找到视频交互区域，执行点击播放操作")
                                        video_interactive_area.click()
                                        logger.info(f"[PlayMonitor] {browser_id} | 播放视频操作成功")
                                        # 清除播放标记
                                        with self._lock:
                                            if browser_id in self._need_play:
                                                del self._need_play[browser_id]
                                except NoSuchElementException:
                                    logger.debug(f"[PlayMonitor] {browser_id} | 未找到视频交互区域元素")
                                except Exception as e:
                                    logger.error(f"[PlayMonitor] {browser_id} | 播放视频操作失败: {e}")
                            else:
                                logger.debug(f"[PlayMonitor] {browser_id} | 无法检查播放状态: {div_class}")
                        except Exception as e:
                            logger.debug(f"[PlayMonitor] {browser_id} | 无法检查播放状态: {e}")
                    
                    # 这里只做轻量级日志，可根据需要扩展逻辑
                    logger.debug(
                        f"[PlayMonitor] {browser_id} | paused={status['is_paused']} | "
                        f"monitoring={status['is_monitoring']} | "
                        f"exceptions={status['exception_count']}"
                    )
                time.sleep(self._check_interval)
            except Exception as e:
                logger.error(f"[PlayMonitor] 视频播放检测线程异常: {e}")
                time.sleep(1.0)

    def stop(self):
        """停止后台线程（一般在程序退出时调用）"""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            logger.info("[PauseManager] 后台线程已停止")
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=3.0)
            logger.info("[PauseManager] 视频播放检测线程已停止")


# 全局单例实例及便捷函数
_global_pause_manager = VideoPauseManager()


def register_browser_for_pause(browser_id: str):
    """将浏览器 ID 注册到暂停管理器"""
    _global_pause_manager.add_browser(browser_id)


def unregister_browser_for_pause(browser_id: str):
    """将浏览器 ID 从暂停管理器中移除"""
    _global_pause_manager.remove_browser(browser_id)


def pause_browser(browser_id: str, reason: str = "") -> bool:
    """对指定浏览器 ID 触发暂停"""
    return _global_pause_manager.pause(browser_id, reason=reason)


def resume_browser(browser_id: str) -> bool:
    """恢复指定浏览器 ID 的暂停状态"""
    return _global_pause_manager.resume(browser_id)


def pause_all(reason: str = ""):
    _global_pause_manager.pause_all(reason=reason)


def resume_all():
    _global_pause_manager.resume_all()


def is_paused(browser_id: str) -> bool:
    """检查指定浏览器 ID 是否处于暂停状态"""
    return _global_pause_manager.is_paused(browser_id)

def is_need_play(browser_id: str) -> bool:
    """检查指定浏览器 ID 是否处于播放视频状态"""
    return _global_pause_manager.is_need_play(browser_id)


def wait_for_resume(browser_id: str, timeout: Optional[float] = None) -> bool:
    """等待指定浏览器 ID 从暂停状态恢复"""
    return _global_pause_manager.wait_for_resume(browser_id, timeout=timeout)


def mark_need_play(browser_id: str):
    """标记指定浏览器 ID 需要播放视频"""
    _global_pause_manager.mark_need_play(browser_id)


def clear_need_play(browser_id: str):
    """清除指定浏览器 ID 的播放标记"""
    _global_pause_manager.clear_need_play(browser_id)


def stop_pause_manager():
    _global_pause_manager.stop()


