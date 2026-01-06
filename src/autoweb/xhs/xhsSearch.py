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
        print(f"滚动失败: {e}")


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
        textarea.send_keys(Keys.ENTER)
        return True
    except Exception as e:
        print(f"输入并发送评论失败: {e}")
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
        print(f"打开比特浏览器时出错: {e}")
        return {}


def scroll_to_load_more_comments(driver, count: int = 5, delta_y: int = 400, sleep_time: float = 2.0):
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
        enable_like=ENABLE_LIKE,
        enable_reply=ENABLE_COMMENT_REPLY,  # 使用新添加的常量作为默认值
        enable_visit_avatar=ENABLE_PROFILE_VISIT,
        max_count=None,
        like_probability=LIKE_PROBABILITY,
        visit_probability=VISIT_ENABLE,
        follow_probability=PROFILE_FOLLOW_PROBABILITY,
        like_wait_min=DEFAULT_LIKE_WAIT_MIN,
        like_wait_max=DEFAULT_LIKE_WAIT_MAX,
        profile_wait_min=DEFAULT_PROFILE_WAIT_MIN,
        profile_wait_max=DEFAULT_PROFILE_WAIT_MAX,
        follow_wait_min=DEFAULT_VISIT_MIN,
        follow_wait_max=DEFAULT_VISIT_MAX,
        min_follows_per_video=MIN_FOLLOWS_PER_VIDEO,
        max_follows_per_video=MAX_FOLLOWS_PER_VIDEO,
        comment_like_count_min=COMMENT_LIKE_COUNT_MIN,
        comment_like_count_max=COMMENT_LIKE_COUNT_MAX,
        comment_scroll_minmax=DEFAULT_MAX_COMMENT,
        comment_reply_probability=COMMENT_REPLY_PROBABILITY,  # 新增评论回复概率参数
        comment_wait_min=COMMENT_WAIT_MIN,  # 新增评论回复前最小等待时间
        comment_wait_max=COMMENT_WAIT_MAX,  # 新增评论回复前最大等待时间
        comment_replies=COMMENT_REPLIES,  # 新增评论回复内容
        enable_search_keywords=ENABLE_SEARCH_KEYWORDS,  # 新增是否启用搜索关键字功能
        comment_filter_keywords=COMMENT_FILTER_KEYWORDS,  # 新增筛选评论区关键字
):
    """
    逐条遍历处理评论区的点赞和回复操作

    Args:
        driver: WebDriver实例
        enable_like: 是否启用点赞功能
        enable_reply: 是否启用回复功能
        enable_visit_avatar: 是否启用访问头像功能
    """
    try:
        print("开始逐条遍历处理评论...")

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

        print(f"初始找到 {len(comment_items)} 条评论")

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
                    
                print(f"\n处理第 {processed_count + 1} 条评论:")

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
                        print(f"  评论内容: {comment_text[:50]}..." if len(
                            comment_text) > 50 else f"  评论内容: {comment_text}")
                    except:
                        print("  无法获取评论内容")

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
                                    print(f"  评论包含关键字 '{keyword}'，执行特殊操作")
                                    break
                    except:
                        print("  无法获取评论内容用于关键字匹配")
                    
                    # 如果包含关键字，则执行访问头像操作（不受上限限制）
                    if (enable_visit_avatar and (not has_filter_keywords or comment_contains_keyword) and 
                        visited_count < profile_target and random.randint(1, 100) <= int(visit_probability)) or \
                       (enable_visit_avatar and has_filter_keywords and comment_contains_keyword):
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
                            print("  已点击头像")
                            time.sleep(2)

                            # 切换到新标签页
                            all_handles = driver.window_handles
                            if len(all_handles) > 1:
                                driver.switch_to.window(all_handles[-1])
                                # 如果是关键字匹配的评论，则不受上限限制
                                if not (has_filter_keywords and comment_contains_keyword):
                                    visited_count += 1
                                print("  已切换到用户主页")
                                rand_sleep(profile_wait_min, profile_wait_max)
                                if ENABLE_FOLLOW and (random.randint(1, 100) <= int(follow_probability) or 
                                                      (has_filter_keywords and comment_contains_keyword)):
                                    followed = follow_user_if_needed(driver)
                                    if followed:
                                        # 如果是关键字匹配的评论，则不受上限限制
                                        if not (has_filter_keywords and comment_contains_keyword):
                                            followed_count += 1
                                        rand_sleep(follow_wait_min, follow_wait_max)
                                # 关闭用户主页标签页，切回原页面
                                driver.close()
                                driver.switch_to.window(all_handles[0])
                                print("  已关闭用户主页，切回原页面")
                            else:
                                print("  未打开新标签页")

                            time.sleep(0.5)
                        except:
                            print("  未找到头像链接或点击失败")
                    else:
                        if not enable_visit_avatar:
                            print("  访问头像功能已禁用")
                        else:
                            print("  访问头像已跳过")

                    # 点赞按钮
                    # 如果包含关键字，则执行点赞操作（不受上限限制）
                    if (enable_like and (not has_filter_keywords or comment_contains_keyword) and 
                        liked_count < like_target and random.randint(1, 100) <= int(like_probability)) or \
                       (enable_like and has_filter_keywords and comment_contains_keyword):
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
                            print("  已点击点赞按钮")
                            # 如果是关键字匹配的评论，则不受上限限制
                            if not (has_filter_keywords and comment_contains_keyword):
                                liked_count += 1
                            rand_sleep(like_wait_min, like_wait_max)
                        except:
                            print("  未找到点赞按钮或点击失败")
                    else:
                        if not enable_like:
                            print("  点赞功能已禁用")
                        else:
                            print("  点赞已跳过")

                    # 回复按钮
                    # 如果包含关键字，则执行回复操作（不受上限限制）
                    if (enable_reply and (not has_filter_keywords or comment_contains_keyword) and 
                        random.randint(1, 100) <= int(comment_reply_probability)) or \
                       (enable_reply and has_filter_keywords and comment_contains_keyword):
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
                            print("  已点击回复按钮")
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
                                    print("  未找到回复输入框")
                                else:
                                    ensure_element_centered(driver, editor)
                                    try:
                                        editor.click()
                                    except Exception:
                                        pass
                                    try:
                                        clear_input(editor)
                                    except Exception:
                                        pass
                                    try:
                                        from selenium.webdriver.common.action_chains import ActionChains
                                        ActionChains(driver).move_to_element(editor).click(editor).send_keys(
                                            reply_text).perform()
                                        print(f"  已输入回复内容: {reply_text}")
                                    except Exception:
                                        try:
                                            editor.send_keys(reply_text)
                                            print(f"  已输入回复内容: {reply_text}")
                                        except Exception:
                                            print("  输入回复内容失败")
                                    try:
                                        send_btn = comment_item.find_element(By.XPATH, ".//span[contains(., '发送')]")
                                        ensure_element_centered(driver, send_btn)
                                        driver.execute_script("arguments[0].click();", send_btn)
                                        print("  已点击发送按钮")
                                    except Exception:
                                        try:
                                            from selenium.webdriver.common.keys import Keys
                                            editor.send_keys(Keys.RETURN)
                                            print("  已按回车发送")
                                        except Exception:
                                            print("  按回车发送失败")
                                    time.sleep(0.5)
                            except Exception as e:
                                print(f"  回复输入或发送失败: {e}")

                        except:
                            print("  未找到回复按钮或点击失败")
                    else:
                        if not enable_reply:
                            print("  回复功能已禁用")
                        else:
                            print("  回复已跳过（概率未满足）")

                    # 尝试获取点赞数
                    try:
                        like_count = item.find_element(
                            By.CSS_SELECTOR,
                            "div.interactions span.count"
                        ).text
                        print(f"  点赞数: {like_count}")
                    except:
                        print("  无法获取点赞数")

                except Exception as e:
                    print(f"  处理第 {processed_count + 1} 条评论时出错: {e}")
                
                # 在处理每条评论之间添加随机间隔，模拟人工浏览
                time.sleep(random.uniform(0.5, 1.5))
                
                processed_count += 1  # 增加已处理评论计数

                # 每处理3条评论就滚动一次，加载更多评论
                if processed_count % 3 == 0:
                    if scroll_done < scroll_times:
                        print(f"已处理 {processed_count} 条评论，进行第 {scroll_done + 1} 次滚动...")
                        scroll_to_load_more_comments(driver, count=1)
                        scroll_done += 1
                        
                        # 滚动后添加等待时间
                        time.sleep(2)
                        
                        # 重新获取评论列表，因为滚动后可能加载了新评论
                        comment_items = driver.find_elements(
                            By.CSS_SELECTOR,
                            "div.comments-container > div.list-container > div.parent-comment"
                        )
                        print(f"滚动后找到 {len(comment_items)} 条评论")

        print(f"评论处理完成，共处理 {processed_count} 条评论，进行了 {scroll_done} 次滚动")

    except Exception as e:
        print(f"遍历处理评论区时出错: {e}")


def process_search_keywords(driver, keywords, log_prefix=""):
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
        print(f"{log_prefix} 搜索关键词: {kw}")
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
            print(f"{log_prefix} [xhs] 未找到搜索输入框")
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
        print(f"{log_prefix} [xhs] 搜索完成: {kw}")
        try:
            items_to_visit = rand_int_range(DEFAULT_MAX_SCROLL_VIDEO, 2, 3)
            browse_search_results_and_operate(driver, items_to_visit=items_to_visit)
        except Exception as e:
            print(f"{log_prefix} [xhs] 浏览并操作失败: {e}")


def get_search_result_covers(driver):
    els = driver.find_elements(By.CSS_SELECTOR, "section.note-item a.cover.mask.ld")
    if not els:
        els = driver.find_elements(By.CSS_SELECTOR, "section.note-item a.cover")
    return els


def visit_video_and_operate(driver):
    if ENABLE_VIDEO_COMMENT and random.randint(1, 100) <= int(VIDEO_REPLY_RATE):
        rand_sleep(VIDEO_REPLY_WAIT_MIN, VIDEO_REPLY_WAIT_MAX)
        comment_texts = parse_video_comments(VIDEO_COMMENTS)
        if comment_texts:
            selected_comment = random.choice(comment_texts)
            send_video_comment(driver, selected_comment)
            time.sleep(0.5)

    process_comments_sequentially(driver)


def browse_search_results_and_operate(driver, items_to_visit=2):
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
        visit_video_and_operate(driver)
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        else:
            driver.back()
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)
        covers = get_search_result_covers(driver)


def run_worker(browser_id, browser_number, kw_queue, kw_lock, log_prefix=""):
    """
    工作线程函数，为每个浏览器ID执行搜索任务
    """
    log_prefix = get_browser_log_prefix(browser_id)
    print(f"{log_prefix} 开始执行小红书自动化任务")
    print(f"{log_prefix} 浏览器ID: {browser_id}")

    res = open_bit_browser(browser_id)

    if not res or "data" not in res:
        print(f"{log_prefix} 无法打开比特浏览器")
        return

    driver_path = res["data"].get("driver")
    debugger_address = res["data"].get("http")

    print(f"{log_prefix} 浏览器已成功打开")
    print(f"{log_prefix} 驱动路径: {driver_path}")
    print(f"{log_prefix} 调试地址: {debugger_address}")

    try:
        from selenium.webdriver.chrome.options import Options
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", debugger_address)
        chrome_service = Service(driver_path)
        driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
        print(f"{log_prefix} WebDriver连接成功")

        # 获取关键词列表
        with kw_lock:
            keywords = list(kw_queue)  # 从队列获取关键词列表

        # 执行搜索任务
        process_search_keywords(driver, keywords, log_prefix)

        print(f"{log_prefix} 所有关键词处理完成，浏览器任务完成...")

    except Exception as e:
        print(f"{log_prefix} 连接浏览器或访问链接时出现错误: {e}")
    finally:
        try:
            driver.quit()
            print(f"{log_prefix} 浏览器已关闭")
        except:
            pass  # 如果driver没有成功初始化，忽略错误


def main():
    """
    主函数 - 使用多个比特浏览器ID并发执行搜索任务
    """
    # 获取配置
    cfg = get_config()
    
    # 解析环境变量或使用配置中心的值
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

    print(f"使用浏览器ID列表: {browser_ids}")
    print(f"使用关键词列表: {keywords}")

    if not browser_ids:
        print("没有配置浏览器ID，程序退出")
        return

    if not keywords:
        print("没有配置关键词，程序退出")
        return

    # 创建关键词队列和锁
    kw_queue = deque(keywords)
    kw_lock = threading.Lock()

    if len(browser_ids) <= 1:
        # 如果只有一个浏览器ID，直接运行
        run_worker(browser_ids[0], 1, kw_queue, kw_lock)
        return

    # 多线程执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(browser_ids)) as executor:
        futures = []
        for i, bid in enumerate(browser_ids):
            # 提交任务到线程池
            future = executor.submit(run_worker, bid, i + 1, kw_queue, kw_lock, "")
            futures.append(future)
            # 间隔启动浏览器，避免同时启动造成资源竞争
            if i < len(browser_ids) - 1:
                time.sleep(2.5)

        # 等待所有任务完成
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()  # 获取执行结果，如有异常会抛出
            except Exception as e:
                print(f"[并发] 线程执行出错: {e}")

    print("\n所有浏览器任务完成，程序退出...")


if __name__ == "__main__":
    main()