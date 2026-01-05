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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 单文件常量与解析
SEARCH_KEYWORDS_DEFAULT = ["美女","美食", "穿搭", "旅行"]
BROWSER_ID_DEFAULT = "57bd9953b5364d3db5c4ac7cfbb9a1b3"

def parse_keywords(raw):
    s = raw
    if not s:
        return SEARCH_KEYWORDS_DEFAULT[:]
    try:
        if isinstance(s, str):
            t = s.strip()
            if not t:
                return SEARCH_KEYWORDS_DEFAULT[:]
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
        return SEARCH_KEYWORDS_DEFAULT[:]
    return SEARCH_KEYWORDS_DEFAULT[:]

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


def process_comments_sequentially(driver, enable_like=True, enable_reply=True, enable_visit_avatar=True, max_count=None):
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

        # 滚动加载更多评论
        scroll_to_load_more_comments(driver)

        # 获取所有评论项
        comment_items = driver.find_elements(
            By.CSS_SELECTOR,
            "div.comments-container > div.list-container > div.parent-comment"
        )

        print(f"总共找到 {len(comment_items)} 条评论")

        # 逐条处理所有评论
        for i, comment_item in enumerate(comment_items):
            if max_count is not None and i >= max_count:
                break
            print(f"\n处理第 {i + 1} 条评论:")

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

                # 访问头像功能
                if enable_visit_avatar:
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
                        time.sleep(2)  # 等待页面加载

                        # 切换到新标签页
                        all_handles = driver.window_handles
                        if len(all_handles) > 1:
                            driver.switch_to.window(all_handles[-1])
                            print("  已切换到用户主页")
                            time.sleep(3)  # 等待页面加载
                            follow_user_if_needed(driver)
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
                    print("  访问头像功能已禁用")

                # 点赞按钮
                if enable_like:
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
                        time.sleep(0.5)  # 您偏好的点击间隔时间
                    except:
                        print("  未找到点赞按钮或点击失败")
                else:
                    print("  点赞功能已禁用")
                
                # 回复按钮
                if enable_reply:
                    try:
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
                            reply_text = "牛"
                            wait = WebDriverWait(driver, 5)
                            try:
                                editor = comment_item.find_element(By.CSS_SELECTOR, "div.reply-box [contenteditable='true']")
                            except Exception:
                                try:
                                    editor = wait.until(EC.presence_of_element_located(
                                        (By.XPATH, ".//*[contains(@placeholder,'回复') or contains(@placeholder,'评论') or @contenteditable='true']")
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
                                    ActionChains(driver).move_to_element(editor).click(editor).send_keys(reply_text).perform()
                                    print("  已输入回复内容")
                                except Exception:
                                    try:
                                        editor.send_keys(reply_text)
                                        print("  已输入回复内容")
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
                    print("  回复功能已禁用")

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
                print(f"  处理第 {i + 1} 条评论时出错: {e}")

    except Exception as e:
        print(f"遍历处理评论区时出错: {e}")

def process_search_keywords(driver):
    raw_env = os.getenv("KEYWORDS")
    kws = parse_keywords(raw_env)
    wait_seconds = 10
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    driver.get("https://www.xiaohongshu.com")
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(1)
    for kw in kws:
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
            print("[xhs] 未找到搜索输入框")
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
        print(f"[xhs] 搜索完成: {kw}")
        try:
            browse_search_results_and_operate(driver, items_to_visit=2, actions_per_video=3)
        except Exception as e:
            print(f"[xhs] 浏览并操作失败: {e}")

def get_search_result_covers(driver):
    els = driver.find_elements(By.CSS_SELECTOR, "section.note-item a.cover.mask.ld")
    if not els:
        els = driver.find_elements(By.CSS_SELECTOR, "section.note-item a.cover")
    return els

def visit_video_and_operate(driver, actions_per_video=3):
    process_comments_sequentially(driver, enable_like=True, enable_reply=False, enable_visit_avatar=True, max_count=actions_per_video)

def browse_search_results_and_operate(driver, items_to_visit=2, actions_per_video=3):
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
        visit_video_and_operate(driver, actions_per_video)
        if len(driver.window_handles) > 1:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        else:
            driver.back()
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1)
        covers = get_search_result_covers(driver)

def main():
    """
    主函数 - 打开指定ID的比特浏览器并访问小红书链接
    """
    browser_id = os.getenv("BIT_BROWSER_ID") or BROWSER_ID_DEFAULT
    print(f"正在打开比特浏览器 (ID: {browser_id})...")
    res = open_bit_browser(browser_id)

    if not res or "data" not in res:
        print("无法打开比特浏览器")
        return

    driver_path = res["data"].get("driver")
    debugger_address = res["data"].get("http")

    print(f"浏览器已成功打开")
    print(f"驱动路径: {driver_path}")
    print(f"调试地址: {debugger_address}")

    try:
        from selenium.webdriver.chrome.options import Options
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", debugger_address)
        chrome_service = Service(driver_path)
        driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
        print("WebDriver连接成功")

        process_search_keywords(driver)
        input("\n按Enter键退出...")

    except Exception as e:
        print(f"连接浏览器或访问链接时出现错误: {e}")


if __name__ == "__main__":
    main()
