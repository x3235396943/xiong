# ==================== 配置参数 ====================
# 在这里集中配置所有参数，方便修改

# 操作参数
LIKE_PROBABILITY = 0.3  # 点赞概率(乘以处理评论的概率后才是真实概率) (0-1)
PROCESS_COMMENT_PROBABILITY = 0.8  # 处理评论的概率 (0-1)
VISIT_PROFILE_PROBABILITY = 0.2  # 点赞时进入主页的概率 (0-1)
PROFILE_FOLLOW_PROBABILITY = 0.2  # 进入主页后关注的概率 (0-1)
MIN_FOLLOWS_PER_VIDEO = 5  # 每条视频最少关注数量
MAX_FOLLOWS_PER_VIDEO = 15  # 每条视频最多关注数量

# 等待时间参数
LIKE_WAIT_MIN = 4  # 点赞后最小等待时间（秒）
LIKE_WAIT_MAX = 10  # 点赞后最大等待时间（秒）
FOLLOW_WAIT_MIN = 2  # 关注后最小等待时间（秒）
FOLLOW_WAIT_MAX = 5  # 关注后最大等待时间（秒）

# 数据库路径
LINKS_DB_PATH = "links.db"

# 并行设置
MAX_WORKERS = None  # 自动根据浏览器ID数量调整并行数

# 其他设置
WAIT_TIME = 10  # 等待元素出现的时间（秒）
HEADLESS = False  # 是否以无头模式运行浏览器(T or F)

# 浏览器ID列表 - 手动配置
BIT_BROWSER_IDS = []

# =================================================

import requests
import json
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
from datetime import datetime


def get_browser_ids_from_user():
    """从用户输入获取浏览器ID列表"""
    print("请输入比特浏览器ID，每行一个，输入空行结束:")
    browser_ids = []
    while True:
        browser_id = input().strip()
        if not browser_id:
            break
        browser_ids.append(browser_id)
    
    if not browser_ids:
        print("未输入任何浏览器ID，程序将退出")
        return None
        
    print(f"已输入 {len(browser_ids)} 个浏览器ID")
    return browser_ids


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

    def get_browser_list(self, page: int = 0, page_size: int = 100):
        """
        获取浏览器列表

        Args:
            page: 页码
            page_size: 每页数量

        Returns:
            浏览器信息列表
        """
        url = f"{self.base_url}/browser/list"
        data = {
            "page": page,
            "pageSize": page_size
        }

        try:
            response = requests.post(url, data=json.dumps(data), headers=self.headers)
            result = response.json()

            if result.get("success"):
                # 检查data字段是否为列表
                data_field = result.get("data", [])
                if isinstance(data_field, list):
                    return data_field
                elif isinstance(data_field, dict) and "list" in data_field:
                    # 如果data是一个字典且包含list字段
                    return data_field.get("list", [])
                else:
                    # 如果data不是列表也不是包含list的字典，则返回空列表
                    return []
            else:
                print(f"获取浏览器列表失败: {result.get('msg')}")
                return []
        except Exception as e:
            print(f"请求浏览器列表时出错: {e}")
            return []

    def get_browser_ids(self, page: int = 0, page_size: int = 100):
        """
        获取浏览器ID列表

        Args:
            page: 页码
            page_size: 每页数量

        Returns:
            浏览器ID列表
        """
        browsers = self.get_browser_list(page, page_size)
        return [browser.get("id") for browser in browsers if browser.get("id")][1:4]


# 全局变量定义
# 连续没有新评论的滚动次数计数器
scroll_count_total = 0
previous_comment_count = 0
no_new_comments_count = 0
# 全局关注计数器
global_followed_count = 0


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
        print(f"正在打开{browser_info}...")
        json_data = {
            "id": str(browser_id_param),
            "args": ["--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding"]
        }

        # 设置无头模式
        if self.headless:
            json_data["args"].append("--headless")
            json_data["ignoreDefaultUrls"] = "true"  # 防止出错的重要参数
            json_data["windowMode"] = "hidden"
        else:
            json_data["windowMode"] = "normal"

        try:
            response = requests.post(
                f"{self.url}/browser/open",
                data=json.dumps(json_data),
                headers=self.headers
            )
            return response.json()
        except Exception as e:
            print(f"打开{browser_info}时出错: {e}")
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
        res = self.open_browser(browser_id_param, browser_number)
        if not res or 'data' not in res:
            print(f"无法打开{browser_info}")
            return None

        print(f"{browser_info}响应: {res}")

        driver_path = res['data']['driver']
        debugger_address = res['data']['http']

        # selenium 连接代码
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", debugger_address)

        # 注意：根据比特浏览器文档，Chrome参数在无头模式下可能不需要额外添加
        # 因为我们已经在API层面设置了--headless参数

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


def human_like_delay(min_delay=0.5, max_delay=2.0):
    """
    模拟人类操作的随机延迟

    Args:
        min_delay (float): 最小延迟时间（秒）
        max_delay (float): 最大延迟时间（秒）
    """
    time.sleep(random.uniform(min_delay, max_delay))


def open_comment_section(driver, wait_time=10, browser_number=None):
    """打开评论区"""
    browser_info = f"浏览器 #{browser_number}" if browser_number is not None else ""
    try:
        # 使用智能等待查找评论按钮
        wait = WebDriverWait(driver, wait_time)
        try:
            comment_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, '//*[contains(@class, "fN2jqmuV")]/div[2]'))
            )
        except:
            print(f"{browser_info} 评论区按钮未找到，尝试刷新页面...")
            driver.refresh()
            # 等待页面刷新完成
            human_like_delay(5, 7)
            # 再次尝试查找元素
            try:
                comment_button = wait.until(
                    EC.element_to_be_clickable((By.XPATH, '//*[contains(@class, "fN2jqmuV")]/div[2]'))
                )
            except:
                print(f"{browser_info} 刷新后仍未找到评论按钮，跳过打开评论区操作")
                return False

        # 模拟人类操作
        human_like_delay(0.5, 1.0)

        comment_button.click()
        print(f"{browser_info} 打开评论区成功")
        return True
    except Exception as e:
        print(f"{browser_info} 打开评论区失败: {e}")
        return False


def switch_to_new_tab(driver, url, wait_time=10, browser_number=None):
    """在新标签页中打开链接并切换到新标签页"""
    browser_info = f"浏览器 #{browser_number}" if browser_number is not None else ""
    # 保存当前窗口句柄
    current_window = driver.current_window_handle

    try:
        # 模拟人类在新标签页中打开链接
        human_like_delay(0.5, 1.5)
        driver.execute_script(f"window.open('{url}','_blank');")

        # 等待新标签页打开
        wait = WebDriverWait(driver, wait_time)
        wait.until(lambda d: len(d.window_handles) > 1)

        # 获取所有窗口句柄
        all_windows = driver.window_handles

        # 切换到新打开的标签页（最后一个）
        driver.switch_to.window(all_windows[-1])

        # 模拟页面加载等待
        human_like_delay(2, 4)

        # 关闭之前的标签页
        driver.switch_to.window(current_window)
        driver.close()

        # 切换回新标签页
        driver.switch_to.window(all_windows[-1])
        print(f"{browser_info} 成功切换到新标签页: {url}")
    except Exception as e:
        print(f"{browser_info} 切换到新标签页时出错: {e}")
        # 确保回到主窗口
        try:
            driver.switch_to.window(current_window)
        except:
            pass
        raise


# Excel相关功能已移除，仅使用数据库作为数据源
def extract_douyin_link(text):
    """从文本中提取抖音链接"""
    if isinstance(text, str):
        # 匹配抖音链接得正则表达式
        pattern = r'https?://v\.douyin\.com/[^\s]+'
        match = re.search(pattern, text)
        return match.group(0) if match else None
    return None


# Excel相关功能已移除，仅使用数据库作为数据源


def process_comment(web_driver, main_window, comment_index, like_probability, process_comment_probability=0.8,
                    wait_time=10, visit_profile_probability=0.3, profile_follow_probability=0.5, browser_number=None):
    """处理单条评论：根据概率决定是否点赞，关注用户"""
    browser_info = f"浏览器 #{browser_number}" if browser_number is not None else ""
    print(f"{browser_info} 开始处理第{comment_index + 1}条评论")

    # 生成随机数决定执行哪些操作
    # 根据概率决定是否处理该条评论
    if random.random() > process_comment_probability:
        print(f"{browser_info} 第{comment_index + 1}条评论随机跳过处理")
        return True

    # 根据概率决定是否点赞
    should_like = random.random() < like_probability

    # 点赞操作
    if should_like:
        try:
            # 先定位评论容器
            comments_container = WebDriverWait(web_driver, wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
            )

            # 获取所有评论项
            comment_items = comments_container.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-list"] > div')

            if comment_index >= len(comment_items):
                print(f"{browser_info} 评论索引 {comment_index} 超出范围，共有 {len(comment_items)} 条评论")
                return False

            # 获取指定索引的评论项
            target_comment = comment_items[comment_index]

            # 查找点赞按钮
            like_button = target_comment.find_element(
                By.XPATH,
                ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]",
            )

            # 模拟人类操作
            human_like_delay(0.5, 1.5)

            like_button.click()
            print(f"{browser_info} 点赞第{comment_index + 1}条评论成功")
            # 点赞后等待，模拟真实用户行为
            like_wait_time = random.uniform(LIKE_WAIT_MIN, LIKE_WAIT_MAX)
            human_like_delay(like_wait_time, like_wait_time)
            print(f"{browser_info} 点赞后等待{like_wait_time:.2f}秒")
        except Exception as like_error:
            print(f"{browser_info} 点赞第{comment_index + 1}条评论失败: {like_error}")
            # 即使点赞失败，我们仍然可以访问用户主页
    else:
        print(f"{browser_info} 第{comment_index + 1}条评论未执行点赞操作")

    # 根据概率决定是否访问用户主页
    if random.random() < visit_profile_probability:
        try:
            # 先定位评论容器
            comments_container = WebDriverWait(web_driver, wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
            )

            # 使用容器定位方法查找用户头像
            comment_items = comments_container.find_elements(By.XPATH, "./div")
            if comment_index >= len(comment_items):
                print(f"{browser_info} 评论索引 {comment_index} 超出范围，共有 {len(comment_items)} 条评论")
                return False

            # 获取指定索引的评论项
            target_comment = comment_items[comment_index]

            # 查找带链接的头像，如果找不到就点击头像容器
            try:
                avatar = target_comment.find_element(
                    By.CSS_SELECTOR, ".comment-item-avatar a"
                )
            except:
                # 如果没找到带a标签的头像，点击头像容器
                avatar = target_comment.find_element(
                    By.CSS_SELECTOR, ".comment-item-avatar"
                )
                print(f"{browser_info} 第{comment_index + 1}条评论未找到带链接的头像，点击头像容器")

            # 模拟人类操作
            human_like_delay(0.5, 1.5)

            # 点击找到的头像元素
            avatar.click()
            print(f"{browser_info} 点击第{comment_index + 1}个评论的用户头像进入主页")

            # 等待新页面加载
            human_like_delay(3, 5)

            # 获取所有窗口句柄
            all_windows = web_driver.window_handles

            # 切换到新窗口（非主窗口）
            new_window = None
            for window in all_windows:
                if window != main_window:
                    new_window = window
                    web_driver.switch_to.window(window)
                    break

            # 等待页面加载
            human_like_delay(2, 4)

            # 进入主页后根据概率决定是否关注
            if random.random() < profile_follow_probability:
                try:
                    # 查找并点击关注按钮
                    follow_button_wait = WebDriverWait(web_driver, wait_time)
                    follow_button = follow_button_wait.until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, '#user_detail_element [data-e2e="user-info-follow-btn"]'))
                    )

                    # 模拟人类操作
                    human_like_delay(0.5, 1.5)
                    follow_button.click()
                    print(f"{browser_info} 在用户主页关注该用户")

                    # 关注后等待，模拟真实用户行为
                    follow_wait_time = random.uniform(FOLLOW_WAIT_MIN, FOLLOW_WAIT_MAX)
                    human_like_delay(follow_wait_time, follow_wait_time)
                    print(f"{browser_info} 关注后等待{follow_wait_time:.2f}秒")

                    # 关注成功后更新全局计数器并返回"followed"标识
                    global global_followed_count
                    global_followed_count += 1
                    print(f"{browser_info} 全局关注计数器更新: {global_followed_count}")

                    # 关闭新窗口并切换回主窗口
                    try:
                        if 'new_window' in locals() and new_window:
                            web_driver.close()  # 关闭新窗口
                            print(f"{browser_info} 用户主页窗口已关闭")
                        web_driver.switch_to.window(main_window)  # 切换回主窗口
                        print(f"{browser_info} 已切换回主窗口")
                        return "followed"
                    except Exception as switch_error:
                        print(f"{browser_info} 窗口切换时出错: {switch_error}")
                        web_driver.switch_to.window(main_window)
                        return "followed"
                except Exception as follow_error:
                    print(f"{browser_info} 关注用户失败: {follow_error}")

            # 关闭新窗口并切换回主窗口
            try:
                if 'new_window' in locals() and new_window:
                    web_driver.close()  # 关闭新窗口
                    print(f"{browser_info} 用户主页窗口已关闭")
                web_driver.switch_to.window(main_window)  # 切换回主窗口
                print(f"{browser_info} 已切换回主窗口")
            except Exception as switch_error:
                print(f"{browser_info} 窗口切换时出错: {switch_error}")
                web_driver.switch_to.window(main_window)

        except Exception as avatar_error:
            print(f"{browser_info} 点击用户头像失败: {avatar_error}")
            # 确保回到主窗口
            web_driver.switch_to.window(main_window)

    # 如果没有执行任何操作，也视为成功
    return True


def run_automation(driver, url, like_probability=0.7, process_comment_probability=0.8, wait_time=10,
                   visit_profile_probability=0.3, profile_follow_probability=0.5,
                   min_follows_per_video=5, max_follows_per_video=15, browser_number=None):
    """
    运行完整的自动化流程

    Args:
        driver: WebDriver实例
        url: 要访问的网页URL
        like_probability: 点赞概率
        process_comment_probability: 处理评论的概率
        wait_time: 等待元素出现的时间（秒）
        visit_profile_probability: 进入主页的概率
        profile_follow_probability: 进入主页后关注的概率
        min_follows_per_video: 每条视频最少关注数量
        max_follows_per_video: 每条视频最多关注数量
        browser_number: 浏览器编号，用于输出标识
    """
    browser_info = f"浏览器 #{browser_number}" if browser_number is not None else ""
    # 每条视频使用独立的关注计数器
    video_followed_count = 0
    target_follow_count = random.randint(min_follows_per_video, max_follows_per_video)

    try:
        print(f"{browser_info} 访问网页: {url}")
        driver.get(url)

        wait = WebDriverWait(driver, wait_time)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        human_like_delay(3, 6)
        human_like_delay(1, 2)

        print(f"{browser_info} 处理视频评论")

        print(f"{browser_info} 打开评论区")

        if not open_comment_section(driver, wait_time, browser_number):
            return False

        human_like_delay(1, 3)

        main_window = driver.current_window_handle

        processed_comment_count = 0
        scroll_number = 0

        comment_index = 0
        print(f"{browser_info} 从第一条开始处理评论")
        print(f"{browser_info} 本视频计划关注 {target_follow_count} 个用户")

        # 初始化评论容器
        comments_container = None
        try:
            comments_container = WebDriverWait(driver, wait_time).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
            )
        except Exception as e:
            print(f"{browser_info} 无法定位评论容器: {e}")
            return False

        while True:
            # 处理单条评论
            result = process_comment(driver, main_window, comment_index, like_probability,
                                     process_comment_probability, wait_time, visit_profile_probability,
                                     profile_follow_probability, browser_number)

            # 增加处理过的评论计数
            processed_comment_count += 1

            # 每处理3条评论就滚动一次
            if processed_comment_count % 3 == 0 or processed_comment_count == 1:
                scroll_number += 1
                print(f"{browser_info} 已处理{processed_comment_count}条评论，执行滚动操作")
                scroll_comments(driver, scroll_number, browser_number)

                # 滚动后重新定位评论容器
                try:
                    comments_container = WebDriverWait(driver, wait_time).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
                    )
                except Exception as e:
                    print(f"{browser_info} 滚动后无法重新定位评论容器: {e}")
                    break

            # 如果成功关注了用户，则增加计数器
            if result == "followed":
                video_followed_count += 1
                print(f"{browser_info} 已成功关注用户，当前视频已关注 {video_followed_count} 个用户")

            # 检查是否达到目标关注数量
            if video_followed_count >= target_follow_count:
                print(f"{browser_info} 已达到目标关注数量 {target_follow_count}，切换到下一个链接")
                break

            # 检查是否还能找到下一条评论
            try:
                if comments_container is not None:
                    comment_items = comments_container.find_elements(By.XPATH, "./div")
                    if comment_index + 2 >= len(comment_items):
                        print(f"{browser_info} 可能已滚动到底部或没有更多评论，结束当前链接操作")
                        break
                else:
                    print(f"{browser_info} 评论容器未正确初始化，结束当前链接操作")
                    break
            except Exception as e:
                print(f"{browser_info} 无法获取评论列表: {e}")
                print(f"{browser_info} 可能已滚动到底部或没有更多评论，结束当前链接操作")
                break

            # 增加评论索引
            comment_index += 1

            # 确保回到主页面
            driver.switch_to.window(main_window)

            # 等待一段时间再处理下一条，模拟人类思考时间
            human_like_delay(2, 5)

        # 确保最终回到主页面
        driver.switch_to.window(main_window)
        print(f"{browser_info} 所有评论处理完成")
        return True

    except Exception as e:
        print(f"{browser_info} 程序执行出错: {e}")
        return False


def process_urls_thread(browser_manager, browser_id, urls, like_probability, process_comment_probability, wait_time,
                        visit_profile_probability, profile_follow_probability,
                        min_follows_per_video, max_follows_per_video, browser_number):
    """在线程中处理URL列表"""
    browser_info = f"浏览器 #{browser_number}" if browser_number is not None else ""
    print(f"{browser_info} 开始处理任务")

    driver = browser_manager.create_driver(browser_id, browser_number)

    if driver is None:
        print(f"{browser_info} 无法创建浏览器驱动")
        return

    try:
        process_urls(driver, urls, like_probability, process_comment_probability,
                     wait_time, visit_profile_probability, profile_follow_probability,
                     min_follows_per_video, max_follows_per_video, browser_number)
    except Exception as e:
        print(f"{browser_info} 处理URL时发生异常: {e}")
    finally:
        # 等待并关闭浏览器
        human_like_delay(3, 5)
        print(f"{browser_info} 浏览器已关闭")


def process_urls(driver, urls, like_probability=0.7, process_comment_probability=0.8, wait_time=10,
                 visit_profile_probability=0.3, profile_follow_probability=0.5,
                 min_follows_per_video=5, max_follows_per_video=15, browser_number=None):
    """处理URL列表"""
    browser_info = f"浏览器 #{browser_number}" if browser_number is not None else ""
    for i, target_url in enumerate(urls):
        print(f"{browser_info} 处理第{i + 1}个链接: {target_url}")

        try:
            # 如果不是第一个链接，则在新标签页中打开并关闭前一个标签页
            if i > 0:
                switch_to_new_tab(driver, target_url, wait_time, browser_number)
            else:
                # 打开第一个链接
                driver.get(target_url)

            success = run_automation(driver, target_url, like_probability,
                                     process_comment_probability, wait_time, visit_profile_probability,
                                     profile_follow_probability,
                                     min_follows_per_video, max_follows_per_video, browser_number)
            if not success:
                print(f"{browser_info} 处理链接 {target_url} 失败")
        except Exception as e:
            print(f"{browser_info} 处理链接 {target_url} 时发生异常: {e}")

        # 在处理下一个链接前等待一段时间
        human_like_delay(3, 7)


def scroll_comments(driver, scroll_number=None, browser_number=None):
    """在打开评论区后执行滚动操作"""
    browser_info = f"浏览器 #{browser_number}" if browser_number is not None else ""

    # 尝试多种滚动方式确保页面能够正常滚动
    try:
        # 方法1: 使用ActionChains的scroll_from_origin进行滚动
        # 定位到页面主体元素
        body = driver.find_element(By.TAG_NAME, "body")

        # 执行单次滚动
        try:
            # 使用ActionChains滚动
            scroll_origin = ScrollOrigin.from_element(body)
            ActionChains(driver).scroll_from_origin(scroll_origin, 0, 450).perform()
            if scroll_number is not None:
                print(f"{browser_info} 使用ActionChains完成滑动 (第 {scroll_number} 次)")
            else:
                print(f"{browser_info} 使用ActionChains完成滑动")
            time.sleep(2)
        except Exception as e:
            print(f"{browser_info} 滚动失败: {e}")
            time.sleep(2)

    except Exception as e:
        print(f"{browser_info} 滚动过程中发生错误: {e}")
    return False  # 默认继续处理


def init_database(db_path=LINKS_DB_PATH):
    """初始化数据库"""
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
    print("数据库初始化完成")


def add_links_cli(db_path=LINKS_DB_PATH):
    """命令行接口：添加链接到数据库"""
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
                print("输入不能为空，请重新输入")
        except KeyboardInterrupt:
            print("\n已退出链接添加工具")
            break
        except EOFError:
            print("\n已退出链接添加工具")
            break


def add_link_to_db(url, db_path=LINKS_DB_PATH):
    """向数据库添加链接"""
    # 清洗链接
    cleaned_url = extract_douyin_link(url)
    if not cleaned_url:
        print(f"无效的抖音链接: {url}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 使用本地时间而不是默认的UTC时间
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "INSERT INTO links (url, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cleaned_url, 'pending', current_time, current_time)
        )
        conn.commit()
        print(f"链接已添加到数据库: {cleaned_url}")
    except sqlite3.IntegrityError:
        print(f"链接已存在: {cleaned_url}")
    finally:
        conn.close()


def get_next_link(db_path=LINKS_DB_PATH):
    """从数据库获取下一个待处理的链接"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 获取一个待处理的链接
    cursor.execute(
        "SELECT id, url FROM links WHERE status = 'pending' LIMIT 1"
    )
    result = cursor.fetchone()

    if result:
        link_id, url = result
        # 标记为处理中，使用本地时间
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "UPDATE links SET status = 'processing', updated_at = ? WHERE id = ?",
            (current_time, link_id)
        )
        conn.commit()
        conn.close()
        return link_id, url
    else:
        conn.close()
        return None, None


def mark_link_as_completed(link_id, db_path=LINKS_DB_PATH):
    """标记链接为已完成（从数据库删除）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 删除已完成的链接
    cursor.execute("DELETE FROM links WHERE id = ?", (link_id,))
    conn.commit()
    conn.close()
    print(f"链接 {link_id} 已从数据库删除")


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
    print(f"链接 {link_id} 标记为处理失败")


def continuous_processing_loop(browser_manager, browser_id, like_probability, process_comment_probability,
                               wait_time, visit_profile_probability, profile_follow_probability,
                               min_follows_per_video, max_follows_per_video, browser_number, db_path=LINKS_DB_PATH):
    """持续处理循环"""
    browser_info = f"浏览器 #{browser_number}" if browser_number is not None else ""
    print(f"{browser_info} 启动持续处理循环")

    driver = browser_manager.create_driver(browser_id, browser_number)

    if driver is None:
        print(f"{browser_info} 无法创建浏览器驱动")
        return

    try:
        while True:
            # 从数据库获取下一个链接
            link_id, url = get_next_link(db_path)

            if url is None:
                print(f"{browser_info} 数据库中没有待处理的链接，等待30秒后重试...")
                time.sleep(30)
                continue

            print(f"{browser_info} 获取到新链接: {url}")

            try:
                # 处理链接
                success = run_automation(driver, url, like_probability,
                                         process_comment_probability, wait_time, visit_profile_probability,
                                         profile_follow_probability,
                                         min_follows_per_video, max_follows_per_video, browser_number)

                if success:
                    # 标记为已完成并从数据库删除
                    mark_link_as_completed(link_id, db_path)
                    print(f"{browser_info} 链接处理成功: {url}")
                else:
                    # 标记为失败
                    mark_link_as_failed(link_id, db_path)
                    print(f"{browser_info} 链接处理失败: {url}")

            except Exception as e:
                print(f"{browser_info} 处理链接 {url} 时发生异常: {e}")
                mark_link_as_failed(link_id, db_path)

            # 处理完一个链接后等待一段时间
            wait_time_between_links = random.uniform(10, 30)
            print(f"{browser_info} 等待 {wait_time_between_links:.2f} 秒后处理下一个链接...")
            time.sleep(wait_time_between_links)

    except KeyboardInterrupt:
        print(f"{browser_info} 收到停止信号，正在退出...")
    except Exception as e:
        print(f"{browser_info} 循环处理过程中发生异常: {e}")
    finally:
        # 关闭浏览器
        try:
            driver.quit()
        except:
            pass
        print(f"{browser_info} 浏览器已关闭")


def main_database():
    """
    使用数据库的主函数 - 持续运行模式
    """
    # 初始化数据库
    init_database()

    # 检查是否已在配置中指定了浏览器ID
    if BIT_BROWSER_IDS:
        BIT_BROWSER_IDS_USED = BIT_BROWSER_IDS
        print(f"使用配置文件中指定的 {len(BIT_BROWSER_IDS_USED)} 个浏览器ID")
    else:
        # 从用户输入获取浏览器ID
        BIT_BROWSER_IDS_USED = get_browser_ids_from_user()
        if not BIT_BROWSER_IDS_USED:
            return

    # 使用文件顶部定义的配置参数
    PROCESS_COMMENT_PROBABILITY_USED = PROCESS_COMMENT_PROBABILITY
    WAIT_TIME_USED = WAIT_TIME
    LIKE_PROBABILITY_USED = LIKE_PROBABILITY
    MAX_WORKERS_USED = len(BIT_BROWSER_IDS_USED)  # 根据实际浏览器数量自适应调整
    HEADLESS_USED = HEADLESS
    VISIT_PROFILE_PROBABILITY_USED = VISIT_PROFILE_PROBABILITY
    PROFILE_FOLLOW_PROBABILITY_USED = PROFILE_FOLLOW_PROBABILITY
    MIN_FOLLOWS_PER_VIDEO_USED = MIN_FOLLOWS_PER_VIDEO
    MAX_FOLLOWS_PER_VIDEO_USED = MAX_FOLLOWS_PER_VIDEO

    # 创建比特浏览器管理器实例
    browser_manager = BitBrowserManager(headless=HEADLESS_USED)

    # 创建线程池来并行处理多个浏览器
    with ThreadPoolExecutor(max_workers=MAX_WORKERS_USED) as executor:
        # 提交任务到线程池
        futures = []
        for i in range(MAX_WORKERS_USED):
            # 为每个线程使用不同的浏览器ID
            browser_id = BIT_BROWSER_IDS_USED[i % len(BIT_BROWSER_IDS_USED)]

            future = executor.submit(continuous_processing_loop, browser_manager, browser_id,
                                     LIKE_PROBABILITY_USED, PROCESS_COMMENT_PROBABILITY_USED,
                                     WAIT_TIME_USED, VISIT_PROFILE_PROBABILITY_USED,
                                     PROFILE_FOLLOW_PROBABILITY_USED,
                                     MIN_FOLLOWS_PER_VIDEO_USED, MAX_FOLLOWS_PER_VIDEO_USED, i + 1)
            futures.append(future)

            # 等待2.5秒再启动下一个浏览器，避免资源竞争
            if i < MAX_WORKERS_USED - 1:  # 最后一个浏览器不需要等待
                time.sleep(2.5)

        # 等待所有任务完成（实际上会持续运行直到手动停止）
        try:
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"线程执行出错: {e}")
        except KeyboardInterrupt:
            print("收到停止信号，正在关闭所有线程...")


def view_links_in_db(db_path=LINKS_DB_PATH):
    """查看数据库中的链接"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 查询所有链接
        cursor.execute("SELECT id, url, status, created_at FROM links ORDER BY created_at")
        links = cursor.fetchall()

        if not links:
            print("数据库中没有链接")
            return

        print(f"数据库中的链接 (共 {len(links)} 条):")
        print("-" * 100)
        print(f"{'ID':<5} {'状态':<12} {'创建时间':<20} {'链接'}")
        print("-" * 100)

        for link in links:
            link_id, url, status, created_at = link
            # 截断长URL以提高可读性
            short_url = (url[:70] + '...') if len(url) > 73 else url
            print(f"{link_id:<5} {status:<12} {created_at:<20} {short_url}")

    except Exception as e:
        print(f"查看链接时出错: {e}")
    finally:
        conn.close()


def main():
    """
    主函数 - 抖音自动化脚本入口点
    直接使用文件顶部定义的配置参数运行脚本
    """
    import sys

    # 检查命令行参数
    if len(sys.argv) > 1:
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
        elif sys.argv[1] == "help":
            # 帮助信息
            print("使用方法:")
            print("  python DY.py run   # 持续运行，从数据库读取链接")
            print("  python DY.py add   # 添加链接到数据库")
            print("  python DY.py look  # 查看数据库中的链接")
            print("  python DY.py help  # 显示此帮助信息")
            return

    # 检查是否已在配置中指定了浏览器ID
    if BIT_BROWSER_IDS:
        BIT_BROWSER_IDS_USED = BIT_BROWSER_IDS
        print(f"使用配置文件中指定的 {len(BIT_BROWSER_IDS_USED)} 个浏览器ID")
    else:
        # 从用户输入获取浏览器ID
        BIT_BROWSER_IDS_USED = get_browser_ids_from_user()
        if not BIT_BROWSER_IDS_USED:
            return

    # 直接调用数据库模式
    main_database()


if __name__ == "__main__":
    main()