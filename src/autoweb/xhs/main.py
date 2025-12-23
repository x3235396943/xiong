#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
打开指定ID的比特浏览器并访问小红书链接，然后对评论进行遍历操作
"""

import json
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def clear_input(element):
    """
    清空输入框（跨平台）

    Args:
        element: 输入框元素
    """
    import sys
    from selenium.webdriver.common.keys import Keys

    if sys.platform == "win32":
        element.send_keys(Keys.CONTROL, "a")
    elif sys.platform == "darwin":  # Mac
        element.send_keys(Keys.COMMAND, "a")
    else:  # Linux
        element.send_keys(Keys.CONTROL, "a")
    element.send_keys(Keys.BACKSPACE)


def scroll_element_sync(driver, element, delta_y=400, sleep_time=2):
    """
    滚动元素（同步版本）

    Args:
        driver: WebDriver实例
        element: 要滚动的元素
        delta_y: 垂直滚动距离
        sleep_time: 滚动后等待时间（秒）
    """
    import time

    try:
        scroll_origin = ScrollOrigin.from_element(element)
        ActionChains(driver).scroll_from_origin(scroll_origin, 0, delta_y).perform()
        time.sleep(sleep_time)
    except Exception as e:
        print(f"滚动失败: {e}")


def ensure_element_centered(driver, element):
    """
    确保元素在屏幕中央

    Args:
        driver: WebDriver实例
        element: 元素
    """
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


# 比特浏览器API配置
_BIT_API_URL = "http://127.0.0.1:54345"
_BIT_HEADERS = {"Content-Type": "application/json"}


def open_bit_browser(browser_id: str) -> dict:
    """
    打开比特浏览器

    Args:
        browser_id: 浏览器ID

    Returns:
        包含驱动路径和调试地址的字典
    """
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


def process_comments_sequentially(driver, enable_like=True, enable_reply=True, enable_visit_avatar=True):
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
                        "div.content > span.text"
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
                        like_btn = item.find_element(
                            By.CSS_SELECTOR,
                            "div.interactions div.like"
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
                        reply_btn = item.find_element(
                            By.CSS_SELECTOR,
                            "div.interactions div.reply"
                        )
                        try:
                            ensure_element_centered(driver, reply_btn)
                        except Exception:
                            pass
                        # 使用JavaScript点击，避免被其他元素遮挡
                        driver.execute_script("arguments[0].click();", reply_btn)
                        print("  已点击回复按钮")
                        time.sleep(0.5)  # 您偏好的点击间隔时间

                        # 点击回复后可能会展开回复框，这里可以添加回复内容的逻辑
                        # 为了演示，我们直接关闭回复框
                        try:
                            cancel_btn = item.find_element(
                                By.CSS_SELECTOR,
                                "div.cancel"
                            )
                            driver.execute_script("arguments[0].click();", cancel_btn)
                            print("  已取消回复")
                            time.sleep(0.5)
                        except:
                            print("  未找到取消按钮")

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


def main():
    """
    主函数 - 打开指定ID的比特浏览器并访问小红书链接
    """
    # 固定的浏览器ID
    browser_id = "57bd9953b5364d3db5c4ac7cfbb9a1b3"

    # 小红书链接
    url = "https://www.xiaohongshu.com/discovery/item/693b98cb000000001e030556?source=webshare&xhsshare=pc_web&xsec_token=ABZ8bY4ZO-6CgS2h3puFrQvc_BqEe8s66nuRxObkjUTAs=&xsec_source=pc_share"

    print(f"正在打开比特浏览器 (ID: {browser_id})...")

    # 打开比特浏览器
    res = open_bit_browser(browser_id)

    if not res or "data" not in res:
        print("无法打开比特浏览器")
        if res:
            print(f"错误信息: {res}")
        return

    driver_path = res["data"].get("driver")
    debugger_address = res["data"].get("http")

    if not driver_path:
        print("驱动路径为空")
        return

    if not debugger_address:
        print("调试地址为空")
        return

    print(f"浏览器已成功打开")
    print(f"驱动路径: {driver_path}")
    print(f"调试地址: {debugger_address}")

    # 配置Chrome选项
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", debugger_address)

    try:
        # 创建WebDriver实例
        chrome_service = Service(driver_path)
        driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

        print("WebDriver连接成功")

        # 访问指定链接
        print(f"正在访问链接: {url}")
        driver.get(url)

        # 等待页面加载完成
        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        print("页面加载完成")
        print(f"页面标题: {driver.title}")

        # 等待一段时间让评论区加载
        print("等待评论区加载...")
        time.sleep(5)

        # 逐条遍历处理评论区
        process_comments_sequentially(driver)

        # 保持脚本运行，直到用户按键
        input("\n按Enter键退出...")

    except Exception as e:
        print(f"连接浏览器或访问链接时出现错误: {e}")


if __name__ == "__main__":
    main()