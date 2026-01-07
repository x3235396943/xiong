#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
打开指定ID的比特浏览器并访问小红书链接，然后对评论进行遍历操作
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
from selenium.webdriver import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ..tools.config import XhsConfig, get_config
from ..tools.core import log, DataReporter
from .base import browse_search_results_and_operate, visit_video_and_operate, process_comments_sequentially, get_search_result_covers

# 初始化小红书配置
xhs_config = XhsConfig()

# 搜索关键词
KEYWORDS = xhs_config.KEYWORDS

# 视频浏览相关参数
DEFAULT_MAX_SCROLL_VIDEO = xhs_config.MAX_SCROLL_VIDEO
DEFAULT_MAX_COMMENT = xhs_config.MAX_COMMENT

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
BIT_BROWSER_IDS = xhs_config.BIT_BROWSER_IDS

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
import sys
from ..tools.license import LicenseManager, LicenseException
from ..tools.ws_client import create_websocket_client, start_websocket_client_in_thread

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
            raise KeyboardInterrupt("收到停止信号")
        time.sleep(min(0.1, end_time - time.time()))


def _ensure_not_stopped():
    if STOP_EVENT.is_set():
        raise KeyboardInterrupt("收到停止信号")


def _send_ws_message(message_dict):
    try:
        import json as _json
        try:
            log.info(f"发送到服务器的消息: {_json.dumps(message_dict, ensure_ascii=False, indent=2)}")
        except Exception:
            pass
        if not ws_client or ws_client.stop_requested:
            return
        loop = getattr(ws_client, "event_loop", None) or ws_loop
        if not loop or not loop.is_running():
            return
        import asyncio
        asyncio.run_coroutine_threadsafe(
            ws_client.send_queue.put(_json.dumps(message_dict, ensure_ascii=False)), loop
        )
    except Exception:
        pass


def _send_ws_message_for_reporter_search(message_dict):
    try:
        if isinstance(message_dict, dict) and message_dict.get("cmd") == "PcDataReq":
            data = message_dict.get("data")
            if isinstance(data, dict):
                data.pop("comment", None)
                data.pop("urlIndex", None)
                data.pop("urlOk", None)
                data.pop("urlFail", None)
            try:
                import json as _json
                log.info(f"PcDataReq 上报: {_json.dumps(message_dict, ensure_ascii=False, indent=2)}")
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
                await asyncio.wait_for(asyncio.get_event_loop().run_in_executor(None, pong_received.wait), timeout=5.0)
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
            ws_client.set_config_update_handler(lambda d: _handle_login_res_command({"data": d}))
            ws_thread = start_websocket_client_in_thread(ws_client, lambda: STOP_EVENT.set())
            ws_client.register_command_handler("HeartbeatRes", _handle_heartbeat_response)
            ws_client.register_command_handler("LoginRes", _handle_login_res_command)
            ws_loop = getattr(ws_client, "event_loop", None)
            if ws_loop and ws_loop.is_running():
                import asyncio
                heartbeat_task = asyncio.run_coroutine_threadsafe(_heartbeat_task(), ws_loop)
            # 发送登录请求
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(cfg.WS_URL)
            device_id = parse_qs(parsed.query).get("id", [cfg.DEVICE_CODE])[0]
            _send_ws_message({"cmd": "LoginReq", "id": device_id, "mode": "pc", "version": getattr(cfg, "VERSION", None)})
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
            ws_client.stop_requested = True
            loop = getattr(ws_client, "event_loop", None) or ws_loop
            if loop and loop.is_running():
                import asyncio
                asyncio.run_coroutine_threadsafe(ws_client.close(), loop)
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
        time.sleep(random.uniform(lo, hi))
    except Exception:
        time.sleep(0.5)


def parse_video_comments(raw: str):
    if not raw:
        return []
    parts = [x.strip() for x in str(raw).split("-&-")]
    return [x for x in parts if x]


def parse_keywords(raw):
    s = raw
    if not s:
        return KEYWORDS[:]
    try:
        if isinstance(s, str):
            t = s.strip()
            if not t:
                return KEYWORDS[:]
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
        return KEYWORDS[:]
    return KEYWORDS[:]


def clear_input(element):
    import sys
    from selenium.webdriver.common.keys import Keys
    if sys.platform == "win32":
        element.send_keys(Keys.CONTROL, "a")
    elif sys.platform == "darwin":
        element.send_keys(Keys.COMMAND, "a")
    else:
        element.send_keys(Keys.CONTROL, "a")
    element.send_keys(Keys.BACKSPACE)


def scroll_element_sync(driver, element, delta_y=400, sleep_time=2):
    import time
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
        scroll_origin = ScrollOrigin.from_element(element)
        ActionChains(driver).scroll_from_origin(scroll_origin, 0, delta_y).perform()
        time.sleep(sleep_time)
    except Exception as e:
        log.error(f"滚动失败: {e}")


def ensure_element_centered(driver, element):
    import time
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior: 'auto', block: 'center', inline: 'nearest'});",
            element,
        )
        time.sleep(0.3)
        return True
    except Exception:
        return False


def follow_user_if_needed(driver, timeout=8, sleep_after=True):
    """
    在小红书用户主页点击「关注」
    - 仅在未关注状态下点击
    - 自动判断按钮文案
    - 使用 JS click，稳定
    """

    try:
        follow_btn = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "button.reds-button-new.follow-button"
            ))
        )

        try:
            ensure_element_centered(driver, follow_btn)
        except Exception:
            pass

        btn_text = follow_btn.text.strip()
        log.info(f"[follow] 当前按钮文本: {btn_text}")

        # 已关注 / 互相关注 / 已请求
        if btn_text != "关注":
            log.info("[follow] 已是关注状态，跳过")
            return False

        # 模拟真人停顿
        time.sleep(0.6 + random.random())

        # JS 点击
        driver.execute_script("arguments[0].click();", follow_btn)
        log.info("[follow] 已点击关注")

        if sleep_after:
            time.sleep(1.2 + random.random())

        return True

    except Exception as e:
        log.error(f"[follow] 点击关注失败: {e}")
        return False


def activate_video_comment(driver, timeout=10):
    try:
        inner = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "div.inner")
            )
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            inner
        )
        time.sleep(0.3)

        # JS 点击，避免被 span 拦
        driver.execute_script("arguments[0].click();", inner)
        return True
    except Exception as e:
        log.error(f"激活视频评论失败: {e}")
        return False


def wait_content_textarea(driver, timeout=10):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(
            (By.ID, "content-textarea")
        )
    )


def input_and_send(driver, text):
    try:
        textarea = wait_content_textarea(driver)

        # 强制 focus（核心）
        driver.execute_script("arguments[0].focus();", textarea)
        time.sleep(0.2)

        # 清空
        driver.execute_script("arguments[0].innerText = '';", textarea)

        # 模拟人类输入
        for ch in text:
            textarea.send_keys(ch)
            time.sleep(random.uniform(0.06, 0.12))

        time.sleep(0.3)

        # 回车发送
        textarea.send_keys(Keys.ENTER)
        return True
    except Exception as e:
        log.error(f"输入并发送评论失败: {e}")
        return False


def send_video_comment(driver, text):
    if activate_video_comment(driver):
        return input_and_send(driver, text)
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
            headers=_BIT_HEADERS
        )
        result = response.json()
        return result
    except Exception as e:
        log.error(f"打开比特浏览器时出错: {e}")
        return {}


def scroll_to_load_more_comments(driver, count: int = 5, delta_y: int = 400, sleep_time: float = 2.0):
    log.info("尝试滚动以加载更多评论...")
    container = None
    try:
        container = driver.find_element(By.CSS_SELECTOR, "div.comments-container > div.list-container")
    except Exception:
        pass
    target = container
    if target is None:
        try:
            target = driver.find_element(By.TAG_NAME, "body")
        except Exception:
            target = None
    for i in range(count):
        if target is not None:
            scroll_element_sync(driver, target, delta_y=delta_y, sleep_time=sleep_time)
        else:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(sleep_time)
        log.info(f"第 {i + 1} 次滚动完成")


def process_single_keyword(driver, keyword, log_prefix="", reporter=None):
    wait_seconds = 10
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    driver.get("https://www.xiaohongshu.com")
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(1)
    
    log.info(f"{log_prefix} 搜索关键词: {keyword}")
    input_el = None
    btn_el = None
    for css in ["input.search-input", "input[placeholder*='搜索']", "input[autocomplete='off']"]:
        try:
            input_el = driver.find_element(By.CSS_SELECTOR, css)
            if input_el:
                break
        except Exception:
            continue
    if not input_el:
        log.warning(f"{log_prefix} [xhs] 未找到搜索输入框")
        return
    try:
        ensure_element_centered(driver, input_el)
    except Exception:
        pass
    try:
        clear_input(input_el)
    except Exception:
        pass
    input_el.click()
    time.sleep(0.2)
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(driver).send_keys(keyword).perform()
    time.sleep(0.2)
    for css in [".search-icon", "button.search-icon", "[class*='search'] svg"]:
        try:
            btn_el = driver.find_element(By.CSS_SELECTOR, css)
            if btn_el:
                break
        except Exception:
            continue
    if btn_el is not None:
        try:
            ensure_element_centered(driver, btn_el)
        except Exception:
            pass
        try:
            driver.execute_script("arguments[0].click();", btn_el)
        except Exception:
            btn_el.click()
    else:
        from selenium.webdriver.common.keys import Keys
        ActionChains(driver).send_keys(Keys.RETURN).perform()
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(1)
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        scroll_element_sync(driver, body, 400, 1.0)
    except Exception:
        pass
    log.info(f"{log_prefix} [xhs] 搜索完成: {keyword}")
    try:
        cfg = get_config()
        max_scroll_video = getattr(cfg, "MAX_SCROLL_VIDEO", None) or xhs_config.MAX_SCROLL_VIDEO
        items_to_visit = rand_int_range(max_scroll_video, 2, 3)
        browse_search_results_and_operate(driver, items_to_visit=items_to_visit, reporter=reporter, browser_id=browser_id)
    except Exception as e:
        log.error(f"{log_prefix} [xhs] 浏览并操作失败: {e}")


def process_search_keywords(driver, keywords, log_prefix="", browser_id=None):
    wait_seconds = 10
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    driver.get("https://www.xiaohongshu.com")
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(1)
    for kw in keywords:
        log.info(f"{log_prefix} 搜索关键词: {kw}")
        input_el = None
        btn_el = None
        for css in ["input.search-input", "input[placeholder*='搜索']", "input[autocomplete='off']"]:
            try:
                input_el = driver.find_element(By.CSS_SELECTOR, css)
                if input_el:
                    break
            except Exception:
                continue
        if not input_el:
            log.warning(f"{log_prefix} [xhs] 未找到搜索输入框")
            continue
        try:
            ensure_element_centered(driver, input_el)
        except Exception:
            pass
        try:
            clear_input(input_el)
        except Exception:
            pass
        input_el.click()
        time.sleep(0.2)
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(driver).send_keys(kw).perform()
        time.sleep(0.2)
        for css in [".search-icon", "button.search-icon", "[class*='search'] svg"]:
            try:
                btn_el = driver.find_element(By.CSS_SELECTOR, css)
                if btn_el:
                    break
            except Exception:
                continue
        if btn_el is not None:
            try:
                ensure_element_centered(driver, btn_el)
            except Exception:
                pass
            try:
                driver.execute_script("arguments[0].click();", btn_el)
            except Exception:
                btn_el.click()
        else:
            from selenium.webdriver.common.keys import Keys
            ActionChains(driver).send_keys(Keys.RETURN).perform()
        WebDriverWait(driver, max(10, wait_seconds)).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(1)
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            scroll_element_sync(driver, body, 400, 1.0)
        except Exception:
            pass
        log.info(f"{log_prefix} [xhs] 搜索完成: {kw}")
        try:
            cfg = get_config()
            max_scroll_video = getattr(cfg, "MAX_SCROLL_VIDEO", None) or xhs_config.MAX_SCROLL_VIDEO
            items_to_visit = rand_int_range(max_scroll_video, 2, 3)
            browse_search_results_and_operate(driver, items_to_visit=items_to_visit, browser_id=browser_id)
        except Exception as e:
            log.error(f"{log_prefix} [xhs] 浏览并操作失败: {e}")


def run_worker(browser_id, browser_number, kw_queue, kw_lock):
    log_prefix = get_browser_log_prefix(browser_id)
    
    log.info(f"{log_prefix} 开始执行小红书自动化任务")
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
        reporter = DataReporter(device_code=cfg.DEVICE_CODE, browser_id=browser_id, send_ws_message_func=_send_ws_message_for_reporter_search)
        _send_ws_message({"browserId": browser_id, "cmd": "RunStateReq", "id": cfg.DEVICE_CODE, "state": "running" if len(browser_id) == 32 else "error"})

        finished_normally = False
        try:
            license_manager.check_license_validity()
        except LicenseException:
            log.error(f"{log_prefix} 卡密无效，停止任务")
            return
        
        log.info(f"{log_prefix} 访问小红书搜索页面")
        driver.get("https://www.xiaohongshu.com")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(1)
        
        # 从队列中获取关键词并处理，直到队列为空
        while True:
            _ensure_not_stopped()
            try:
                license_manager.check_license_validity()
            except LicenseException:
                log.error(f"{log_prefix} 卡密无效，停止任务")
                break
            
            with kw_lock:
                kw = kw_queue.popleft() if kw_queue else None
            if not kw:
                log.info(f"{log_prefix} 所有关键词已处理完毕")
                try:
                    reporter.set_completed(True)
                except Exception:
                    pass
                break
            
            log.info(f"{log_prefix} 处理关键词: {kw}")
            try:
                reporter.set_keywords(kw)
            except Exception:
                pass
            # 处理单个关键词
            process_single_keyword(driver, kw, log_prefix, reporter)

        log.info(f"{log_prefix} 所有关键词处理完成，浏览器任务完成...")
        finished_normally = True

    except Exception as e:
        log.error(f"{log_prefix} 连接浏览器或访问链接时出现错误: {e}")
    finally:
        try:
            driver.quit()
        except:
            pass  # 如果driver没有成功初始化，忽略错误
        try:
            if finished_normally and not STOP_EVENT.is_set():
                reporter.set_completed(True)
        except Exception:
            pass
        try:
            reporter.force_report()
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
        browser_ids = BIT_BROWSER_IDS

    raw_env = os.getenv("KEYWORDS")
    keywords = parse_keywords(raw_env)
    
    # 如果配置中心有值，优先使用配置中心的值
    if hasattr(cfg, 'BIT_BROWSER_IDS') and cfg.BIT_BROWSER_IDS:
        browser_ids = cfg.BIT_BROWSER_IDS
    if hasattr(cfg, 'KEYWORDS') and cfg.KEYWORDS:
        keywords = cfg.KEYWORDS

    log.info(f"使用浏览器ID列表: {browser_ids}")
    log.info(f"使用关键词列表: {keywords}")

    if not browser_ids:
        log.error("没有配置浏览器ID，程序退出")
        _stop_ws_client()
        return

    if not keywords:
        log.error("没有配置关键词，程序退出")
        _stop_ws_client()
        return

    # 创建关键词队列和锁
    kw_queue = deque(keywords)
    kw_lock = threading.Lock()

    if len(browser_ids) <= 1:
        # 如果只有一个浏览器ID，直接运行
        run_worker(browser_ids[0], 1, kw_queue, kw_lock)
        _stop_ws_client()
        return

    if not license_manager.verify_license():
        log.error("卡密验证失败")
        _stop_ws_client()
        return
    
    license_manager.start_periodic_check()
    
    # 多线程执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(browser_ids)) as executor:
        futures = []
        for i, bid in enumerate(browser_ids):
            # 提交任务到线程池
            future = executor.submit(run_worker, bid, i + 1, kw_queue, kw_lock)
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
