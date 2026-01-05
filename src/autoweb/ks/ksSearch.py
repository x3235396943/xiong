import json, os, random, time
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

from ..tools.config import KsConfig
from .base import KuaishouUtils

from ..tools.core import log
from ..tools.license import LicenseManager, LicenseException

# 初始化快手配置
ks_config = KsConfig()

# 搜索关键词
DEFAULT_KEYWORDS = ks_config.KEYWORDS

# 视频浏览相关参数
DEFAULT_MAX_SCROLL_VIDEO = ks_config.MAX_SCROLL_VIDEO
DEFAULT_MAX_COMMENT = ks_config.MAX_COMMENT

# 互动操作相关参数
LIKE_PROBABILITY = ks_config.LIKE_PROBABILITY
VISIT_ENABLE = ks_config.VISIT_ENABLE
PROFILE_FOLLOW_PROBABILITY = ks_config.PROFILE_FOLLOW_PROBABILITY
DEFAULT_LIKE_WAIT_MIN = ks_config.LIKE_WAIT_MIN
DEFAULT_LIKE_WAIT_MAX = ks_config.LIKE_WAIT_MAX
DEFAULT_VISIT_MIN = ks_config.VISIT_MIN
DEFAULT_VISIT_MAX = ks_config.VISIT_MAX
DEFAULT_PROFILE_WAIT_MIN = ks_config.COMMENT_WAIT_MIN
DEFAULT_PROFILE_WAIT_MAX = ks_config.COMMENT_WAIT_MAX
VIDEO_REPLY_RATE = ks_config.VIDEO_REPLY_RATE
VIDEO_REPLY_WAIT_MIN = ks_config.VIDEO_REPLY_WAIT_MIN
VIDEO_REPLY_WAIT_MAX = ks_config.VIDEO_REPLY_WAIT_MAX

# 新增：每条视频点赞和关注上限参数
MIN_FOLLOWS_PER_VIDEO = ks_config.MIN_FOLLOWS_PER_VIDEO
MAX_FOLLOWS_PER_VIDEO = ks_config.MAX_FOLLOWS_PER_VIDEO
COMMENT_LIKE_COUNT_MIN = ks_config.COMMENT_LIKE_COUNT_MIN
COMMENT_LIKE_COUNT_MAX = ks_config.COMMENT_LIKE_COUNT_MAX

# 视频评论内容列表
VIDEO_COMMENTS = ks_config.VIDEO_COMMENTS
DEFAULT_BIT_BROWSER_IDS = ks_config.BIT_BROWSER_IDS

# 评论关键词过滤
COMMENT_FILTER_KEYWORDS = ks_config.COMMENT_FILTER_KEYWORDS

# 是否启用功能
ENABLE_LIKE = ks_config.ENABLE_LIKE
ENABLE_FOLLOW = ks_config.ENABLE_FOLLOW
ENABLE_PROFILE_VISIT = ks_config.ENABLE_PROFILE_VISIT
ENABLE_VIDEO_COMMENT = ks_config.ENABLE_VIDEO_COMMENT
ENABLE_SEARCH_KEYWORDS = ks_config.ENABLE_SEARCH_KEYWORDS

DEFAULT_WAIT_TIME = ks_config.KS_DEFAULT_WAIT_TIME
license_manager = LicenseManager()
STOP_EVENT = threading.Event()

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


def _kws(d):
    s = (os.getenv("KEYWORDS") or "").strip()
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


def run_worker(browser_id, browser_number, kw_queue, kw_lock):
    log_prefix = get_browser_log_prefix(browser_id)
    
    wait_time = DEFAULT_WAIT_TIME
    video_min, video_max = DEFAULT_MAX_SCROLL_VIDEO
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
    

    log.info(f"{log_prefix} 开始执行快手自动化任务")
    log.info(f"{log_prefix} 浏览器ID: {browser_id}")
    log.info(f"{log_prefix} 等待时间: {wait_time}s")
    log.info(f"{log_prefix} 视频数量范围: {video_min}-{video_max}")
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
        try:
            license_manager.check_license_validity()
        except LicenseException:
            log.error(f"{log_prefix} 卡密无效，停止任务")
            return
        log.info(f"{log_prefix} 访问快手搜索页面")
        # 清理浏览器句柄，确保只有快手首页的界面
        if len(driver.window_handles) > 1:
            log.info(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
            for handle in driver.window_handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
            log.info(f"{log_prefix} 已关闭额外窗口，保留主窗口")
        
        driver.get("https://www.kuaishou.com/search/video"); w(); time.sleep(0.8)
        empty_retries = 0
        while True:
            if STOP_EVENT.is_set():
                log.info(f"{log_prefix} 收到停止信号，退出任务")
                break
            try:
                license_manager.check_license_validity()
            except LicenseException:
                log.error(f"{log_prefix} 卡密无效，停止任务")
                break
            with kw_lock:
                kw = kw_queue.popleft() if kw_queue else None
            if not kw:
                empty_retries += 1
                time.sleep(3.0)
                if empty_retries >= 5:
                    break
                continue
            log.info(f"{log_prefix} 搜索关键词: {kw}")
            if "/search/" not in (driver.current_url or ""):
                # 在每次进入搜索页面前清理浏览器句柄
                if len(driver.window_handles) > 1:
                    print(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
                    for handle in driver.window_handles[1:]:
                        driver.switch_to.window(handle)
                        driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    print(f"{log_prefix} 已关闭额外窗口，保留主窗口")
                
                driver.get("https://www.kuaishou.com/search/video"); w(); time.sleep(0.5)
            inp = KuaishouUtils.el(driver, "input.search-input") or KuaishouUtils.el(driver, ".search-input")
            if not inp:
                log.warning(f"{log_prefix} 未找到搜索输入框，跳过关键词: {kw}")
                continue
            try:
                inp.click(); inp.send_keys(Keys.CONTROL, "a"); inp.send_keys(Keys.BACKSPACE)
            except Exception:
                pass
            ActionChains(driver).send_keys(kw).perform(); time.sleep(0.2)
            if not KuaishouUtils.click(driver, KuaishouUtils.el(driver, ".search-icon")):
                ActionChains(driver).send_keys(Keys.RETURN).perform()
            time.sleep(1.0)

            cont = KuaishouUtils.el(driver, "div.video-container"); cards = KuaishouUtils.els(driver, ".video-card .card-link", cont) or KuaishouUtils.els(driver, ".card-link", cont)
            if not cards:
                log.warning(f"{log_prefix} 未找到视频卡片，跳过关键词: {kw}")
                continue
            main_h = driver.current_window_handle; hs0 = set(driver.window_handles)
            KuaishouUtils.click(driver, cards[0]); time.sleep(0.8)
            new_h = next(iter(set(driver.window_handles) - hs0), None)
            if new_h:
                driver.switch_to.window(new_h)
            w(); time.sleep(0.5)
            
            def leave_video_comment():
                """在当前视频页面留下评论"""
                return KuaishouUtils.leave_video_comment(driver, video_comment_wait_min, video_comment_wait_max, log_prefix)
                
            vids = random.randint(video_min, video_max)
            print(f"{log_prefix} 开始浏览 {vids} 个视频")
            
            for i in range(vids):
                print(f"{log_prefix} 正在处理第 {i+1}/{vids} 个视频")
                try:
                    WebDriverWait(driver, max(8, wait_time)).until(
                        lambda d: d.find_elements(By.CSS_SELECTOR, ".comment-item.comment-list-item.dark-mode")
                        or d.find_elements(By.CSS_SELECTOR, ".comment-item")
                    )
                except Exception:
                    time.sleep(1.0)
                
                if ENABLE_VIDEO_COMMENT and (random.random() * 100 <= video_comment_prob):
                    log.info(f"{log_prefix} 根据概率决定进行视频留言")
                    leave_video_comment()
                
                # 为每个视频设置随机的点赞和关注上限
                max_follow_per_video = random.randint(MIN_FOLLOWS_PER_VIDEO, MAX_FOLLOWS_PER_VIDEO)
                max_like_per_video = random.randint(COMMENT_LIKE_COUNT_MIN, COMMENT_LIKE_COUNT_MAX)
                current_follow_count = 0  # 当前视频关注计数器
                current_like_count = 0    # 当前视频点赞计数器
                
                scroll_times = random.randint(scroll_min, scroll_max)
                processed = 0
                scroll_done = 0
                since_scroll = 0
                while scroll_done < scroll_times:
                    items = KuaishouUtils.els(driver, ".comment-item.comment-list-item.dark-mode") or KuaishouUtils.els(driver, ".comment-item")
                    if not items:
                        time.sleep(0.8)
                        continue
                    if processed >= len(items):
                        try:
                            KuaishouUtils.scroll_ks_comment_container(driver, times=1)
                            scroll_done += 1
                            since_scroll = 0
                            print(f"{log_prefix} 已滚动评论区 ({scroll_done}/{scroll_times})")
                            # 滚动后添加随机等待，模拟人工操作
                            time.sleep(random.uniform(2, 4))
                        except Exception as e:
                            print(f"{log_prefix} 滚动评论区失败: {e}")
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
                                    driver.switch_to.window(new_h or main_h)
                                    # 关闭用户主页后等待
                                    time.sleep(random.uniform(1.0, 2.0))

                    if since_scroll >= 3:
                        try:
                            KuaishouUtils.scroll_ks_comment_container(driver, times=1)
                            scroll_done += 1
                            since_scroll = 0
                            log.info(f"{log_prefix} 已滚动评论区 ({scroll_done}/{scroll_times})")
                            # 滚动后添加随机等待，模拟人工操作
                            time.sleep(random.uniform(2, 4))
                        except Exception as e:
                            log.error(f"{log_prefix} 滚动评论区失败: {e}")
                            scroll_done += 1
                            since_scroll = 0

                log.info(f"{log_prefix} 第 {i+1} 个视频处理完成，点赞数: {current_like_count}/{max_like_per_video}，关注数: {current_follow_count}/{max_follow_per_video}")

                # 如果不是最后一个视频，尝试切换到下一个视频
                if i < vids - 1:
                    log.info(f"{log_prefix} 尝试切换到下一个视频")
                    switch_next_btn = KuaishouUtils.el(driver, ".switch-item.video-switch-next")
                    if switch_next_btn:
                        if KuaishouUtils.click(driver, switch_next_btn):
                            log.info(f"{log_prefix} 成功点击下一个视频按钮")
                            # 等待新视频加载
                            time.sleep(2.0)
                        else:
                            log.error(f"{log_prefix} 点击下一个视频按钮失败")
                    else:
                        log.warning(f"{log_prefix} 未找到下一个视频按钮")
                        # 如果找不到切换按钮，则继续执行（可能已经在最后一个视频）
                else:
                    # 最后一个视频处理完成后，退出视频播放页面
                    if new_h:
                        try:
                            driver.close()
                        except Exception:
                            pass
                        driver.switch_to.window(main_h)
                    else:
                        root = KuaishouUtils.el(driver, ".short-video-info-container") or KuaishouUtils.el(driver, "div.comment-container.vertical-comment")
                        if not KuaishouUtils.click(driver, KuaishouUtils.el(driver, ".close-page", root) if root else None):
                            KuaishouUtils.click(driver, KuaishouUtils.el(driver, ".close-page"))
                            try:
                                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                            except Exception:
                                pass
                        time.sleep(0.7)
            
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
    keywords = _kws(DEFAULT_KEYWORDS)
    license_manager.set_stop_callback(lambda: STOP_EVENT.set())
    if not license_manager.verify_license():
        log.error("卡密验证失败")
        return
    license_manager.start_periodic_check()
    try:
        if len(browser_ids) <= 1:
            kw_queue = deque(keywords)
            kw_lock = threading.Lock()
            run_worker(browser_ids[0], 1, kw_queue, kw_lock)
            return
        kw_queue = deque(keywords)
        kw_lock = threading.Lock()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(browser_ids)) as ex:
            futures = []
            for i, bid in enumerate(browser_ids):
                futures.append(ex.submit(run_worker, bid, i + 1, kw_queue, kw_lock))
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


if __name__ == "__main__":
    main()
