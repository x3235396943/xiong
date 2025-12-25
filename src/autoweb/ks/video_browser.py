"""
视频浏览模块：为单个浏览器提供刷视频的多线程任务
"""
import time
import random
import os
import re
import queue
from enum import IntEnum
from typing import Tuple, Optional, Callable
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from .selenium_kuaisou import kuaishou_search, click_video, click_comment_like, click_comment_follow
from .selenium_common import scroll_element_down_js, safe_click, is_element_visible
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    NoSuchWindowException,
    StaleElementReferenceException
)
import logging
import threading
from collections import OrderedDict
from .video_monitor import (
    create_monitor, remove_monitor, start_monitoring, stop_monitoring,
)
from .video_pause_manager import (
    register_browser_for_pause,
    unregister_browser_for_pause,
    is_paused,
    wait_for_resume,
    resume_browser,
    mark_need_play,
    clear_need_play,
    is_need_play
)
from ..tools import log as logger
from ..tools import config


class ActionType(IntEnum):
    """操作类型枚举"""
    FOLLOW = 0  # 关注操作
    LIKE = 1    # 点赞操作


def _pause_video(driver):
    """
    暂停视频
    Args:
        driver: Selenium WebDriver 对象
    Returns:
        bool: 是否暂停成功
    """
    logger.debug("[_pause_video] 开始执行暂停视频操作")
    try:
        logger.debug("[_pause_video] 正在查找视频交互区域元素...")
        video_interactive_area = driver.find_element(By.CLASS_NAME, 'video-interactive-area')
        if video_interactive_area:
            logger.debug("[_pause_video] 找到视频交互区域，执行点击操作")
            video_interactive_area.click()
            logger.info("[_pause_video] 暂停视频操作成功")
            return True
    except NoSuchElementException:
        logger.debug("[_pause_video] 未找到视频交互区域元素")
        pass
    except Exception as e:
        logger.error(f"[_pause_video] 暂停视频失败: {e}")
    logger.error("[_pause_video] 暂停视频操作失败，返回False")
    return False


def _register_and_pause(driver, pause_manager_id: Optional[str]):
    """
    立即将浏览器加入暂停管理并尝试同步暂停一次
    """
    if not pause_manager_id:
        return
    try:
        register_browser_for_pause(pause_manager_id)
        if 'short-video' in getattr(driver, 'current_url', ''):
            _pause_video(driver)
    except Exception as e:
        logger.debug(f"[_register_and_pause] 注册或暂停失败: {e}")



def _click_video_switch(driver, direction: str) -> bool:
    """
    点击视频区域中的切换按钮（上一条/下一条）
    """
    try:
        video_area_element = driver.find_element(By.CSS_SELECTOR, '.video-container-player.video-area.vertical')
    except Exception as e:
        logger.debug(f"[_click_video_switch] 找不到视频区域: {e}")
        return False
    
    selector = f'.switch-item.video-switch-{direction}'
    try:
        switch_item = video_area_element.find_element(By.CSS_SELECTOR, selector)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", switch_item)
        switch_item.click()
        logger.debug(f"[_click_video_switch] 点击{direction}按钮成功")
        return True
    except NoSuchElementException:
        logger.debug(f"[_click_video_switch] 未找到{direction}切换按钮")
        return False
    except Exception as e:
        logger.error(f"[_click_video_switch] 点击{direction}按钮失败: {e}")
        return False


def _perform_video_exchange(driver, revert_to_original: bool = True, wait_between: float = 1.0) -> bool:
    """
    通过切换视频（下一条 -> 上一条）来刷新当前视频的播放状态
    """
    exchanged = False
    try:
        next_clicked = _click_video_switch(driver, 'next')
        if next_clicked:
            exchanged = True
            time.sleep(wait_between)
        
        if revert_to_original:
            prev_clicked = _click_video_switch(driver, 'prev')
            if prev_clicked:
                exchanged = True
                time.sleep(0.5)
        
        if exchanged:
            try:
                driver.execute_script("""
                    try {
                        const video = document.querySelector('video');
                        if (video) {
                            const playPromise = video.play();
                            if (playPromise && playPromise.catch) {
                                playPromise.catch(() => video.click());
                            }
                            return true;
                        }
                        return false;
                    } catch (e) {
                        return false;
                    }
                """)
            except Exception as e:
                logger.debug(f"[_perform_video_exchange] 刷新后尝试播放失败: {e}")
    except Exception as e:
        logger.error(f"[_perform_video_exchange] 视频交换过程出错: {e}")
    return exchanged


def _fetch_latest_poster(check_video_change: Optional[Callable]) -> Optional[str]:
    """通过提供的检测函数获取最新的poster"""
    if not callable(check_video_change):
        return None
    try:
        poster = check_video_change()
        if poster:
            logger.debug(f"[pause_recover] 获取最新poster: {poster[:50]}...")
        return poster
    except Exception as e:
        logger.debug(f"[pause_recover] 获取poster失败: {e}")
        return None


def _recover_video_from_pause(
    driver,
    browser_name: str,
    *,
    wait_timeout: Optional[float] = 5.0,
    check_video_change: Optional[Callable] = None,
    revert_swap: bool = True
) -> tuple[bool, Optional[str]]:
    """
    尝试在监控检测到暂停后自动恢复播放：
    1. 短暂等待监控器自行恢复
    2. 尝试点击视频区域恢复
    3. 通过视频交换（下一条->上一条）恢复
    """
    recovered = False
    updated_poster: Optional[str] = None
    
    effective_wait = 0.0
    if wait_timeout is None:
        effective_wait = 0.0
    else:
        effective_wait = max(0.0, min(wait_timeout, 5.0))
    
    if effective_wait > 0:
        logger.debug(f"[{browser_name}] 暂停恢复：等待监控器自动恢复（{effective_wait:.1f}s）")
        recovered = wait_for_resume(browser_name, timeout=effective_wait)
    
    if not recovered:
        logger.debug(f"[{browser_name}] 暂停仍未恢复，标记需要播放视频")
        # 使用播放线程来播放视频
        mark_need_play(browser_name)
        # 等待一小段时间让播放线程执行
        time.sleep(0.5)
        # 检查是否已恢复播放
        try:
            play_icon = driver.find_element(By.CSS_SELECTOR, "span.play-icon")
            div_element = play_icon.find_element(By.XPATH, ".//div")
            div_class = div_element.get_attribute('class')
            if div_class == "pause-icon":
                recovered = True
                monitor_mark_resume(browser_name)
                updated_poster = _fetch_latest_poster(check_video_change)
                if updated_poster:
                    monitor_update_poster(browser_name, updated_poster)
        except Exception:
            pass
    
    if not recovered:
        logger.debug(f"[{browser_name}] 点击恢复失败，尝试通过视频交换恢复播放")
        exchange_ok = _perform_video_exchange(driver, revert_swap)
        if exchange_ok:
            recovered = True
            monitor_mark_resume(browser_name)
            time.sleep(1.0)
            updated_poster = _fetch_latest_poster(check_video_change)
            if updated_poster:
                monitor_update_poster(browser_name, updated_poster)
    
    if recovered:
        logger.info(f"[{browser_name}] 暂停后已恢复播放")
    else:
        logger.warning(f"[{browser_name}] 暂停恢复失败，已尝试视频交换仍未成功")
    
    # 无论是否恢复成功，都清理暂停标志，避免一直处于“暂停”状态
    resume_browser(browser_name)
    return recovered, updated_poster


def _get_video_poster(driver):
    """
    获取当前视频的唯一标识（由URL中的 short-video/* 部分截取）
    Args:
        driver: Selenium WebDriver 对象
    Returns:
        str: 用于标识当前视频的字符串，如果获取失败返回None
    """
    try:
        current_url = getattr(driver, "current_url", "") or ""
        if 'short-video' in current_url:
            # 使用 URL 中 short-video/ 到 ? 之间的部分作为“poster”判断依据
            try:
                # 先截取 short-video/ 之后的部分
                after = current_url.split("short-video/", 1)[1]
                # 再截取到 ? 之前（如果没有 ? 就取到结尾）
                video_key = after.split("?", 1)[0]
                if video_key:
                    return video_key
            except Exception:
                # URL 解析失败时退回 None
                return None
        else:
            return None
    except Exception as e:
        # 如果是浏览器窗口已关闭，不打印错误日志，直接返回 None
        msg = str(e).lower()
        if isinstance(e, NoSuchWindowException) or "no such window" in msg or "web view not found" in msg:
            return None
        logger.error(f"[_get_video_poster] 获取url标识失败: {e}")
    return None


def _get_comment_count(driver) -> int:
    """
    获取当前视频评论区的评论数量
    返回 -1 表示无法判断
    """
    logger.debug("[_get_comment_count] 开始获取评论数量")
    try:
        logger.debug("[_get_comment_count] 正在查找评论区容器元素...")
        container = driver.find_element(By.CLASS_NAME, 'short-video-info-container')
        logger.debug("[_get_comment_count] 找到评论区容器元素")
    except Exception as e:
        logger.debug(f"[_get_comment_count] 未找到评论区容器元素: {e}")
        return -1

    # 只尝试第一个选择器
    selector = '.comment-item'
    logger.debug(f"[_get_comment_count] 使用选择器 '{selector}' 查找评论...")
    try:
        items = container.find_elements(By.CSS_SELECTOR, selector)
        if items and len(items) > 0:
            logger.debug(f"[_get_comment_count] 找到 {len(items)} 条评论")
            return len(items)
        else:
            logger.debug(f"[_get_comment_count] 未找到评论")
            return -1
    except Exception as e:
        logger.error(f"[_get_comment_count] 查找评论失败: {e}")
        return -1


def _log_play_state_after_pause(driver, browser_name: str) -> None:
	"""
	在执行暂停后检查播放图标并打印结果：
	- 存在且可见 span.play-icon -> 处于暂停态（期望）
	- 否则若存在且可见 span.pause-icon -> 仍在播放（异常）
	- 两者都未找到 -> 无法判断
	"""
	try:
		play_icon = driver.find_element(By.CSS_SELECTOR, "span.play-icon")
		if play_icon and play_icon.is_displayed():
			logger.debug(f"[{browser_name}] 暂停检查：显示 play-icon（已暂停）")
			return
	except Exception:
		pass

	try:
		pause_icon = driver.find_element(By.CSS_SELECTOR, "span.pause-icon")
		if pause_icon and pause_icon.is_displayed():
			logger.debug(f"[{browser_name}] 暂停检查：显示 pause-icon（仍在播放，需关注）")
			return
	except Exception:
		pass

	logger.debug(f"[{browser_name}] 暂停检查：未找到播放/暂停图标，无法判定状态")


def _is_on_video_page(driver) -> bool:
    """
    判断当前是否在快手短视频详情页：
    - 优先检测视频容器
    - 其次检测评论容器
    """
    try:
        driver.find_element(By.CSS_SELECTOR, '.video-container-player.video-area.vertical')
        return True
    except Exception:
        pass
    try:
        driver.find_element(By.CLASS_NAME, 'short-video-info-container')
        return True
    except Exception:
        return False


def _ensure_on_url(driver, target_url: str) -> bool:
    """
    确保当前页面处于目标URL：
    - 若已在目标URL（前缀或完全一致），返回False表示无需跳转
    - 若不一致，则切换到当前标签并重新跳转，返回True表示已重新跳转
    """
    try:
        current = driver.current_url
    except Exception:
        current = ""
    try:
        # 先确保聚焦当前标签页
        driver.switch_to.window(driver.current_window_handle)
    except Exception:
        pass
    if not current or (not current.startswith(target_url)):
        try:
            driver.get(target_url)
            return True
        except Exception:
            return False
    return False


class _VideoRefreshMonitor:
    """
    单线程监控器：最多监控5个浏览器，每个浏览器间隔检测0.05秒。
    仅检测poster变化，检测到即尝试暂停。
    """
    def __init__(self, max_browsers: int = 5, per_browser_interval: float = 0.05):
        self.max_browsers = max_browsers
        self.per_browser_interval = per_browser_interval
        self._lock = threading.Lock()
        # OrderedDict: browser_name -> {'driver': driver, 'last_poster': str|None, 'resume_time': float|None}
        # resume_time: 记录视频恢复播放的时间，用于在恢复后的一段时间内忽略poster变化
        self._targets: "OrderedDict[str, dict]" = OrderedDict()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def register(self, browser_name: str, driver) -> None:
        with self._lock:
            if len(self._targets) >= self.max_browsers and browser_name not in self._targets:
                logger.warning(f"[{browser_name}][monitor] 已达到最大监控数量({self.max_browsers})，忽略注册")
                return
            self._targets[browser_name] = {'driver': driver, 'last_poster': None, 'resume_time': None}
            logger.info(f"[{browser_name}][monitor] 已注册到刷新监控器，当前数量: {len(self._targets)}")
            if not self._thread or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()
                logger.info(f"[monitor] 线程已启动(thread={self._thread.ident})")

    def unregister(self, browser_name: str) -> None:
        with self._lock:
            if browser_name in self._targets:
                self._targets.pop(browser_name, None)
                logger.info(f"[{browser_name}][monitor] 已从刷新监控器注销，剩余: {len(self._targets)}")
            if not self._targets:
                self._stop.set()
    
    def update_poster(self, browser_name: str, poster: str) -> None:
        """
        手动更新指定浏览器的poster，用于主循环恢复播放后同步状态
        Args:
            browser_name: 浏览器名称
            poster: 当前poster URL
        """
        with self._lock:
            if browser_name in self._targets:
                self._targets[browser_name]['last_poster'] = poster
                # 清除恢复播放时间标记，因为这是手动同步的状态
                self._targets[browser_name]['resume_time'] = None
                logger.debug(f"[{browser_name}][monitor] 手动更新poster: {poster[:50] if poster else 'None'}...")
    
    def mark_resume(self, browser_name: str) -> None:
        """
        标记视频已恢复播放，监控器将在恢复后1秒内忽略poster变化
        Args:
            browser_name: 浏览器名称
        """
        with self._lock:
            if browser_name in self._targets:
                import time
                self._targets[browser_name]['resume_time'] = time.time()
                logger.debug(f"[{browser_name}][monitor] 标记视频已恢复播放，将在1秒内忽略poster变化")

    def _safe_get_poster(self, driver):
        try:
            return _get_video_poster(driver)
        except Exception:
            return None

    def _worker(self):
        logger.info("[monitor] 刷新监控线程进入运行")
        while not self._stop.is_set():
            with self._lock:
                items = list(self._targets.items())
            if not items:
                time.sleep(0.1)
                continue
            for browser_name, ctx in items[:self.max_browsers]:
                driver = ctx.get('driver')
                last_poster = ctx.get('last_poster')
                resume_time = ctx.get('resume_time')
                # 每个浏览器的检测
                try:
                    # 驱动不存在或当前URL不在 short-video 页面时直接跳过
                    if (not driver) or ('short-video' not in getattr(driver, "current_url", "") or ""):
                        continue
                    # # 仅在视频页检测
                    # try:
                    #     on_video = _is_on_video_page(driver)
                    # except Exception:
                    #     on_video = False
                    # if not on_video:
                    #     time.sleep(self.per_browser_interval)
                    #     continue
                    
                    # 检查是否在恢复播放后的1秒内，如果是则忽略poster变化（避免与主循环冲突）
                    if resume_time is not None:
                        elapsed_since_resume = time.time() - resume_time
                        if elapsed_since_resume < 1.0:
                            # 在恢复播放后的1秒内，忽略poster变化，避免与主循环的恢复播放操作冲突
                            time.sleep(self.per_browser_interval)
                            continue
                        else:
                            # 超过1秒，清除恢复播放标记
                            with self._lock:
                                if browser_name in self._targets:
                                    self._targets[browser_name]['resume_time'] = None
                    
                    # 使用 _get_video_poster 获取当前poster
                    try:
                        poster = _get_video_poster(driver)
                    except Exception:
                        poster = None
                    
                    # 判断：如果poster不为None，且与last_poster不一样，且last_poster也不为None，才暂停视频
                    if poster is not None and last_poster is not None and poster != last_poster:
                        try:
                            pause_ok = _pause_video(driver)
                            if not pause_ok:
                                try:
                                    driver.execute_script("""
                                        try {
                                            const v = document.querySelector('video');
                                            if (v) { v.pause(); return true; }
                                            return false;
                                        } catch (e) { return false; }
                                    """)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        # 更新last_poster
                        with self._lock:
                            if browser_name in self._targets:
                                self._targets[browser_name]['last_poster'] = poster
                    elif last_poster is None and poster is not None:
                        # 首次获得poster，更新但不暂停（由主循环处理首次暂停）
                        with self._lock:
                            if browser_name in self._targets:
                                self._targets[browser_name]['last_poster'] = poster
                except Exception:
                    # 驱动可能失效（invalid session id），忽略本轮
                    pass
                # 浏览器间隔
                time.sleep(self.per_browser_interval)
        logger.info("[monitor] 刷新监控线程退出")


_global_refresh_monitor = _VideoRefreshMonitor(max_browsers=5, per_browser_interval=0.05)

def monitor_register_browser(browser_name: str, driver) -> None:
    try:
        _global_refresh_monitor.register(browser_name, driver)
    except Exception as e:
        logger.error(f"[{browser_name}] 注册到刷新监控器失败: {e}")

def monitor_unregister_browser(browser_name: str) -> None:
    try:
        _global_refresh_monitor.unregister(browser_name)
    except Exception as e:
        logger.error(f"[{browser_name}] 从刷新监控器注销失败: {e}")

def monitor_update_poster(browser_name: str, poster: str) -> None:
    """
    手动更新监控器中的poster，用于主循环恢复播放后同步状态
    Args:
        browser_name: 浏览器名称
        poster: 当前poster URL
    """
    try:
        _global_refresh_monitor.update_poster(browser_name, poster)
    except Exception as e:
        logger.error(f"[{browser_name}] 更新监控器poster失败: {e}")

def monitor_mark_resume(browser_name: str) -> None:
    """
    标记视频已恢复播放，监控器将在恢复后1秒内忽略poster变化
    Args:
        browser_name: 浏览器名称
    """
    try:
        _global_refresh_monitor.mark_resume(browser_name)
    except Exception as e:
        logger.error(f"[{browser_name}] 标记视频恢复播放失败: {e}")


def sleep_with_monitor_check(
    browser_name: str,
    duration: float,
    check_interval: float = 0.5,
    shutdown_event: Optional[threading.Event] = None
) -> bool:
    """
    在等待期间检查监控暂停状态和退出信号
    
    Args:
        browser_name: 浏览器名称
        duration: 总等待时间（秒）
        check_interval: 检查间隔（秒）
        shutdown_event: 退出事件（可选）
    
    Returns:
        bool: True=正常完成等待, False=被暂停中断或收到退出信号
    """
    elapsed = 0.0
    while elapsed < duration:
        # 检查退出标志
        if shutdown_event and shutdown_event.is_set():
            logger.info(f"[{browser_name}] 收到退出信号，中断等待")
            return False
        
        # 检查是否被暂停
        if is_paused(browser_name):
            logger.warning(f"[{browser_name}] 检测到暂停标志，等待恢复...")
            # 等待恢复（最多等待剩余时间，但不超过30秒）
            remaining_time = duration - elapsed
            wait_timeout = min(remaining_time, 30.0)
            resumed = wait_for_resume(browser_name, timeout=wait_timeout)
            if resumed:
                logger.info(f"[{browser_name}] 已恢复，继续等待")
                resume_browser(browser_name)
            else:
                logger.warning(f"[{browser_name}] 等待恢复超时（{wait_timeout}秒），自动清除暂停标志并继续")
                resume_browser(browser_name)
            # 如果被暂停，返回False表示被中断
            return False
        
        # 等待检查间隔
        sleep_time = min(check_interval, duration - elapsed)
        # 使用可中断的 sleep
        if shutdown_event:
            sleep_elapsed = 0
            while sleep_elapsed < sleep_time:
                if shutdown_event.is_set():
                    return False
                sleep_chunk = min(0.1, sleep_time - sleep_elapsed)
                time.sleep(sleep_chunk)
                sleep_elapsed += sleep_chunk
        else:
            time.sleep(sleep_time)
        elapsed += sleep_time
    
    return True


def _handle_new_video(
    driver,
    browser_name: str,
    now_video_poster_url: str,
    check_video_change,
    start_time: float,
    main_loop_duration: float,
    min_comment_count: int = 4
) -> Tuple[bool, bool]:
    """
    处理新视频检测后的逻辑：暂停视频 -> 检查评论数量 -> 决定是否跳过
    
    Args:
        driver: Selenium WebDriver 对象
        browser_name: 浏览器名称
        now_video_poster_url: 当前视频poster URL
        check_video_change: 检查视频变化的函数
        start_time: 主流程开始时间
        main_loop_duration: 主流程持续时间
        min_comment_count: 最小评论数量阈值（<=此值则跳过）
    
    Returns:
        tuple[bool, bool]: (是否跳过该视频, 是否正在播放)
    """
    logger.debug(f"[_handle_new_video][{browser_name}] 开始处理新视频，poster: {now_video_poster_url[:50] if now_video_poster_url else 'None'}...")
    
    # 等待一下让页面稳定（暂停由监控器负责）
    logger.debug(f"[_handle_new_video][{browser_name}] 等待页面稳定（0.5秒）")
    time.sleep(0.5)
    
    # 检查评论数量
    logger.debug(f"[_handle_new_video][{browser_name}] 步骤3: 检查评论数量（阈值: >{min_comment_count}）")
    try:
        comment_count = _get_comment_count(driver)
        logger.debug(f"[_handle_new_video][{browser_name}] 获取到评论数量: {comment_count}")
    except Exception as e:
        logger.error(f"[_handle_new_video][{browser_name}] 获取评论数量时发生异常: {e}")
        comment_count = -1
    
    # 如果评论数量 <= min_comment_count 或无法获取评论数量（-1），直接播放到下一个视频
    if comment_count == -1 or comment_count == 0 or (comment_count > 0 and comment_count <= min_comment_count):
        if comment_count == -1:
            reason = "无法获取评论数量（可能没有评论或页面未加载完成）"
        elif comment_count == 0:
            reason = "没有评论"
        else:
            reason = f"评论数量较少({comment_count}，阈值>{min_comment_count})"
        logger.debug(f"[_handle_new_video][{browser_name}] {reason}，直接播放至结束后再看下一个视频")
        
        # 恢复播放
        logger.debug(f"[_handle_new_video][{browser_name}] 步骤4: 恢复播放视频")
        # 使用播放线程来播放视频
        mark_need_play(browser_name)
        is_video_playing = True
        # 通知监控器视频已恢复播放，避免监控器误判并立即暂停
        monitor_mark_resume(browser_name)
        # 更新监控器中的poster，保持状态同步
        monitor_update_poster(browser_name, now_video_poster_url)
        
        # 等待视频播放完成（检测到新视频）
        max_wait_time = 300  # 最多等待5分钟
        wait_start = time.time()
        check_count = 0
        logger.info(f"[_handle_new_video][{browser_name}] 步骤5: 开始监控视频播放完成（最多等待{max_wait_time}秒）")
        
        # 启动视频状态监控
        start_monitoring(browser_name)
        logger.debug(f"[_handle_new_video][{browser_name}] 视频状态监控已启动")
        
        while is_video_playing and (time.time() - wait_start) < max_wait_time:
            # 检查暂停状态
            if is_paused(browser_name):
                logger.warning(f"[_handle_new_video][{browser_name}] 检测到暂停标志，等待恢复...")
                remaining_time = max_wait_time - (time.time() - wait_start)
                wait_timeout = min(max(remaining_time, 0.0), 30.0)
                recovered, updated_poster = _recover_video_from_pause(
                    driver,
                    browser_name,
                    wait_timeout=wait_timeout,
                    check_video_change=check_video_change
                )
                if updated_poster:
                    now_video_poster_url = updated_poster
                if recovered:
                    logger.info(f"[_handle_new_video][{browser_name}] 通过视频交换恢复播放")
                else:
                    logger.warning(f"[_handle_new_video][{browser_name}] 恢复失败，继续尝试监控")
            
            time.sleep(0.3)
            check_count += 1
            
            # 检查poster是否变化
            check_poster = check_video_change()
            if check_poster and check_poster != now_video_poster_url:
                logger.info(f"[_handle_new_video][{browser_name}] 视频播放完成（评论较少策略），检测到新视频（检查{check_count}次）")
                is_video_playing = False
                return True, False  # 跳过该视频，不在播放状态
            
            # 检查主流程时间
            elapsed_time = time.time() - start_time
            if elapsed_time >= main_loop_duration:
                logger.debug(f"[_handle_new_video][{browser_name}] 主流程时间已到，退出视频播放监控")
                is_video_playing = False
                return True, False  # 跳过该视频，不在播放状态
            
            # 每10次检查打印一次进度
            if check_count % 10 == 0:
                elapsed_wait = time.time() - wait_start
                logger.debug(f"[_handle_new_video][{browser_name}] 播放监控中... 已检查{check_count}次，已等待{elapsed_wait:.1f}秒")
        
        # 如果超时
        if is_video_playing:
            logger.debug(f"[_handle_new_video][{browser_name}] 视频播放监控超时（{max_wait_time}秒），继续下一次循环")
            return True, False  # 跳过该视频，不在播放状态
        
        return True, False  # 跳过该视频，不在播放状态
    
    # 评论数量足够，继续正常流程
    logger.debug(f"[_handle_new_video][{browser_name}] 评论数量充足({comment_count}个)，进入正常操作流程")
    return False, False  # 不跳过，不在播放状态


def _determine_action_type(
    total_follow_count: int,
    max_follow_count: int = 100,
    like_follow_ratio: float = 3.0,
    view_profile_after_like_prob: float = 0.33
) -> tuple[ActionType, bool]:
    """
    根据当前状态决定执行的操作类型
    
    Args:
        total_follow_count: 累计关注数量
        max_follow_count: 最大关注数量上限，达到后只执行点赞操作
        like_follow_ratio: 点赞与关注的比例，例如 3.0 表示点赞:关注 = 3:1
        view_profile_after_like_prob: 点赞后查看个人信息的概率（0.0-1.0）
    
    Returns:
        Tuple[ActionType, bool]: (操作类型, 是否在点赞后查看个人信息)
    """
    logger.debug(f"[_determine_action_type] 开始决定操作类型，当前关注数: {total_follow_count}/{max_follow_count}")
    
    # 如果达到关注上限，只执行点赞操作
    if total_follow_count >= max_follow_count:
        should_view = random.random() < view_profile_after_like_prob
        logger.debug(f"[_determine_action_type] 已达到关注上限，选择点赞操作，查看个人信息: {should_view}")
        return ActionType.LIKE, should_view
    
    # 根据点赞/关注比例随机选择操作
    # 例如 ratio=3.0 表示 3次点赞对应1次关注，即点赞概率为 3/(3+1) = 0.75
    like_probability = like_follow_ratio / (like_follow_ratio + 1.0)
    logger.debug(f"[_determine_action_type] 计算点赞概率: {like_probability:.2%} (比例: {like_follow_ratio}:1)")
    
    random_value = random.random()
    logger.debug(f"[_determine_action_type] 随机值: {random_value:.3f}")
    
    if random_value < like_probability:
        # 执行点赞操作，有概率查看个人信息
        should_view = random.random() < view_profile_after_like_prob
        logger.debug(f"[_determine_action_type] 选择点赞操作，查看个人信息: {should_view}")
        return ActionType.LIKE, should_view
    else:
        # 执行关注操作
        logger.debug(f"[_determine_action_type] 选择关注操作")
        return ActionType.FOLLOW, False


def _get_stats_file_path(browser_name: str, browser_id: Optional[str] = None, date_label: Optional[str] = None) -> str:
    """
    获取统计记录文件路径
    路径结构：记录/浏览器名字_id/启动浏览器名称_时间.txt
    
    Args:
        browser_name: 浏览器名称
        browser_id: 浏览器ID（可选）
        date_label: 日期标签，格式：2024年01月01日 12:00:00
    
    Returns:
        文件路径
    """
    # 基础目录：记录
    base_dir = os.path.join(os.path.dirname(__file__), "记录")
    
    # 浏览器目录名：浏览器名字_id（如果有ID）
    if browser_id:
        browser_dir_name = f"{browser_name}_{browser_id}"
    else:
        browser_dir_name = browser_name
    
    browser_dir = os.path.join(base_dir, browser_dir_name)
    
    # 确保目录存在
    os.makedirs(browser_dir, exist_ok=True)
    
    # 文件名：启动浏览器名称_时间.txt
    # 时间格式需要去掉冒号，替换为 "-"
    if date_label:
        # 将 "2024年01月01日 12:00:00" 转换为 "2024年01月01日_12-00-00"
        time_str = date_label.replace(":", "-").replace(" ", "_")
        file_name = f"{browser_name}_{time_str}.txt"
    else:
        # 如果没有提供日期，使用当前时间
        current_time = time.strftime("%Y年%m月%d日_%H-%M-%S")
        file_name = f"{browser_name}_{current_time}.txt"
    
    return os.path.join(browser_dir, file_name)


def _update_stats_file(file_path: str, date_label: str, like_count: int, follow_count: int, browser_name: str = ""):
    """
    创建/更新统计记录文本。
    - 若文件不存在：创建并写入一个新的日期分段
    - 若存在相同日期分段：只更新该分段下的点赞/关注行
    - 若不存在相同日期分段：在末尾追加新的分段
    Args:
        file_path: 记录文件路径
        date_label: 日期标签
        like_count: 点赞数量
        follow_count: 关注数量
        browser_name: 浏览器名称，用于区分不同浏览器的记录
    """
    if browser_name:
        header_line = f"于{date_label}[{browser_name}]启动---------------"
    else:
        header_line = f"于{date_label}启动---------------"
    like_line = f"点赞：{like_count}"
    follow_line = f"关注：{follow_count}"
    delimiter_line = "------------------"
    
    if not os.path.exists(file_path):
        content = (
            f"{header_line}\n"
            f"{like_line}\n\n"
            f"{follow_line}\n\n"
            f"{delimiter_line}\n\n"
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return
    
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    # 使用正则匹配当前日期的分段，并替换点赞/关注两行
    # 分段结构：
    # 于{date_label}[{browser_name}]启动---------------  (如果提供了浏览器名称)
    # 或 于{date_label}启动---------------  (如果没有提供浏览器名称)
    # 点赞：x
    #
    # 关注：y
    #
    # ------------------
    # 注意：中间可能存在空行，因此用非贪婪匹配直到分隔线
    pattern = (
        rf"(^{re.escape(header_line)}\n)"              # 分组1：标题行
        rf"(.*?\n)?"                                    # 可能的点赞行前缀（兼容额外行）
        rf"点赞：\d+\n"                                 # 原点赞行
        rf"(?:\n)?"                                     # 可能的空行
        rf"关注：\d+\n"                                 # 原关注行
        rf"(?:\n)?"                                     # 可能的空行
        rf"(?={re.escape(delimiter_line)}\n)"           # 直到分隔线为止（不消耗）
    )
    # DOTALL + MULTILINE
    regex = re.compile(pattern, re.DOTALL | re.MULTILINE)
    
    def repl(match):
        prefix = match.group(1)
        return f"{prefix}{like_line}\n\n{follow_line}\n\n"
    
    if header_line in text:
        new_text, count = regex.subn(repl, text, count=1)
        if count == 0:
            # 如果未成功通过正则替换（格式变动），采取保守策略：在该标题后到分隔符前粗暴替换
            # 构造一个新块，并用简单替换方式更新
            block_pattern = rf"{re.escape(header_line)}\n.*?{re.escape(delimiter_line)}"
            block_regex = re.compile(block_pattern, re.DOTALL)
            new_block = (
                f"{header_line}\n"
                f"{like_line}\n\n"
                f"{follow_line}\n\n"
                f"{delimiter_line}"
            )
            new_text = block_regex.sub(new_block, text, count=1)
    else:
        # 末尾追加新分段
        if text and not text.endswith("\n"):
            text += "\n"
        new_text = (
            text
            + f"{header_line}\n"
            + f"{like_line}\n\n"
            + f"{follow_line}\n\n"
            + f"{delimiter_line}\n\n"
        )
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_text)


def _check_comment_end_reached(driver) -> bool:
    """
    检查评论区是否已经滚动到底部
    通过检查评论容器的滚动位置来判断，如果到底部则等待3秒看是否有新评论加载
    Args:
        driver: Selenium WebDriver 对象
    Returns:
        bool: 如果确认已经到底部且没有新评论，返回True；否则返回False
    """
    try:
        # 查找评论容器元素
        comment_container = None
        try:
            # 尝试查找 comment-container vertical-comment dark-mode
            comment_container = driver.find_element(By.CSS_SELECTOR, 'div.comment-container.vertical-comment.dark-mode')
            logger.debug("[_check_comment_end_reached] 找到评论容器元素 (comment-container vertical-comment dark-mode)")
        except Exception:
            try:
                # 如果找不到，尝试使用 short-video-info-container 作为备选
                comment_container = driver.find_element(By.CLASS_NAME, 'short-video-info-container')
                logger.debug("[_check_comment_end_reached] 使用备选评论容器元素 (short-video-info-container)")
            except Exception as e:
                logger.debug(f"[_check_comment_end_reached] 未找到评论容器元素: {e}")
                return False
        
        if not comment_container:
            return False
        
        # 滚动误差阈值（允许的底部偏差范围，单位：px）
        SCROLL_THRESHOLD = 50

        position_info = driver.execute_script("""
            var container = arguments[0];
            var rect = container.getBoundingClientRect();
            var scrollTop = container.scrollTop;
            var scrollHeight = container.scrollHeight;
            var clientHeight = container.clientHeight;
            var windowHeight = window.innerHeight;

            // 元素基础位置信息
            var elementY = rect.top;
            var elementHeight = rect.height;
            var elementBottomY = elementY + elementHeight;

            // 判断是否有滚动条
            var hasScrollbar = scrollHeight > clientHeight;

            // 判断滚动是否到底部（允许指定阈值的误差）
            var isScrollAtBottom = hasScrollbar 
                ? (scrollTop + clientHeight >= scrollHeight - arguments[1])  // 有滚动条：基于滚动位置
                : (scrollHeight - clientHeight <= arguments[1]);           // 无滚动条：基于内容高度

            // 元素底部是否进入屏幕可视范围（含阈值）
            var elementBottomVisible = elementBottomY <= windowHeight + arguments[1];

            return {
                elementY: elementY,
                elementHeight: elementHeight,
                elementBottomY: elementBottomVisible,
                windowHeight: windowHeight,
                scrollTop: scrollTop,
                scrollHeight: scrollHeight,
                clientHeight: clientHeight,
                hasScrollbar: hasScrollbar,
                isScrollAtBottom: isScrollAtBottom,
                elementBottomVisible: elementBottomVisible
            };
        """, comment_container, SCROLL_THRESHOLD)  # 传入容器和误差阈值

        # 提取核心判断结果
        has_scrollbar = position_info['hasScrollbar']
        scroll_at_bottom = position_info['isScrollAtBottom']
        element_bottom_visible = position_info['elementBottomVisible']

        # 未到底部的情况
        if not element_bottom_visible:
            reason = (
                f"元素底部在屏幕下方 (底部Y={position_info['elementBottomY']:.0f} > 屏幕高度{position_info['windowHeight']:.0f})"
                if has_scrollbar 
                else f"元素底部未进入屏幕范围 (底部Y={position_info['elementBottomY']:.0f})"
            )
            logger.debug(f"[_check_comment_end_reached] 未到底部: {reason}")
            return False
        
        # 已经到底部，记录当前评论数量
        try:
            current_comments = comment_container.find_elements(By.CSS_SELECTOR, '.comment-item')
            comment_count_before = len(current_comments)
            logger.debug(f"[_check_comment_end_reached] 已到底部，当前评论数量: {comment_count_before}")
        except Exception as e:
            logger.error(f"[_check_comment_end_reached] 获取评论数量失败: {e}")
            comment_count_before = 0
        
        # 等待3秒，看是否有新评论加载
        time.sleep(3)
        
        # 再次检查评论数量
        try:
            current_comments_after = comment_container.find_elements(By.CSS_SELECTOR, '.comment-item')
            comment_count_after = len(current_comments_after)
            logger.debug(f"[_check_comment_end_reached] 等待3秒后评论数量: {comment_count_after}")
            
            # 如果评论数量没有增加，说明真的到底了
            if comment_count_after == comment_count_before:
                logger.debug(f"[_check_comment_end_reached] 确认评论已到底部（评论数量未增加）")
                return True
            else:
                logger.info(f"[_check_comment_end_reached] 检测到新评论加载（{comment_count_before} -> {comment_count_after}），未到底部")
                return False
        except Exception as e:
            logger.error(f"[_check_comment_end_reached] 检查新评论时发生错误: {e}")
            # 如果检查失败，假设已经到底了
            return True
        
    except Exception as e:
        logger.error(f"[_check_comment_end_reached] 检查评论到底时发生异常: {e}")
        logger.exception("[_check_comment_end_reached] 详细异常堆栈")
        return False


def _check_video_ended(driver) -> bool:
    """
    检查视频是否播放完成
    通过检查视频是否自动切换到下一个视频来判断
    Args:
        driver: Selenium WebDriver 对象
    Returns:
        bool: True表示视频已播放完成，False表示仍在播放
    """
    try:
        # 检查是否有重播按钮或视频是否自动切换
        # 如果视频播放完成，通常会显示重播按钮或自动切换到下一个视频
        try:
            # 检查是否有重播按钮
            replay_button = driver.find_element(By.CLASS_NAME, 'replay-btn')
            if replay_button and replay_button.is_displayed():
                return True
        except NoSuchElementException:
            pass
        
        # 检查视频poster是否变化（如果变化说明切换到新视频，原视频播放完成）
        # 这个方法需要在调用时保存初始poster进行比较
        return False
    except Exception as e:
        logger.error(f"[_check_video_ended] 检查视频播放状态失败: {e}")
        return False


def _check_is_on_video_url(driver) -> bool:
    """
    检查当前网页链接是否在视频链接里（包含short-video）
    Args:
        driver: Selenium WebDriver 对象
    Returns:
        bool: True表示在视频页面，False表示不在视频页面
    """
    try:
        current_url = driver.current_url
        if 'short-video' in current_url:
            return True
        else:
            logger.warning(f"[_check_is_on_video_url] 当前URL不在视频页面: {current_url}")
            return False
    except Exception as e:
        logger.error(f"[_check_is_on_video_url] 检查URL失败: {e}")
        return False


def browser_video_url_list_loop(
    params: dict,  # 接收封装的参数字典
    browser,
    url_queue: queue.Queue,
    cluster
):
    """

    """
    logger.debug(f"\n[{params['browser_name']}] {'='*60}")
    logger.debug(f"[{params['browser_name']}] 开始视频URL列表模式")
    try:
        initial_qsize = url_queue.qsize()
    except Exception:
        initial_qsize = -1
    logger.debug(f"[{params['browser_name']}] URL队列初始长度: {initial_qsize}")
    logger.debug(f"[{params['browser_name']}] {'='*60}\n")
    
    driver = browser.driver
    if not driver:
        logger.error(f"[{params['browser_name']}] ✗ 浏览器驱动未初始化，跳过")
        return
    
    logger.info(f"[{params['browser_name']}] ✓ 浏览器驱动已初始化")
    
    # 删除多余页面保留一个
    _delete_extra_pages(driver, params)
    
    # 统计本次任务期间的累计数据
    total_like_count = 0
    total_follow_count = 0
    session_date_label = time.strftime("%Y年%m月%d日 %H:%M:%S")
    # 获取浏览器ID（如果有）
    browser_id = params.get('id')
    # 生成统计文件路径：记录/浏览器名字_id/启动浏览器名称_时间.txt
    stats_file_path = _get_stats_file_path(params['browser_name'], browser_id, session_date_label)
    logger.info(f"[{params['browser_name']}] 统计文件路径: {stats_file_path}")
    logger.debug(f"[{params['browser_name']}] 会话日期标签: {session_date_label}")
    _update_stats_file(stats_file_path, session_date_label, total_like_count, total_follow_count, params['browser_name'])
    
    # # 注册到全局刷新监控器（URL列表模式全程共用）
    # monitor_register_browser(params['browser_name'], driver)
    # 将浏览器加入暂停管理列表
    register_browser_for_pause(params['browser_name'])
    
    # 创建视频状态监控器
    check_interval = getattr(config, 'VIDEO_MONITOR_CHECK_INTERVAL', 1.0)
    paused_threshold = getattr(config, 'VIDEO_MONITOR_PAUSED_THRESHOLD', 3.0)
    progress_stall_threshold = getattr(config, 'VIDEO_MONITOR_PROGRESS_STALL_THRESHOLD', 5.0)
    monitor = create_monitor(
        browser_name=params['browser_name'],
        browser_id=params['id'],
        driver=driver,
        check_interval=check_interval,
        paused_threshold=paused_threshold,
        progress_stall_threshold=progress_stall_threshold
    )

    try:
        url_index = 0
        shutdown_event = params.get('shutdown_event')
        while True:
            # 检查退出标志
            if shutdown_event and shutdown_event.is_set():
                logger.info(f"[{params['browser_name']}] 收到退出信号，停止处理URL列表")
                break
            try:
                video_url = url_queue.get_nowait()
                url_index += 1
            except queue.Empty:
                if url_index == 0:
                    logger.warning(f"[{params['browser_name']}] ⚠ 未分配到任何URL，结束本浏览器任务（URL数量可能少于浏览器数量）")
                else:
                    logger.info(f"[{params['browser_name']}] URL队列为空，已处理 {url_index} 个URL，结束本浏览器任务")
                break
            logger.debug(f"\n[{params['browser_name']}] {'='*50}")
            logger.debug(f"[{params['browser_name']}] 处理第 {url_index} 个视频URL")
            logger.debug(f"[{params['browser_name']}] URL: {video_url}")
            logger.debug(f"[{params['browser_name']}] {'='*50}\n")
            
            try:
                # 步骤1: 跳转到视频URL
                logger.debug(f"[{params['browser_name']}] 步骤1: 跳转到视频URL...")
                # 跳转前先切换到当前标签页
                try:
                    driver.switch_to.window(driver.current_window_handle)
                except Exception:
                    pass
                driver.get(video_url)
                logger.info(f"[{params['browser_name']}] ✓ 跳转成功")
                try:
                    time.sleep(0.5)
                    driver.find_element(By.CLASS_NAME, "video-interactive-area").click()
                except Exception as e:
                    logger.info(f"点击视频交互区域失败: {e}")
                    pass
                # 等待页面加载
                logger.info(f"[{params['browser_name']}] 等待页面加载完成（1秒）...")
                time.sleep(0.5)
                # 校验是否仍在目标URL，不是则重新跳转
                try:
                    _ensure_on_url(driver, video_url)
                except Exception:
                    pass
                
                # 暂停由全局监控器处理，这里不主动暂停
                time.sleep(0.5)
                
                # 步骤3: 执行刷视频操作（点赞、关注等）
                logger.debug(f"[{params['browser_name']}] 步骤3: 开始执行刷视频操作...")
                
                # 获取当前视频的poster作为标识
                initial_poster = _get_video_poster(driver)
                logger.debug(f"[{params['browser_name']}] 当前视频poster: {initial_poster[:50] if initial_poster else 'None'}...")
                # 再次校验URL（防止跳转过程中发生偏移）
                try:
                    _ensure_on_url(driver, video_url)
                except Exception:
                    pass
                
                # 初始化当前视频的已关注用户ID集合
                params['followed_user_ids'] = set()
                logger.debug(f"[{params['browser_name']}] 新视频URL开始，初始化已关注用户ID集合")
                
                # 检查版本过低按钮
                check_button(driver, params)
                
                # 评论区操作次数（使用参数配置，而不是固定的3次）
                comment_operation_count = random.randint(params.get('comment_min_operation_count', 3), params.get('comment_max_operation_count', 5))
                logger.info(f"[{params['browser_name']}] 本次视频操作次数: {comment_operation_count}")
                
                # 当前视频的操作计数
                current_video_action_count = 0
                video_operation_completed = False
                pause_manager_id = params.get('id')
                
                # 将浏览器加入暂停管理列表
                if pause_manager_id:
                    register_browser_for_pause(pause_manager_id)
                
                # 评论区数量（用于判断是否操作）
                comment_elements_count = random.randint(params.get('comment_min_elements_count', 3), params.get('comment_max_elements_count', 5))
                
                # 执行操作（使用与 browser_video_loop 相同的逻辑）
                while current_video_action_count < comment_operation_count and not video_operation_completed:
                    try:
                        # 操作前校验URL一致性
                        try:
                            _ensure_on_url(driver, video_url)
                        except Exception:
                            pass
                        
                        # 检查当前网页链接是否在视频链接里（包含short-video）
                        is_on_video_url = _check_is_on_video_url(driver)
                        if not is_on_video_url:
                            logger.warning(f"[{params['browser_name']}] 当前不在视频页面，重新跳转到视频URL...")
                            try:
                                try:
                                    driver.switch_to.window(driver.current_window_handle)
                                except Exception:
                                    pass
                                driver.get(video_url)
                                time.sleep(1)
                                _ensure_on_url(driver, video_url)
                                # 重新检查
                                is_on_video_url = _check_is_on_video_url(driver)
                                if not is_on_video_url:
                                    logger.error(f"[{params['browser_name']}] 重新跳转后仍不在视频页面，跳过本次操作")
                                    break
                                logger.info(f"[{params['browser_name']}] ✓ 重新跳转成功，继续执行操作")
                            except Exception as e:
                                logger.error(f"[{params['browser_name']}] 重新跳转失败: {e}，跳过本次操作")
                                break
                        
                        # 获取评论区元素
                        comment_element = _get_comment_element(driver, params)
                        if comment_element:
                            logger.debug(f"[{params['browser_name']}] 成功获取评论区元素")
                        else:
                            logger.error(f"[{params['browser_name']}] 无法获取评论区元素")
                            time.sleep(2)
                            continue
                        
                        if 'short-video' in driver.current_url:
                            comment_elements = comment_element.find_elements(By.CSS_SELECTOR, '.comment-item.comment-list-item.dark-mode')
                            
                            # 滚动评论区判断是否到底部
                            if _check_comment_end_reached(driver):
                                try:
                                    logger.info(f"[{params['browser_name']}] 评论区到底部，播放视频")
                                    if pause_manager_id:
                                        mark_need_play(pause_manager_id)
                                    video_operation_completed = True
                                    break
                                except Exception as e:
                                    video_operation_completed = False
                                    logger.error(f"[{params['browser_name']}] 播放视频失败: {e}")
                                    continue
                            else:
                                # 未到底部，继续滚动评论区
                                scroll_comment(driver, comment_element)
                                time.sleep(random.uniform(0.5, 2))
                            
                            # 视频单次操作（使用 _video_single_operation 方法，支持优先关注评论关键词）
                            params_with_count = params.copy()
                            params_with_count['total_follow_count'] = total_follow_count
                            
                            operation_success, action_type = _video_single_operation(driver, comment_elements, params_with_count)
                            
                            if operation_success:
                                current_video_action_count += 1
                                
                                # 根据操作类型更新统计
                                if action_type == ActionType.LIKE:
                                    total_like_count += 1
                                    logger.info(f"[{params['browser_name']}] ✓ 点赞操作完成 | 累计点赞: {total_like_count}")
                                elif action_type == ActionType.FOLLOW:
                                    total_follow_count += 1
                                    logger.info(f"[{params['browser_name']}] ✓ 关注操作完成 | 累计关注: {total_follow_count}")
                                
                                logger.info(f"[{params['browser_name']}] 视频单次操作完成，当前操作次数: {current_video_action_count}/{comment_operation_count}")
                                
                                # 滚动评论区到底部
                                scroll_time = int(random.uniform(params['action_interval_min'], params['action_interval_max']))
                                scroll_comment_to_bottom(driver, params, comment_element, scroll_time, params['scroll_interval_min'], params['scroll_interval_max'])
                                
                                # 更新统计文件
                                _update_stats_file(stats_file_path, session_date_label, total_like_count, total_follow_count, params['browser_name'])
                            else:
                                # 操作失败或不在视频页面
                                if 'short-video' not in driver.current_url:
                                    logger.warning(f"[{params['browser_name']}] 不在视频页面，退出操作循环")
                                    break
                            
                            # 检查是否达到操作次数
                            if current_video_action_count >= comment_operation_count:
                                try:
                                    video_operation_completed = True
                                    if pause_manager_id:
                                        mark_need_play(pause_manager_id)
                                    logger.info(f"[{params['browser_name']}] 达到操作次数上限，完成本次视频操作")
                                except Exception as e:
                                    video_operation_completed = False
                                    logger.error(f"[{params['browser_name']}] 播放视频失败: {e}")
                                    continue
                            else:
                                logger.debug(f"[{params['browser_name']}] 操作次数未达到值 {current_video_action_count}/{comment_operation_count}")
                                # 操作间隔等待
                                wait_time = random.uniform(params['action_interval_min'], params['action_interval_max'])
                                logger.debug(f"[{params['browser_name']}] 操作间隔等待 {wait_time:.1f} 秒...")
                                time.sleep(wait_time)
                        else:
                            logger.warning(f"[{params['browser_name']}] 不在视频页面，退出操作循环")
                            break
                            
                    except Exception as e:
                        logger.error(f"[{params['browser_name']}] 评论操作失败: {e}")
                        import traceback
                        logger.error(f"[{params['browser_name']}] 错误堆栈:\n{traceback.format_exc()}")
                        time.sleep(2)
                        continue
                
                # 更新统计文件（在操作完成后）
                _update_stats_file(stats_file_path, session_date_label, total_like_count, total_follow_count, params['browser_name'])
                
                # 步骤4: 恢复播放视频
                logger.debug(f"[{params['browser_name']}] 步骤4: 恢复播放视频...")
                # 使用播放线程来播放视频
                mark_need_play(params['browser_name'])
                # 通知监控器视频已恢复播放，避免监控器误判并立即暂停
                monitor_mark_resume(params['browser_name'])
                # 更新监控器中的poster，保持状态同步
                if initial_poster:
                    monitor_update_poster(params['browser_name'], initial_poster)
                time.sleep(1)

                # 步骤5: 等待视频播放完成（参考另一个循环的稳定停止逻辑）
                logger.info(f"[{params['browser_name']}] 步骤5: 等待视频播放完成...")
                max_wait_time = 300  # 最多等待5分钟
                wait_start = time.time()
                check_count = 0
                now_video_poster_url = initial_poster
                
                # 启动视频状态监控
                start_monitoring(params['browser_name'])
                logger.debug(f"[{params['browser_name']}] 视频状态监控已启动")

                def check_video_change():
                    return _get_video_poster(driver)

                shutdown_event = params.get('shutdown_event')
                while (time.time() - wait_start) < max_wait_time:
                    # 检查退出标志
                    if shutdown_event and shutdown_event.is_set():
                        logger.info(f"[{params['browser_name']}] 收到退出信号，退出等待循环")
                        break
                    # 检查暂停状态
                    if is_paused(params['browser_name']):
                        logger.warning(f"[{params['browser_name']}] 检测到暂停标志，等待恢复...")
                        remaining_time = max_wait_time - (time.time() - wait_start)
                        wait_timeout = min(max(remaining_time, 0.0), 30.0)
                        recovered, updated_poster = _recover_video_from_pause(
                            driver,
                            params['browser_name'],
                            wait_timeout=wait_timeout,
                            check_video_change=check_video_change
                        )
                        if updated_poster:
                            now_video_poster_url = updated_poster
                        if recovered:
                            logger.info(f"[{params['browser_name']}] 暂停后已通过视频交换恢复")
                        else:
                            logger.warning(f"[{params['browser_name']}] 恢复失败，继续监控")
                    
                    time.sleep(0.3)
                    check_count += 1
                    # 循环中周期性校验URL（每10次约3秒一次）
                    if check_count % 10 == 0:
                        try:
                            _ensure_on_url(driver, video_url)
                        except Exception:
                            pass

                    # 1) 检查poster是否变化（优先且高频）
                    try:
                        check_poster = check_video_change()
                        if check_poster and check_poster != now_video_poster_url:
                            logger.info(f"[{params['browser_name']}] ✓ 视频播放完成，检测到新视频（检查{check_count}次）")
                            break
                    except Exception:
                        pass

                    # 2) 检查是否出现重播按钮
                    try:
                        replay_button = driver.find_element(By.CLASS_NAME, 'replay-btn')
                        if replay_button and replay_button.is_displayed():
                            logger.info(f"[{params['browser_name']}] ✓ 检测到重播按钮，视频播放完成（检查{check_count}次）")
                            break
                    except NoSuchElementException:
                        pass
                    except Exception:
                        pass

                    # 3) 周期性检查是否存在“下一个视频”按钮；若不存在且poster未变，再二次确认
                    if check_count % 10 == 0:
                        try:
                            def check_has_next_video():
                                try:
                                    video_area_element = driver.find_element(By.CSS_SELECTOR, '.video-container-player.video-area.vertical')
                                    try:
                                        switch_item = video_area_element.find_element(By.CSS_SELECTOR, '.switch-item.video-switch-next')
                                        return True
                                    except NoSuchElementException:
                                        return False
                                except:
                                    return False
                            has_next = check_has_next_video()
                            if not has_next:
                                current_check_poster = check_video_change()
                                if current_check_poster == now_video_poster_url:
                                    time.sleep(2)
                                    final_check_poster = check_video_change()
                                    if final_check_poster == now_video_poster_url:
                                        logger.info(f"[{params['browser_name']}] 无下一个视频且poster未变，判定播放完成")
                                        break
                        except Exception:
                            pass

                else:
                    logger.warning(f"[{params['browser_name']}] ⚠ 达到最大等待时间 {max_wait_time} 秒，继续下一个URL")
                
                logger.info(f"[{params['browser_name']}] ✓ 第 {url_index} 个视频URL处理完成\n")
                try:
                    url_queue.task_done()
                except Exception:
                    pass
                
            except Exception as e:
                logger.error(f"[{params['browser_name']}] ✗ 处理第 {url_index} 个视频URL时发生错误: {e}")
                logger.exception(f"[{params['browser_name']}] 处理第 {url_index} 个视频URL时的异常堆栈")
                # 继续处理下一个URL
                try:
                    url_queue.task_done()
                except Exception:
                    pass
                continue
        
        logger.debug(f"\n[{params['browser_name']}] {'='*60}")
        logger.info(f"[{params['browser_name']}] 所有视频URL处理完成")
        logger.debug(f"[{params['browser_name']}] 累计点赞: {total_like_count}")
        logger.debug(f"[{params['browser_name']}] 累计关注: {total_follow_count}")
        logger.debug(f"[{params['browser_name']}] {'='*60}\n")
        
        # URL列表模式完成后不关闭浏览器，让浏览器继续运行
        logger.info(f"[{params['browser_name']}] 所有视频URL处理完成，浏览器继续运行")
        
    except KeyboardInterrupt:
        logger.debug(f"\n[{params['browser_name']}] 用户中断，停止处理")
        # 用户中断时不关闭浏览器，让浏览器继续运行
    except Exception as e:
        logger.error(f"\n[{params['browser_name']}] 执行过程中发生错误: {e}")
        logger.exception(f"[{params['browser_name']}] 执行过程中发生错误的异常堆栈")
        # 发生错误时不关闭浏览器，继续运行
    finally:
        # 停止并移除视频状态监控器（使用 browser_id 而不是 browser_name）
        browser_id = params.get('id') or params['browser_name']
        stop_monitoring(browser_id)
        remove_monitor(browser_id)
        cluster.remove_browser(browser_id)
        # 从暂停管理列表移除
        unregister_browser_for_pause(browser_id)
        if len(cluster.browsers) == 1:
            # 注销全局刷新监控器
            monitor_unregister_browser(browser_id)

def _random_search_keyword(params: dict, now_search_keywords: Optional[str]) -> Optional[str]:
    """
    随机选择一个尚未使用过的关键词。
    每个关键词仅可使用一次，用完即不可再用。
    """
    logger.debug(f"[{params['browser_name']}] 开始选择搜索关键词（当前关键词: {now_search_keywords}）")
    # 初始化剩余可用关键词列表（仅首次执行）
    remaining_key = '_remaining_search_keywords'
    if remaining_key not in params:
        original_keywords = params.get('search_keywords') or []
        params[remaining_key] = original_keywords.copy()
        random.shuffle(params[remaining_key])
        logger.debug(f"[{params['browser_name']}] 初始化剩余关键词列表，共 {len(params[remaining_key])} 个")
    remaining_keywords = params.get(remaining_key, [])
    if not remaining_keywords:
        logger.warning(f"[{params['browser_name']}] 搜索关键词已全部使用完毕，将不再执行新的搜索")
        return None

    search_keyword = remaining_keywords.pop()
    params[remaining_key] = remaining_keywords
    logger.info(f"[{params['browser_name']}] 关键词已更新: {search_keyword}（剩余 {len(remaining_keywords)} 个）")
    return search_keyword

def _search_and_click_video(driver, browser, params: dict, search_keyword: str):
    """搜索和点击视频逻辑，只做有限次数重试，不再重启浏览器"""
    search_click_success = False

    # 先尝试固定次数的搜索和点击
    for attempt in range(3):
        try:
            logger.debug(f"[{params['browser_name']}] 尝试搜索和点击视频 (第 {attempt + 1}/3 次)")
            # 执行搜索
            logger.debug(f"[{params['browser_name']}] 开始执行搜索操作，关键词: {search_keyword}")
            kuaishou_search(driver, search_keyword, browser)
            logger.info(f"[{params['browser_name']}] 搜索操作完成，开始点击视频")

            # 检查driver是否有效
            if not driver:
                logger.error(f"[{params['browser_name']}] 浏览器驱动无效，不再重启浏览器，结束当前任务")
                break

            click_result = click_video(driver)
            if click_result:
                logger.info(f"[{params['browser_name']}] ✓ 点击视频成功")
                search_click_success = True
                break
            else:
                logger.error(f"[{params['browser_name']}] ✗ 点击视频失败 (第 {attempt + 1}/3 次)")
        except Exception as e:
            logger.error(f"[{params['browser_name']}] ✗ 搜索或点击操作异常 (第 {attempt + 1}/3 次): {e}")
            # 检查driver是否仍然有效
            try:
                driver.current_url
            except Exception:
                logger.error(f"[{params['browser_name']}] 浏览器驱动已失效，不再重启浏览器，结束当前任务")
                break

    # 如果最终还是没有成功，结束任务
    if not search_click_success:
        logger.error(f"[{params['browser_name']}] ✗ 多次尝试后搜索和点击仍然失败，不再重启浏览器，结束当前任务")
        return

def check_button(driver, params: dict):
    """版本过低按钮或重试按钮是否可见"""
    # 判断 点击重试 按钮是否可见
    logger.debug(f"[{params['browser_name']}] 检查是否存在按钮...")
    try:
        retry_button_visible = driver.find_element(By.CLASS_NAME, 'retry-btn')
        if retry_button_visible.is_displayed():
            logger.info(f"[{params['browser_name']}] 发现按钮，执行点击")
            retry_button_visible.click()
            logger.info(f"[{params['browser_name']}] 点击按钮成功")
        else:
            logger.debug(f"[{params['browser_name']}] 按钮存在但不可见")
    except NoSuchElementException:
        logger.debug(f"[{params['browser_name']}] 未找到按钮（正常情况）")
        pass
    except Exception as e:
        logger.error(f"[{params['browser_name']}] 检查按钮时发生错误: {e}")

def _get_comment_element(driver, params: dict):
    """获取评论区元素"""
    if 'short-video' not in driver.current_url:
        logger.debug(f"[{params['browser_name']}] 当前URL不在视频页面，无法获取评论区元素")
        return None
    try:
        return driver.find_element(By.CLASS_NAME, 'short-video-info-container')
    except Exception as e:
        logger.error(f"[{params['browser_name']}] 获取评论区元素失败: {e}")
        return None


def _extract_user_id_from_comment(comment_text: str) -> str:
    """
    从评论文本中提取用户ID
    评论文本格式示例: '苦橙雨䇝 1月前\n前排，前排\n1'
    Args:
        comment_text: 评论文本
    Returns:
        str: 用户ID，如果提取失败返回空字符串
    """
    try:
        # 按换行符分割，取第一行
        first_line = comment_text.split('\n')[0].strip()
        if not first_line:
            return ""
        
        # 第一行格式通常是: "用户ID 时间信息" 或 "用户ID"
        # 尝试去掉时间信息（如 "1月前"、"2小时前" 等）
        # 时间信息通常在空格后面
        parts = first_line.split()
        if len(parts) > 1:
            # 检查最后一部分是否是时间信息（包含"前"、"月"、"小时"、"天"等）
            last_part = parts[-1]
            if any(keyword in last_part for keyword in ['前', '月', '小时', '天', '分钟', '秒']):
                # 去掉时间部分，返回用户ID
                user_id = ' '.join(parts[:-1])
                return user_id.strip()
        
        # 如果没有时间信息，直接返回第一行
        return first_line.strip()
    except Exception as e:
        logger.debug(f"提取用户ID失败: {e}")
        return ""


def _video_single_operation(driver, comment_elements:list, params: dict) -> tuple[bool, ActionType | None]:
    """
    视频单次操作(时间版本)
    Args:
        driver: 浏览器
        comment_elements: list评论区列表
        params: 参数
            comment_filter_keywords: 优先关注评论关键词列表，如果评论中包含这些关键词则优先关注
            followed_user_ids: 当前视频已关注的用户ID集合（set），用于避免重复关注同一用户
    return:
        tuple[bool, ActionType | None]: (操作是否成功, 操作类型)
    """
    try:
        
        # 获取累计关注数（从params中获取，如果没有则默认为0）
        total_follow_count = params.get('total_follow_count', 0)
        max_follow_count = params.get('follow_count', 100)
        
        selected_comment = None
        is_priority_comment = False
        
        # 获取当前视频已关注的用户ID集合（如果不存在则创建）
        followed_user_ids = params.get('followed_user_ids', set())
        if not isinstance(followed_user_ids, set):
            followed_user_ids = set()
            params['followed_user_ids'] = followed_user_ids
        
        # 特定评论优先关注（支持多个关键词列表）
        comment_filter_keywords = params.get('comment_filter_keywords', [])
        if comment_filter_keywords:
            for comment_element in comment_elements:
                try:
                    comment_text = comment_element.text
                    # 提取用户ID
                    user_id = _extract_user_id_from_comment(comment_text)
                    
                    # 如果该用户已经被关注过，跳过
                    if user_id and user_id in followed_user_ids:
                        logger.debug(f"[{params['browser_name']}] 用户 {user_id} 已被关注，跳过")
                        continue
                    
                    # 检查评论是否包含任何一个关键词
                    for keyword in comment_filter_keywords:
                        if keyword and keyword in comment_text:
                            # 找到匹配的评论且用户未被关注
                            selected_comment = comment_element
                            is_priority_comment = True
                            logger.info(f"[{params['browser_name']}] 找到特定评论（关键词: {keyword}，用户: {user_id}），将执行关注操作")
                            break
                    if is_priority_comment:
                        break
                except Exception as e:
                    logger.error(f"[{params['browser_name']}] 获取优先评论失败: {e}")
                    continue
            
            # 如果找到特定评论但已达到关注上限，不执行操作
            if is_priority_comment and total_follow_count >= max_follow_count:
                logger.warning(f"[{params['browser_name']}] 找到特定评论但已达到关注上限({total_follow_count}/{max_follow_count})，跳过本次操作")
                return False, None

        # 如果没有找到特定评论，从可见评论中随机选择
        if not selected_comment:
            # 获取可见评论（使用 is_element_visible 判断元素是否真正在视口中可见）
            visible_comments = is_element_visible(driver, comment_elements)
            
            # 如果没有可见评论，返回False
            if not visible_comments:
                logger.warning(f"[{params['browser_name']}] 没有可见评论，跳过本次操作")
                return False, None
            
            # 从可见评论中随机选择一个
            random_index = random.randint(0, len(visible_comments) - 1)
            selected_comment = visible_comments[random_index]
        
        # 滚动到选中的评论，确保它在可视区域内
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", selected_comment)
            time.sleep(random.uniform(0.2, 0.4))
        except Exception as e:
            logger.debug(f"[{params['browser_name']}] 滚动到评论失败: {e}")
        
        # 决定操作类型（点赞或关注）
        # 如果有特定评论，强制执行关注操作（除非达到上限，但已在上面处理）
        if is_priority_comment:
            action_type = ActionType.FOLLOW
        elif total_follow_count >= max_follow_count:
            # 如果达到关注上限，只执行点赞操作
            action_type = ActionType.LIKE
        else:
            # 点赞与关注的比例（3:1）
            LIKE_FOLLOW_RATIO = 3.0
            # 点赞概率 = 3/(3+1) = 0.75
            like_probability = LIKE_FOLLOW_RATIO / (LIKE_FOLLOW_RATIO + 1.0)
            # 根据比例随机选择操作
            if random.random() < like_probability:
                action_type = ActionType.LIKE
            else:
                action_type = ActionType.FOLLOW
        
        # 执行相应操作
        if action_type == ActionType.LIKE:
            # 执行点赞操作
            logger.debug(f"[{params['browser_name']}] 执行评论点赞操作...")
            try:
                if 'short-video' in driver.current_url:
                    # 获取点赞按钮
                    like_element = selected_comment.find_element(By.CLASS_NAME, 'comment-item-likeicon')
                    # 点击点赞按钮
                    safe_click(driver, like_element)
                    # 等待一下，让点赞操作生效
                    time.sleep(0.5)
                    logger.info(f"[{params['browser_name']}] ✓ 点赞操作完成")
                    # log2.info(
                    #     {
                    #         "code": 0,
                    #         "data": {
                    #             "type": "like",
                    #             "id": config.DEVICE_CODE,
                    #         },
                    #     }
                    # )
                    return True, ActionType.LIKE
                return False, None
            except Exception as e:
                logger.error(f"[{params['browser_name']}] 点赞操作失败: {e}")
                return False, None
        elif action_type == ActionType.FOLLOW:
            # 执行关注操作
            logger.debug(f"[{params['browser_name']}] 执行评论关注操作...")
            # 保存当前窗口句柄（视频页面），在 try 块之前初始化，确保在 except 块中可用
            original_handle = None
            try:
                if 'short-video' in driver.current_url:
                    # 获取作者名称元素
                    author_name_element = selected_comment.find_element(By.CLASS_NAME, 'author-name')
                    # 从 author-name 元素获取用户ID（最准确的方式）
                    user_id = author_name_element.text.strip() if author_name_element else ""
                    if not user_id:
                        # 如果无法从 author-name 获取，尝试从评论文本中提取
                        try:
                            comment_text = selected_comment.text
                            user_id = _extract_user_id_from_comment(comment_text)
                        except Exception as e:
                            logger.debug(f"[{params['browser_name']}] 从评论文本提取用户ID失败: {e}")
                else:
                    return False, None
                # 保存当前窗口句柄（视频页面）
                original_handle = driver.current_window_handle
                # 点击作者名称，打开个人资料页面
                safe_click(driver, author_name_element)
                time.sleep(1)
                
                # 切换到新打开的标签页
                window_handles = driver.window_handles
                for handle in window_handles:
                    if handle != original_handle:
                        driver.switch_to.window(handle)
                        break
                
                # 等待页面加载
                time.sleep(2)
                
                # 查找并点击关注按钮
                follow_success = False
                already_followed = False  # 标记是否已关注
                try:
                    follow_button = driver.find_element(By.CLASS_NAME, 'btn-words')
                    if follow_button.is_displayed() and follow_button.text == '关注':
                        safe_click(driver, follow_button)
                        time.sleep(3)
                        follow_success = True
                        logger.info(f"[{params['browser_name']}] ✓ 关注操作完成")
                        # log2.info(
                        #     {
                        #         "code": 0,
                        #         "data": {
                        #             "type": "comment",
                        #             "id": config.DEVICE_CODE,
                        #         },
                        #     }
                        # )
                    else:
                        # 关注按钮不可见或已关注
                        already_followed = True
                        logger.info(f"[{params['browser_name']}] 关注按钮不可见或已关注")
                except Exception as e:
                    logger.warning(f"[{params['browser_name']}] 查找关注按钮失败: {e}")
                
                # 无论关注是否成功，只要能够获取到用户ID，都应该将其添加到已关注列表中
                # 这样可以避免重复尝试关注同一个用户
                if user_id:
                    followed_user_ids = params.get('followed_user_ids', set())
                    if not isinstance(followed_user_ids, set):
                        followed_user_ids = set()
                        params['followed_user_ids'] = followed_user_ids
                    
                    if user_id not in followed_user_ids:
                        followed_user_ids.add(user_id)
                        if follow_success:
                            logger.info(f"[{params['browser_name']}] 已记录用户ID: {user_id}，当前视频已关注 {len(followed_user_ids)} 个用户")
                        elif already_followed:
                            logger.info(f"[{params['browser_name']}] 用户 {user_id} 已关注，已添加到关注列表，当前视频已关注 {len(followed_user_ids)} 个用户")
                        else:
                            logger.info(f"[{params['browser_name']}] 关注失败，但已记录用户ID: {user_id}，避免重复尝试，当前视频已关注 {len(followed_user_ids)} 个用户")
                    else:
                        logger.debug(f"[{params['browser_name']}] 用户 {user_id} 已在关注列表中")
                
                # 关闭个人资料标签页
                if 'profile' in driver.current_url or driver.current_window_handle != original_handle:
                    driver.close()
                
                # 切换回原来的视频页面
                window_handles = driver.window_handles
                if original_handle in window_handles:
                    driver.switch_to.window(original_handle)
                elif window_handles:
                    # 如果原始窗口不存在，切换到第一个可用窗口
                    driver.switch_to.window(window_handles[0])
                
                if follow_success:
                    return True, ActionType.FOLLOW
                else:
                    # 即使关注失败，如果用户已关注或无法关注，也应该返回 False
                    # 但用户ID已经被记录到列表中，避免下次再尝试
                    return False, None
            except Exception as e:
                logger.error(f"[{params['browser_name']}] 关注操作失败: {e}")
                # 尝试切换回原窗口
                try:
                    # 关闭个人资料标签页
                    if 'profile' in driver.current_url or driver.current_window_handle != original_handle:
                        driver.close()
                    window_handles = driver.window_handles
                    if window_handles:
                        driver.switch_to.window(window_handles[0])
                except:
                    pass
                return False, None
        
        return False, None
    except Exception as e:
        logger.error(f"[{params['browser_name']}] 视频单次操作失败: {e}")
        return False, None

def _delete_extra_pages(driver, params: dict):
    """删除多余页面保留一个"""
    try:
        window_handles = driver.window_handles
        if len(window_handles) >= 2:
            # 保留第一个标签页，关闭其他多余的标签页
            logger.info(f"[{params['browser_name']}] 关闭多余标签页，如果报错可能是打开开发者工具")
            main_handle = window_handles[0]
            for handle in window_handles[1:]:
                try:
                    driver.switch_to.window(handle)
                    driver.close()
                except Exception as e:
                    logger.debug(f"[{params['browser_name']}] 关闭多余标签页失败: {e}")
                    # 如果关闭失败，继续处理下一个
                    continue
            # 切换回主标签页
            try:
                remaining_handles = driver.window_handles
                if main_handle in remaining_handles:
                    driver.switch_to.window(main_handle)
                elif remaining_handles:
                    # 如果主标签页不存在了，切换到第一个可用标签页
                    driver.switch_to.window(remaining_handles[0])
                else:
                    logger.warning(f"[{params['browser_name']}] 所有标签页都已关闭，无法继续")
                    return
                driver.get('https://www.kuaishou.com/')
                logger.info(f"[{params['browser_name']}] ✓ 浏览器驱动已初始化")
            except Exception as e:
                logger.error(f"[{params['browser_name']}] 切换回主标签页失败: {e}")
                # 检查是否还有可用的标签页
                try:
                    remaining_handles = driver.window_handles
                    if remaining_handles:
                        driver.switch_to.window(remaining_handles[0])
                        logger.info(f"[{params['browser_name']}] ✓ 已切换到可用标签页")
                    else:
                        logger.error(f"[{params['browser_name']}] 没有可用的标签页，无法继续")
                        return
                except Exception:
                    logger.error(f"[{params['browser_name']}] 浏览器会话已失效，无法继续")
                    return
        else:
            logger.info(f"[{params['browser_name']}] ✓ 浏览器驱动已初始化（标签页数量正常）")
    except Exception as e:
        logger.error(f"[{params['browser_name']}] 初始化浏览器标签页时发生错误: {e}")
        # 检查浏览器是否仍然有效
        try:
            driver.current_url
            logger.info(f"[{params['browser_name']}] 浏览器仍然有效，继续执行")
        except Exception:
            logger.error(f"[{params['browser_name']}] 浏览器会话已失效，无法继续")
            return

def scroll_comment(driver, comment_element):
    if 'short-video' in driver.current_url:
        driver.execute_script(f"arguments[0].scrollTop += 100;", comment_element)

def scroll_comment_to_bottom(driver, params: dict, comment_element, scroll_time: int, scroll_time_min: int, scroll_time_max: int):
    """
    Args:
        driver: Selenium WebDriver 对象
        params: 参数
        comment_element: 评论元素
        scroll_time: 滚动时间
        scroll_time_max: 每次滚动最大时间
        scroll_time_min: 每次滚动最小时间
    Returns:
        bool: 是否滚动到底部
    """
    start_time = time.time()
    while time.time() - start_time < scroll_time:
        try:
            scroll_comment(driver, comment_element)
            time.sleep(random.uniform(scroll_time_min, scroll_time_max))
        except Exception as e:
            logger.error(f"[{params['browser_name']}] 滚动评论区失败: {e}")
            continue
    return True

def _get_video_duration(driver) -> Tuple[Optional[float], Optional[float]]:
    """
    获取视频总时长和当前时长
    Returns:
        tuple: (总时长(秒), 当前时长(秒))，获取失败则返回(None, None)
    """
    try:
        if "short-video" in driver.current_url:
            # 获取总时长
            total_elem = driver.find_element(By.CSS_SELECTOR, "span.total")
            total_text = total_elem.text.strip()
            # 解析格式如 "01:23" 为秒数
            total_parts = total_text.split(":")
            total_seconds = None
            if len(total_parts) == 2:
                minutes, seconds = total_parts
                total_seconds = int(minutes) * 60 + int(seconds)
            
            # 获取当前时长
            current_elem = driver.find_element(By.CSS_SELECTOR, "span.current")
            current_text = current_elem.text.strip()
            current_parts = current_text.split(":")
            current_seconds = None
            if len(current_parts) == 2:
                minutes, seconds = current_parts
                current_seconds = int(minutes) * 60 + int(seconds)
            
            return (total_seconds, current_seconds)
        else:
            return (None, None)
    except Exception as e:
        logger.debug(f"[_get_video_duration] 获取时长失败: {e}")
        return (None, None)


def browser_video_loop(
    params: dict,  # 接收封装的参数字典
    browser
):
    """
    单个浏览器的刷视频循环任务
    Args:
        params:
            browser_name: 浏览器名称
            id: 浏览器id
            search_keywords: 搜索关键词列表
            comment_filter_keywords: 优先关注评论关键词列表，如果评论中包含这些关键词则优先关注
            main_loop_interval_min: 主流程最小间隔（秒）
            main_loop_interval_max: 主流程最大间隔（秒）
            action_interval_min: 操作最小间隔（秒）
            action_interval_max: 操作最大间隔（秒）
            scroll_interval_min: 滑动最小间隔（秒）
            scroll_interval_max: 滑动最大间隔（秒）
            videos_per_loop_min: 每轮最少刷视频数量，默认15个
            videos_per_loop_max: 每轮最多刷视频数量，默认30个
            follow_count: 最大关注数量上限，达到后只执行点赞操作，默认100
            comment_min_count: 每个视频最小操作次数，默认3次
            comment_max_count: 每个视频最大操作次数，默认5次
        browser: SeleniumBrowser 实例
    """
    driver = browser.driver
    if not driver:
        logger.error(f"[{params['browser_name']}] ✗ 浏览器驱动未初始化，跳过")
        return

    # log2.info(
    #             {
    #                 "code": 0,
    #                 "data": {
    #                     "type": "start",
    #                     "id": config.DEVICE_CODE
    #                 },
    #             }
    #         )

    # 删除多余页面保留一个
    _delete_extra_pages(driver, params)
    
    now_search_keywords = None
    # 统计本次任务期间的累计数据
    total_like_count = 0
    total_follow_count = 0
    # 文档记录：以日期为键（年月日）
    session_date_label = time.strftime("%Y年%m月%d日 %H:%M:%S")
    # 获取浏览器ID（如果有）
    browser_id = params.get('id')
    # 生成统计文件路径：记录/浏览器名字_id/启动浏览器名称_时间.txt
    stats_file_path = _get_stats_file_path(params['browser_name'], browser_id, session_date_label)
    logger.info(f"[{params['browser_name']}] 统计文件路径: {stats_file_path}")
    logger.debug(f"[{params['browser_name']}] 会话日期标签: {session_date_label}")
    # 启动时先写入/对齐一次
    _update_stats_file(stats_file_path, session_date_label, total_like_count, total_follow_count, params['browser_name'])
    loop_count = 0
    shutdown_event = params.get('shutdown_event')
    keywords_exhausted = False
    try:
        while True:
            if keywords_exhausted:
                logger.info(f"[{params['browser_name']}] 无可用搜索关键词，结束刷视频任务")
                break
            # 检查退出标志
            if shutdown_event and shutdown_event.is_set():
                logger.info(f"[{params['browser_name']}] 收到退出信号，停止主流程循环")
                break
            loop_count += 1
            logger.debug(f"\n[{params['browser_name']}] {'='*50}")
            logger.debug(f"[{params['browser_name']}] 开始第 {loop_count} 次主流程执行")
            logger.debug(f"[{params['browser_name']}] {'='*50}\n")
            logger.debug(f"[{params['browser_name']}] 代理: {browser.proxy}")
            # 当次主流程内统计
            loop_like_count = 0
            loop_follow_count = 0
            # 初始化视频计数（在try块外定义，以便在finally中使用）
            video_count = 0
            try:
                # ==================== 主流程 ====================
                logger.info(f"[{params['browser_name']}] 执行搜索和点击视频...")
                
                now_search_keywords = _random_search_keyword(params, now_search_keywords)
                if not now_search_keywords:
                    keywords_exhausted = True
                    logger.info(f"[{params['browser_name']}] 搜索关键词已耗尽，停止新的搜索流程")
                    # log2.info(
                    #         {
                    #             "code": 0,
                    #             "data": {
                    #                 "type": "exit",
                    #                 "id": config.DEVICE_CODE
                    #             },
                    #         }
                    #     )
                    break
                _search_and_click_video(driver, browser, params, now_search_keywords)
                time.sleep(1)
                if "short-video" not in driver.current_url:
                    logger.error(f"[{params['browser_name']}] ✗ 点击视频失败，当前URL不在视频页面")
                    # 不break，而是continue，继续下一次主流程循环
                    logger.info(f"[{params['browser_name']}] 等待10秒后继续下一次主流程...")
                    time.sleep(10)
                    continue
                else:
                    logger.info(f"[{params['browser_name']}] ✓ 点击视频完成")
                    # log2.info(
                    #         {
                    #             "code": 0,
                    #             "data": {
                    #                 "type": "search_keywords",
                    #                 "id": config.DEVICE_CODE,
                    #                 "search_keywords": now_search_keywords
                    #             },
                    #         }
                    #     )

                
                # ==================== 刷视频流程 ====================
                logger.debug(f"[{params['browser_name']}] 开始刷视频流程...")
                # 注册到全局刷新监控器（单线程最多5个浏览器，每个间隔0.05秒）
                # monitor_register_browser(params['browser_name'], driver)
                
                # 创建视频状态监控器
                check_interval = getattr(config, 'VIDEO_MONITOR_CHECK_INTERVAL', 1.0)
                paused_threshold = getattr(config, 'VIDEO_MONITOR_PAUSED_THRESHOLD', 3.0)
                progress_stall_threshold = getattr(config, 'VIDEO_MONITOR_PROGRESS_STALL_THRESHOLD', 5.0)
                monitor = create_monitor(
                    browser_name=params['browser_name'],
                    browser_id=params['id'],
                    driver=driver,
                    check_interval=check_interval,
                    paused_threshold=paused_threshold,
                    progress_stall_threshold=progress_stall_threshold,
                )

                # 检查版本过低按钮
                check_button(driver, params)
                # 评论区操作次数
                comment_operation_count = random.randint(params['comment_min_operation_count'], params['comment_max_operation_count'])
                # 计算本次主流程循环的持续时间
                main_loop_duration = random.uniform(params['main_loop_interval_min'], params['main_loop_interval_max'])
                start_time = time.time()
                logger.debug(f"[{params['browser_name']}] 主流程开始时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
                # 本轮视频上限：在 [videos_per_loop_min, videos_per_loop_max] 内随机
                loop_max_videos = random.randint(params['videos_per_loop_min'], params['videos_per_loop_max'])
                logger.debug(f"[{params['browser_name']}] 本次主流程将持续 {main_loop_duration/3600:.2f} 小时（{main_loop_duration:.0f}秒），开始执行操作...")
                logger.info(f"[{params['browser_name']}] 本轮随机刷视频上限: {loop_max_videos} 个\n")
                # 当前视频是否正在播放
                is_video_playing = False
                # 当前视频评论区本轮滑动次数
                current_video_scroll_count = 0
                # 标志变量：是否需要退出刷视频流程，回到主流程重新搜索
                should_exit_video_loop = False
                # 本轮视频计数（重置为0，因为每次主流程开始新的刷视频循环）
                video_count = 0
                now_video_poster_url = None
                old_video_poster_url = None
                # 评论区数量（用于判断是否操作）
                comment_elements_count = random.randint(params['comment_min_elements_count'], params['comment_max_elements_count'])
                video_operation_completed = False

                pause_manager_id = params.get('id')
                if not pause_manager_id:
                    logger.warning(f"[{params['browser_name']}] 缺少浏览器id，暂停/播放管理将被跳过")
                while main_loop_duration > (time.time() - start_time) and loop_max_videos > video_count:
                    time.sleep(1)
                    if "short-video" not in driver.current_url:
                        logger.error(f"[{params['browser_name']}] 不在视频页面，跳出循环")
                        break
                    last_current_duration = None  # 记录上一次的当前时长
                    # 当前视频的操作计数
                    current_video_action_count = 0
                    # 第一个视频
                    if now_video_poster_url is None:
                        now_video_poster_url = _get_video_poster(driver)
                        # 将浏览器加入暂停管理列表
                        _register_and_pause(driver, pause_manager_id)
                        video_count += 1
                        old_video_poster_url = now_video_poster_url
                        # 初始化当前视频的已关注用户ID集合
                        params['followed_user_ids'] = set()
                        logger.debug(f"[{params['browser_name']}] 新视频开始，初始化已关注用户ID集合")
                        
                    # 新视频暂停
                    if old_video_poster_url != now_video_poster_url and video_operation_completed:
                        # 将浏览器加入暂停管理列表
                        _register_and_pause(driver, pause_manager_id)
                        video_count += 1
                        old_video_poster_url = now_video_poster_url
                        video_operation_completed = False
                        # 初始化新视频的已关注用户ID集合
                        params['followed_user_ids'] = set()
                        logger.debug(f"[{params['browser_name']}] 切换到新视频，初始化已关注用户ID集合")

                    # 同一个视频播放
                    elif old_video_poster_url == now_video_poster_url and video_operation_completed:
                        # 同一个视频循环
                        if pause_manager_id and not is_need_play(pause_manager_id):
                            mark_need_play(pause_manager_id)
                        time.sleep(1)
                        total_seconds, old_current_seconds = _get_video_duration(driver)
                        if old_current_seconds is None:
                            logger.debug(f"[{params['browser_name']}] 无法获取上一帧进度，跳过本次播放完毕检测")
                            video_operation_completed = False
                            # log2.info(
                            #     {
                            #         "code": 0,
                            #         "data": {
                            #             "type": "video",
                            #             "id": config.DEVICE_CODE,
                            #         },
                            #     }
                            # )
                            continue
                        while old_video_poster_url == now_video_poster_url and video_operation_completed:
                            if pause_manager_id and not is_need_play(pause_manager_id):
                                mark_need_play(pause_manager_id)
                            time.sleep(0.5)
                            total_seconds, current_seconds = _get_video_duration(driver)
                            logger.debug(f"[{params['browser_name']}] 当前进度: {current_seconds} 秒/{total_seconds} 秒")
                            if current_seconds is None:
                                logger.debug(f"[{params['browser_name']}] 当前进度为空，结束本次检测循环")
                                break
                            if current_seconds < old_current_seconds:
                                now_video_poster_url = _get_video_poster(driver)
                                if old_video_poster_url == now_video_poster_url:
                                    should_exit_video_loop = True
                                    logger.info(f"[{params['browser_name']}] 视频已播放完毕，跳出循环")
                                    break
                            now_video_poster_url = _get_video_poster(driver)
                            # 不同视频跳出循环
                            if now_video_poster_url and now_video_poster_url != old_video_poster_url:
                                old_video_poster_url = now_video_poster_url
                                video_operation_completed =False
                                # log2.info(
                                #     {
                                #         "code": 0,
                                #         "data": {
                                #             "type": "video",
                                #             "id": config.DEVICE_CODE,
                                #         },
                                #     }
                                # )
                                break
                        if not video_operation_completed:
                            # 将浏览器加入暂停管理列表
                            _register_and_pause(driver, pause_manager_id)

                    if should_exit_video_loop:
                        break

                    time.sleep(4)

                    now_video_poster_url = _get_video_poster(driver)
                    # 操作次数未达到值跟视频未操作
                    while current_video_action_count <= comment_operation_count and not video_operation_completed:
                        try:
                            comment_elements: Optional[list[WebElement]] = None
                            # 评论区
                            comment_element = _get_comment_element(driver, params)
                            if comment_element:
                                logger.info(f"[{params['browser_name']}] 成功获取评论区元素")
                            else:
                                logger.error(f"[{params['browser_name']}] 无法获取评论区元素")
                                continue
                            if 'short-video' in driver.current_url:
                                comment_elements = comment_element.find_elements(By.CSS_SELECTOR, '.comment-item.comment-list-item.dark-mode')
                                # 滚动评论区判断是否到底部
                                if _check_comment_end_reached(driver):
                                    try:
                                        logger.info(f"[{params['browser_name']}] 评论区到底部，播放视频")
                                        # # 如果评论区数量少于一定值
                                        # if len(comment_elements) <= comment_elements_count:

                                        #     mark_need_play(pause_manager_id)
                                        # # 到底部，并且评论区数量小于一定值，播放视频
                                        # if pause_manager_id:
                                        #     logger.info(f"[{params['browser_name']}] 评论区到底部，且评论区数量小于一定值，播放视频")
                                        if pause_manager_id:
                                            mark_need_play(pause_manager_id)
                                        video_operation_completed = True
                                        break
                                    except Exception as e:
                                        video_operation_completed = False
                                        logger.error(f"[{params['browser_name']}] 播放视频失败: {e}")
                                        continue
                                else:
                                    # 未到底部，继续滚动评论区
                                    scroll_comment(driver, comment_element)
                                    time.sleep(random.uniform(0.5, 2))

                            # 视频单次操作
                            # 将当前累计关注数传递到params中
                            params_with_count = params.copy()
                            params_with_count['total_follow_count'] = total_follow_count
                            operation_success, action_type = _video_single_operation(driver, comment_elements or [], params_with_count)
                            if operation_success:
                                current_video_action_count += 1
                                
                                # 根据操作类型更新统计
                                if action_type == ActionType.LIKE:
                                    total_like_count += 1
                                elif action_type == ActionType.FOLLOW:
                                    total_follow_count += 1
                                
                                logger.info(f"[{params['browser_name']}] 视频单次操作完成，当前操作次数: {current_video_action_count}")
                                scroll_time = int(random.uniform(params['action_interval_min'], params['action_interval_max']))
                                scroll_comment_to_bottom(driver, params, comment_element, scroll_time, params['scroll_interval_min'], params['scroll_interval_max'])
                            # 纠正情况
                            else:
                                if 'short-video' not in driver.current_url:
                                    
                                    break
                                
                            if current_video_action_count >= comment_operation_count:
                                try:
                                    video_operation_completed = True
                                    if pause_manager_id:
                                        mark_need_play(pause_manager_id)
                                except Exception as e:
                                    video_operation_completed = False
                                    logger.error(f"[{params['browser_name']}] 播放视频失败: {e}")
                                    continue
                            else:
                                logger.debug(f"[{params['browser_name']}] 操作次数未达到值{current_video_action_count}")
                                continue
                        except Exception as e:
                            logger.error(f"[{params['browser_name']}] 评论操作失败: {e}")
                            continue
                    
                
            except KeyboardInterrupt:
                logger.info(f"[{params['browser_name']}] 用户中断，退出程序")
                raise
            except Exception as e:
                logger.error(f"[{params['browser_name']}] ✗ 主流程执行中发生错误: {e}")
                import traceback
                logger.error(f"[{params['browser_name']}] 错误堆栈:\n{traceback.format_exc()}")
                # 等待一段时间后继续下一次主流程
                logger.debug(f"[{params['browser_name']}] 等待10秒后继续下一次主流程...")
                time.sleep(10)
                continue
            finally:

                # 本次主流程的统计总结
                logger.debug(f"\n[{params['browser_name']}] {'='*50}")
                logger.info(f"[{params['browser_name']}] 本轮统计 | 点赞: {loop_like_count} | 关注: {loop_follow_count} | 视频数: {video_count}")
                logger.info(f"[{params['browser_name']}] 累计统计 | 点赞: {total_like_count} | 关注: {total_follow_count}")
                logger.debug(f"[{params['browser_name']}] {'='*50}\n")
                # 结束本轮后也进行一次同步（确保最新）
                logger.info(f"[{params['browser_name']}] 更新统计文件...")
                _update_stats_file(stats_file_path, session_date_label, total_like_count, total_follow_count, params['browser_name'])
                logger.info(f"[{params['browser_name']}] 统计文件更新完成")
                
    except KeyboardInterrupt:
        logger.debug(f"[{params['browser_name']}] 任务被中断")
    except Exception as e:
        logger.error(f"[{params['browser_name']}] ✗ 任务执行失败: {e}")
        import traceback
        logger.error(f"[{params['browser_name']}] 错误堆栈:\n{traceback.format_exc()}")
