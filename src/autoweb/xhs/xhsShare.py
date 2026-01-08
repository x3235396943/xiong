#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
打开指定ID的比特浏览器并访问小红书分享链接，然后对视频进行操作处理
"""

import json
import random
import time
import requests
import os
import concurrent.futures
import threading
from collections import deque
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ..tools.config import XhsConfig, get_config
from ..tools.core import log, DataReporter
from .base import visit_video_and_operate, process_comments_sequentially

import sys
from ..tools.license import LicenseManager, LicenseException
from ..tools.ws_client import create_websocket_client, start_websocket_client_in_thread

xhs_config = XhsConfig()

URLS = []


def extract_urls_from_text(text):
    """
    从文本中提取小红书URL
    """
    import re

    # 匹配小红书URL的正则表达式
    url_pattern = (
        r"https://www\.xiaohongshu\.com/(?:explore|discovery/item)/[a-zA-Z0-9\-_&=%?.]+"
    )
    urls = re.findall(url_pattern, text)
    return urls


def clean_urls(urls):
    """
    清洗URL列表，提取出有效的URL
    """
    cleaned_urls = []
    for item in urls:
        if item.startswith("http"):  # 如果已经是完整URL
            cleaned_urls.append(item)
        else:
            # 如果是包含URL的文本，尝试从中提取URL
            extracted = extract_urls_from_text(item)
            cleaned_urls.extend(extracted)
    return cleaned_urls


# 互动操作相关参数
LIKE_PROBABILITY = xhs_config.LIKE_PROBABILITY
VISIT_ENABLE = xhs_config.VISIT_ENABLE
PROFILE_FOLLOW_PROBABILITY = xhs_config.PROFILE_FOLLOW_PROBABILITY
DEFAULT_LIKE_WAIT_MIN = xhs_config.LIKE_WAIT_MIN
DEFAULT_LIKE_WAIT_MAX = xhs_config.LIKE_WAIT_MAX
DEFAULT_VISIT_MIN = xhs_config.VISIT_MIN
DEFAULT_VISIT_MAX = xhs_config.VISIT_MAX
DEFAULT_PROFILE_WAIT_MIN = xhs_config.COMMENT_WAIT_MIN
DEFAULT_PROFILE_WAIT_MAX = xhs_config.COMMENT_WAIT_MAX
VIDEO_REPLY_RATE = xhs_config.VIDEO_REPLY_RATE
VIDEO_REPLY_WAIT_MIN = xhs_config.VIDEO_REPLY_WAIT_MIN
VIDEO_REPLY_WAIT_MAX = xhs_config.VIDEO_REPLY_WAIT_MAX

# 新增：每条视频点赞和关注上限参数
MIN_FOLLOWS_PER_VIDEO = xhs_config.MIN_FOLLOWS_PER_VIDEO
MAX_FOLLOWS_PER_VIDEO = xhs_config.MAX_FOLLOWS_PER_VIDEO
COMMENT_LIKE_COUNT_MIN = xhs_config.COMMENT_LIKE_COUNT_MIN
COMMENT_LIKE_COUNT_MAX = xhs_config.COMMENT_LIKE_COUNT_MAX

# 视频评论内容列表
VIDEO_COMMENTS = xhs_config.VIDEO_COMMENTS

# 评论关键词过滤
COMMENT_FILTER_KEYWORDS = xhs_config.COMMENT_FILTER_KEYWORDS

# 是否启用功能
ENABLE_LIKE = xhs_config.ENABLE_LIKE
ENABLE_FOLLOW = xhs_config.ENABLE_FOLLOW
ENABLE_PROFILE_VISIT = xhs_config.ENABLE_PROFILE_VISIT
ENABLE_VIDEO_COMMENT = xhs_config.ENABLE_VIDEO_COMMENT
ENABLE_SEARCH_KEYWORDS = xhs_config.ENABLE_SEARCH_KEYWORDS
ENABLE_COMMENT_REPLY = xhs_config.ENABLE_COMMENT_REPLY

# 评论相关参数
COMMENT_REPLY_PROBABILITY = xhs_config.COMMENT_REPLY_PROBABILITY
COMMENT_WAIT_MIN = xhs_config.COMMENT_WAIT_MIN
COMMENT_WAIT_MAX = xhs_config.COMMENT_WAIT_MAX
COMMENT_REPLIES = xhs_config.COMMENT_REPLIES

# 导入日志系统相关模块

# 初始化许可证管理器
license_manager = LicenseManager()
STOP_EVENT = threading.Event()

# WebSocket客户端相关变量
ws_client = None
ws_thread = None
ws_loop = None
heartbeat_task = None
pong_received = threading.Event()
heartbeat_timeout_count = 0
MAX_HEARTBEAT_TIMEOUTS = 3


def _sleep_interruptible(seconds: float):
    end_time = time.time() + max(0.0, float(seconds))
    while time.time() < end_time:
        if STOP_EVENT.is_set():
            return False
        time.sleep(min(0.1, end_time - time.time()))
    return True


def _ensure_not_stopped():
    if STOP_EVENT.is_set():
        raise KeyboardInterrupt("收到停止信号")


def _send_ws_message(message_dict):
    try:
        import json as _json

        try:
            log.info(
                f"发送到服务器的消息: {_json.dumps(message_dict, ensure_ascii=False, indent=2)}"
            )
        except Exception:
            pass
        if not ws_client or ws_client.stop_requested:
            return
        loop = getattr(ws_client, "event_loop", None) or ws_loop
        if not loop or not loop.is_running():
            return
        import asyncio

        asyncio.run_coroutine_threadsafe(
            ws_client.send_queue.put(_json.dumps(message_dict, ensure_ascii=False)),
            loop,
        )
    except Exception:
        pass


def _send_ws_message_for_reporter_share(message_dict):
    try:
        if isinstance(message_dict, dict) and message_dict.get("cmd") == "PcDataReq":
            data = message_dict.get("data")
            if isinstance(data, dict):
                data.pop("comment", None)
            try:
                import json as _json

                log.info(
                    f"PcDataReq 上报: {_json.dumps(message_dict, ensure_ascii=False, indent=2)}"
                )
            except Exception:
                pass
    except Exception:
        pass
    _send_ws_message(message_dict)


def _handle_heartbeat_response(data: dict):
    global heartbeat_timeout_count
    try:
        if isinstance(data, dict) and data.get("cmd") == "HeartbeatRes":
            pong_received.set()
            heartbeat_timeout_count = 0
    except Exception:
        pass


def _handle_login_res_command(data: dict):
    try:
        if isinstance(data, dict) and data.get("cmd") in ("StopReq", "StopPubForce"):
            STOP_EVENT.set()
            cfg = get_config()
            cfg.request_stop()
            return
        if isinstance(data, dict) and "data" in data:
            cfg = get_config()
            cfg.update_from_dict(data.get("data", {}))
            if "SIBERIAN_URL" in data["data"]:
                license_manager.url = data["data"]["SIBERIAN_URL"]
            if "SIBERIAN_KEY" in data["data"]:
                license_manager.key = data["data"]["SIBERIAN_KEY"]
            if "DEVICE_CODE" in data["data"]:
                license_manager.code = data["data"]["DEVICE_CODE"]
    except Exception:
        pass


async def _heartbeat_task():
    global heartbeat_timeout_count
    import asyncio
    from datetime import datetime

    cfg = get_config()
    while not STOP_EVENT.is_set():
        try:
            _send_ws_message(
                {
                    "cmd": "HeartbeatReq",
                    "id": cfg.DEVICE_CODE,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, pong_received.wait),
                    timeout=5.0,
                )
                heartbeat_timeout_count = 0
                pong_received.clear()
            except asyncio.TimeoutError:
                heartbeat_timeout_count += 1
                if heartbeat_timeout_count >= MAX_HEARTBEAT_TIMEOUTS:
                    STOP_EVENT.set()
                    break
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            break
        except Exception:
            break


def _start_ws_client():
    global ws_client, ws_thread, ws_loop, heartbeat_task
    try:
        cfg = get_config()
        ws_client = create_websocket_client(cfg)
        if ws_client:
            ws_client.set_external_send_func(_send_ws_message)
            ws_client.set_config_update_handler(
                lambda d: _handle_login_res_command({"data": d})
            )
            ws_thread = start_websocket_client_in_thread(
                ws_client, lambda: (STOP_EVENT.set(), cfg.request_stop())
            )
            ws_client.register_command_handler(
                "HeartbeatRes", _handle_heartbeat_response
            )
            ws_client.register_command_handler("LoginRes", _handle_login_res_command)
            ws_loop = getattr(ws_client, "event_loop", None)
            if ws_loop and ws_loop.is_running():
                import asyncio

                heartbeat_task = asyncio.run_coroutine_threadsafe(
                    _heartbeat_task(), ws_loop
                )
            # 发送登录请求
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(cfg.WS_URL)
            device_id = parse_qs(parsed.query).get("id", [cfg.DEVICE_CODE])[0]
            _send_ws_message(
                {
                    "cmd": "LoginReq",
                    "id": device_id,
                    "mode": "pc",
                    "version": getattr(cfg, "VERSION", None),
                }
            )
    except Exception:
        pass


def _stop_ws_client():
    global ws_client, ws_thread, ws_loop, heartbeat_task
    try:
        if heartbeat_task:
            try:
                heartbeat_task.cancel()
            except Exception:
                pass
        if ws_client:
            loop = getattr(ws_client, "event_loop", None) or ws_loop
            if loop and loop.is_running():
                import asyncio

                async def _shutdown():
                    try:
                        if not getattr(ws_client, "stop_requested", False) and hasattr(
                            ws_client, "_wait_for_message_sent"
                        ):
                            try:
                                await ws_client._wait_for_message_sent(
                                    max_wait_time=1.5
                                )
                            except Exception:
                                pass
                    finally:
                        try:
                            await ws_client.close()
                        except Exception:
                            pass

                asyncio.run_coroutine_threadsafe(_shutdown(), loop)
        if ws_thread and ws_thread.is_alive():
            try:
                ws_thread.join(timeout=5.0)
            except Exception:
                pass
    except Exception:
        pass


def get_browser_log_prefix(browser_id):
    """生成浏览器日志前缀，格式为'浏览器 #编号'"""
    # 提取浏览器ID的最后几位作为编号
    browser_num = browser_id.split("-")[-1] if "-" in browser_id else browser_id[:8]
    return f"[浏览器 #{browser_num}]"


def rand_int_range(v, fallback_min=0, fallback_max=0):
    try:
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            a, b = int(v[0]), int(v[1])
            lo, hi = (a, b) if a <= b else (b, a)
            return random.randint(lo, hi)
    except Exception:
        pass
    return random.randint(int(fallback_min), int(fallback_max))


def rand_sleep(min_s, max_s):
    try:
        a, b = float(min_s), float(max_s)
        lo, hi = (a, b) if a <= b else (b, a)
        time.sleep(random.uniform(lo, hi) * 1.5)
    except Exception:
        time.sleep(0.5 * 1.5)


def parse_keywords(raw):
    s = raw
    if not s:
        return URLS[:]
    try:
        if isinstance(s, str):
            t = s.strip()
            if not t:
                return URLS[:]
            # 尝试按 JSON 列表解析
            try:
                data = json.loads(t)
                if isinstance(data, list):
                    return [str(x).strip() for x in data if str(x).strip()]
            except Exception:
                pass
            # 按常见分隔符解析
            for sep in [",", "，", ";", "；", " "]:
                t = t.replace(sep, ",")
            return [x.strip() for x in t.split(",") if x.strip()]
        elif isinstance(s, list):
            return [str(x).strip() for x in s if str(x).strip()]
    except Exception:
        return URLS[:]
    return URLS[:]


def ensure_element_centered(driver, element):
    import time

    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'auto', block: 'center', inline: 'nearest'});",
            element,
        )
        time.sleep(0.3 * 1.5)
        return True
    except Exception:
        return False


# 比特浏览器API配置
_BIT_API_URL = "http://127.0.0.1:54345"
_BIT_HEADERS = {"Content-Type": "application/json"}


def open_bit_browser(browser_id: str) -> dict:
    json_data = {"id": str(browser_id)}
    try:
        response = requests.post(
            f"{_BIT_API_URL}/browser/open",
            data=json.dumps(json_data),
            headers=_BIT_HEADERS,
        )
        result = response.json()
        return result
    except Exception as e:
        log.error(f"打开比特浏览器时出错: {e}")
        return {}


def process_single_url(driver, url, log_prefix=""):
    """
    处理单个小红书分享链接
    """
    # 清理浏览器句柄，确保只有小红书首页的界面
    if len(driver.window_handles) > 1:
        log.info(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
        for handle in driver.window_handles[1:]:
            driver.switch_to.window(handle)
            driver.close()
        driver.switch_to.window(driver.window_handles[0])
        log.info(f"{log_prefix} 已关闭额外窗口，保留主窗口")

    # 清洗单个URL
    cleaned_urls = clean_urls([url])

    if not cleaned_urls:
        log.warning(f"{log_prefix} URL清洗失败: {url}")
        return

    url = cleaned_urls[0]  # 获取清洗后的URL

    wait_seconds = 10
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    log.info(f"{log_prefix} 访问链接: {url}")
    try:
        driver.get(url)
        WebDriverWait(driver, max(10, wait_seconds)).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2 * 1.5)

        # 使用base模块中的方法对视频进行操作处理
        visit_video_and_operate(driver)

        log.info(f"{log_prefix} 链接 {url} 处理完成")
    except Exception as e:
        log.error(f"{log_prefix} 处理链接 {url} 时出现错误: {e}")

    # 在处理不同链接之间添加间隔
    _sleep_interruptible(2.0)


def process_share_urls(driver, urls, log_prefix=""):
    """
    处理小红书分享链接列表
    """
    # 清洗URL列表
    cleaned_urls = clean_urls(urls)

    wait_seconds = 10
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    # 清理浏览器句柄，确保只有小红书首页的界面
    if len(driver.window_handles) > 1:
        log.info(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
        for handle in driver.window_handles[1:]:
            driver.switch_to.window(handle)
            driver.close()
        driver.switch_to.window(driver.window_handles[0])
        log.info(f"{log_prefix} 已关闭额外窗口，保留主窗口")

    for url in cleaned_urls:
        log.info(f"{log_prefix} 访问链接: {url}")
        try:
            driver.get(url)
            WebDriverWait(driver, max(10, wait_seconds)).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2 * 1.5)

            # 使用base模块中的方法对视频进行操作处理
            visit_video_and_operate(driver)

            log.info(f"{log_prefix} 链接 {url} 处理完成")
        except Exception as e:
            log.error(f"{log_prefix} 处理链接 {url} 时出现错误: {e}")

        # 在处理不同链接之间添加间隔
        _sleep_interruptible(2.0)


def run_worker(browser_id, browser_number, url_queue, url_lock, total_count):
    log_prefix = get_browser_log_prefix(browser_id)

    log.info(f"{log_prefix} 开始执行小红书分享链接自动化任务")
    log.info(f"{log_prefix} 浏览器ID: {browser_id}")

    res = open_bit_browser(browser_id)

    if not res or "data" not in res:
        log.error(f"{log_prefix} 无法打开比特浏览器")
        return

    driver_path = res["data"].get("driver")
    debugger_address = res["data"].get("http")

    log.info(f"{log_prefix} 浏览器已成功打开")
    log.info(f"{log_prefix} 驱动路径: {driver_path}")
    log.info(f"{log_prefix} 调试地址: {debugger_address}")

    try:
        from selenium.webdriver.chrome.options import Options

        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", debugger_address)
        chrome_service = Service(driver_path)
        driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
        log.info(f"{log_prefix} WebDriver连接成功")

        cfg = get_config()
        reporter = DataReporter(
            device_code=cfg.DEVICE_CODE,
            browser_id=browser_id,
            send_ws_message_func=_send_ws_message_for_reporter_share,
        )
        if total_count:
            try:
                reporter.set_total_links(total_count)
            except Exception:
                pass
        _send_ws_message(
            {
                "browserId": browser_id,
                "cmd": "RunStateReq",
                "id": cfg.DEVICE_CODE,
                "state": "running" if len(browser_id) == 32 else "error",
            }
        )

        # 从队列中获取链接并处理，直到队列为空
        visited_count = 0
        while True:
            if STOP_EVENT.is_set():
                log.info(f"{log_prefix} 收到停止信号，退出任务")
                break
            try:
                license_manager.check_license_validity()
            except LicenseException:
                log.error(f"{log_prefix} 卡密无效，停止任务")
                break

            with url_lock:
                url = url_queue.popleft() if url_queue else None
            if not url:
                # 队列为空，表示所有URL都已处理完毕
                log.info(
                    f"{log_prefix} 所有URL已处理完毕，共处理 {visited_count} 个链接"
                )
                try:
                    reporter.set_completed(True)
                except Exception:
                    pass
                break

            log.info(f"{log_prefix} 处理链接: {url}")
            # 处理单个链接
            try:
                _ensure_not_stopped()

                # 清理浏览器句柄，确保只有小红书首页的界面
                if len(driver.window_handles) > 1:
                    log.info(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
                    for handle in driver.window_handles[1:]:
                        driver.switch_to.window(handle)
                        driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    log.info(f"{log_prefix} 已关闭额外窗口，保留主窗口")

                # 访问分享链接
                target_url = url
                if not isinstance(target_url, str):
                    target_url = str(target_url)
                target_url = target_url.strip()
                if not target_url.startswith("http"):
                    extracted = extract_urls_from_text(target_url)
                    target_url = extracted[0] if extracted else ""
                if not target_url.startswith("http"):
                    raise ValueError("未找到可用URL")

                driver.get(target_url)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(2 * 1.5)

                # 使用base模块中的方法对视频进行操作处理
                visit_video_and_operate(driver)

                log.info(f"{log_prefix} 链接 {url} 处理完成")
                visited_count += 1
                try:
                    reporter.update_url_index(visited_count)
                    reporter.increment_url_ok(1)
                except Exception:
                    pass
            except Exception as e:
                log.error(f"{log_prefix} 处理链接 {url} 时出现错误: {e}")
                try:
                    reporter.increment_url_fail(1)
                except Exception:
                    pass
                continue

            # 在处理不同链接之间添加间隔
            _sleep_interruptible(2.0)

        log.info(f"{log_prefix} 所有链接处理完成，浏览器任务完成...")

    except Exception as e:
        log.error(f"{log_prefix} 连接浏览器或访问链接时出现错误: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass  # 如果driver没有成功初始化，忽略错误
        try:
            if not STOP_EVENT.is_set():
                stats = reporter.get_stats()
                if (stats.get("urlOk", 0) + stats.get("urlFail", 0)) >= int(
                    total_count or 0
                ):
                    reporter.set_completed(True)
        except Exception:
            pass
        try:
            reporter.force_report()
        except Exception:
            pass
        try:
            reporter._stop_send_thread(flush_timeout=2.0)
        except Exception:
            pass
        log.info(f"{log_prefix} 浏览器已关闭，任务完成")


def main():
    cfg = get_config()
    license_manager.set_stop_callback(lambda: STOP_EVENT.set())
    _start_ws_client()
    try:
        cfg.wait_for_initialization()
    except TimeoutError as e:
        log.error(f"等待服务器配置初始化超时: {e}")
        _stop_ws_client()
        sys.exit(1)

    # 获取配置
    raw_env = os.getenv("BIT_BROWSER_IDS")
    if raw_env:
        browser_ids = parse_keywords(raw_env)  # 使用现有的关键词解析函数来解析浏览器ID
    else:
        browser_ids = xhs_config.BIT_BROWSER_IDS

    raw_env = os.getenv("URLS")
    urls = parse_keywords(raw_env)

    # 如果配置中心有URLS值，优先使用配置中心的值
    if hasattr(cfg, "URLS") and cfg.URLS:
        urls = cfg.URLS
    if hasattr(cfg, "BIT_BROWSER_IDS") and cfg.BIT_BROWSER_IDS:
        browser_ids = cfg.BIT_BROWSER_IDS
    urls = clean_urls(urls)

    log.info(f"使用浏览器ID列表: {browser_ids}")
    log.info(f"使用链接列表: {urls}")

    if not browser_ids:
        log.error("没有配置浏览器ID，程序退出")
        _stop_ws_client()
        return

    if not urls:
        log.error("没有配置链接，程序退出")
        _stop_ws_client()
        return

    # 创建链接队列和锁
    url_queue = deque(urls)
    url_lock = threading.Lock()

    if len(browser_ids) <= 1:
        # 如果只有一个浏览器ID，直接运行
        run_worker(browser_ids[0], 1, url_queue, url_lock, len(urls))
        _stop_ws_client()
        return

    if not license_manager.verify_license():
        log.error("卡密验证失败")
        _stop_ws_client()
        return

    license_manager.start_periodic_check()

    # 多线程执行
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(browser_ids)
    ) as executor:
        futures = []
        for i, bid in enumerate(browser_ids):
            # 提交任务到线程池
            future = executor.submit(
                run_worker, bid, i + 1, url_queue, url_lock, len(urls)
            )
            futures.append(future)
            # 间隔启动浏览器，避免同时启动造成资源竞争
            if i < len(browser_ids) - 1:
                time.sleep(2.5)

        # 等待所有任务完成
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()  # 获取执行结果，如有异常会抛出
            except LicenseException:
                log.error("卡密无效，取消剩余任务")
                STOP_EVENT.set()
                for fut in futures:
                    fut.cancel()
                break
            except Exception as e:
                log.error(f"[并发] 线程执行出错: {e}")

    license_manager.stop_periodic_check()
    _stop_ws_client()
    log.info("\n所有浏览器任务完成，程序退出...")


if __name__ == "__main__":
    main()
