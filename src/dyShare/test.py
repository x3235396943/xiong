#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试脚本 - 打开指定链接
使用Chrome浏览器访问指定的URL
"""

import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def human_like_delay(min_delay=0.5, max_delay=1.5):
    """
    模拟人类操作的随机延迟

    Args:
        min_delay (float): 最小延迟时间（秒）
        max_delay (float): 最大延迟时间（秒）
    """
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)

def open_url_in_chrome(url, headless=False):
    """
    在Chrome浏览器中打开指定URL
    
    Args:
        url (str): 要访问的网址
        headless (bool): 是否以无头模式运行浏览器
    """
    # 配置Chrome选项
    chrome_options = webdriver.ChromeOptions()
    if headless:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--lang=zh-CN')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36')
    
    print("正在启动Chrome浏览器...")
    try:
        # 启动Chrome浏览器
        driver = webdriver.Chrome(options=chrome_options)
        
        print(f"正在访问: {url}")
        driver.get(url)
        
        # 等待页面加载
        human_like_delay(3, 5)
        
        # 等待body元素加载完成
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            print("页面加载完成")
        except TimeoutException:
            print("页面加载超时，但浏览器仍保持打开状态")
        
        print("浏览器将保持打开状态，按Ctrl+C关闭")
        
        # 保持浏览器打开
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n正在关闭浏览器...")
            driver.quit()
            
    except Exception as e:
        print(f"执行过程中出错: {e}")
        if 'driver' in locals():
            driver.quit()

def main():
    """主函数"""
    print("=" * 50)
    print("链接访问测试工具")
    print("=" * 50)
    
    # 默认链接
    default_url = "https://www.douyin.com"
    
    # 获取用户输入
    url = input(f"请输入要访问的链接 (默认: {default_url}): ").strip()
    if not url:
        url = default_url
    
    # 检查链接是否包含协议
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    headless = input("是否以无头模式运行? (y/N): ").strip().lower() == 'y'
    
    print(f"访问链接: {url}")
    print(f"无头模式: {'是' if headless else '否'}")
    
    open_url_in_chrome(url, headless)

if __name__ == "__main__":
    main()