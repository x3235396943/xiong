#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音评论抓取工具
用于抓取指定抖音视频的评论内容

使用方法:
    python keyw.py
"""

import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
import random
import re
import os
from dotenv import load_dotenv
from tools import log

# 加载环境变量
load_dotenv()

# 从环境变量获取搜索关键字，如果没有设置则使用默认值"兔"
def get_search_keywords():
    # 从环境变量获取 COMMENT_FILTER_KEYWORDS
    keywords_str = os.getenv("COMMENT_FILTER_KEYWORDS", '["关键字1,关键字2,关键字3,关键字4,关键字5"]')
    try:
        # 解析 JSON 格式的字符串
        keywords_list = json.loads(keywords_str)
        if keywords_list and isinstance(keywords_list, list):
            # 获取第一个元素并按逗号分割
            keywords = keywords_list[0].split(',') if isinstance(keywords_list[0], str) else ["兔"]
            # 清理空格
            return [kw.strip() for kw in keywords]
    except:
        pass
    return ["免"]

SEARCH_KEYWORDS = get_search_keywords()

def human_like_delay(min_delay=0.5, max_delay=2.0):
    """
    模拟人类操作的随机延迟

    Args:
        min_delay (float): 最小延迟时间（秒）
        max_delay (float): 最大延迟时间（秒）
    """
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)


class BitBrowserManager:
    """
    比特浏览器管理器类
    用于创建和管理比特浏览器实例
    """

    def __init__(self, base_url="http://127.0.0.1:54345", headless=False):
        """
        初始化比特浏览器管理器

        Args:
            base_url (str): 比特浏览器API的基础URL
            headless (bool): 是否以无头模式运行浏览器
        """
        self.url = base_url
        self.headers = {'Content-Type': 'application/json'}
        self.headless = headless

    def open_browser(self, browser_id_param, browser_number=None):
        """
        打开指定ID的浏览器窗口

        Args:
            browser_id_param (str): 浏览器ID
            browser_number (int): 浏览器编号，用于输出标识

        Returns:
            dict: 浏览器打开结果
        """
        # 添加启动参数以确保浏览器在后台运行
        browser_info = f"浏览器 #{browser_number}" if browser_number is not None else f"浏览器 {browser_id_param}"
        log.info(f"正在打开{browser_info}...")
        json_data = {
            "id": str(browser_id_param),
            "args": ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                     "--remote-debugging-port=0"]
        }

        log.info(f"{browser_info} 请求参数: {json_data}")

        # 设置无头模式
        if self.headless:
            json_data["args"].append("--headless")
            json_data["ignoreDefaultUrls"] = True  # 防止出错的重要参数
            json_data["windowMode"] = "hidden"
            log.debug(f"{browser_info} 使用无头模式")
        else:
            json_data["windowMode"] = "normal"

        try:
            log.info(f"{browser_info} 发送请求到: {self.url}/browser/open")
            response = requests.post(
                f"{self.url}/browser/open",
                data=json.dumps(json_data),
                headers=self.headers
            )
            result = response.json()
            log.info(f"{browser_info} 响应: {result}")
            return result
        except Exception as e:
            log.error(f"打开{browser_info}时出错: {e}")
            return None

    def create_driver(self, browser_id_param, browser_number=None):
        """
        创建并返回一个WebDriver实例

        Args:
            browser_id_param (str): 浏览器ID
            browser_number (int): 浏览器编号，用于输出标识

        Returns:
            webdriver.Chrome: Chrome WebDriver实例
        """
        browser_info = f"浏览器 #{browser_number}" if browser_number is not None else f"浏览器 {browser_id_param}"
        log.info(f"{browser_info} 开始创建WebDriver实例")
        res = self.open_browser(browser_id_param, browser_number)
        if not res or 'data' not in res:
            log.error(f"{browser_info} 无法打开浏览器")
            if res:
                log.error(f"{browser_info} 错误响应: {res}")
            return None

        driver_path = res['data']['driver']
        debugger_address = res['data']['http']
        log.info(f"{browser_info} 驱动路径: {driver_path}, 调试地址: {debugger_address}")

        # 验证必要参数
        if not driver_path:
            log.error(f"{browser_info} 驱动路径为空")
            return None
        if not debugger_address:
            log.error(f"{browser_info} 调试地址为空")
            return None

        # selenium 连接代码
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", debugger_address)

        # 添加一些稳定性的选项
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-ipc-flooding-protection')

        log.info(f"{browser_info} Chrome选项已配置")
        log.info(f"{browser_info} 调试地址: {debugger_address}")
        log.info(f"{browser_info} 驱动路径: {driver_path}")

        # 检查driver_path是否存在
        try:
            chrome_service = Service(driver_path)
            log.info(f"{browser_info} Service创建成功")
        except Exception as e:
            log.error(f"{browser_info} 创建Service失败: {e}")
            return None

        # 检查debugger_address格式
        if not debugger_address or not isinstance(debugger_address, str):
            log.error(f"{browser_info} 无效的调试地址: {debugger_address}")
            return None

        log.info(f"{browser_info} 准备创建WebDriver实例")
        try:
            driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
            log.info(f"{browser_info} WebDriver创建成功")
        except Exception as e:
            log.error(f"{browser_info} 创建WebDriver失败: {e}")
            import traceback
            log.error(f"{browser_info} 详细错误信息: {traceback.format_exc()}")
            return None

        # 等待浏览器完全启动并只保留一个窗口
        log.debug(f"{browser_info} 等待浏览器完全启动...")
        time.sleep(3)
        if len(driver.window_handles) > 1:
            # 关闭额外的窗口，只保留第一个窗口
            log.debug(f"{browser_info} 检测到多个窗口，关闭额外窗口...")
            for handle in driver.window_handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
            log.debug(f"{browser_info} 已关闭额外窗口，保留主窗口")

        log.info(f"{browser_info} WebDriver创建成功")
        return driver


def scroll_comments(driver, scroll_number=None):
    """在打开评论区后执行滚动操作，参考 DY_ku.py 的实现"""
    # 方法1: 使用ActionChains的scroll_from_origin进行滚动
    # 定位到页面主体元素
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        
        # 执行单次滚动
        # 使用ActionChains滚动，增加滚动幅度到600像素
        scroll_origin = ScrollOrigin.from_element(body)
        ActionChains(driver).scroll_from_origin(scroll_origin, 0, 600).perform()
        time.sleep(2)
    except Exception as e:
        # 如果定位body元素失败，使用整个页面滚动
        driver.execute_script("window.scrollBy(0, 600);")
        time.sleep(2)
    return False  # 默认继续处理


def scrape_comments(max_comments=100, wait_time=10):
    """
    抓取抖音视频评论，使用比特浏览器替代普通Chrome浏览器
    
    Args:
        max_comments (int): 最大抓取评论数
        wait_time (int): 等待元素出现的时间（秒）
    
    Returns:
        list: 评论列表
    """
    # 创建比特浏览器管理器实例
    browser_manager = BitBrowserManager()
    
    # 固定使用指定的比特浏览器ID
    browser_id = "933622f2f6394705809a7b7dadaec70d"
    
    # 创建WebDriver实例
    driver = browser_manager.create_driver(browser_id, browser_number=1)
    
    if driver is None:
        print("无法创建比特浏览器驱动")
        return []
    
    comments = []
    # 固定的视频链接
    video_url = "https://v.douyin.com/LtRViqp5V7A/"
    
    try:
        driver.get(video_url)
        
        # 等待页面加载
        wait = WebDriverWait(driver, wait_time)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        
        # 模拟人类操作延迟
        human_like_delay(3, 6)
        human_like_delay(1, 2)
        
        # 尝试点击评论按钮打开评论区
        try:
            comment_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, '//*[contains(@class, "fN2jqmuV")]/div[2]'))
            )
            # 模拟人类操作
            human_like_delay(0.5, 1.0)
            comment_button.click()
        except Exception as e:
            pass# 如果找不到评论按钮，尝试直接查找评论元素
        
        # 等待评论区加载
        human_like_delay(1, 3)
        
        # 初始化评论容器
        comments_container = None
        try:
            comments_container = WebDriverWait(driver, wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
            )
        except Exception as e:
            return comments
        
        # 抓取评论
        processed_comment_count = 0
        scroll_number = 0
        comment_index = 0
        
        while len(comments) < max_comments:
            try:
                # 使用容器定位方法查找评论
                comment_items = comments_container.find_elements(By.XPATH, "./div")
                
                if comment_index >= len(comment_items):
                    # 如果索引超出范围，尝试滚动加载更多评论
                    scroll_number += 1
                    scroll_comments(driver, scroll_number)
                    
                    # 滚动后重新定位评论容器
                    try:
                        comments_container = WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
                        )
                        # 等待新评论加载
                        human_like_delay(2, 3)
                        continue  # 继续循环处理新加载的评论
                    except Exception as e:
                        break
                
                # 获取指定索引的评论项
                target_comment = comment_items[comment_index]

                # 提取评论文本 - 使用更灵活的选择器和异常处理
                comment_text = ""
                try:
                    # 尝试多种可能的选择器
                    selectors = [
                        '.C7LroK_h span span span',
                        '[data-e2e="comment-text"]',
                        '.comment-text',
                        'span'
                    ]
                    
                    for selector in selectors:
                        try:
                            comment_text_element = target_comment.find_element(
                                By.CSS_SELECTOR, selector
                            )
                            comment_text = comment_text_element.text
                            if comment_text:  # 如果找到了文本内容
                                break
                        except:
                            continue
                            
                    # 如果所有选择器都失败了，尝试获取评论项内的所有文本
                    if not comment_text:
                        comment_text = target_comment.text
                except Exception as e:
                    comment_text = ""

                # 提取用户名
                username = ""
                try:
                    # 尝试多种可能的选择器
                    username_selectors = [
                        '.EpsntdUI div div a',
                        '[data-e2e="comment-user-nickname"]',
                        '.user-nickname',
                        'a'
                    ]
                    
                    for selector in username_selectors:
                        try:
                            username_element = target_comment.find_element(
                                By.CSS_SELECTOR, selector
                            )
                            username = username_element.text
                            if username:  # 如果找到了用户名
                                break
                        except:
                            continue
                            
                    # 如果所有选择器都失败了，设置默认值
                    if not username:
                        username = "未知用户"
                except Exception as e:
                    username = "未知用户"

                # 提取点赞数
                try:
                    like_count_element = target_comment.find_element(
                        By.CSS_SELECTOR,
                        '.comment-item-stats-container div:first-child p:first-child'
                    )
                    like_count = like_count_element.text
                except:
                    like_count = "0"

                comment_data = {
                    "username": username,
                    "comment": comment_text,
                    "likes": like_count
                }

                # 避免重复添加
                if comment_data not in comments:
                    comments.append(comment_data)

                    # 检查是否包含任何关键字
                    matched_keyword = None
                    for keyword in SEARCH_KEYWORDS:
                        if keyword in comment_text:
                            matched_keyword = keyword
                            break
                    
                    if matched_keyword:
                        print(f"[{len(comments)}] {username}: {comment_text} (点赞: {like_count}) <<<--- 包含关键字'{matched_keyword}'")
                    else:
                        print(f"[{len(comments)}] {username}: {comment_text} (点赞: {like_count})")

                    # 增加处理过的评论计数
                    processed_comment_count += 1

                    # 每处理5条评论就滚动一次，增加滚动频率
                    if processed_comment_count % 5 == 0:
                        scroll_number += 1
                        scroll_comments(driver, scroll_number)

                        # 滚动后重新定位评论容器
                        try:
                            comments_container = WebDriverWait(driver, wait_time).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
                            )
                            # 等待新评论加载
                            human_like_delay(2, 3)
                        except Exception as e:
                             continue
                            # 继续处理已加载的评论


                # 增加评论索引
                comment_index += 1
                
                # 模拟人类思考时间
                human_like_delay(1, 2)
                
            except Exception as e:
                comment_index += 1  # 继续处理下一条评论
                continue
        
    except Exception as e:
        pass
    
    finally:
        # 关闭浏览器
        if driver:
            driver.quit()
    
    return comments


def main():
    """主函数"""
    print("抖音评论抓取工具")
    print("=" * 30)
    print(f"正在抓取固定链接的评论: https://v.douyin.com/LtRViqp5V7A/")
    print(f"搜索关键字: {', '.join(SEARCH_KEYWORDS)}")
    
    # 抓取评论
    comments = scrape_comments(max_comments=100)
    
    # 筛选包含关键字的评论
    keyword_comments = []
    for comment in comments:
        for keyword in SEARCH_KEYWORDS:
            if keyword in comment["comment"]:
                keyword_comments.append(comment)
                break
    
    # 只在控制台输出结果，不保存到文件
    if comments:
        print("\n抓取完成，共获得以下评论:")
        print("-" * 50)
        for i, comment in enumerate(comments, 1):
            # 检查是否包含关键字
            matched_keyword = None
            for keyword in SEARCH_KEYWORDS:
                if keyword in comment["comment"]:
                    matched_keyword = keyword
                    break
            
            if matched_keyword:
                print(f"{i}. {comment['username']}: {comment['comment']} (点赞: {comment['likes']}) <<<--- 包含关键字'{matched_keyword}'")
            else:
                print(f"{i}. {comment['username']}: {comment['comment']} (点赞: {comment['likes']})")
        
        # 显示包含关键字的评论统计
        if keyword_comments:
            print(f"\n包含关键字的评论共 {len(keyword_comments)} 条:")
            print("-" * 30)
            for i, comment in enumerate(keyword_comments, 1):
                matched_keyword = None
                for keyword in SEARCH_KEYWORDS:
                    if keyword in comment["comment"]:
                        matched_keyword = keyword
                        break
                print(f"{i}. {comment['username']}: {comment['comment']} (点赞: {comment['likes']})")
        else:
            print(f"\n未找到包含关键字的评论")
    else:
        print("未抓取到任何评论")


if __name__ == "__main__":
    main()