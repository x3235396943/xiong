from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random

from ..tools.config import XhsConfig, get_config

_DEFAULT_XHS_CONFIG = XhsConfig()


def _is_empty_value(v):
    if v is None:
        return True
    if isinstance(v, (str, list, tuple, dict, set)) and len(v) == 0:
        return True
    return False


def _coerce_bool(v, default: bool) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(int(v))
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("1", "true", "t", "yes", "y", "on"):
            return True
        if t in ("0", "false", "f", "no", "n", "off"):
            return False
    return default


def _coerce_int(v, default: int) -> int:
    if v is None:
        return default
    if isinstance(v, bool):
        return int(v)
    try:
        return int(v)
    except Exception:
        return default


def _coerce_list(v, default: list):
    if _is_empty_value(v):
        return list(default)
    if isinstance(v, list):
        return v
    if isinstance(v, tuple):
        return list(v)
    if isinstance(v, set):
        return list(v)
    if isinstance(v, str):
        t = v.strip()
        if not t:
            return list(default)
        try:
            import json

            data = json.loads(t)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        for sep in [",", "，", ";", "；", " "]:
            t = t.replace(sep, ",")
        parts = [x.strip() for x in t.split(",") if x.strip()]
        return parts if parts else list(default)
    return list(default)


def _coerce_range_pair(v, default_pair: list):
    arr = _coerce_list(v, default_pair)
    if len(arr) >= 2:
        return [arr[0], arr[1]]
    return list(default_pair)


def get_xhs_effective_settings(cfg=None) -> dict:
    cfg = cfg or get_config()
    d = _DEFAULT_XHS_CONFIG

    return {
        "KEYWORDS": _coerce_list(getattr(cfg, "KEYWORDS", None), d.KEYWORDS),
        "MAX_SCROLL_VIDEO": _coerce_range_pair(getattr(cfg, "MAX_SCROLL_VIDEO", None), d.MAX_SCROLL_VIDEO),
        "MAX_COMMENT": _coerce_range_pair(getattr(cfg, "MAX_COMMENT", None), d.MAX_COMMENT),
        "LIKE_PROBABILITY": _coerce_int(getattr(cfg, "LIKE_PROBABILITY", None), d.LIKE_PROBABILITY),
        "VISIT_ENABLE": _coerce_int(getattr(cfg, "VISIT_ENABLE", None), d.VISIT_ENABLE),
        "PROFILE_FOLLOW_PROBABILITY": _coerce_int(
            getattr(cfg, "PROFILE_FOLLOW_PROBABILITY", None), d.PROFILE_FOLLOW_PROBABILITY
        ),
        "LIKE_WAIT_MIN": _coerce_int(getattr(cfg, "LIKE_WAIT_MIN", None), d.LIKE_WAIT_MIN),
        "LIKE_WAIT_MAX": _coerce_int(getattr(cfg, "LIKE_WAIT_MAX", None), d.LIKE_WAIT_MAX),
        "VISIT_MIN": _coerce_int(getattr(cfg, "VISIT_MIN", None), d.VISIT_MIN),
        "VISIT_MAX": _coerce_int(getattr(cfg, "VISIT_MAX", None), d.VISIT_MAX),
        "VIDEO_REPLY_RATE": _coerce_int(getattr(cfg, "VIDEO_REPLY_RATE", None), d.VIDEO_REPLY_RATE),
        "VIDEO_REPLY_WAIT_MIN": _coerce_int(getattr(cfg, "VIDEO_REPLY_WAIT_MIN", None), d.VIDEO_REPLY_WAIT_MIN),
        "VIDEO_REPLY_WAIT_MAX": _coerce_int(getattr(cfg, "VIDEO_REPLY_WAIT_MAX", None), d.VIDEO_REPLY_WAIT_MAX),
        "MIN_FOLLOWS_PER_VIDEO": _coerce_int(getattr(cfg, "MIN_FOLLOWS_PER_VIDEO", None), d.MIN_FOLLOWS_PER_VIDEO),
        "MAX_FOLLOWS_PER_VIDEO": _coerce_int(getattr(cfg, "MAX_FOLLOWS_PER_VIDEO", None), d.MAX_FOLLOWS_PER_VIDEO),
        "COMMENT_LIKE_COUNT_MIN": _coerce_int(
            getattr(cfg, "COMMENT_LIKE_COUNT_MIN", None), d.COMMENT_LIKE_COUNT_MIN
        ),
        "COMMENT_LIKE_COUNT_MAX": _coerce_int(
            getattr(cfg, "COMMENT_LIKE_COUNT_MAX", None), d.COMMENT_LIKE_COUNT_MAX
        ),
        "VIDEO_COMMENTS": getattr(cfg, "VIDEO_COMMENTS", None)
        if not _is_empty_value(getattr(cfg, "VIDEO_COMMENTS", None))
        else d.VIDEO_COMMENTS,
        "COMMENT_FILTER_KEYWORDS": _coerce_list(getattr(cfg, "COMMENT_FILTER_KEYWORDS", None), d.COMMENT_FILTER_KEYWORDS),
        "ENABLE_LIKE": _coerce_bool(getattr(cfg, "ENABLE_LIKE", None), d.ENABLE_LIKE),
        "ENABLE_FOLLOW": _coerce_bool(getattr(cfg, "ENABLE_FOLLOW", None), d.ENABLE_FOLLOW),
        "ENABLE_PROFILE_VISIT": _coerce_bool(getattr(cfg, "ENABLE_PROFILE_VISIT", None), d.ENABLE_PROFILE_VISIT),
        "ENABLE_VIDEO_COMMENT": _coerce_bool(getattr(cfg, "ENABLE_VIDEO_COMMENT", None), d.ENABLE_VIDEO_COMMENT),
        "ENABLE_SEARCH_KEYWORDS": _coerce_bool(getattr(cfg, "ENABLE_SEARCH_KEYWORDS", None), d.ENABLE_SEARCH_KEYWORDS),
        "ENABLE_COMMENT_REPLY": _coerce_bool(getattr(cfg, "ENABLE_COMMENT_REPLY", None), d.ENABLE_COMMENT_REPLY),
        "COMMENT_REPLY_PROBABILITY": _coerce_int(
            getattr(cfg, "COMMENT_REPLY_PROBABILITY", None), d.COMMENT_REPLY_PROBABILITY
        ),
        "COMMENT_WAIT_MIN": _coerce_int(getattr(cfg, "COMMENT_WAIT_MIN", None), d.COMMENT_WAIT_MIN),
        "COMMENT_WAIT_MAX": _coerce_int(getattr(cfg, "COMMENT_WAIT_MAX", None), d.COMMENT_WAIT_MAX),
        "COMMENT_REPLIES": getattr(cfg, "COMMENT_REPLIES", None)
        if not _is_empty_value(getattr(cfg, "COMMENT_REPLIES", None))
        else d.COMMENT_REPLIES,
        "BIT_BROWSER_IDS": _coerce_list(getattr(cfg, "BIT_BROWSER_IDS", None), d.BIT_BROWSER_IDS),
        "URLS": _coerce_list(getattr(cfg, "URLS", None), []),
    }


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
        print(f"[follow] 当前按钮文本: {btn_text}")

        # 已关注 / 互相关注 / 已请求
        if btn_text != "关注":
            print("[follow] 已是关注状态，跳过")
            return False

        # 模拟真人停顿
        time.sleep(0.6 + random.random())

        # JS 点击
        driver.execute_script("arguments[0].click();", follow_btn)
        print("[follow] 已点击关注")

        if sleep_after:
            time.sleep(1.2 + random.random())

        return True

    except Exception as e:
        print(f"[follow] 点击关注失败: {e}")
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
        print(f"激活视频评论失败: {e}")
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
        textarea.send_keys(WebDriverWait.Keys.ENTER)
        return True
    except Exception as e:
        print(f"输入并发送评论失败: {e}")
        return False


def send_video_comment(driver, text):
    if activate_video_comment(driver):
        return input_and_send(driver, text)
    return False


def scroll_element_sync(driver, element, delta_y=400, sleep_time=2):
    import time
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
        scroll_origin = ScrollOrigin.from_element(element)
        ActionChains(driver).scroll_from_origin(scroll_origin, 0, delta_y).perform()
        time.sleep(sleep_time)
    except Exception as e:
        print(f"滚动失败: {e}")


def scroll_to_load_more_comments(driver, count: int = 5, delta_y: int = 500, sleep_time: float = 2.0):
    print("尝试滚动以加载更多评论...")
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
        print(f"第 {i + 1} 次滚动完成")


def process_comments_sequentially(
        driver,
        enable_like=None,
        enable_reply=None,
        enable_visit_avatar=None,
        enable_follow=None,
        max_count=None,
        like_probability=None,
        visit_probability=None,
        follow_probability=None,
        like_wait_min=None,
        like_wait_max=None,
        profile_wait_min=None,
        profile_wait_max=None,
        follow_wait_min=None,
        follow_wait_max=None,
        min_follows_per_video=None,
        max_follows_per_video=None,
        comment_like_count_min=None,
        comment_like_count_max=None,
        comment_scroll_minmax=None,
        comment_reply_probability=None,
        comment_wait_min=None,
        comment_wait_max=None,
        comment_replies=None,
        enable_search_keywords=None,
        comment_filter_keywords=None,
        reporter=None,  # 新增数据上报对象
        cfg=None,
        browser_id=None,  # 浏览器ID参数
):
    """
    逐条遍历处理评论区的点赞和回复操作

    Args:
        driver: WebDriver实例
        enable_like: 是否启用点赞功能
        enable_reply: 是否启用回复功能
        enable_visit_avatar: 是否启用访问头像功能
        reporter: 数据上报对象
    """
    try:
        from ..tools.core import log
        settings = get_xhs_effective_settings(cfg)
        enable_like = settings["ENABLE_LIKE"] if enable_like is None else enable_like
        enable_reply = settings["ENABLE_COMMENT_REPLY"] if enable_reply is None else enable_reply
        enable_visit_avatar = settings["ENABLE_PROFILE_VISIT"] if enable_visit_avatar is None else enable_visit_avatar
        enable_follow = settings["ENABLE_FOLLOW"] if enable_follow is None else enable_follow
        like_probability = settings["LIKE_PROBABILITY"] if like_probability is None else like_probability
        visit_probability = settings["VISIT_ENABLE"] if visit_probability is None else visit_probability
        follow_probability = settings["PROFILE_FOLLOW_PROBABILITY"] if follow_probability is None else follow_probability
        like_wait_min = settings["LIKE_WAIT_MIN"] if like_wait_min is None else like_wait_min
        like_wait_max = settings["LIKE_WAIT_MAX"] if like_wait_max is None else like_wait_max
        profile_wait_min = settings["COMMENT_WAIT_MIN"] if profile_wait_min is None else profile_wait_min
        profile_wait_max = settings["COMMENT_WAIT_MAX"] if profile_wait_max is None else profile_wait_max
        follow_wait_min = settings["VISIT_MIN"] if follow_wait_min is None else follow_wait_min
        follow_wait_max = settings["VISIT_MAX"] if follow_wait_max is None else follow_wait_max
        min_follows_per_video = (
            settings["MIN_FOLLOWS_PER_VIDEO"] if min_follows_per_video is None else min_follows_per_video
        )
        max_follows_per_video = (
            settings["MAX_FOLLOWS_PER_VIDEO"] if max_follows_per_video is None else max_follows_per_video
        )
        comment_like_count_min = (
            settings["COMMENT_LIKE_COUNT_MIN"] if comment_like_count_min is None else comment_like_count_min
        )
        comment_like_count_max = (
            settings["COMMENT_LIKE_COUNT_MAX"] if comment_like_count_max is None else comment_like_count_max
        )
        comment_scroll_minmax = settings["MAX_COMMENT"] if comment_scroll_minmax is None else comment_scroll_minmax
        comment_reply_probability = (
            settings["COMMENT_REPLY_PROBABILITY"] if comment_reply_probability is None else comment_reply_probability
        )
        comment_wait_min = settings["COMMENT_WAIT_MIN"] if comment_wait_min is None else comment_wait_min
        comment_wait_max = settings["COMMENT_WAIT_MAX"] if comment_wait_max is None else comment_wait_max
        comment_replies = settings["COMMENT_REPLIES"] if comment_replies is None else comment_replies
        enable_search_keywords = (
            settings["ENABLE_SEARCH_KEYWORDS"] if enable_search_keywords is None else enable_search_keywords
        )
        comment_filter_keywords = (
            settings["COMMENT_FILTER_KEYWORDS"] if comment_filter_keywords is None else comment_filter_keywords
        )
        log.info("开始逐条遍历处理评论...")

        # 等待评论区加载
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "div.comments-container > div.list-container > div.parent-comment"
        )))

        # 初始化变量
        scroll_times = rand_int_range(comment_scroll_minmax, 2, 5)
        processed_count = 0  # 已处理的评论数量
        scroll_done = 0      # 已滚动次数
        
        # 获取初始评论项
        comment_items = driver.find_elements(
            By.CSS_SELECTOR,
            "div.comments-container > div.list-container > div.parent-comment"
        )

        log.info(f"初始找到 {len(comment_items)} 条评论")

        like_target = rand_int_range([comment_like_count_min, comment_like_count_max], 0, 0) if enable_like else 0
        profile_target = rand_int_range([min_follows_per_video, max_follows_per_video], 0,
                                        0) if enable_visit_avatar else 0
        liked_count = 0
        visited_count = 0
        followed_count = 0
        
        # 检查是否有设置评论过滤关键字
        has_filter_keywords = enable_search_keywords and comment_filter_keywords and len(comment_filter_keywords) > 0

        # 循环处理评论，直到达到目标或滚动次数用完
        while scroll_done < scroll_times:
            # 重新获取评论项，因为滚动后可能会加载新评论
            comment_items = driver.find_elements(
                By.CSS_SELECTOR,
                "div.comments-container > div.list-container > div.parent-comment"
            )

            # 检查是否已达到目标或评论数量
            if (liked_count >= like_target and visited_count >= profile_target) or \
               (max_count is not None and processed_count >= max_count):
                break

            # 遍历当前页面的评论
            for i, comment_item in enumerate(comment_items):
                # 检查是否已达到目标或评论数量
                if (liked_count >= like_target and visited_count >= profile_target) or \
                   (max_count is not None and processed_count >= max_count):
                    break
                    
                # 生成浏览器日志前缀
                log_prefix = ""
                if browser_id:
                    browser_num = browser_id.split("-")[-1] if "-" in browser_id else browser_id[:8]
                    log_prefix = f"[浏览器 #{browser_num}] "
                log.info(f"\n{log_prefix}处理第 {processed_count + 1} 条评论:")

                try:
                    # 获取评论容器的第一个子元素
                    item = comment_item.find_element(
                        By.CSS_SELECTOR,
                        "div:first-child"
                    )

                    # 提取评论文本
                    try:
                        comment_text = item.find_element(
                            By.CSS_SELECTOR,
                            "div.content span span"
                        ).text
                        log.info(f"  评论内容: {comment_text[:50]}..." if len(
                            comment_text) > 50 else f"  评论内容: {comment_text}")
                    except:
                        log.info("  无法获取评论内容")

                    # 检查评论内容是否包含过滤关键字
                    comment_contains_keyword = False
                    comment_text_for_keyword = ""
                    try:
                        comment_text_for_keyword = item.find_element(
                            By.CSS_SELECTOR,
                            "div.content span span"
                        ).text
                        if has_filter_keywords:
                            for keyword in comment_filter_keywords:
                                if keyword.lower() in comment_text_for_keyword.lower():
                                    comment_contains_keyword = True
                                    log.info(f"  评论包含关键字 '{keyword}'，执行特殊操作")
                                    break
                    except:
                        log.info("  无法获取评论内容用于关键字匹配")
                    
                    # 正常按概率执行访问头像操作，关键字命中时强制执行
                    should_visit = enable_visit_avatar and \
                                   visited_count < profile_target and \
                                   ((not has_filter_keywords and random.randint(1, 100) <= int(visit_probability)) or \
                                    (has_filter_keywords and comment_contains_keyword) or \
                                    (has_filter_keywords and not comment_contains_keyword and random.randint(1, 100) <= int(visit_probability)))
                    if should_visit:
                        try:
                            avatar_link = item.find_element(
                                By.CSS_SELECTOR,
                                "div.avatar > a"
                            )
                            try:
                                ensure_element_centered(driver, avatar_link)
                            except Exception:
                                pass
                            # 点击头像链接
                            driver.execute_script("arguments[0].click();", avatar_link)
                            log.info("  已点击头像")
                            time.sleep(2)

                            # 切换到新标签页
                            all_handles = driver.window_handles
                            if len(all_handles) > 1:
                                driver.switch_to.window(all_handles[-1])
                                # 如果是关键字匹配的评论，则不受上限限制
                                if not (has_filter_keywords and comment_contains_keyword):
                                    visited_count += 1
                                log.info("  已切换到用户主页")
                                rand_sleep(profile_wait_min, profile_wait_max)
                                if enable_follow and (random.randint(1, 100) <= int(follow_probability) or 
                                                      (has_filter_keywords and comment_contains_keyword)):
                                    followed = follow_user_if_needed(driver)
                                    if followed:
                                        # 如果是关键字匹配的评论，则不受上限限制
                                        if not (has_filter_keywords and comment_contains_keyword):
                                            followed_count += 1
                                        rand_sleep(follow_wait_min, follow_wait_max)
                                        # 数据上报
                                        if reporter:
                                            try:
                                                reporter.set_action("follow")
                                                reporter.increment_follow(1)
                                            except Exception:
                                                pass
                                # 关闭用户主页标签页，切回原页面
                                driver.close()
                                driver.switch_to.window(all_handles[0])
                                log.info("  已关闭用户主页，切回原页面")
                            else:
                                log.info("  未打开新标签页")

                            time.sleep(0.5)
                        except:
                            log.info("  未找到头像链接或点击失败")
                    else:
                        if not enable_visit_avatar:
                            log.info("  访问头像功能已禁用")
                        else:
                            log.info("  访问头像已跳过")

                    # 点赞按钮
                    # 正常按概率执行点赞操作，关键字命中时强制执行
                    should_like = enable_like and \
                                  liked_count < like_target and \
                                  ((not has_filter_keywords and random.randint(1, 100) <= int(like_probability)) or \
                                   (has_filter_keywords and comment_contains_keyword) or \
                                   (has_filter_keywords and not comment_contains_keyword and random.randint(1, 100) <= int(like_probability)))
                    if should_like:
                        try:
                            # 使用完整的CSS选择器路径在parent-comment元素下寻找点赞按钮
                            like_btn = comment_item.find_element(
                                By.CSS_SELECTOR,
                                "div:first-child div.interactions span.like-wrapper"
                            )
                            try:
                                ensure_element_centered(driver, like_btn)
                            except Exception:
                                pass
                            # 使用JavaScript点击，避免被其他元素遮挡
                            driver.execute_script("arguments[0].click();", like_btn)
                            log.info("  已点击点赞按钮")
                            # 如果是关键字匹配的评论，则不受上限限制
                            if not (has_filter_keywords and comment_contains_keyword):
                                liked_count += 1
                            rand_sleep(like_wait_min, like_wait_max)
                            # 数据上报
                            if reporter:
                                try:
                                    reporter.set_action("like")
                                    reporter.increment_like(1)
                                except Exception:
                                    pass
                        except:
                            log.info("  未找到点赞按钮或点击失败")
                    else:
                        if not enable_like:
                            log.info("  点赞功能已禁用")
                        else:
                            log.info("  点赞已跳过")

                    # 回复按钮
                    # 正常按概率执行回复操作，关键字命中时强制执行
                    should_reply = enable_reply and \
                                   ((not has_filter_keywords and random.randint(1, 100) <= int(comment_reply_probability)) or \
                                    (has_filter_keywords and comment_contains_keyword) or \
                                    (has_filter_keywords and not comment_contains_keyword and random.randint(1, 100) <= int(comment_reply_probability)))
                    if should_reply:
                        try:
                            # 添加评论回复前的等待时间
                            if not (has_filter_keywords and comment_contains_keyword):
                                rand_sleep(comment_wait_min, comment_wait_max)
                            
                            # 使用完整的CSS选择器路径在parent-comment元素下寻找回复按钮
                            reply_btn = comment_item.find_element(
                                By.CSS_SELECTOR,
                                "div:first-child div.interactions > div.reply"
                            )
                            try:
                                ensure_element_centered(driver, reply_btn)
                            except Exception:
                                pass
                            # 使用JavaScript点击，避免被其他元素遮挡
                            driver.execute_script("arguments[0].click();", reply_btn)
                            log.info("  已点击回复按钮")
                            time.sleep(0.5)  # 您偏好的点击间隔时间
                            try:
                                # 从多个可能的回复中随机选择一个
                                possible_replies = comment_replies.split('-&-') if '-&-' in comment_replies else [comment_replies]
                                reply_text = random.choice(possible_replies)
                                wait = WebDriverWait(driver, 5)
                                try:
                                    editor = comment_item.find_element(By.CSS_SELECTOR,
                                                                       "div.reply-box [contenteditable='true']")
                                except Exception:
                                    try:
                                        editor = wait.until(EC.presence_of_element_located(
                                            (By.XPATH,
                                             ".//*[contains(@placeholder,'回复') or contains(@placeholder,'评论') or @contenteditable='true']")
                                        ))
                                    except Exception:
                                        editor = None
                                if not editor:
                                    log.info("  未找到回复输入框")
                                else:
                                    ensure_element_centered(driver, editor)
                                    try:
                                        editor.click()
                                    except Exception:
                                        pass
                                    try:
                                        from selenium.webdriver.common.action_chains import ActionChains
                                        ActionChains(driver).move_to_element(editor).click(editor).send_keys(
                                            reply_text).perform()
                                        log.info(f"  已输入回复内容: {reply_text}")
                                    except Exception:
                                        try:
                                            editor.send_keys(reply_text)
                                            log.info(f"  已输入回复内容: {reply_text}")
                                        except Exception:
                                            log.info("  输入回复内容失败")
                                    try:
                                        send_btn = comment_item.find_element(By.XPATH, ".//span[contains(., '发送')]")
                                        ensure_element_centered(driver, send_btn)
                                        driver.execute_script("arguments[0].click();", send_btn)
                                        log.info("  已点击发送按钮")
                                    except Exception:
                                        try:
                                            from selenium.webdriver.common.keys import Keys
                                            editor.send_keys(Keys.ENTER)
                                            log.info("  已按回车发送")
                                        except Exception:
                                            log.info("  按回车发送失败")
                                    time.sleep(0.5)
                                    # 数据上报
                                    if reporter:
                                        try:
                                            reporter.set_action("comment")
                                            reporter.increment_comment(1)
                                        except Exception:
                                            pass
                            except Exception as e:
                                log.info(f"  回复输入或发送失败: {e}")

                        except:
                            log.info("  未找到回复按钮或点击失败")
                    else:
                        if not enable_reply:
                            log.info("  回复功能已禁用")
                        else:
                            log.info("  回复已跳过（概率未满足）")

                    # 尝试获取点赞数
                    try:
                        like_count = item.find_element(
                            By.CSS_SELECTOR,
                            "div.interactions span.count"
                        ).text
                        log.info(f"  点赞数: {like_count}")
                    except:
                        log.info("  无法获取点赞数")

                except Exception as e:
                    log.info(f"  处理第 {processed_count + 1} 条评论时出错: {e}")
                
                # 在处理每条评论之间添加随机间隔，模拟人工浏览
                time.sleep(random.uniform(1.5, 2))
                
                processed_count += 1  # 增加已处理评论计数

                # 每处理3条评论就滚动一次，加载更多评论
                if processed_count % 3 == 0:
                    if scroll_done < scroll_times:
                        log.info(f"已处理 {processed_count} 条评论，进行第 {scroll_done + 1} 次滚动...")
                        scroll_to_load_more_comments(driver, count=1)
                        scroll_done += 1
                        
                        # 滚动后添加等待时间
                        time.sleep(2)
                        
                        # 重新获取评论列表，因为滚动后可能加载了新评论
                        comment_items = driver.find_elements(
                            By.CSS_SELECTOR,
                            "div.comments-container > div.list-container > div.parent-comment"
                        )
                        log.info(f"滚动后找到 {len(comment_items)} 条评论")

        log.info(f"评论处理完成，共处理 {processed_count} 条评论，进行了 {scroll_done} 次滚动")

    except Exception as e:
        log.info(f"遍历处理评论区时出错: {e}")


def visit_video_and_operate(driver, reporter=None, browser_id=None):
    from ..tools.core import log
    settings = get_xhs_effective_settings()
    if settings["ENABLE_VIDEO_COMMENT"] and random.randint(1, 100) <= int(settings["VIDEO_REPLY_RATE"]):
        rand_sleep(settings["VIDEO_REPLY_WAIT_MIN"], settings["VIDEO_REPLY_WAIT_MAX"])
        comment_texts = parse_video_comments(settings["VIDEO_COMMENTS"])
        if comment_texts:
            selected_comment = random.choice(comment_texts)
            if send_video_comment(driver, selected_comment):
                # 视频评论数据上报
                if reporter:
                    try:
                        reporter.set_action("videoComment")
                        reporter.increment_video_comment(1)
                    except Exception:
                        pass
            time.sleep(0.5)

    process_comments_sequentially(driver, reporter=reporter, browser_id=browser_id)


def get_search_result_covers(driver):
    els = driver.find_elements(By.CSS_SELECTOR, "section.note-item a.cover.mask.ld")
    if not els:
        els = driver.find_elements(By.CSS_SELECTOR, "section.note-item a.cover")
    return els


def browse_search_results_and_operate(driver, items_to_visit=2, reporter=None, browser_id=None):
    covers = get_search_result_covers(driver)
    n = min(items_to_visit, len(covers))
    for i in range(n):
        target = covers[i]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", target)
        time.sleep(0.5)
        handles = driver.window_handles
        if len(handles) > 1:
            driver.switch_to.window(handles[-1])
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        visit_video_and_operate(driver, reporter=reporter, browser_id=browser_id)
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        else:
            driver.back()
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)
        covers = get_search_result_covers(driver)
