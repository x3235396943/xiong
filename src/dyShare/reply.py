#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
链接访问脚本
使用比特浏览器打开指定链接，并在指定时间后点击指定元素
"""

import time
import random
import sys
import os
import requests
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# 添加项目根目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


def human_like_delay(min_delay=0.5, max_delay=1.5):
    """
    模拟人类操作的随机延迟

    Args:
        min_delay (float): 最小延迟时间（秒）
        max_delay (float): 最大延迟时间（秒）
    """
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)


def open_bitbrowser(browser_id):
    """
    打开比特浏览器

    Args:
        browser_id (str): 比特浏览器ID

    Returns:
        dict: 浏览器打开结果
    """
    url = "http://127.0.0.1:54345"
    headers = {"Content-Type": "application/json"}

    json_data = {
        "id": str(browser_id),
        "args": ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                 "--remote-debugging-port=0"],
        "windowMode": "normal"
    }

    try:
        print(f"浏览器 #1 正在打开比特浏览器 #{browser_id}...")
        response = requests.post(
            f"{url}/browser/open",
            data=json.dumps(json_data),
            headers=headers
        )
        result = response.json()
        if result.get('success'):
            print("浏览器 #1 比特浏览器启动成功")
            return result
        else:
            print(f"浏览器 #1 比特浏览器启动失败: {result.get('msg')}")
            return None
    except Exception as e:
        print(f"浏览器 #1 打开比特浏览器时出错: {e}")
        return None


def create_driver(browser_result):
    """
    根据比特浏览器结果创建WebDriver实例

    Args:
        browser_result (dict): 比特浏览器打开结果

    Returns:
        webdriver.Chrome: WebDriver实例
    """
    if not browser_result or 'data' not in browser_result:
        print("浏览器 #1 无效的浏览器结果")
        return None

    driver_path = browser_result['data']['driver']
    debugger_address = browser_result['data']['http']

    print(f"浏览器 #1 驱动路径: {driver_path}")
    print(f"浏览器 #1 调试地址: {debugger_address}")

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

    try:
        chrome_service = Service(driver_path)
        driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

        # 等待浏览器完全启动并只保留一个窗口
        time.sleep(3)
        if len(driver.window_handles) > 1:
            # 关闭额外的窗口，只保留第一个窗口
            for handle in driver.window_handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])

        return driver
    except Exception as e:
        print(f"浏览器 #1 创建WebDriver失败: {e}")
        return None


def input_reply_text(driver, reply_text):
    """
    直接输入文本，不尝试定位输入框

    Args:
        driver: WebDriver实例
        reply_text (str): 要输入的文本
    """
    print("浏览器 #1 直接输入文本，不尝试定位输入框")
    try:

        time.sleep(0.5)
        webdriver.ActionChains(driver).send_keys(reply_text).perform()
        print("浏览器 #1 文本输入完成")
        return True
    except Exception as e:
        print(f"浏览器 #1 文本输入失败: {e}")
        return False


def open_url_and_click_element():
    """
    在比特浏览器中打开指定URL，等待10秒后点击指定元素，然后输入文本
    """
    # 固定配置
    browser_id = "933622f2f6394705809a7b7dadaec70d"
    url = "https://v.douyin.com/LtRViqp5V7A/"
    xpath = '//*[@id="douyin-right-container"]/div[2]/div/div/div[1]/div[5]/div/div/div[3]/div[1]/div/div[2]/div/div[4]/div/div[3]/div'
    wait_time = 3
    reply_text = "1内f"

    print("=" * 50)
    print("链接访问和元素点击工具")
    print("=" * 50)
    print(f"浏览器 #1 浏览器ID: {browser_id}")
    print(f"浏览器 #1 自动打开链接: {url}")
    print(f"浏览器 #1 固定等待时间: {wait_time}秒")
    print(f"浏览器 #1 固定点击元素XPath: {xpath}")
    print(f"浏览器 #1 回复文本: {reply_text}")
    print("浏览器 #1 无头模式: 关闭")

    # 打开比特浏览器
    browser_result = open_bitbrowser(browser_id)
    if not browser_result:
        return

    # 创建WebDriver实例
    driver = create_driver(browser_result)
    if not driver:
        return

    try:
        print(f"浏览器 #1 正在访问: {url}")
        driver.get(url)

        # 等待页面加载
        human_like_delay(3, 5)

        # 等待body元素加载完成
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            print("浏览器 #1 页面加载完成")
        except TimeoutException:
            print("浏览器 #1 页面加载超时，但浏览器仍保持打开状态")

        # 等待指定时间
        print(f"浏览器 #1 等待 {wait_time} 秒...")
        time.sleep(wait_time)

        # 尝试点击指定元素
        try:
            print(f"浏览器 #1 正在查找元素: {xpath}")
            element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            print("浏览器 #1 找到元素，正在点击...")
            # 使用JavaScript点击以确保元素可点击
            driver.execute_script("arguments[0].click();", element)
            print("浏览器 #1 元素点击成功")
        except TimeoutException:
            print(f"浏览器 #1 在 {wait_time} 秒后未找到指定元素")
            return
        except Exception as e:
            print(f"浏览器 #1 点击元素时出错: {e}")
            return

        # 等待1秒后直接尝试输入文本
        print("浏览器 #1 等待1秒后直接尝试输入文本...")
        time.sleep(1)

        try:
            # 输入文本并点击发送按钮
            success = input_reply_text(driver, reply_text)
            if success:
                print(f"浏览器 #1 文本 '{reply_text}' 输入完成")
                # 等待并点击发送按钮
                time.sleep(1)
                try:
                    send_button = driver.find_element(By.XPATH,
                                                      '//*[@id="douyin-right-container"]/div[2]/div/div/div[1]/div[5]/div/div/div[3]/div[1]/div/div[2]/div/div[4]/div[2]/div/div/div[2]/div/span[3]')
                    driver.execute_script("arguments[0].click();", send_button)
                    print("浏览器 #1 发送按钮点击成功")
                except Exception as e:
                    print(f"浏览器 #1 点击发送按钮时出错: {e}")
            else:
                print("浏览器 #1 文本输入失败")
        except Exception as e:
            print(f"浏览器 #1 输入文本时出错: {e}")

        print("浏览器 #1 浏览器将保持打开状态，按Ctrl+C关闭")

        # 保持浏览器打开
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n浏览器 #1 正在关闭浏览器...")

    except Exception as e:
        print(f"浏览器 #1 执行过程中出错: {e}")
    finally:
        # 注意：根据项目规范，我们不主动关闭浏览器
        pass


def main():
    """主函数"""
    open_url_and_click_element()


if __name__ == "__main__":
    main()