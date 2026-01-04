import json, os, random, time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# 搜索关键词
DEFAULT_KEYWORDS = ["美女", "美食", "穿搭", "旅行"]

# 视频浏览相关参数
DEFAULT_MAX_SCROLL_VIDEO = [2, 3]  # 默认视频数量范围
DEFAULT_MAX_COMMENT = [2, 5]  # 默认评论滚动范围

# 互动操作相关参数
LIKE_PROBABILITY = 20  # 默认点赞概率
VISIT_ENABLE = 10  # 默认访问主页概率
PROFILE_FOLLOW_PROBABILITY = 20  # 默认主页关注概率
DEFAULT_LIKE_WAIT_MIN = 4  # 点赞后最小等待时间
DEFAULT_LIKE_WAIT_MAX = 10  # 点赞后最大等待时间
DEFAULT_VISIT_MIN = 2  # 关注后最小等待时间
DEFAULT_VISIT_MAX = 5  # 关注后最大等待时间
DEFAULT_PROFILE_WAIT_MIN = 5  # 进入主页后最小等待时间
DEFAULT_PROFILE_WAIT_MAX = 15  # 进入主页后最大等待时间
VIDEO_REPLY_RATE = 20  # 视频留言概率
VIDEO_REPLY_WAIT_MIN = 5  # 视频留言前最小等待时间
VIDEO_REPLY_WAIT_MAX = 10  # 视频留言前最大等待时间

# 新增：每条视频点赞和关注上限参数
MIN_FOLLOWS_PER_VIDEO = 2  # 每条视频最少关注数量
MAX_FOLLOWS_PER_VIDEO = 3  # 每条视频最多关注数量
COMMENT_LIKE_COUNT_MIN = 4  # 每条视频最少点赞数量
COMMENT_LIKE_COUNT_MAX = 8  # 每条视频最多点赞数量

# 视频评论内容列表
VIDEO_COMMENTS = "这个视频不错！-&-内容很棒！-&-支持一下！-&-666-&-好看！-&-不错哦-&-赞一个"  # 视频评论列表，使用-&-分隔
DEFAULT_BIT_BROWSER_IDS = ["57bd9953b5364d3db5c4ac7cfbb9a1b3"]  # 默认浏览器ID列表

# 评论关键词过滤
COMMENT_FILTER_KEYWORDS = "美女-&-帅哥-&-喜欢"

# 是否启用点赞功能
ENABLE_LIKE = True
# 是否启用关注功能
ENABLE_FOLLOW = True
# 是否启用进入个人主页功能
ENABLE_PROFILE_VISIT = True
# 是否启用视频评论功能
ENABLE_VIDEO_COMMENT = True
# 是否启用关键词搜索功能
ENABLE_SEARCH_KEYWORDS = True

DEFAULT_WAIT_TIME = 5  # 默认等待元素加载时间

def get_browser_log_prefix(browser_id):
    """生成浏览器日志前缀，格式为'浏览器 #编号'"""
    # 提取浏览器ID的最后几位作为编号
    browser_num = browser_id.split("-")[-1] if "-" in browser_id else browser_id[:8]
    return f"[浏览器 #{browser_num}]"

# 滚动距离
def scroll_ks_comment_container(driver, times=5, step=500, sleep=1.5):
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
        "http://127.0.0.1:54345/browser/open",
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
    video_comment_prob = VIDEO_REPLY_RATE
    video_comment_wait_min = VIDEO_REPLY_WAIT_MIN
    video_comment_wait_max = VIDEO_REPLY_WAIT_MAX
    like_count = 0
    follow_count = 0
    

    print(f"{log_prefix} 开始执行快手自动化任务")
    print(f"{log_prefix} 浏览器ID: {browser_id}")
    print(f"{log_prefix} 等待时间: {wait_time}s")
    print(f"{log_prefix} 视频数量范围: {video_min}-{video_max}")
    print(f"{log_prefix} 评论滚动范围: {scroll_min}-{scroll_max}")
    print(f"{log_prefix} 点赞概率: {like_prob}%")
    print(f"{log_prefix} 访问主页概率: {visit_profile_prob}%")
    print(f"{log_prefix} 主页关注概率: {profile_follow_prob}%")
    print(f"{log_prefix} 点赞后等待时间范围: {like_wait_min}-{like_wait_max}s")
    print(f"{log_prefix} 关注后等待时间范围: {visit_min}-{visit_max}s")
    print(f"{log_prefix} 进入主页等待时间范围: {profile_wait_min}-{profile_wait_max}s")
    print(f"{log_prefix} 视频留言概率: {video_comment_prob}%")
    print(f"{log_prefix} 视频留言前等待时间范围: {video_comment_wait_min}-{video_comment_wait_max}s")
    print(f"{log_prefix} 每条视频最少关注数量: {MIN_FOLLOWS_PER_VIDEO}")
    print(f"{log_prefix} 每条视频最多关注数量: {MAX_FOLLOWS_PER_VIDEO}")
    print(f"{log_prefix} 每条视频最少点赞数量: {COMMENT_LIKE_COUNT_MIN}")
    print(f"{log_prefix} 每条视频最多点赞数量: {COMMENT_LIKE_COUNT_MAX}")

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

    def human_like_delay(min_delay=0.3, max_delay=0.8):
        """模拟人工点击的随机延迟"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)

    def click(x):
        if not x:
            return False
        try:
            driver.execute_script("arguments[0].click();", x)
            human_like_delay(0.3, 0.8)  # 点击后添加随机等待
            return True
        except Exception:
            try:
                x.click()
                human_like_delay(0.3, 0.8)  # 点击后添加随机等待
                return True
            except Exception:
                return False

    # 文本标准化函数（转小写、去除多余空格）
    def normalize_text(text):
        """文本标准化（转小写、去除多余空格）"""
        try:
            s = str(text).lower()
            import re
            s = re.sub(r"\s+", " ", s).strip()
            return s
        except Exception:
            return str(text)

    # 检查评论是否包含关键词
    def check_comment_contains_keywords(comment_text, keywords):
        """检查评论是否包含指定关键词"""
        keyword_list = [x.strip() for x in keywords.split("-&-") if x.strip()]
        norm_comment = normalize_text(comment_text)
        for kw in keyword_list:
            if normalize_text(kw) in norm_comment:
                return True
        return False

    try:
        print(f"{log_prefix} 访问快手搜索页面")
        # 清理浏览器句柄，确保只有快手首页的界面
        if len(driver.window_handles) > 1:
            print(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
            for handle in driver.window_handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
            print(f"{log_prefix} 已关闭额外窗口，保留主窗口")
        
        driver.get("https://www.kuaishou.com/search/video"); w(); time.sleep(0.8)
        for kw in _kws(DEFAULT_KEYWORDS):
            print(f"{log_prefix} 搜索关键词: {kw}")
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
            
            def leave_video_comment():
                """在当前视频页面留下评论"""
                try:
                    # 等待视频加载并等待一段时间后进行评论
                    wait_time = random.uniform(video_comment_wait_min, video_comment_wait_max)
                    print(f"{log_prefix} 等待 {wait_time:.2f} 秒后进行视频留言")
                    time.sleep(wait_time)
                    
                    # 查找评论输入框
                    comment_input = el(".pl-textarea")
                    if comment_input:
                        # 点击输入框
                        click(comment_input)
                        time.sleep(0.5)
                        
                        # 输入评论内容
                        comment_text = random.choice(["这个视频不错！", "内容很棒！", "支持一下！", "666", "好看！"])
                        comment_input.send_keys(comment_text)
                        time.sleep(0.5)
                        
                        # 尝试找到并点击发送按钮
                        send_button = el(".pl-send-btn") or el(".send-btn") or el(".comment-send-btn")
                        if send_button:
                            click(send_button)
                            print(f"{log_prefix} 已留言: {comment_text}")
                            return True
                        else:
                            # 如果没有找到发送按钮，尝试按回车键
                            comment_input.send_keys(Keys.RETURN)
                            print(f"{log_prefix} 已留言: {comment_text}")
                            return True
                    else:
                        print(f"{log_prefix} 未找到评论输入框")
                        return False
                except Exception as e:
                    print(f"{log_prefix} 留言失败: {e}")
                    return False
                
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
                    print(f"{log_prefix} 根据概率决定进行视频留言")
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
                        print(comment_text)
                        
                        # 检查评论是否包含关键词
                        if check_comment_contains_keywords(comment_text, COMMENT_FILTER_KEYWORDS):
                            comment_ok = True
                    except Exception:
                        pass
                    effective_comment_ok = comment_ok if ENABLE_SEARCH_KEYWORDS else False

                    # 点赞逻辑 - 如果包含关键词则强制点赞，否则按概率点赞，但不超过当前视频的点赞上限
                    if ENABLE_LIKE and (effective_comment_ok or (current_like_count < max_like_per_video and random.random() * 100 <= like_prob)):
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
                                    current_like_count += 1  # 增加当前视频点赞计数
                                    print(f"{log_prefix} 已点赞评论 (当前视频点赞数: {current_like_count}/{max_like_per_video}, 累计点赞次数: {like_count})")
                                    time.sleep(random.uniform(like_wait_min, like_wait_max))

                    # 访问主页逻辑 - 如果评论包含关键词则强制访问，否则按概率访问
                    should_visit = ENABLE_PROFILE_VISIT and (effective_comment_ok or (random.random() * 100 <= visit_profile_prob))
                    if should_visit:
                        a = el(".author-name", it)
                        if a:
                            hs_a = set(driver.window_handles)
                            if click(a):
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
                                            follow_button = el(".btn-words")
                                            if follow_button and click(follow_button):
                                                follow_count += 1
                                                current_follow_count += 1  # 增加当前视频关注计数
                                                print(f"{log_prefix} 已关注用户 (当前视频关注数: {current_follow_count}/{max_follow_per_video}, 累计关注次数: {follow_count})")
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
                            scroll_ks_comment_container(driver, times=1)
                            scroll_done += 1
                            since_scroll = 0
                            print(f"{log_prefix} 已滚动评论区 ({scroll_done}/{scroll_times})")
                            # 滚动后添加随机等待，模拟人工操作
                            time.sleep(random.uniform(2, 4))
                        except Exception as e:
                            print(f"{log_prefix} 滚动评论区失败: {e}")
                            scroll_done += 1
                            since_scroll = 0

                print(f"{log_prefix} 第 {i+1} 个视频处理完成，点赞数: {current_like_count}/{max_like_per_video}，关注数: {current_follow_count}/{max_follow_per_video}")

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
            
            # 确保只保留主窗口，清理可能残留的窗口
            if len(driver.window_handles) > 1:
                print(f"{log_prefix} 检测到多个窗口，关闭额外窗口...")
                for handle in driver.window_handles[1:]:
                    driver.switch_to.window(handle)
                    driver.close()
                driver.switch_to.window(driver.window_handles[0])
                print(f"{log_prefix} 已关闭额外窗口，保留主窗口")
            
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
