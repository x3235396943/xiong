#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音自动化脚本

环境变量配置说明:
    SIBERIAN_KEY: 卡密密钥，用于验证脚本使用权限
    DEVICE_CODE: 设备码，标识当前设备

使用方法:
    1. 在Windows命令行中设置环境变量:
       set SIBERIAN_KEY=你的卡密
       set DEVICE_CODE=设备标识

    2. 在Linux/Mac终端中设置环境变量:
       export SIBERIAN_KEY=你的卡密
       export DEVICE_CODE=设备标识

    3. 或者在运行脚本前直接指定环境变量:
       SIBERIAN_KEY=你的卡密 DEVICE_CODE=设备标识

注意事项:
    - 服务器端可以随时使卡密失效，失效后脚本将停止运行
    - 脚本每3分钟验证一次卡密有效性
"""
from tools import config
import json
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import re
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from datetime import datetime
import threading
# 从 tools 导入 LicenseManager, LicenseException 和 log
from tools import LicenseManager, LicenseException, log
import concurrent.futures

LINKS_DB_PATH = config.LINKS_DB_PATH

# 并行设置
MAX_WORKERS = None  # 自动根据浏览器ID数量调整并行数


class BitBrowserIDManager:
    """比特浏览器ID管理器"""

    def __init__(self, base_url="http://127.0.0.1:54345"):
        """
        初始化比特浏览器ID管理器

        Args:
            base_url: 比特浏览器API基础URL
        """
        self.base_url = base_url
        self.headers = {"Content-Type": "application/json"}


# 全局变量定义
# 连续没有新评论的滚动次数计数器
scroll_count_total = 0
previous_comment_count = 0
no_new_comments_count = 0
# 全局关注计数器
global_followed_count = 0

# 卡密验证管理器实例
li = LicenseManager()


def parse_search_keywords():
    raw = config.COMMENT_FILTER_KEYWORDS or []
    seps = [',', '，', ' ', '\t', ';', '；']
    kws = []
    if isinstance(raw, str):
        s = raw.strip()
        try:
            data = json.loads(s)
            if isinstance(data, list):
                raw = data
            else:
                raw = [s]
        except Exception:
            raw = [s]
    if isinstance(raw, list):
        if len(raw) == 1 and isinstance(raw[0], str):
            base = raw[0]
            for sep in seps:
                base = base.replace(sep, ',')
            kws = [x.strip() for x in base.split(',') if x.strip()]
        else:
            kws = [str(x).strip() for x in raw if str(x).strip()]
    return kws


SEARCH_KEYWORDS = parse_search_keywords()


def normalize_text(t):
    try:
        s = str(t).lower()
        s = re.sub(r"\s+", " ", s).strip()
        return s
    except Exception:
        return str(t)


def _extract_comment_text(element):
    selectors = [
        '.C7LroK_h span span span',
        '[data-e2e="comment-text"]',
        '.comment-text',
        'span'
    ]
    for css in selectors:
        try:
            t = element.find_element(By.CSS_SELECTOR, css).text
            if t:
                return t
        except Exception:
            pass
    try:
        return element.text
    except Exception:
        return ""


def output_json(code, msg="", data_type="", browser_id="", url_index=None):
    """
    输出JSON格式的操作结果

    Args:
        code: 0表示成功，-1表示找不到按钮等异常，1表示链接失效
        msg: 错误信息，只在错误时输出
        data_type: 操作类型 start|exit|like|follow|video|url_ok|url_fail
        browser_id: 浏览器ID
        url_index: URL在数据库中的索引（从0开始）
    """
    result = {
        "code": code,
        "data": {
            "type": data_type,
            "id": browser_id
        }
    }
    # 只在有错误信息时添加msg字段
    if msg:
        result["msg"] = msg

    # 如果提供了url_index，添加到结果中
    if url_index is not None:
        result["urlIndex"] = url_index

    # 输出JSON（使用print，因为用户要求只输出这个）
    print(json.dumps(result, ensure_ascii=False))


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
        browser_info = get_browser_info(browser_number, browser_id_param)
        debug_log("info", "正在打开...", browser_number, browser_id_param)
        json_data: dict[str, str | list[str] | bool | None] = {
            "id": str(browser_id_param),
            "args": ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
                     "--remote-debugging-port=0"]
        }

        debug_log("info", f"请求参数: {json_data}", browser_number, browser_id_param)

        # 设置无头模式
        if self.headless:
            # type: ignore
            args = json_data.get("args")
            if isinstance(args, list):
                args.append("--headless")
            json_data["ignoreDefaultUrls"] = True
            json_data["windowMode"] = "hidden"
            debug_log("debug", "使用无头模式", browser_number, browser_id_param)
        else:
            json_data["windowMode"] = "normal"

        try:
            debug_log("info", f"发送请求到: {self.url}/browser/open", browser_number, browser_id_param)
            response = requests.post(
                f"{self.url}/browser/open",
                data=json.dumps(json_data),
                headers=self.headers
            )
            result = response.json()
            debug_log("info", f"响应: {result}", browser_number, browser_id_param)
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
        browser_info = get_browser_info(browser_number, browser_id_param)
        debug_log("info", "开始创建WebDriver实例", browser_number, browser_id_param)
        res = self.open_browser(browser_id_param, browser_number)
        if not res or 'data' not in res:
            log.error(f"{browser_info} 无法打开浏览器")
            if res:
                log.error(f"{browser_info} 错误响应: {res}")
            return None

        driver_path = res['data']['driver']
        debugger_address = res['data']['http']
        debug_log("info", f"驱动路径: {driver_path}, 调试地址: {debugger_address}", browser_number, browser_id_param)

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

        debug_log("info", "Chrome选项已配置", browser_number, browser_id_param)
        debug_log("info", f"调试地址: {debugger_address}", browser_number, browser_id_param)
        debug_log("info", f"驱动路径: {driver_path}", browser_number, browser_id_param)

        # 检查driver_path是否存在
        try:
            chrome_service = Service(driver_path)
            debug_log("info", "Service创建成功", browser_number, browser_id_param)
        except Exception as e:
            log.error(f"{browser_info} 创建Service失败: {e}")
            return None

        # 检查debugger_address格式
        if not debugger_address or not isinstance(debugger_address, str):
            log.error(f"{browser_info} 无效的调试地址: {debugger_address}")
            return None

        debug_log("info", "准备创建WebDriver实例", browser_number, browser_id_param)
        try:
            driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
            debug_log("info", "WebDriver创建成功", browser_number, browser_id_param)
        except Exception as e:
            log.error(f"{browser_info} 创建WebDriver失败: {e}")
            import traceback
            log.error(f"{browser_info} 详细错误信息: {traceback.format_exc()}")
            return None

        # 等待浏览器完全启动并只保留一个窗口
        debug_log("debug", "等待浏览器完全启动...", browser_number, browser_id_param)
        safe_sleep(3)
        if len(driver.window_handles) > 1:
            # 关闭额外的窗口，只保留第一个窗口
            debug_log("debug", "检测到多个窗口，关闭额外窗口...", browser_number, browser_id_param)
            for handle in driver.window_handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
            debug_log("debug", "已关闭额外窗口，保留主窗口", browser_number, browser_id_param)

        debug_log("info", "WebDriver创建成功", browser_number, browser_id_param)
        return driver


def human_like_delay(min_delay=0.5, max_delay=2.0, browser_number=None):
    """
    模拟人类操作的随机延迟

    Args:
        min_delay (float): 最小延迟时间（秒）
        max_delay (float): 最大延迟时间（秒）
        browser_number (int): 浏览器编号，用于日志
    """
    delay = random.uniform(min_delay, max_delay)
    debug_log("debug", f"等待 {delay:.2f} 秒模拟人类操作", browser_number)
    safe_sleep(delay)


def open_comment_section(driver, wait_time=10, browser_number=None):
    """打开评论区"""
    browser_info = get_browser_info(browser_number)
    debug_log("info", "尝试打开评论区", browser_number)
    check_stop_signal()

    # 使用智能等待查找评论按钮
    wait = WebDriverWait(driver, wait_time)
    try:
        comment_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, '//*[contains(@class, "fN2jqmuV")]/div[2]'))
        )
    except:
        debug_log("warning", "评论区按钮未找到，尝试刷新页面...", browser_number)
        driver.refresh()
        # 等待页面刷新完成
        human_like_delay(5, 7, browser_number)
        # 再次尝试查找元素
        try:
            comment_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, '//*[contains(@class, "fN2jqmuV")]/div[2]'))
            )
        except:
            debug_log("warning", "刷新后仍未找到评论按钮，跳过打开评论区操作", browser_number)
            return False

    # 模拟人类操作
    human_like_delay(0.5, 1.0, browser_number)

    comment_button.click()
    debug_log("info", "打开评论区成功", browser_number)
    return True


def open_new_tab_and_close_others(driver, url, browser_number=None):
    """
    在新标签页中打开链接并关闭所有旧标签页

    Args:
        driver: WebDriver实例
        url: 要打开的URL
        browser_number: 浏览器编号，用于日志输出
    """
    browser_info = get_browser_info(browser_number)
    try:
        # 获取当前所有窗口句柄
        original_windows = driver.window_handles.copy()

        # 在新标签页中打开链接
        debug_log("info", f"在新标签页中打开链接: {url}", browser_number)
        driver.execute_script(f"window.open('{url}', '_blank');")

        # 等待新标签页打开
        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > len(original_windows))

        # 获取所有窗口句柄（包括新打开的）
        all_windows = driver.window_handles

        # 切换到新打开的标签页（最后一个）
        new_window = all_windows[-1]
        driver.switch_to.window(new_window)

        # 关闭所有旧的标签页
        for window in original_windows:
            try:
                driver.switch_to.window(window)
                driver.close()
                debug_log("info", "已关闭旧标签页", browser_number)
            except Exception as e:
                log.error(f"{browser_info} 关闭旧标签页时出错: {e}")

        # 切换回新标签页
        driver.switch_to.window(new_window)
        debug_log("info", "已切换到新标签页并关闭所有旧标签页", browser_number)

        # 等待页面加载
        human_like_delay(2, 4, browser_number)

        return True
    except Exception as e:
        log.error(f"{browser_info} 在新标签页中打开链接并关闭旧标签页时出错: {e}")
        return False


def switch_to_new_tab(driver, url, wait_time=10, browser_number=None):
    """在新标签页中打开链接并切换到新标签页"""
    browser_info = get_browser_info(browser_number)
    debug_log("info", f"尝试在新标签页中打开链接: {url}", browser_number)
    check_stop_signal()

    # 保存当前窗口句柄
    current_window = driver.current_window_handle

    # 模拟人类在新标签页中打开链接
    human_like_delay(0.5, 1.5, browser_number)
    driver.execute_script(f"window.open('{url}','_blank');")

    # 等待新标签页打开
    wait = WebDriverWait(driver, wait_time)
    wait.until(lambda d: len(d.window_handles) > 1)

    # 获取所有窗口句柄
    all_windows = driver.window_handles

    # 切换到新打开的标签页（最后一个）
    driver.switch_to.window(all_windows[-1])

    # 模拟页面加载等待
    human_like_delay(2, 4, browser_number)

    # 关闭之前的标签页
    driver.switch_to.window(current_window)
    driver.close()

    # 切换回新标签页
    driver.switch_to.window(all_windows[-1])
    debug_log("info", f"成功切换到新标签页: {url}", browser_number)


# 使用数据库作为数据源
def extract_douyin_link(text):
    """从文本中提取抖音链接"""
    if isinstance(text, str):
        # 匹配抖音链接的正则表达式
        pattern = r'https?://v\.douyin\.com/[^\s]+'
        match = re.search(pattern, text)
        return match.group(0) if match else None
    return None


def process_comment(web_driver, main_window, comment_index, like_count, target_like_count,
                    wait_time=10, like_probability=0.5, visit_profile_probability=0.3, profile_follow_probability=0.5,
                    browser_number=None,
                    browser_id="", enable_follow=True):
    """处理单条评论：根据概率和次数决定是否点赞，关注用户"""
    browser_info = get_browser_info(browser_number)
    debug_log("info", f"开始处理第{comment_index + 1}条评论", browser_number)
    check_stop_signal()

    try:
        comments_container = WebDriverWait(web_driver, wait_time).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
        )
        comment_items = comments_container.find_elements(By.XPATH, "./div")
        if comment_index >= len(comment_items):
            log.warning(f"{browser_info} 评论索引 {comment_index} 超出范围，共有 {len(comment_items)} 条评论")
            return False, like_count
        target_comment = comment_items[comment_index]
    except Exception as e:
        log.error(f"{browser_info} 无法定位评论项: {e}")
        return False, like_count

    comment_text = _extract_comment_text(target_comment)
    norm_comment = normalize_text(comment_text)
    keyword_matched = False
    matched_keyword = None
    if SEARCH_KEYWORDS:
        for kw in SEARCH_KEYWORDS:
            nk = normalize_text(kw)
            if nk and nk in norm_comment:
                keyword_matched = True
                matched_keyword = kw
                break

    if keyword_matched:
        try:
            snippet = comment_text[:100]
            output_json(0, f"关键词:{matched_keyword} 内容:{snippet}", "keyword", browser_id)
        except Exception:
            pass

    should_like = (like_count < target_like_count) and (keyword_matched or (random.random() < like_probability))

    # 点赞操作
    if should_like:
        debug_log("debug", f"尝试点赞第{comment_index + 1}条评论", browser_number)
        try:
            # 查找点赞按钮
            like_button = target_comment.find_element(
                By.XPATH,
                ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]",
            )

            # 模拟人类操作
            human_like_delay(0.5, 1.5, browser_number)

            like_button.click()
            # 输出点赞成功
            output_json(0, "", "like", browser_id)
            # 增加点赞计数
            like_count += 1
            debug_log("info", f"点赞第{comment_index + 1}条评论成功", browser_number)
            # 点赞后等待，模拟真实用户行为（使用time.sleep避免频繁检查停止信号）
            like_wait_time = random.uniform(config.LIKE_WAIT_MIN, config.LIKE_WAIT_MAX)
            time.sleep(like_wait_time)
            debug_log("info", f"点赞后等待{like_wait_time:.2f}秒", browser_number)
        except Exception as e:
            # 找不到按钮等异常
            error_msg = repr(e)
            log.error(f"{browser_info} 点赞第{comment_index + 1}条评论失败: {e}")
            output_json(-1, error_msg, "like", browser_id)
    else:
        debug_log("info", f"第{comment_index + 1}条评论未执行点赞操作", browser_number)

    if enable_follow and (keyword_matched or (random.random() < visit_profile_probability)):
        try:
            # 先定位评论容器
            comments_container = WebDriverWait(web_driver, wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
            )

            # 使用容器定位方法查找用户头像
            comment_items = comments_container.find_elements(By.XPATH, "./div")
            if comment_index >= len(comment_items):
                log.warning(f"{browser_info} 评论索引 {comment_index} 超出范围，共有 {len(comment_items)} 条评论")
                return False, like_count

            # 获取指定索引的评论项
            target_comment = comment_items[comment_index]

            # 查找带a链接的头像，如果找不到就点击头像容器
            try:
                avatar = target_comment.find_element(
                    By.CSS_SELECTOR, ".comment-item-avatar a"
                )
            except:
                # 如果没找到带a标签的头像，点击头像容器
                avatar = target_comment.find_element(
                    By.CSS_SELECTOR, ".comment-item-avatar"
                )
                debug_log("info", f"第{comment_index + 1}条评论未找到带链接的头像，点击头像容器", browser_number)

            # 模拟人类操作
            human_like_delay(0.5, 1.5, browser_number)

            # 点击找到的头像元素
            avatar.click()
            debug_log("info", f"点击第{comment_index + 1}个评论的用户头像进入主页", browser_number)

            # 等待新页面加载（使用time.sleep避免频繁检查停止信号）
            time.sleep(random.uniform(3, 5))

            # 获取所有窗口句柄
            all_windows = web_driver.window_handles

            # 切换到新窗口（非主窗口）
            new_window = None
            for window in all_windows:
                if window != main_window:
                    new_window = window
                    web_driver.switch_to.window(window)
                    break

            # 等待页面加载（使用time.sleep避免频繁检查停止信号）
            time.sleep(random.uniform(2, 4))

            # 进入主页后根据概率决定是否关注
            if enable_follow and (keyword_matched or (random.random() < profile_follow_probability)):
                try:
                    # 查找并点击关注按钮
                    follow_button_wait = WebDriverWait(web_driver, wait_time)
                    follow_button = follow_button_wait.until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, '#user_detail_element [data-e2e="user-info-follow-btn"]'))
                    )

                    # 模拟人类操作
                    human_like_delay(0.5, 1.5, browser_number)
                    follow_button.click()
                    # 输出关注成功
                    output_json(0, "", "follow", browser_id)
                    debug_log("info", "在用户主页关注该用户", browser_number)

                    # 关注后等待，模拟真实用户行为（使用time.sleep避免频繁检查停止信号）
                    follow_wait_time = random.uniform(config.VISIT_MIN, config.VISIT_MAX)
                    time.sleep(follow_wait_time)
                    debug_log("info", f"关注后等待{follow_wait_time:.2f}秒", browser_number)

                    # 关注成功后更新全局计数器并返回"followed"标识
                    global global_followed_count
                    global_followed_count += 1
                    debug_log("info", f"全局关注计数器更新: {global_followed_count}", browser_number)

                    # 关闭新窗口并切换回主窗口
                    try:
                        if 'new_window' in locals() and new_window:
                            web_driver.close()  # 关闭新窗口
                            debug_log("info", "用户主页窗口已关闭", browser_number)
                        web_driver.switch_to.window(main_window)  # 切换回主窗口
                        debug_log("info", "已切换回主窗口", browser_number)
                        return "followed", like_count
                    except Exception as switch_error:
                        log.error(f"{browser_info} 窗口切换时出错: {switch_error}")
                        try:
                            web_driver.switch_to.window(main_window)
                        except:
                            pass
                        return "followed", like_count
                except Exception as follow_error:
                    # 找不到按钮等异常
                    error_msg = repr(follow_error)
                    debug_log("error", f"{browser_info} 关注用户失败: {follow_error}", browser_number)
                    output_json(-1, error_msg, "follow", browser_id)

            # 关闭新窗口并切换回主窗口
            try:
                if 'new_window' in locals() and new_window:
                    web_driver.close()  # 关闭新窗口
                    debug_log("info", "用户主页窗口已关闭", browser_number)
                web_driver.switch_to.window(main_window)  # 切换回主窗口
                debug_log("info", "已切换回主窗口", browser_number)
            except Exception as switch_error:
                log.error(f"{browser_info} 窗口切换时出错: {switch_error}")
                try:
                    web_driver.switch_to.window(main_window)
                except:
                    pass

        except Exception as avatar_error:
            log.error(f"{browser_info} 点击用户头像失败: {avatar_error}")
            # 确保回到主窗口
            try:
                web_driver.switch_to.window(main_window)
            except:
                pass

    # 如果没有执行任何操作，也视为成功
    return True, like_count


def run_automation(driver, url, wait_time=10,
                   like_probability=0.5, visit_profile_probability=0.3, profile_follow_probability=0.5,
                   min_follows_per_video=5, max_follows_per_video=15,
                   min_likes_per_video=5, max_likes_per_video=15,
                   browser_number=None, browser_id="", enable_follow=True):
    """
    运行完整的自动化流程

    Args:
        driver: WebDriver实例
        url: 要访问的网页URL
        wait_time: 等待元素出现的时间（秒）
        like_probability: 点赞的概率 (0-1之间的浮点数)
        visit_profile_probability: 进入主页的概率 (0-1之间的浮点数)
        profile_follow_probability: 进入主页后关注的概率 (0-1之间的浮点数)
        min_follows_per_video: 每条视频最少关注数量
        max_follows_per_video: 每条视频最多关注数量
        min_likes_per_video: 每条视频最少点赞数量
        max_likes_per_video: 每条视频最多点赞数量
        browser_number: 浏览器编号，用于输出标识
        browser_id: 浏览器ID
        enable_follow: 是否启用关注功能
    """
    browser_info = get_browser_info(browser_number)
    debug_log("info", f"开始运行自动化流程，访问网页: {url}", browser_number)
    check_stop_signal()

    # 检查浏览器会话是否有效
    try:
        driver.current_url  # 尝试获取当前URL来检查会话
    except Exception as e:
        if "invalid session id" in str(e):
            log.error(f"{browser_info} 浏览器会话已失效: {e}")
            return False
        else:
            raise e

    # 每条视频使用独立的关注和点赞计数器
    video_followed_count = 0
    # 确保最小值不大于最大值
    if min_follows_per_video > max_follows_per_video:
        min_follows_per_video, max_follows_per_video = max_follows_per_video, min_follows_per_video
    target_follow_count = random.randint(min_follows_per_video, max_follows_per_video)

    video_liked_count = 0
    # 确保最小值不大于最大值
    if min_likes_per_video > max_likes_per_video:
        min_likes_per_video, max_likes_per_video = max_likes_per_video, min_likes_per_video
    target_like_count = random.randint(min_likes_per_video, max_likes_per_video)
    debug_log("info", f"本视频计划关注 {target_follow_count} 个用户，点赞 {target_like_count} 条评论", browser_number)
    # 检查卡密是否仍然有效（移到try-except块外面）
    li.check_license_validity()

    try:
        debug_log("info", f"访问网页: {url}", browser_number)
        driver.get(url)

        wait = WebDriverWait(driver, wait_time)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        human_like_delay(3, 6, browser_number)
        human_like_delay(1, 2, browser_number)

        debug_log("info", "处理视频评论", browser_number)
        debug_log("info", "打开评论区", browser_number)

        try:
            if not open_comment_section(driver, wait_time, browser_number):
                # 只有当新打开链接后第一个操作（打开评论区）无法完成时才视为处理失败
                # 链接失效，返回False，由上层函数输出url_fail
                debug_log("error", "无法打开评论区，链接可能失效", browser_number)
                return False
        except Exception as e:
            # 捕获open_comment_section可能抛出的异常，返回False，由上层函数输出url_fail
            log.error(f"{browser_info} 打开评论区时发生异常: {e}")
            return False

        human_like_delay(1, 3, browser_number)

        main_window = driver.current_window_handle

        processed_comment_count = 0
        scroll_number = 0

        comment_index = 0
        debug_log("info", "从第一条开始处理评论", browser_number)

        # 初始化评论容器
        comments_container = None
        try:
            comments_container = WebDriverWait(driver, wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
            )
        except Exception as e:
            # 这种情况也视为处理失败，因为是打开链接后的关键操作
            # 返回False，由上层函数输出url_fail
            log.error(f"{browser_info} 无法定位评论容器: {e}")
            return False

        while True:
            check_stop_signal()

            try:
                li.check_license_validity()

                # 处理单条评论
                result, video_liked_count = process_comment(driver, main_window, comment_index, video_liked_count,
                                                            target_like_count,
                                                            wait_time, like_probability, visit_profile_probability,
                                                            profile_follow_probability, browser_number, browser_id,
                                                            enable_follow)  # 传递enable_follow参数

                # 增加处理过的评论计数
                processed_comment_count += 1

                # 每处理3条评论就滚动一次
                if processed_comment_count % 3 == 0 or processed_comment_count == 1:
                    scroll_number += 1
                    debug_log("info", f"已处理{processed_comment_count}条评论，执行滚动操作", browser_number)
                    scroll_comments(driver, scroll_number, browser_number)

                    # 滚动后重新定位评论容器
                    try:

                        comments_container = WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
                        )
                    except Exception as e:
                        # 滚动后无法重新定位评论容器，但不视为处理失败
                        log.error(f"{browser_info} 滚动后无法重新定位评论容器: {e}")
                        break

                # 如果成功关注了用户，则增加计数器
                if result == "followed":
                    video_followed_count += 1
                    debug_log("info", f"已成功关注用户，当前视频已关注 {video_followed_count} 个用户", browser_number)

                # 检查是否达到目标关注数量或点赞数量
                if video_followed_count >= target_follow_count and video_liked_count >= target_like_count:
                    debug_log("info",
                              f"已达到目标关注数量 {target_follow_count} 和点赞数量 {target_like_count}，切换到下一个链接",
                              browser_number)
                    break

                # 检查是否还能找到下一条评论
                try:
                    if comments_container is not None:
                        comment_items = comments_container.find_elements(By.XPATH, "./div")
                        if comment_index + 2 >= len(comment_items):
                            debug_log("info", "可能已滚动到底部或没有更多评论，结束当前链接操作", browser_number)
                            break
                    else:
                        log.error(f"{browser_info} 评论容器未正确初始化，结束当前链接操作")
                        # 评论容器未正确初始化，但不视为处理失败
                        break
                except Exception as e:
                    log.error(f"{browser_info} 无法获取评论列表: {e}")
                    debug_log("info", "可能已滚动到底部或没有更多评论，结束当前链接操作", browser_number)
                    break

                # 增加评论索引
                comment_index += 1

                # 确保回到主页面
                driver.switch_to.window(main_window)

                # 等待一段时间再处理下一条，模拟人类思考时间
                human_like_delay(2, 5, browser_number)
            except LicenseException:
                raise
            except Exception as e:
                msg = str(e)
                if "invalid session id" in msg or "Failed to establish a new connection" in msg or "ConnectionResetError" in msg:
                    raise
                log.error(f"{browser_info} 处理第{comment_index + 1}条评论时发生异常: {e}")
                comment_index += 1
                continue

        # 确保最终回到主页面
        driver.switch_to.window(main_window)
        debug_log("info", "所有评论处理完成", browser_number)

        # 评论处理完成，标记为成功
        return True

    except LicenseException:
        # 重新抛出LicenseException，不捕获它，让程序终止
        raise
    except Exception as e:
        # 程序执行出错，尝试重新打开浏览器而不是直接标记为失败
        log.error(f"{browser_info} 程序执行出错: {e}")
        log.info(f"{browser_info} 尝试重新打开浏览器以恢复控制...")
        raise  # 重新抛出异常，让上层逻辑处理浏览器重启


def process_urls_thread(browser_manager, browser_id, urls, wait_time,
                        like_probability, visit_profile_probability, profile_follow_probability,
                        min_follows_per_video, max_follows_per_video,
                        min_likes_per_video, max_likes_per_video, browser_number):
    """在线程中处理URL列表"""
    browser_info = get_browser_info(browser_number)
    log.info(f"{browser_info} 开始处理任务")

    driver = browser_manager.create_driver(browser_id, browser_number)

    if driver is None:
        log.error(f"{browser_info} 无法创建浏览器驱动")
        return

    try:
        process_urls(driver, urls,
                     wait_time, like_probability, visit_profile_probability, profile_follow_probability,
                     min_follows_per_video, max_follows_per_video,
                     min_likes_per_video, max_likes_per_video, browser_number)
    except Exception as e:
        log.error(f"{browser_info} 处理URL时发生异常: {e}")
    finally:
        # 等待并关闭浏览器
        human_like_delay(3, 5)
        log.info(f"{browser_info} 浏览器已关闭")


def process_urls(driver, urls, wait_time=10,
                 like_probability=0.5, visit_profile_probability=0.3, profile_follow_probability=0.5,
                 min_follows_per_video=5, max_follows_per_video=15,
                 min_likes_per_video=5, max_likes_per_video=15, browser_number=None):
    """处理URL列表"""
    browser_info = get_browser_info(browser_number)
    log.info(f"{browser_info} 开始处理URL列表，共 {len(urls)} 个链接")
    for i, target_url in enumerate(urls):
        check_stop_signal()
        log.info(f"{browser_info} 处理第{i + 1}个链接: {target_url}")

        try:
            # 如果不是第一个链接，则在新标签页中打开并关闭前一个标签页
            if i > 0:
                switch_to_new_tab(driver, target_url, wait_time, browser_number)
            else:
                # 打开第一个链接
                driver.get(target_url)

            success = run_automation(driver, target_url,
                                     wait_time, like_probability, visit_profile_probability,
                                     profile_follow_probability,
                                     min_follows_per_video, max_follows_per_video,
                                     min_likes_per_video, max_likes_per_video,
                                     browser_number, "")
            if not success:
                log.error(f"{browser_info} 处理链接 {target_url} 失败")
        except Exception as e:
            log.error(f"{browser_info} 处理链接 {target_url} 时发生异常: {e}")

        # 在处理下一个链接前等待一段时间
        human_like_delay(3, 7, browser_number)


def scroll_comments(driver, scroll_number=None, browser_number=None):
    """在打开评论区后执行滚动操作"""
    browser_info = get_browser_info(browser_number)
    debug_log("debug", "执行评论区滚动操作", browser_number)

    # 方法1: 使用ActionChains的scroll_from_origin进行滚动
    # 定位到页面主体元素
    body = driver.find_element(By.TAG_NAME, "body")

    # 执行单次滚动
    # 使用ActionChains滚动
    scroll_origin = ScrollOrigin.from_element(body)
    ActionChains(driver).scroll_from_origin(scroll_origin, 0, 470).perform()
    if scroll_number is not None:
        debug_log("info", f"使用ActionChains完成滑动 (第 {scroll_number} 次)", browser_number)
    else:
        debug_log("info", "使用ActionChains完成滑动", browser_number)
    time.sleep(2)
    return False  # 默认继续处理


def init_database(db_path=LINKS_DB_PATH):
    """初始化数据库"""
    debug_log("info", "初始化数据库")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建链接表，不使用默认的CURRENT_TIMESTAMP，而是在应用层处理时间
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
    ''')

    conn.commit()
    conn.close()
    # log.info("数据库初始化完成")


def add_links_cli(db_path=LINKS_DB_PATH):
    """命令行接口：添加链接到数据库"""
    log.info("启动链接添加工具")
    # 初始化数据库（确保表存在）
    init_database(db_path)

    print("链接添加工具")
    print("输入包含抖音链接的文本（每行一个），输入 'quit' 结束:")
    print("支持直接输入链接或包含链接的文本，程序会自动提取链接")

    while True:
        try:
            text = input().strip()
            if text.lower() == 'quit':
                break
            if text:
                add_link_to_db(text, db_path)
            else:
                log.info("输入不能为空，请重新输入")
        except KeyboardInterrupt:
            log.info("用户中断链接添加工具\n已退出链接添加工具")
            break
        except EOFError:
            log.info("链接添加工具输入结束\n已退出链接添加工具")
            break


def add_link_to_db(url, db_path=LINKS_DB_PATH):
    """向数据库添加链接"""
    log.debug(f"尝试添加链接到数据库: {url}")
    # 清洗链接
    cleaned_url = extract_douyin_link(url)
    if not cleaned_url:
        log.warning(f"无效的抖音链接: {url}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 使用本地时间
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO links (url, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cleaned_url, 'pending', current_time, current_time)
        )
        conn.commit()
        log.info(f"链接已添加到数据库: {cleaned_url}")
    except sqlite3.IntegrityError:
        log.warning(f"链接已存在: {cleaned_url}")
    finally:
        conn.close()


# 全局线程安全的URL列表索引计数器
_url_list_index = 0
_url_list_lock = threading.Lock()

# 全局停止标志，用于通知所有线程立即停止
_stop_flag = threading.Event()


# ==================== 辅助函数：减少重复代码 ====================

def check_stop_signal():
    """检查是否收到停止信号，如果收到则抛出异常"""
    if _stop_flag.is_set():
        raise KeyboardInterrupt("收到全局停止信号")


def get_browser_info(browser_number=None, browser_id_param=None):
    """格式化浏览器信息字符串"""
    if browser_number is not None:
        return f"浏览器 #{browser_number}"
    elif browser_id_param is not None:
        return f"浏览器 {browser_id_param}"
    else:
        return "浏览器"


def debug_log(level, message, browser_number=None, browser_id_param=None):
    """条件DEBUG日志输出"""
    if config.DEBUG:
        browser_info = get_browser_info(browser_number, browser_id_param)
        if level == "info":
            log.info(f"{browser_info} {message}")
        elif level == "debug":
            log.debug(f"{browser_info} {message}")
        elif level == "warning":
            log.warning(f"{browser_info} {message}")
        elif level == "error":
            log.error(f"{browser_info} {message}")


def safe_sleep(seconds, check_interval=1.0):
    """安全的睡眠函数，会检查停止信号"""
    elapsed = 0
    while elapsed < seconds:
        check_stop_signal()
        wait_time = min(check_interval, seconds - elapsed)
        time.sleep(wait_time)
        elapsed += wait_time


def safe_driver_quit(driver, browser_info=""):
    """安全关闭浏览器驱动"""
    if driver:
        try:
            driver.quit()
        except Exception:
            pass


def reset_url_list_index():
    """重置URL列表索引（用于程序重新启动时）"""
    global _url_list_index
    with _url_list_lock:
        _url_list_index = 0


def get_next_link_from_list(urls_list):
    """从URL列表获取下一个待处理的链接（线程安全）"""
    global _url_list_index

    # 使用锁保护共享的索引变量
    with _url_list_lock:
        # 循环查找有效的URL（跳过无效的URL）
        while _url_list_index < len(urls_list):
            # 获取当前URL和索引
            raw_url = urls_list[_url_list_index]
            url_index = _url_list_index

            # 清洗URL（作为备用，因为启动时已经清洗过了）
            url = extract_douyin_link(raw_url)
            if not url:
                # 如果清洗失败，记录警告并跳过
                log.warning(f"索引 {url_index} 的URL清洗失败，已跳过: {raw_url}")
                # 跳过这个URL，继续下一个
                _url_list_index += 1
                continue

            # 找到有效URL，增加索引并返回
            _url_list_index += 1

            if config.DEBUG:
                log.info(f"从列表获取到待处理链接: {url}, 索引: {url_index}")
            return None, url, url_index  # 列表模式下link_id为None

        # 所有URL都已处理完毕
        return None, None, None


def get_next_link(db_path=LINKS_DB_PATH):
    """从数据库或列表获取下一个待处理的链接"""
    # 判断使用列表模式还是数据库模式
    if config.URLS and len(config.URLS) > 0:
        # 使用列表模式
        return get_next_link_from_list(config.URLS)
    else:
        # 使用数据库模式
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 先获取所有链接的ID和状态，用于计算索引（按创建时间或ID排序）
        cursor.execute(
            "SELECT id FROM links ORDER BY id"
        )
        all_link_ids = [row[0] for row in cursor.fetchall()]

        # 获取一个待处理的链接
        cursor.execute(
            "SELECT id, url FROM links WHERE status = 'pending' LIMIT 1"
        )
        result = cursor.fetchone()

        if result:
            link_id, url = result
            # 计算该链接在所有链接中的索引（从0开始）
            # 使用所有链接列表来计算索引，这样即使链接状态改变，索引也不会变
            url_index = all_link_ids.index(link_id) if link_id in all_link_ids else 0

            # 标记为处理中，使用本地时间
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                "UPDATE links SET status = 'processing', updated_at = ? WHERE id = ?",
                (current_time, link_id)
            )
            conn.commit()
            conn.close()
            if config.DEBUG:
                log.info(f"获取到待处理链接: {url}, 索引: {url_index}")
            return link_id, url, url_index
        else:
            conn.close()
            log.debug("数据库中没有待处理的链接")
            return None, None, None


def mark_link_as_completed(link_id, db_path=LINKS_DB_PATH):
    """标记链接为已完成（更新状态而不是删除）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 标记为完成状态，使用本地时间
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "UPDATE links SET status = 'completed', updated_at = ? WHERE id = ?",
        (current_time, link_id)
    )
    conn.commit()
    conn.close()


def mark_link_as_failed(link_id, db_path=LINKS_DB_PATH):
    """标记链接为处理失败（可选择重新处理或删除）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 标记为失败状态，使用本地时间
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute(
        "UPDATE links SET status = 'failed', updated_at = ? WHERE id = ?",
        (current_time, link_id)
    )
    conn.commit()
    conn.close()
    # log.warning(f"链接 {link_id} 标记为处理失败")


def continuous_processing_loop(browser_manager, browser_id,
                               wait_time, like_probability, visit_profile_probability, profile_follow_probability,
                               min_follows_per_video, max_follows_per_video,
                               min_likes_per_video, max_likes_per_video,
                               browser_number, db_path=LINKS_DB_PATH):
    """持续处理循环"""
    browser_info = get_browser_info(browser_number)
    debug_log("info", "启动持续处理循环", browser_number)

    driver = None
    max_retries = 3

    # 检查卡密是否仍然有效（移到try-except块外面）
    li.check_license_validity()

    # 根据配置决定是否启用关注功能
    enable_follow = config.ENABLE_FOLLOW

    # 将整数概率转换为浮点数用于计算
    like_probability = like_probability / 100.0
    visit_profile_probability = visit_profile_probability / 100.0
    profile_follow_probability = profile_follow_probability / 100.0

    # 程序启动时输出一次 start
    output_json(0, "", "start", browser_id)

    try:
        while True:
            # 检查并重建浏览器驱动（如果需要）
            if driver is None:
                debug_log("info", "尝试创建浏览器驱动...", browser_number)
                driver = browser_manager.create_driver(browser_id, browser_number)
                if driver is None:
                    log.error(f"{browser_info} 无法创建浏览器驱动，等待30秒后重试...")
                    safe_sleep(30)
                    continue
                debug_log("info", "浏览器驱动创建成功", browser_number)

            # 从数据库或列表获取下一个链接
            link_id, url, url_index = get_next_link(db_path)

            if url is None:
                # 判断是列表模式还是数据库模式
                if config.URLS and len(config.URLS) > 0:
                    # 列表模式下，所有URL处理完毕，退出循环
                    debug_log("info", "列表中的所有URL已处理完毕", browser_number)
                    break
                else:
                    # 数据库模式下，等待新链接
                    debug_log("info", "数据库中没有待处理的链接，等待30秒后重试...", browser_number)
                    safe_sleep(30)
                    continue

            debug_log("info", f"获取到新链接: {url}", browser_number)

            retry_count = 0
            while retry_count < max_retries:
                try:
                    # 处理链接
                    success = run_automation(driver, url,
                                             wait_time, like_probability, visit_profile_probability,
                                             profile_follow_probability,
                                             min_follows_per_video, max_follows_per_video,
                                             min_likes_per_video, max_likes_per_video,
                                             browser_number, browser_id, enable_follow)  # 传递enable_follow参数

                    if success:
                        # 只有在数据库模式下才标记为已完成
                        if link_id is not None:
                            mark_link_as_completed(link_id, db_path)
                        # 输出链接处理成功
                        output_json(0, "", "url_ok", browser_id, url_index)
                        debug_log("info", f"链接处理成功: {url}", browser_number)
                    else:
                        # 只有在数据库模式下才标记为失败
                        if link_id is not None:
                            mark_link_as_failed(link_id, db_path)
                        # 链接失效，输出错误
                        output_json(1, "链接失效", "url_fail", browser_id, url_index)
                        debug_log("error", f"{browser_info} 链接处理失败（链接失效）: {url}", browser_number)
                    break  # 处理完成，跳出重试循环

                except LicenseException:
                    # 重新抛出LicenseException，不捕获它，让程序终止
                    raise
                except Exception as e:
                    retry_count += 1
                    log.error(f"{browser_info} 处理链接 {url} 时发生异常 (第{retry_count}次): {e}")

                    # 记录详细的错误信息
                    import traceback
                    log.error(f"{browser_info} 详细错误堆栈: {traceback.format_exc()}")

                    # 处理浏览器相关异常，包括渲染器断开连接的情况
                    error_msg = str(e).lower()
                    if ("disconnected: unable to receive message from renderer" in error_msg or
                            "disconnected: not connected to devtools" in error_msg or
                            "invalid session id" in error_msg or
                            "session not created" in error_msg or
                            "invalid argument" in error_msg):
                        log.warning(
                            f"{browser_info} 浏览器会话失效或连接断开，尝试在新标签页中打开链接并关闭旧标签页...")
                        # 尝试在新标签页中打开链接并关闭所有旧标签页
                        if open_new_tab_and_close_others(driver, url, browser_number):
                            log.info(f"{browser_info} 成功在新标签页中打开链接并关闭旧标签页")
                            # 重置retry_count，继续当前链接的处理
                            retry_count = 0
                            continue
                        else:
                            # 如果在新标签页中打开失败，则尝试关闭浏览器进程并重新打开浏览器
                            log.warning(
                                f"{browser_info} 在新标签页中打开链接失败，尝试关闭浏览器进程并重新打开浏览器...")
                            try:
                                safe_driver_quit(driver)
                                # 等待一段时间确保浏览器完全关闭
                                safe_sleep(3)
                                # 重新创建浏览器驱动
                                driver = browser_manager.create_driver(browser_id, browser_number)
                                if driver is not None:
                                    log.info(f"{browser_info} 成功重新打开浏览器")
                                    # 重置retry_count，继续当前链接的处理
                                    retry_count = 0
                                    continue
                                else:
                                    log.error(f"{browser_info} 重新创建浏览器驱动失败")
                            except Exception as restart_error:
                                log.error(f"{browser_info} 重新打开浏览器时发生异常: {restart_error}")

                            # 如果重新打开浏览器也失败，则使用最后的备选方案
                            log.warning(f"{browser_info} 重新打开浏览器失败，使用最后的备选方案...")
                            driver = None
                            safe_sleep(5)
                            break  # 重新创建浏览器后重试

                    # 处理一般异常，尝试重新打开浏览器
                    if retry_count >= max_retries:
                        log.warning(f"{browser_info} 尝试重新打开浏览器以恢复控制...")
                        safe_driver_quit(driver)
                        driver = None
                        safe_sleep(5)
                        break  # 重新创建浏览器后重试
                    else:
                        # 还有重试机会，等待后继续尝试
                        log.info(f"{browser_info} 还有重试机会，等待10秒后继续尝试...")
                        safe_sleep(10)

            # 处理完一个链接后等待一段时间
            wait_time_between_links = random.uniform(10, 30)
            debug_log("info", f"等待 {wait_time_between_links:.2f} 秒后处理下一个链接...", browser_number)
            safe_sleep(wait_time_between_links)

    except KeyboardInterrupt:
        log.info(f"{browser_info} 收到停止信号，正在退出...")
        # 程序退出时输出一次 exit
        output_json(0, "", "exit", browser_id)
        # 关闭浏览器
        safe_driver_quit(driver)
        log.info(f"{browser_info} 浏览器已关闭")
        # 不再重新抛出KeyboardInterrupt，直接返回
        return
    except Exception as e:
        # 程序异常退出时也输出一次 exit
        log.error(f"{browser_info} 程序异常退出: {e}")
        output_json(0, "", "exit", browser_id)
        raise


def print_config_debug():
    """打印所有配置参数，用于调试"""
    log.info("=" * 80)
    log.info("📋 配置参数调试信息 (DEBUG MODE)")
    log.info("=" * 80)

    # 定义需要忽略的方法和内部属性
    ignore_attrs = {
        'construct', 'copy', 'dict', 'json', 'from_orm', 'model_computed_fields',
        'model_config', 'model_construct', 'model_copy', 'model_dump', 'model_dump_json',
        'model_extra', 'model_fields', 'model_fields_set', 'model_json_schema',
        'model_dump_json', 'model_parametrized_name', 'model_post_init', 'model_rebuild',
        'model_validate', 'model_validate_json', 'model_validate_strings', 'model_validate_python',
        'parse_obj', 'parse_raw', 'parse_file', 'parse_obj_or_dict', 'schema', 'schema_json',
        'update_forward_refs', 'validate'
    }

    # 动态获取KuSettings的所有属性
    for attr_name in dir(config):
        # 跳过私有属性、方法和需要忽略的属性
        if not attr_name.startswith('_') and attr_name not in ignore_attrs:
            try:
                attr_value = getattr(config, attr_name)
                # 检查是否为方法或函数
                if callable(attr_value):
                    continue

                # 特殊处理列表类型的属性，只显示前几项
                if isinstance(attr_value, list) and len(attr_value) > 0:
                    if len(attr_value) <= 5:
                        log.info(f"  {attr_name}: {attr_value}")
                    else:
                        log.info(
                            f"  {attr_name}: 共 {len(attr_value)} 项 [{', '.join(map(str, attr_value[:3]))}, ...]")
                else:
                    log.info(f"  {attr_name}: {attr_value}")
            except Exception as e:
                log.info(f"  {attr_name}: 无法获取值 (错误: {e})")

    log.info("=" * 80)


def main_database():
    """
    使用数据库或列表的主函数 - 持续运行模式，从环境变量获取卡密信息

    环境变量:
        SIBERIAN_KEY: 卡密密钥
        DEVICE_CODE: 设备码
        URLS: URL列表（如果配置了则使用列表模式，否则使用数据库模式）
        DEBUG: 是否输出调试信息（True/False）
    """
    # 首先验证卡密
    if not li.verify_license():
        log.error("❌ 卡密不存在！")
        return

    # 如果启用了调试模式，打印所有配置参数
    if config.DEBUG:
        print_config_debug()

    # 启动定期验证线程
    li.start_periodic_check()

    # 判断使用列表模式还是数据库模式
    use_list_mode = config.URLS and len(config.URLS) > 0

    if use_list_mode:
        # 清洗URLS列表中的链接
        cleaned_urls = []
        invalid_count = 0
        for url in config.URLS:
            cleaned_url = extract_douyin_link(url)
            if cleaned_url:
                cleaned_urls.append(cleaned_url)
            else:
                invalid_count += 1
                if config.DEBUG:
                    log.warning(f"无效的抖音链接，已跳过: {url}")

        # 更新配置中的URLS列表为清洗后的列表
        config.URLS = cleaned_urls

        if invalid_count > 0:
            log.warning(f"URLS列表中有 {invalid_count} 个无效链接已跳过")

        log.info(f"使用列表模式，共 {len(config.URLS)} 个有效URL")
        # 重置URL列表索引，确保每次启动时从0开始
        reset_url_list_index()
    else:
        log.info("使用数据库模式")
        # 只有在数据库模式下才初始化数据库
        init_database()

    # 检查是否有配置浏览器ID
    if not config.BIT_BROWSER_IDS:
        log.error("请在代码中的 BIT_BROWSER_IDS 列表中配置浏览器ID")
        return

    # 使用.env的配置参数（现在是整数，将在continuous_processing_loop中转换为浮点数）
    WAIT_TIME_USED = config.WAIT_TIME
    MAX_WORKERS_USED = len(config.BIT_BROWSER_IDS)  # 根据实际浏览器数量自适应调整
    HEADLESS_USED = config.HEADLESS
    LIKE_PROBABILITY_USED = config.LIKE_PROBABILITY
    VISIT_PROFILE_PROBABILITY_USED = config.VISIT_ENABLE
    PROFILE_FOLLOW_PROBABILITY_USED = config.PROFILE_FOLLOW_PROBABILITY
    MIN_FOLLOWS_PER_VIDEO_USED = config.MIN_FOLLOWS_PER_VIDEO
    MAX_FOLLOWS_PER_VIDEO_USED = config.MAX_FOLLOWS_PER_VIDEO
    MIN_LIKES_PER_VIDEO_USED = config.COMMENT_LIKE_COUNT_MIN
    MAX_LIKES_PER_VIDEO_USED = config.COMMENT_LIKE_COUNT_MAX
    ENABLE_FOLLOW_USED = config.ENABLE_FOLLOW  # 获取关注功能开关状态

    # 创建比特浏览器管理器实例
    browser_manager = BitBrowserManager(headless=HEADLESS_USED)

    try:
        # 创建线程池来并行处理多个浏览器
        with ThreadPoolExecutor(max_workers=MAX_WORKERS_USED) as executor:
            # 提交任务到线程池
            futures = []
            for i in range(MAX_WORKERS_USED):
                # 为每个线程使用不同的浏览器ID
                browser_id = config.BIT_BROWSER_IDS[i % len(config.BIT_BROWSER_IDS)]

                future = executor.submit(continuous_processing_loop, browser_manager, browser_id,
                                         WAIT_TIME_USED, LIKE_PROBABILITY_USED, VISIT_PROFILE_PROBABILITY_USED,
                                         PROFILE_FOLLOW_PROBABILITY_USED,
                                         MIN_FOLLOWS_PER_VIDEO_USED, MAX_FOLLOWS_PER_VIDEO_USED,
                                         MIN_LIKES_PER_VIDEO_USED, MAX_LIKES_PER_VIDEO_USED, i + 1)
                futures.append(future)

                # 等待2.5秒再启动下一个浏览器，避免资源竞争
                if i < MAX_WORKERS_USED - 1:
                    time.sleep(2.5)

            # 等待所有任务完成（实际上会持续运行直到手动停止）
            # 使用 concurrent.futures.wait 替代 as_completed 以更好地处理 KeyboardInterrupt
            while futures:
                try:
                    done, not_done = concurrent.futures.wait(futures, timeout=1)
                    for future in done:
                        try:
                            future.result()
                        except LicenseException:
                            # 捕获LicenseException并重新抛出，使程序终止
                            log.error("卡密验证失败，程序终止")
                            raise
                        except Exception as e:
                            log.error(f"线程执行出错: {e}")
                    futures = list(not_done)
                except KeyboardInterrupt:
                    log.info("收到停止信号，正在关闭所有线程...")
                    # 设置全局停止标志
                    _stop_flag.set()
                    # 取消所有未完成的任务
                    for future in futures:
                        future.cancel()
                    # 直接退出程序
                    import sys
                    sys.exit(0)
    except LicenseException:
        # 捕获LicenseException并记录，然后让程序终止
        log.error("卡密验证失败，程序终止")
        raise
    finally:
        # 停止定期验证线程
        li.stop_periodic_check()


def view_links_in_db(db_path=LINKS_DB_PATH):
    """查看数据库中的链接"""
    log.info("查看数据库中的链接")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 查询所有链接
        cursor.execute("SELECT id, url, status, created_at FROM links ORDER BY created_at")
        links = cursor.fetchall()

        # 查询各种状态的链接数量
        cursor.execute("SELECT status, COUNT(*) FROM links GROUP BY status")
        status_counts = cursor.fetchall()
        status_dict = {status: count for status, count in status_counts}

        total_count = sum(status_dict.values())
        pending_count = status_dict.get('pending', 0)
        processing_count = status_dict.get('processing', 0)
        failed_count = status_dict.get('failed', 0)
        completed_count = status_dict.get('completed', 0)

        if not links:
            log.info("数据库中没有链接")
            return

        log.info(f"数据库中的链接 (共 {len(links)} 条)")
        print(f"数据库中的链接 (共 {len(links)} 条):")

        # 显示进度条和统计信息
        print(f"总链接数: {total_count}")
        print(
            f"待处理: {pending_count} | 处理中: {processing_count} | 失败: {failed_count} | 已完成: {completed_count}")

        # 显示进度条 (已完成+失败+处理中的链接都算作已处理)
        if total_count > 0:
            processed = completed_count + failed_count + processing_count
            progress = processed / total_count
            bar_length = 40
            filled_length = int(bar_length * progress)
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            print(f"完成进度: |{bar}| {progress:.1%} ({processed}/{total_count})")

        print("-" * 100)
        print(f"{'ID':<5} {'状态':<12} {'创建时间':<20} {'链接'}")
        print("-" * 100)

        for link in links:
            link_id, url, status, created_at = link
            # 截断长URL以提高可读性
            short_url = (url[:70] + '...') if len(url) > 73 else url
            print(f"{link_id:<5} {status:<12} {created_at:<20} {short_url}")

    except Exception as e:
        log.error(f"查看链接时出错: {e}")
    finally:
        conn.close()


def clear_database(db_path=LINKS_DB_PATH, status=None):
    """清空数据库中的链接"""
    log.info("开始清空数据库")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        if status:
            # 删除特定状态的链接
            cursor.execute("DELETE FROM links WHERE status = ?", (status,))
            log.info(f"已删除状态为 {status} 的链接")
        else:
            # 删除所有链接
            cursor.execute("DELETE FROM links")
            log.info("已删除所有链接")

        conn.commit()
        log.info("数据库清空完成")
    except Exception as e:
        log.error(f"清空数据库时出错: {e}")
    finally:
        conn.close()


def main():
    """
    主函数 - 抖音自动化脚本入口点
    直接使用文件顶部定义的配置参数运行脚本
    """
    import sys

    try:
        # 检查命令行参数
        if len(sys.argv) > 1:
            log.info(f"命令行参数: {sys.argv}")
            if sys.argv[1] == "add":
                # 添加链接模式
                add_links_cli()
                return
            elif sys.argv[1] == "run":
                # 持续运行模式
                main_database()
                return
            elif sys.argv[1] == "look":
                # 查看链接模式
                view_links_in_db()
                return
            elif sys.argv[1] == "clear":
                # 清空数据库
                if len(sys.argv) > 2:
                    clear_database(status=sys.argv[2])
                else:
                    clear_database()
                return
            elif sys.argv[1] == "help":
                # 帮助信息
                log.info("显示帮助信息")
                log.info("使用方法:")
                log.info("  python DY_ku.py run    # 持续运行，从数据库读取链接")
                log.info("  python DY_ku.py add    # 添加链接到数据库")
                log.info("  python DY_ku.py look   # 查看数据库中的链接")
                log.info("  python DY_ku.py clear  # 清空数据库中的所有链接")
                log.info("  python DY_ku.py clear pending  # 清空待处理链接")
                log.info("  python DY_ku.py clear failed   # 清空失败链接")
                log.info("  python DY_ku.py help   # 显示此帮助信息")
                return

        # 检查是否有配置浏览器ID
        if not config.BIT_BROWSER_IDS:
            log.error("请在代码中的 BIT_BROWSER_IDS 列表中配置浏览器ID")
            return

        # 直接调用数据库模式
        main_database()

    except LicenseException:
        # 捕获LicenseException并退出程序
        log.error("卡密验证失败，程序即将退出")
        sys.exit(1)
    except KeyboardInterrupt:
        log.info("程序已被用户中断")
        sys.exit(0)


if __name__ == "__main__":
    main()
