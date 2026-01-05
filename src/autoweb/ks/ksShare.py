import json
import os
import random
import time
import sys
import concurrent.futures
import threading
from collections import deque
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..tools.core import log, DataReporter

from ..tools.config import KsConfig, get_config
from ..tools.ws_client import create_websocket_client, start_websocket_client_in_thread

from .base import KuaishouUtils
from ..tools.license import LicenseManager, LicenseException

# 初始化快手配置
ks_config = KsConfig()

# URL列表配置
URLS = ks_config.KS_SHARE_URLS if hasattr(ks_config, 'KS_SHARE_URLS') else [
    "https://www.kuaishou.com/f/X-2dKHX1NhEkj1oh",
    "https://www.kuaishou.com/f/X-8KhLhFzsM9CW34",
    "https://www.kuaishou.com/f/X-1XE4j64AuGQDfX",
    "https://www.kuaishou.com/f/X-8HoRGuDNGxP1C3",
    "https://www.kuaishou.com/f/X-6SBqfXzOVHjcHM",
    "https://www.kuaishou.com/f/X3qsaFh6BNsoDDo",
]

# 视频浏览相关参数
DEFAULT_MAX_VISIT_URLS = ks_config.MAX_VISIT_URLS if hasattr(ks_config, 'MAX_VISIT_URLS') else (5, 10)
DEFAULT_MAX_COMMENT = ks_config.MAX_COMMENT if hasattr(ks_config, 'MAX_COMMENT') else (3, 5)

# 互动操作相关参数
LIKE_PROBABILITY = ks_config.LIKE_PROBABILITY if hasattr(ks_config, 'LIKE_PROBABILITY') else 30
VISIT_ENABLE = ks_config.VISIT_ENABLE if hasattr(ks_config, 'VISIT_ENABLE') else True
PROFILE_FOLLOW_PROBABILITY = ks_config.PROFILE_FOLLOW_PROBABILITY if hasattr(ks_config, 'PROFILE_FOLLOW_PROBABILITY') else 10
DEFAULT_LIKE_WAIT_MIN = ks_config.LIKE_WAIT_MIN if hasattr(ks_config, 'LIKE_WAIT_MIN') else 1
DEFAULT_LIKE_WAIT_MAX = ks_config.LIKE_WAIT_MAX if hasattr(ks_config, 'LIKE_WAIT_MAX') else 3
DEFAULT_VISIT_MIN = ks_config.VISIT_MIN if hasattr(ks_config, 'VISIT_MIN') else 2
DEFAULT_VISIT_MAX = ks_config.VISIT_MAX if hasattr(ks_config, 'VISIT_MAX') else 5
DEFAULT_PROFILE_WAIT_MIN = ks_config.COMMENT_WAIT_MIN if hasattr(ks_config, 'COMMENT_WAIT_MIN') else 1
DEFAULT_PROFILE_WAIT_MAX = ks_config.COMMENT_WAIT_MAX if hasattr(ks_config, 'COMMENT_WAIT_MAX') else 3
VIDEO_REPLY_RATE = ks_config.VIDEO_REPLY_RATE if hasattr(ks_config, 'VIDEO_REPLY_RATE') else 15
VIDEO_REPLY_WAIT_MIN = ks_config.VIDEO_REPLY_WAIT_MIN if hasattr(ks_config, 'VIDEO_REPLY_WAIT_MIN') else 2
VIDEO_REPLY_WAIT_MAX = ks_config.VIDEO_REPLY_WAIT_MAX if hasattr(ks_config, 'VIDEO_REPLY_WAIT_MAX') else 4

# 新增：每条视频点赞和关注上限参数
MIN_FOLLOWS_PER_VIDEO = ks_config.MIN_FOLLOWS_PER_VIDEO if hasattr(ks_config, 'MIN_FOLLOWS_PER_VIDEO') else 0
MAX_FOLLOWS_PER_VIDEO = ks_config.MAX_FOLLOWS_PER_VIDEO if hasattr(ks_config, 'MAX_FOLLOWS_PER_VIDEO') else 2
COMMENT_LIKE_COUNT_MIN = ks_config.COMMENT_LIKE_COUNT_MIN if hasattr(ks_config, 'COMMENT_LIKE_COUNT_MIN') else 0
COMMENT_LIKE_COUNT_MAX = ks_config.COMMENT_LIKE_COUNT_MAX if hasattr(ks_config, 'COMMENT_LIKE_COUNT_MAX') else 3

# 视频评论内容列表
VIDEO_COMMENTS = ks_config.VIDEO_COMMENTS if hasattr(ks_config, 'VIDEO_COMMENTS') else [
    "这个视频不错！", 
    "内容很棒！", 
    "支持一下！", 
    "666", 
    "好看！"
]

DEFAULT_BIT_BROWSER_IDS = ks_config.BIT_BROWSER_IDS if hasattr(ks_config, 'BIT_BROWSER_IDS') else []

# 评论关键词过滤
COMMENT_FILTER_KEYWORDS = ks_config.COMMENT_FILTER_KEYWORDS if hasattr(ks_config, 'COMMENT_FILTER_KEYWORDS') else ""

# 是否启用功能
ENABLE_LIKE = ks_config.ENABLE_LIKE if hasattr(ks_config, 'ENABLE_LIKE') else True
ENABLE_FOLLOW = ks_config.ENABLE_FOLLOW if hasattr(ks_config, 'ENABLE_FOLLOW') else True
ENABLE_PROFILE_VISIT = ks_config.ENABLE_PROFILE_VISIT if hasattr(ks_config, 'ENABLE_PROFILE_VISIT') else True
ENABLE_VIDEO_COMMENT = ks_config.ENABLE_VIDEO_COMMENT if hasattr(ks_config, 'ENABLE_VIDEO_COMMENT') else True
ENABLE_SEARCH_KEYWORDS = ks_config.ENABLE_SEARCH_KEYWORDS if hasattr(ks_config, 'ENABLE_SEARCH_KEYWORDS') else False

DEFAULT_WAIT_TIME = ks_config.KS_DEFAULT_WAIT_TIME if hasattr(ks_config, 'KS_DEFAULT_WAIT_TIME') else 8
license_manager = LicenseManager()
STOP_EVENT = threading.Event()

ws_client = None
ws_thread = None
ws_loop = None
heartbeat_task = None
pong_received = threading.Event()
heartbeat_timeout_count = 0
MAX_HEARTBEAT_TIMEOUTS = 3

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

def _send_ws_message_for_reporter_share(message_dict):
    try:
        if isinstance(message_dict, dict) and message_dict.get("cmd") == "PcDataReq":
            data = message_dict.get("data")
            if isinstance(data, dict):
                data.pop("comment", None)
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

def _rng(name, d):
    s = (os.getenv(name) or "").strip()
    if not s:
        return d
    try:
        v = json.loads(s)
        if isinstance(v, list) and len(v) == 2:
            a, b = int(v[0]), int(v[1])
            return (a, b) if a <= b else (b, a)
    except Exception:
        pass
    return d

def _urls(d):
    s = (os.getenv("KS_SHARE_URLS") or "").strip()
    if not s:
        return d[:]
    try:
        v = json.loads(s)
        if isinstance(v, list):
            r = [str(x).strip() for x in v if str(x).strip()]
            return r or d[:]
    except Exception:
        pass
    for sep in ["\n", "\r", "\t", "，", ";", "；", " "]:
        s = s.replace(sep, ",")
    r = [x.strip() for x in s.split(",") if x.strip()]
    return r or d[:]

def parse_browser_ids():
    s = (os.getenv("BIT_BROWSER_IDS") or "").strip()
    if not s:
        return DEFAULT_BIT_BROWSER_IDS[:]
    try:
        v = json.loads(s)
        if isinstance(v, list):
            r = [str(x).strip() for x in v if str(x).strip()]
            return r or DEFAULT_BIT_BROWSER_IDS[:]
    except Exception:
        pass
    for sep in ["\n", "\r", "\t", "，", ";", "；", " "]:
        s = s.replace(sep, ",")
    r = [x.strip() for x in s.split(",") if x.strip()]
    return r or DEFAULT_BIT_BROWSER_IDS[:]

def _open_bit(browser_id):
    payload = {"id": str(browser_id), "queue": True, "ignoreDefaultUrls": True}
    if (os.getenv("HEADLESS") or "").strip().lower() in {"1", "true", "yes", "y"}:
        payload["args"] = ["--headless"]
    return requests.post(
        "http://127.0.0.1:54345/browser/open",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=30,
    ).json()

def _as_int_range(value, fallback):
    try:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            a, b = int(value[0]), int(value[1])
            return (a, b) if a <= b else (b, a)
    except Exception:
        pass
    return fallback

def _current_settings_share():
    cfg = get_config()
    wait_time = getattr(cfg, "WAIT_TIME", DEFAULT_WAIT_TIME) or DEFAULT_WAIT_TIME
    url_range = getattr(cfg, "MAX_VISIT_URLS", None)
    url_range = _as_int_range(url_range, _as_int_range(getattr(cfg, "MAX_SCROLL_VIDEO", None), DEFAULT_MAX_VISIT_URLS))
    comment_range = _as_int_range(getattr(cfg, "MAX_COMMENT", None), DEFAULT_MAX_COMMENT)
    return {
        "wait_time": int(wait_time),
        "url_range": url_range,
        "comment_range": comment_range,
        "like_probability": int(getattr(cfg, "LIKE_PROBABILITY", LIKE_PROBABILITY)),
        "visit_enable": int(getattr(cfg, "VISIT_ENABLE", VISIT_ENABLE)),
        "profile_follow_probability": int(getattr(cfg, "PROFILE_FOLLOW_PROBABILITY", PROFILE_FOLLOW_PROBABILITY)),
        "like_wait_range": _as_int_range([getattr(cfg, "LIKE_WAIT_MIN", DEFAULT_LIKE_WAIT_MIN), getattr(cfg, "LIKE_WAIT_MAX", DEFAULT_LIKE_WAIT_MAX)], (DEFAULT_LIKE_WAIT_MIN, DEFAULT_LIKE_WAIT_MAX)),
        "visit_wait_range": _as_int_range([getattr(cfg, "VISIT_MIN", DEFAULT_VISIT_MIN), getattr(cfg, "VISIT_MAX", DEFAULT_VISIT_MAX)], (DEFAULT_VISIT_MIN, DEFAULT_VISIT_MAX)),
        "profile_wait_range": _as_int_range([getattr(cfg, "COMMENT_WAIT_MIN", DEFAULT_PROFILE_WAIT_MIN), getattr(cfg, "COMMENT_WAIT_MAX", DEFAULT_PROFILE_WAIT_MAX)], (DEFAULT_PROFILE_WAIT_MIN, DEFAULT_PROFILE_WAIT_MAX)),
        "video_reply_rate": int(getattr(cfg, "VIDEO_REPLY_RATE", VIDEO_REPLY_RATE)),
        "video_reply_wait_range": _as_int_range([getattr(cfg, "VIDEO_REPLY_WAIT_MIN", VIDEO_REPLY_WAIT_MIN), getattr(cfg, "VIDEO_REPLY_WAIT_MAX", VIDEO_REPLY_WAIT_MAX)], (VIDEO_REPLY_WAIT_MIN, VIDEO_REPLY_WAIT_MAX)),
        "min_follows_per_video": int(getattr(cfg, "MIN_FOLLOWS_PER_VIDEO", MIN_FOLLOWS_PER_VIDEO)),
        "max_follows_per_video": int(getattr(cfg, "MAX_FOLLOWS_PER_VIDEO", MAX_FOLLOWS_PER_VIDEO)),
        "comment_like_count_min": int(getattr(cfg, "COMMENT_LIKE_COUNT_MIN", COMMENT_LIKE_COUNT_MIN)),
        "comment_like_count_max": int(getattr(cfg, "COMMENT_LIKE_COUNT_MAX", COMMENT_LIKE_COUNT_MAX)),
        "video_comments": getattr(cfg, "VIDEO_COMMENTS", VIDEO_COMMENTS),
        "comment_filter_keywords": getattr(cfg, "COMMENT_FILTER_KEYWORDS", COMMENT_FILTER_KEYWORDS),
        "enable_like": bool(getattr(cfg, "ENABLE_LIKE", ENABLE_LIKE)),
        "enable_follow": bool(getattr(cfg, "ENABLE_FOLLOW", ENABLE_FOLLOW)),
        "enable_profile_visit": bool(getattr(cfg, "ENABLE_PROFILE_VISIT", ENABLE_PROFILE_VISIT)),
        "enable_video_comment": bool(getattr(cfg, "ENABLE_VIDEO_COMMENT", ENABLE_VIDEO_COMMENT)),
        "enable_search_keywords": bool(getattr(cfg, "ENABLE_SEARCH_KEYWORDS", ENABLE_SEARCH_KEYWORDS)),
    }

def run_worker(browser_id, browser_number, url_queue, url_lock, total_count):
    log_prefix = get_browser_log_prefix(browser_id)

    settings = _current_settings_share()
    wait_time = settings["wait_time"]
    url_min, url_max = settings["url_range"]
    scroll_min, scroll_max = settings["comment_range"]
    like_prob = settings["like_probability"]
    visit_profile_prob = settings["visit_enable"]
    profile_follow_prob = settings["profile_follow_probability"]
    like_wait_min, like_wait_max = settings["like_wait_range"]
    visit_min, visit_max = settings["visit_wait_range"]
    profile_wait_min, profile_wait_max = settings["profile_wait_range"]
    video_comment_prob = settings["video_reply_rate"]
    video_comment_wait_min, video_comment_wait_max = settings["video_reply_wait_range"]
    min_follows_per_video = settings["min_follows_per_video"]
    max_follows_per_video = settings["max_follows_per_video"]
    comment_like_count_min = settings["comment_like_count_min"]
    comment_like_count_max = settings["comment_like_count_max"]
    enable_like = settings["enable_like"]
    enable_follow = settings["enable_follow"]
    enable_profile_visit = settings["enable_profile_visit"]
    enable_video_comment = settings["enable_video_comment"]
    enable_search_keywords = settings["enable_search_keywords"]
    comment_filter_keywords = settings["comment_filter_keywords"]
    video_comments = settings["video_comments"]
    like_count = 0
    follow_count = 0

    log.info(f"{log_prefix} 开始执行快手分享链接访问任务")
    log.info(f"{log_prefix} 浏览器ID: {browser_id}")
    log.info(f"{log_prefix} 等待时间: {wait_time}s")
    log.info(f"{log_prefix} 访问链接数量范围: {url_min}-{url_max}")
    log.info(f"{log_prefix} 评论滚动范围: {scroll_min}-{scroll_max}")
    log.info(f"{log_prefix} 点赞概率: {like_prob}%")
    log.info(f"{log_prefix} 访问主页概率: {visit_profile_prob}%")
    log.info(f"{log_prefix} 主页关注概率: {profile_follow_prob}%")
    log.info(f"{log_prefix} 点赞后等待时间范围: {like_wait_min}-{like_wait_max}s")
    log.info(f"{log_prefix} 关注后等待时间范围: {visit_min}-{visit_max}s")
    log.info(f"{log_prefix} 进入主页等待时间范围: {profile_wait_min}-{profile_wait_max}s")
    log.info(f"{log_prefix} 视频留言概率: {video_comment_prob}%")
    log.info(f"{log_prefix} 视频留言前等待时间范围: {video_comment_wait_min}-{video_comment_wait_max}s")
    log.info(f"{log_prefix} 每条视频最少关注数量: {min_follows_per_video}")
    log.info(f"{log_prefix} 每条视频最多关注数量: {max_follows_per_video}")
    log.info(f"{log_prefix} 每条视频最少点赞数量: {comment_like_count_min}")
    log.info(f"{log_prefix} 每条视频最多点赞数量: {comment_like_count_max}")

    res = _open_bit(browser_id)
    data = (res or {}).get("data") or {}
    if not data.get("driver") or not data.get("http"):
        raise RuntimeError(f"{log_prefix} 打开比特浏览器失败: {res}")

    log.info(f"{log_prefix} 比特浏览器打开成功")
    
    opt = webdriver.ChromeOptions()
    opt.add_experimental_option("debuggerAddress", data["http"])
    driver = webdriver.Chrome(service=Service(data["driver"]), options=opt)
    cfg = get_config()
    reporter = DataReporter(device_code=cfg.DEVICE_CODE, browser_id=browser_id, send_ws_message_func=_send_ws_message_for_reporter_share)
    try:
        reporter.set_total_links(total_count)
    except Exception:
        pass
    _send_ws_message({"browserId": browser_id, "cmd": "RunStateReq", "id": cfg.DEVICE_CODE, "state": "running" if len(browser_id) == 32 else "error"})

    def w(t=None):
        WebDriverWait(driver, t or max(8, wait_time)).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    try:
        try:
            license_manager.check_license_validity()
        except LicenseException:
            log.error(f"{log_prefix} 卡密无效，停止任务")
            return
        log.info(f"{log_prefix} 开始访问快手分享链接")
        # 清理浏览器句柄，确保只有快手首页的界面
        if len(driver.window_handles) > 1:
            log.info(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
            for handle in driver.window_handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
            log.info(f"{log_prefix} 已关闭额外窗口，保留主窗口")
        
        log.info(f"{log_prefix} 开始处理所有可用链接")
        
        visited_count = 0
        while True:  # 持续处理直到队列为空
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
                log.info(f"{log_prefix} 所有URL已处理完毕，共处理 {visited_count} 个链接")
                break
            
            log.info(f"{log_prefix} 访问链接: {url}")
            try:
                settings = _current_settings_share()
                wait_time = settings["wait_time"]
                url_min, url_max = settings["url_range"]
                scroll_min, scroll_max = settings["comment_range"]
                like_prob = settings["like_probability"]
                visit_profile_prob = settings["visit_enable"]
                profile_follow_prob = settings["profile_follow_probability"]
                like_wait_min, like_wait_max = settings["like_wait_range"]
                visit_min, visit_max = settings["visit_wait_range"]
                profile_wait_min, profile_wait_max = settings["profile_wait_range"]
                video_comment_prob = settings["video_reply_rate"]
                video_comment_wait_min, video_comment_wait_max = settings["video_reply_wait_range"]
                min_follows_per_video = settings["min_follows_per_video"]
                max_follows_per_video = settings["max_follows_per_video"]
                comment_like_count_min = settings["comment_like_count_min"]
                comment_like_count_max = settings["comment_like_count_max"]
                enable_like = settings["enable_like"]
                enable_follow = settings["enable_follow"]
                enable_profile_visit = settings["enable_profile_visit"]
                enable_video_comment = settings["enable_video_comment"]
                enable_search_keywords = settings["enable_search_keywords"]
                comment_filter_keywords = settings["comment_filter_keywords"]
                video_comments = settings["video_comments"]

                # 访问分享链接
                driver.get(url)
                w()
                w()
                time.sleep(2.0)
                
                # 等待页面加载完成
                try:
                    # 等待视频元素出现
                    WebDriverWait(driver, max(8, wait_time)).until(
                        lambda d: d.find_elements(By.CSS_SELECTOR, ".comment-item.comment-list-item.dark-mode")
                        or d.find_elements(By.CSS_SELECTOR, ".comment-item")
                    )
                except Exception:
                    time.sleep(1.0)
                
                # 根据概率决定是否进行视频留言
                if enable_video_comment and (random.random() * 100 <= video_comment_prob):
                    log.info(f"{log_prefix} 根据概率决定进行视频留言")
                    if KuaishouUtils.leave_video_comment(
                        driver,
                        video_comment_wait_min,
                        video_comment_wait_max,
                        log_prefix,
                        video_comments,
                    ):
                        try:
                            reporter.set_action("videoComment")
                            reporter.increment_video_comment(1)
                        except Exception:
                            pass
                
                # 为每个视频设置随机的点赞和关注上限
                max_follow_per_video = random.randint(min_follows_per_video, max_follows_per_video)
                max_like_per_video = random.randint(comment_like_count_min, comment_like_count_max)
                current_follow_count = 0  # 当前视频关注计数器
                current_like_count = 0    # 当前视频点赞计数器
                
                processed = 0
                scroll_done = 0
                since_scroll = 0
                
                # 滚动并处理评论，直到达到点赞和关注上限
                while current_like_count < max_like_per_video or current_follow_count < max_follow_per_video:
                    items = KuaishouUtils.els(driver, ".comment-item.comment-list-item.dark-mode") or KuaishouUtils.els(driver, ".comment-item")
                    if not items:
                        time.sleep(0.8)
                        continue
                    if processed >= len(items):
                        try:
                            KuaishouUtils.scroll_ks_comment_container(driver, times=1)
                            scroll_done += 1
                            since_scroll = 0
                            log.info(f"{log_prefix} 已滚动评论区 (第 {scroll_done} 次)")
                            # 滚动后添加随机等待，模拟人工操作
                            time.sleep(random.uniform(2, 4))
                        except Exception as e:
                            log.error(f"{log_prefix} 滚动评论区失败: {e}")
                            scroll_done += 1
                        continue

                    it = items[processed]
                    processed += 1
                    since_scroll += 1
                    
                    # 处理每个评论项之间添加随机等待，模拟人工浏览
                    time.sleep(random.uniform(0.5, 1.5))

                    # 检查评论是否包含关键词
                    comment_ok = False
                    try:
                        content_el = it.find_element(By.CSS_SELECTOR, "div.comment-item-content > span")
                        spans = content_el.find_elements(By.CSS_SELECTOR, "span")
                        comment_text = "".join(span.text for span in spans).strip()
                        log.info(f"{log_prefix} 评论内容: {comment_text}")
                        
                        # 检查评论是否包含关键词
                        if KuaishouUtils.check_comment_contains_keywords(comment_text, comment_filter_keywords):
                            comment_ok = True
                    except Exception:
                        pass
                    effective_comment_ok = comment_ok if enable_search_keywords else False

                    # 点赞逻辑 - 如果包含关键词则强制点赞，否则按概率点赞，但不超过当前视频的点赞上限
                    if enable_like and (effective_comment_ok or (current_like_count < max_like_per_video and random.random() * 100 <= like_prob)):
                        like_el = KuaishouUtils.el(driver, ".comment-item-likeicon", it)
                        if like_el:
                            cls0 = ""
                            try:
                                cls0 = like_el.get_attribute("class") or ""
                            except Exception:
                                cls0 = ""
                            if KuaishouUtils.click(driver, like_el):
                                cls1 = ""
                                try:
                                    cls1 = like_el.get_attribute("class") or ""
                                except Exception:
                                    cls1 = cls0
                                if cls1 != cls0:
                                    like_count += 1
                                    current_like_count += 1  # 增加当前视频点赞计数
                                    log.info(f"{log_prefix} 已点赞评论 (当前视频点赞数: {current_like_count}/{max_like_per_video}, 累计点赞次数: {like_count})")
                                    time.sleep(random.uniform(like_wait_min, like_wait_max))
                                    try:
                                        reporter.set_action("like")
                                        reporter.increment_like(1)
                                    except Exception:
                                        pass

                    # 访问主页逻辑 - 如果评论包含关键词则强制访问，否则按概率访问
                    should_visit = enable_profile_visit and (effective_comment_ok or (random.random() * 100 <= visit_profile_prob))
                    if should_visit:
                        a = KuaishouUtils.el(driver, ".author-name", it)
                        if a:
                            hs_a = set(driver.window_handles)
                            if KuaishouUtils.click(driver, a):
                                time.sleep(random.uniform(1.0, 2.0))  # 点击头像后等待
                                prof = next(iter(set(driver.window_handles) - hs_a), None)
                                if prof:
                                    driver.switch_to.window(prof)
                                try:
                                    time.sleep(random.uniform(profile_wait_min, profile_wait_max))
                                    
                                    # 如果评论包含关键词，则强制关注，否则按概率关注，但不超过当前视频的关注上限
                                    if enable_follow and current_follow_count < max_follow_per_video:
                                        follow_prob = 100 if effective_comment_ok else profile_follow_prob
                                        if random.random() * 100 <= follow_prob:
                                            follow_button = KuaishouUtils.el(driver, ".btn-words")
                                            if follow_button and KuaishouUtils.click(driver, follow_button):
                                                follow_count += 1
                                                current_follow_count += 1  # 增加当前视频关注计数
                                                log.info(f"{log_prefix} 已关注用户 (当前视频关注数: {current_follow_count}/{max_follow_per_video}, 累计关注次数: {follow_count})")
                                                time.sleep(random.uniform(visit_min, visit_max))
                                                try:
                                                    reporter.set_action("follow")
                                                    reporter.increment_follow(1)
                                                except Exception:
                                                    pass
                                finally:
                                    if prof:
                                        try:
                                            driver.close()
                                        except Exception:
                                            pass
                                    driver.switch_to.window(driver.window_handles[0])  # 切换回主窗口
                                    # 关闭用户主页后等待
                                    time.sleep(random.uniform(1.0, 2.0))

                    if since_scroll >= 3:
                        try:
                            KuaishouUtils.scroll_ks_comment_container(driver, times=1)
                            scroll_done += 1
                            since_scroll = 0
                            log.info(f"{log_prefix} 已滚动评论区 (第 {scroll_done} 次)")
                            # 滚动后添加随机等待，模拟人工操作
                            time.sleep(random.uniform(2, 4))
                        except Exception as e:
                            log.error(f"{log_prefix} 滚动评论区失败: {e}")
                            scroll_done += 1
                            since_scroll = 0

                log.info(f"{log_prefix} 链接 {url} 处理完成，已达到点赞/关注上限，点赞数: {current_like_count}/{max_like_per_video}，关注数: {current_follow_count}/{max_follow_per_video}")
                
                visited_count += 1
                try:
                    reporter.update_url_index(visited_count)
                    reporter.increment_url_ok(1)
                except Exception:
                    pass
                
                # 访问完一个链接后等待一段时间
                time.sleep(random.uniform(3, 6))
                
            except Exception as e:
                log.error(f"{log_prefix} 访问链接 {url} 时出错: {e}")
                try:
                    reporter.increment_url_fail(1)
                except Exception:
                    pass
                continue
        
        log.info(f"{log_prefix} 完成 {visited_count} 个链接的访问")
            
        # 确保只保留主窗口，清理可能残留的窗口
        if len(driver.window_handles) > 1:
            log.info(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
            for handle in driver.window_handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
            log.info(f"{log_prefix} 已关闭额外窗口，保留主窗口")
        
        time.sleep(random.uniform(1.0, 2.0))
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        try:
            reporter.force_report()
        except Exception:
            pass
        log.info(f"{log_prefix} 浏览器已关闭，任务完成")
        log.info(f"{log_prefix} 本次任务累计点赞次数: {like_count}")
        log.info(f"{log_prefix} 本次任务累计关注次数: {follow_count}")

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
    browser_ids = cfg.BIT_BROWSER_IDS or parse_browser_ids()
    urls = cfg.URLS or _urls(URLS)
    if not license_manager.verify_license():
        log.error("卡密验证失败")
        _stop_ws_client()
        return
    license_manager.start_periodic_check()
    try:
        if len(browser_ids) <= 1:
            url_queue = deque(urls)
            url_lock = threading.Lock()
            run_worker(browser_ids[0], 1, url_queue, url_lock, len(urls))
            return
        url_queue = deque(urls)
        url_lock = threading.Lock()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(browser_ids)) as ex:
            futures = []
            for i, bid in enumerate(browser_ids):
                futures.append(ex.submit(run_worker, bid, i + 1, url_queue, url_lock, len(urls)))
                if i < len(browser_ids) - 1:
                    time.sleep(2.5)
            for f in concurrent.futures.as_completed(futures):
                try:
                    f.result()
                except LicenseException:
                    log.error("卡密无效，取消剩余任务")
                    STOP_EVENT.set()
                    for fut in futures:
                        fut.cancel()
                    break
                except Exception as e:
                    log.error(f"[并发] 线程执行出错: {e}")
    finally:
        license_manager.stop_periodic_check()
        _stop_ws_client()

if __name__ == "__main__":
    main()
