import json
import os
import random
import time
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

from ..tools.core import log

from ..tools.config import KsConfig

from .base import KuaishouUtils

# 初始化快手配置
ks_config = KsConfig()

# URL列表配置
DEFAULT_URLS = ks_config.KS_SHARE_URLS if hasattr(ks_config, 'KS_SHARE_URLS') else [
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

def run_worker(browser_id, browser_number, url_queue, url_lock):
    log_prefix = get_browser_log_prefix(browser_id)
    
    wait_time = DEFAULT_WAIT_TIME
    url_min, url_max = DEFAULT_MAX_VISIT_URLS
    scroll_min, scroll_max = DEFAULT_MAX_COMMENT
    like_prob = LIKE_PROBABILITY
    visit_profile_prob = VISIT_ENABLE
    profile_follow_prob = PROFILE_FOLLOW_PROBABILITY
    like_wait_min = DEFAULT_LIKE_WAIT_MIN
    like_wait_max = DEFAULT_LIKE_WAIT_MAX
    visit_min = DEFAULT_VISIT_MIN
    visit_max = DEFAULT_VISIT_MAX
    profile_wait_min = DEFAULT_PROFILE_WAIT_MIN
    profile_wait_max = DEFAULT_PROFILE_WAIT_MAX
    video_comment_prob = VIDEO_REPLY_RATE
    video_comment_wait_min = VIDEO_REPLY_WAIT_MIN
    video_comment_wait_max = VIDEO_REPLY_WAIT_MAX
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
    log.info(f"{log_prefix} 每条视频最少关注数量: {MIN_FOLLOWS_PER_VIDEO}")
    log.info(f"{log_prefix} 每条视频最多关注数量: {MAX_FOLLOWS_PER_VIDEO}")
    log.info(f"{log_prefix} 每条视频最少点赞数量: {COMMENT_LIKE_COUNT_MIN}")
    log.info(f"{log_prefix} 每条视频最多点赞数量: {COMMENT_LIKE_COUNT_MAX}")

    res = _open_bit(browser_id)
    data = (res or {}).get("data") or {}
    if not data.get("driver") or not data.get("http"):
        raise RuntimeError(f"{log_prefix} 打开比特浏览器失败: {res}")

    log.info(f"{log_prefix} 比特浏览器打开成功")
    
    opt = webdriver.ChromeOptions()
    opt.add_experimental_option("debuggerAddress", data["http"])
    driver = webdriver.Chrome(service=Service(data["driver"]), options=opt)

    def w(t=None):
        WebDriverWait(driver, t or max(8, wait_time)).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    try:
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
            with url_lock:
                url = url_queue.popleft() if url_queue else None
            if not url:
                # 队列为空，表示所有URL都已处理完毕
                log.info(f"{log_prefix} 所有URL已处理完毕，共处理 {visited_count} 个链接")
                break
            
            log.info(f"{log_prefix} 访问链接: {url}")
            try:
                # 访问分享链接
                driver.get(url)
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
                if ENABLE_VIDEO_COMMENT and (random.random() * 100 <= video_comment_prob):
                    log.info(f"{log_prefix} 根据概率决定进行视频留言")
                    KuaishouUtils.leave_video_comment(driver, video_comment_wait_min, video_comment_wait_max, log_prefix)
                
                # 为每个视频设置随机的点赞和关注上限
                max_follow_per_video = random.randint(MIN_FOLLOWS_PER_VIDEO, MAX_FOLLOWS_PER_VIDEO)
                max_like_per_video = random.randint(COMMENT_LIKE_COUNT_MIN, COMMENT_LIKE_COUNT_MAX)
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
                        if KuaishouUtils.check_comment_contains_keywords(comment_text, COMMENT_FILTER_KEYWORDS):
                            comment_ok = True
                    except Exception:
                        pass
                    effective_comment_ok = comment_ok if ENABLE_SEARCH_KEYWORDS else False

                    # 点赞逻辑 - 如果包含关键词则强制点赞，否则按概率点赞，但不超过当前视频的点赞上限
                    if ENABLE_LIKE and (effective_comment_ok or (current_like_count < max_like_per_video and random.random() * 100 <= like_prob)):
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

                    # 访问主页逻辑 - 如果评论包含关键词则强制访问，否则按概率访问
                    should_visit = ENABLE_PROFILE_VISIT and (effective_comment_ok or (random.random() * 100 <= visit_profile_prob))
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
                                    if ENABLE_FOLLOW and current_follow_count < max_follow_per_video:
                                        follow_prob = 100 if effective_comment_ok else profile_follow_prob
                                        if random.random() * 100 <= follow_prob:
                                            follow_button = KuaishouUtils.el(driver, ".btn-words")
                                            if follow_button and KuaishouUtils.click(driver, follow_button):
                                                follow_count += 1
                                                current_follow_count += 1  # 增加当前视频关注计数
                                                log.info(f"{log_prefix} 已关注用户 (当前视频关注数: {current_follow_count}/{max_follow_per_video}, 累计关注次数: {follow_count})")
                                                time.sleep(random.uniform(visit_min, visit_max))
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
                
                # 访问完一个链接后等待一段时间
                time.sleep(random.uniform(3, 6))
                
            except Exception as e:
                log.error(f"{log_prefix} 访问链接 {url} 时出错: {e}")
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
        log.info(f"{log_prefix} 浏览器已关闭，任务完成")
        log.info(f"{log_prefix} 本次任务累计点赞次数: {like_count}")
        log.info(f"{log_prefix} 本次任务累计关注次数: {follow_count}")

def main():
    browser_ids = parse_browser_ids()
    urls = _urls(DEFAULT_URLS)
    if len(browser_ids) <= 1:
        url_queue = deque(urls)
        url_lock = threading.Lock()
        run_worker(browser_ids[0], 1, url_queue, url_lock)
        return
    url_queue = deque(urls)
    url_lock = threading.Lock()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(browser_ids)) as ex:
        futures = []
        for i, bid in enumerate(browser_ids):
            futures.append(ex.submit(run_worker, bid, i + 1, url_queue, url_lock))
            if i < len(browser_ids) - 1:
                time.sleep(2.5)
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except Exception as e:
                log.error(f"[并发] 线程执行出错: {e}")

if __name__ == "__main__":
    main()