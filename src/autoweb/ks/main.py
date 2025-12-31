import json, os, random, time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BIT_API_URL = "http://127.0.0.1:54345"
DEFAULT_KEYWORDS = ["美女", "美食", "穿搭", "旅行"]

# 滚动操作相关参数
DEFAULT_SCROLL_DELTA = 400  # 默认滚动增量

# 视频浏览相关参数
DEFAULT_WAIT_TIME = 5  # 默认等待时间
DEFAULT_MAX_SCROLL_VIDEO = [2, 3]  # 默认视频数量范围
DEFAULT_MAX_COMMENT = [2, 5]  # 默认评论滚动范围

# 互动操作相关参数
LIKE_PROBABILITY = 0.2  # 默认点赞概率
VISIT_ENABLE = 0.1  # 默认访问主页概率
PROFILE_FOLLOW_PROBABILITY = 0.2  # 默认主页关注概率
DEFAULT_LIKE_WAIT_MIN = 4  # 点赞后最小等待时间
DEFAULT_LIKE_WAIT_MAX = 10  # 点赞后最大等待时间
DEFAULT_VISIT_MIN = 2  # 关注后最小等待时间
DEFAULT_VISIT_MAX = 5  # 关注后最大等待时间
DEFAULT_PROFILE_WAIT_MIN = 5  # 进入主页后最小等待时间
DEFAULT_PROFILE_WAIT_MAX = 15  # 进入主页后最大等待时间
DEFAULT_BIT_BROWSER_IDS = ["57bd9953b5364d3db5c4ac7cfbb9a1b3"]  # 默认浏览器ID列表

def get_browser_log_prefix(browser_id):
    """生成浏览器日志前缀，格式为'浏览器 #编号'"""
    # 提取浏览器ID的最后几位作为编号
    browser_num = browser_id.split("-")[-1] if "-" in browser_id else browser_id[:8]
    return f"[浏览器 #{browser_num}]"

def scroll_ks_comment_container(driver, times=5, step=600, sleep=1.5):
    css = "div.comment-container.vertical-comment"
    container = driver.find_element(By.CSS_SELECTOR, css)
    from selenium.webdriver.common.actions.wheel_input import ScrollOrigin

    for _ in range(times):
        ActionChains(driver).move_to_element(container).pause(0.05).scroll_from_origin(
            ScrollOrigin.from_element(container), 0, step
        ).perform()
        time.sleep(sleep)
    return True


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


def _open_bit(browser_id):
    payload = {"id": str(browser_id), "queue": True, "ignoreDefaultUrls": True}
    if (os.getenv("HEADLESS") or "").strip().lower() in {"1", "true", "yes", "y"}:
        payload["args"] = ["--headless"]
    return requests.post(
        f"{BIT_API_URL}/browser/open",
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=30,
    ).json()


def main():
    browser_id = DEFAULT_BIT_BROWSER_IDS[0]
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
    like_count = 0
    follow_count = 0

    print(f"{log_prefix} 开始执行快手自动化任务")
    print(f"{log_prefix} 浏览器ID: {browser_id}")
    print(f"{log_prefix} 等待时间: {wait_time}s")
    print(f"{log_prefix} 视频数量范围: {video_min}-{video_max}")
    print(f"{log_prefix} 评论滚动范围: {scroll_min}-{scroll_max}")
    print(f"{log_prefix} 点赞概率: {like_prob}")
    print(f"{log_prefix} 访问主页概率: {visit_profile_prob}")
    print(f"{log_prefix} 主页关注概率: {profile_follow_prob}")
    print(f"{log_prefix} 点赞后等待时间范围: {like_wait_min}-{like_wait_max}s")
    print(f"{log_prefix} 关注后等待时间范围: {visit_min}-{visit_max}s")
    print(f"{log_prefix} 进入主页等待时间范围: {profile_wait_min}-{profile_wait_max}s")

    res = _open_bit(browser_id)
    data = (res or {}).get("data") or {}
    if not data.get("driver") or not data.get("http"):
        raise RuntimeError(f"{log_prefix} 打开比特浏览器失败: {res}")

    print(f"{log_prefix} 比特浏览器打开成功")
    
    opt = webdriver.ChromeOptions()
    opt.add_experimental_option("debuggerAddress", data["http"])
    driver = webdriver.Chrome(service=Service(data["driver"]), options=opt)

    def w(t=None):
        WebDriverWait(driver, t or max(8, wait_time)).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    def el(css, root=None):
        try:
            return (root or driver).find_element(By.CSS_SELECTOR, css)
        except Exception:
            return None

    def els(css, root=None):
        try:
            return (root or driver).find_elements(By.CSS_SELECTOR, css)
        except Exception:
            return []

    def click(x):
        if not x:
            return False
        try:
            driver.execute_script("arguments[0].click();", x)
            return True
        except Exception:
            try:
                x.click()
                return True
            except Exception:
                return False

    try:
        print(f"{log_prefix} 访问快手搜索页面")
        driver.get("https://www.kuaishou.com/search/video"); w(); time.sleep(0.8)
        for kw in _kws(DEFAULT_KEYWORDS):
            print(f"{log_prefix} 搜索关键词: {kw}")
            if "/search/" not in (driver.current_url or ""):
                driver.get("https://www.kuaishou.com/search/video"); w(); time.sleep(0.5)
            inp = el("input.search-input") or el(".search-input")
            if not inp:
                print(f"{log_prefix} 未找到搜索输入框，跳过关键词: {kw}")
                continue
            try:
                inp.click(); inp.send_keys(Keys.CONTROL, "a"); inp.send_keys(Keys.BACKSPACE)
            except Exception:
                pass
            ActionChains(driver).send_keys(kw).perform(); time.sleep(0.2)
            if not click(el(".search-icon")):
                ActionChains(driver).send_keys(Keys.RETURN).perform()
            time.sleep(1.0)

            cont = el("div.video-container"); cards = els(".video-card .card-link", cont) or els(".card-link", cont)
            if not cards:
                print(f"{log_prefix} 未找到视频卡片，跳过关键词: {kw}")
                continue
            main_h = driver.current_window_handle; hs0 = set(driver.window_handles)
            click(cards[0]); time.sleep(0.8)
            new_h = next(iter(set(driver.window_handles) - hs0), None)
            if new_h:
                driver.switch_to.window(new_h)
            w(); time.sleep(0.5)

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
                scroll_times = random.randint(scroll_min, scroll_max)
                processed = 0
                scroll_done = 0
                since_scroll = 0
                while scroll_done < scroll_times:
                    items = els(".comment-item.comment-list-item.dark-mode") or els(".comment-item")
                    if not items:
                        time.sleep(0.8)
                        continue
                    if processed >= len(items):
                        try:
                            scroll_ks_comment_container(driver, times=1)
                            scroll_done += 1
                            since_scroll = 0
                            print(f"{log_prefix} 已滚动评论区 ({scroll_done}/{scroll_times})")
                        except Exception as e:
                            print(f"{log_prefix} 滚动评论区失败: {e}")
                            scroll_done += 1
                        continue

                    it = items[processed]
                    processed += 1
                    since_scroll += 1

                    if random.random() <= like_prob:
                        like_el = el(".comment-item-likeicon", it)
                        if like_el:
                            cls0 = ""
                            try:
                                cls0 = like_el.get_attribute("class") or ""
                            except Exception:
                                cls0 = ""
                            if click(like_el):
                                cls1 = ""
                                try:
                                    cls1 = like_el.get_attribute("class") or ""
                                except Exception:
                                    cls1 = cls0
                                if cls1 != cls0:
                                    like_count += 1
                                    print(f"{log_prefix} 已点赞评论 (累计点赞次数: {like_count})")
                                    time.sleep(random.uniform(like_wait_min, like_wait_max))

                    if random.random() <= visit_profile_prob:
                        a = el(".author-name", it)
                        if a:
                            hs_a = set(driver.window_handles)
                            if click(a):
                                time.sleep(0.5)
                                prof = next(iter(set(driver.window_handles) - hs_a), None)
                                if prof:
                                    driver.switch_to.window(prof)
                                try:
                                    time.sleep(random.uniform(profile_wait_min, profile_wait_max))
                                    if random.random() <= profile_follow_prob:
                                        follow_button = el(".btn-words")
                                        if follow_button and click(follow_button):
                                            follow_count += 1
                                            print(f"{log_prefix} 已关注用户 (累计关注次数: {follow_count})")
                                            time.sleep(random.uniform(visit_min, visit_max))
                                finally:
                                    if prof:
                                        try:
                                            driver.close()
                                        except Exception:
                                            pass
                                    driver.switch_to.window(new_h or main_h)

                    if since_scroll >= 3:
                        try:
                            scroll_ks_comment_container(driver, times=1)
                            scroll_done += 1
                            since_scroll = 0
                            print(f"{log_prefix} 已滚动评论区 ({scroll_done}/{scroll_times})")
                        except Exception as e:
                            print(f"{log_prefix} 滚动评论区失败: {e}")
                            scroll_done += 1
                            since_scroll = 0

                if i < vids - 1:
                    if not click(el(".switch-item.video-switch-next")):
                        print(f"{log_prefix} 未找到下一个视频按钮，提前结束")
                        break
                    time.sleep(random.uniform(1.0, 2.0))
                else:
                    print(f"{log_prefix} 视频浏览完成")

            if new_h:
                try:
                    driver.close()
                except Exception:
                    pass
                driver.switch_to.window(main_h)
            else:
                root = el(".short-video-info-container") or el("div.comment-container.vertical-comment")
                if not click(el(".close-page", root) if root else None):
                    click(el(".close-page"))
                    try:
                        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    except Exception:
                        pass
                time.sleep(0.7)
            time.sleep(random.uniform(1.0, 2.0))
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print(f"{log_prefix} 浏览器已关闭，任务完成")
        print(f"{log_prefix} 本次任务累计点赞次数: {like_count}")
        print(f"{log_prefix} 本次任务累计关注次数: {follow_count}")


if __name__ == "__main__":
    main()
