#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
打开指定ID的比特浏览器并访问小红书分享链接，然后对视频进行操作处理
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
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from ..tools.config import XhsConfig, get_config
from .base import visit_video_and_operate, process_comments_sequentially

# 初始化小红书配置
xhs_config = XhsConfig()

# 小红书链接列表
URLS = [
    "黑暗时代来和我https://www.xiaohongshu.com/discovery/item/6718b2c8000000001b0105fa?source=webshare&xhsshare=pc_web&xsec_token=ABfPA5AZwCLuncyIMZ1MYbPNlLuh-ysjQ-KUI1oRKFe3U=&xsec_source=pc_share",
    "40 【这个时节不穿衬衫简直可惜 - 僵僵鱼 | 小红书 - 你的生活兴趣社区】 😆 k5gxtaE4RYMtliE 😆 https://www.xiaohongshu.com/discovery/item/6720cff0000000001a037707?source=webshare&xhsshare=pc_web&xsec_token=ABQVwG6gSi2q-LHdyeaiMv27pO9bMu6RrwSWNEQ-5sNUU=&xsec_source=pc_share",
    "95 【姐姐是种感觉 - 四点七七 | 小红书 - 你的生活兴趣社区】 😆 l5O54XSgt1yqrXr 😆 https://www.xiaohongshu.com/discovery/item/6943fb17000000001e0331e5?source=webshare&xhsshare=pc_web&xsec_token=ABZ3QQAPbVPfU1jwjeVFVhU5L1w8c3gku9eQkcYh5eh-k=&xsec_source=pc_share",
    "29 【 宗蕊zr | 小红书 - 你的生活兴趣社区】 😆vj4YSdBXUdnyVu2 😆https://www.xiaohongshu.com/discovery/item/68a854f1000000001d0212f0?source=webshare&xhsshare=pc_web&xsec_token=ABvFJ2hHO8TxFUsGcBattDn7t9azj0dDIQpo2fC-9FJls=&xsec_source=pc_share"

    ]

def extract_urls_from_text(text):
    """
    从文本中提取小红书URL
    """
    import re
    # 匹配小红书URL的正则表达式
    url_pattern = r'https://www\.xiaohongshu\.com/(?:explore|discovery/item)/[a-zA-Z0-9\-_&=%?.]+'
    urls = re.findall(url_pattern, text)
    return urls


def clean_urls(urls):
    """
    清洗URL列表，提取出有效的URL
    """
    cleaned_urls = []
    for item in urls:
        if item.startswith('http'):  # 如果已经是完整URL
            cleaned_urls.append(item)
        else:
            # 如果是包含URL的文本，尝试从中提取URL
            extracted = extract_urls_from_text(item)
            cleaned_urls.extend(extracted)
    return cleaned_urls


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


def parse_keywords(raw):
    s = raw
    if not s:
        return URLS[:]
    try:
        if isinstance(s, str):
            t = s.strip()
            if not t:
                return URLS[:]
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
        return URLS[:]
    return URLS[:]


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


def process_share_urls(driver, urls, log_prefix=""):
    """
    处理小红书分享链接列表
    """
    # 清洗URL列表
    cleaned_urls = clean_urls(urls)
    
    wait_seconds = 10
    WebDriverWait(driver, max(10, wait_seconds)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    
    for url in cleaned_urls:
        print(f"{log_prefix} 访问链接: {url}")
        try:
            driver.get(url)
            WebDriverWait(driver, max(10, wait_seconds)).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)
            
            # 使用base模块中的方法对视频进行操作处理
            visit_video_and_operate(driver)
            
            print(f"{log_prefix} 链接 {url} 处理完成")
        except Exception as e:
            print(f"{log_prefix} 处理链接 {url} 时出现错误: {e}")
        
        # 在处理不同链接之间添加间隔
        time.sleep(2)


def run_worker(browser_id, browser_number, url_queue, url_lock, log_prefix=""):
    """
    工作线程函数，为每个浏览器ID执行分享链接任务
    """
    log_prefix = get_browser_log_prefix(browser_id)
    print(f"{log_prefix} 开始执行小红书分享链接自动化任务")
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

        # 获取链接列表
        with url_lock:
            urls = list(url_queue)  # 从队列获取链接列表

        # 执行分享链接任务
        process_share_urls(driver, urls, log_prefix)

        print(f"{log_prefix} 所有链接处理完成，浏览器任务完成...")

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
    主函数 - 使用多个比特浏览器ID并发执行分享链接任务
    """
    # 获取配置
    cfg = get_config()
    
    # 解析环境变量或使用配置中心的值
    raw_env = os.getenv("BIT_BROWSER_IDS")
    if raw_env:
        browser_ids = parse_keywords(raw_env)  # 使用现有的关键词解析函数来解析浏览器ID
    else:
        browser_ids = xhs_config.BIT_BROWSER_IDS

    raw_env = os.getenv("URLS")
    urls = parse_keywords(raw_env)
    
    # 如果配置中心有URLS值，优先使用配置中心的值
    if hasattr(cfg, 'URLS') and cfg.URLS:
        urls = cfg.URLS

    print(f"使用浏览器ID列表: {browser_ids}")
    print(f"使用链接列表: {urls}")

    if not browser_ids:
        print("没有配置浏览器ID，程序退出")
        return

    if not urls:
        print("没有配置链接，程序退出")
        return

    # 创建链接队列和锁
    url_queue = deque(urls)
    url_lock = threading.Lock()

    if len(browser_ids) <= 1:
        # 如果只有一个浏览器ID，直接运行
        run_worker(browser_ids[0], 1, url_queue, url_lock)
        return

    # 多线程执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(browser_ids)) as executor:
        futures = []
        for i, bid in enumerate(browser_ids):
            # 提交任务到线程池
            future = executor.submit(run_worker, bid, i + 1, url_queue, url_lock, "")
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