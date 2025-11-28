#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音分享自动化工具类
包含从 main.py 提取出的各种工具函数和类
"""

import json
import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import re
import sqlite3
from datetime import datetime
import threading
import concurrent.futures

from ..tools import log, log2
from ..tools.config import KuSettings
from ..tools.base import AbstractCrawler
from ..tools.bit_api import openBrowser, closeBrowser

try:
    from ..tools.verify import LicenseManager, LicenseException
except ImportError:
    log.error("❌ 无法导入 verify 模块，请检查 tools/verify.py 是否存在")
    sys.exit(1)

# 配置和全局变量
config: KuSettings = KuSettings()  # type: ignore
LINKS_DB_PATH = config.LINKS_DB_PATH

# 全局变量定义
scroll_count_total = 0
previous_comment_count = 0
no_new_comments_count = 0
global_followed_count = 0

# 实例化卡密管理器
li = LicenseManager()


class DyShareUtils:
    def __init__(self):
        self.scroll_count_total = 0
        self.previous_comment_count = 0
        self.no_new_comments_count = 0
        self.global_followed_count = 0
        self._url_list_index = 0
        self._url_list_lock = threading.Lock()
        self._stop_flag = threading.Event()

    # ----------------------------------------------------------------------
    # 工具函数
    # ----------------------------------------------------------------------

    def safe_check_license(self):
        """
        带有网络容错的卡密检查
        由于 LicenseManager 已经在后台处理了网络请求，
        这里主要负责检查状态标记。
        """
        try:
            li.check_license_validity()
            return True
        except LicenseException:
            # 如果是真正的卡密无效，直接抛出，中断程序
            raise
        except Exception as e:
            # 其他未知错误，记录日志但不中断
            log.warning(f"状态检查异常: {e}")
            return True

    def parse_search_keywords(self):
        raw = config.COMMENT_FILTER_KEYWORDS or []
        seps = [",", "，", " ", "\t", ";", "；"]
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
                    base = base.replace(sep, ",")
                kws = [x.strip() for x in base.split(",") if x.strip()]
            else:
                kws = [str(x).strip() for x in raw if str(x).strip()]
        return kws

    def parse_comment_replies(self):
        """解析评论回复内容列表，使用 & 作为分隔符"""
        raw = getattr(config, 'COMMENT_REPLIES', '') or ''
        if not raw:
            return []

        replies = []

        if isinstance(raw, str):
            s = raw.strip()
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    replies = [str(x).strip() for x in data if str(x).strip()]
                else:
                    replies = [s] if s else []
            except Exception:
                # 不是JSON，按 & 分隔符分割
                replies = [x.strip() for x in s.split("&") if x.strip()]
        elif isinstance(raw, list):
            replies = [str(x).strip() for x in raw if str(x).strip()]

        return replies if replies else []

    def parse_video_comments(self):
        """解析视频留言内容列表，使用 & 作为分隔符"""
        raw = getattr(config, 'VIDEO_COMMENTS', '') or ''
        if not raw:
            return []

        comments = []

        if isinstance(raw, str):
            s = raw.strip()
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    comments = [str(x).strip() for x in data if str(x).strip()]
                else:
                    comments = [s] if s else []
            except Exception:
                # 不是JSON，按 & 分隔符分割
                comments = [x.strip() for x in s.split("&") if x.strip()]
        elif isinstance(raw, list):
            comments = [str(x).strip() for x in raw if str(x).strip()]

        return comments if comments else []

    def normalize_text(self, t):
        try:
            s = str(t).lower()
            s = re.sub(r"\s+", " ", s).strip()
            return s
        except Exception:
            return str(t)

    def _extract_comment_text(self, element):
        selectors = [
            ".C7LroK_h span span span",
            '[data-e2e="comment-text"]',
            ".comment-text",
            "span",
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

    def output_json(self, code, msg="", data_type="", browser_id="", url_index=None, comment_reply=None, keywords=None):
        """
        输出JSON格式的操作结果

        Args:
            code: 0表示成功，-1表示找不到按钮等异常，1表示链接失效
            msg: 错误信息，只在错误时输出
            data_type: 操作类型 start|exit|like|follow|video|url_ok|url_fail
            browser_id: 浏览器ID
            url_index: URL在数据库中的索引（从0开始）
            comment_reply: 评论回复内容
            keywords: 关键词匹配信息
        """
        result = {"code": code, "data": {"type": data_type, "id": browser_id}}
        # 只在有错误信息时添加msg字段
        if msg:
            result["msg"] = msg

        # 如果提供了url_index，且不是关注操作，添加到结果中
        if url_index is not None and data_type != "follow":
            result["urlIndex"] = url_index

        # 如果提供了comment_reply，添加到data中
        if comment_reply is not None:
            result["data"]["comment_reply"] = comment_reply

        # 如果提供了keywords，添加到结果中
        if keywords is not None:
            result["keywords"] = keywords

        # 输出JSON并立即刷新，确保在打包环境中也能正常输出
        output = json.dumps(result, ensure_ascii=False)
        print(output)
        sys.stdout.flush()

    def get_driver(self, browser_id, browser_number=None):
        """
        创建并返回一个WebDriver实例
        替代原有的 BitBrowserManager.create_driver

        Args:
            browser_id (str): 浏览器ID
            browser_number (int): 浏览器编号，用于输出标识

        Returns:
            webdriver.Chrome: Chrome WebDriver实例
        """
        browser_info = self.get_browser_info(browser_number, browser_id)
        self.debug_log("info", "开始创建WebDriver实例", browser_number, browser_id)

        # 使用导入的API打开浏览器
        try:
            res = openBrowser(browser_id)
        except Exception as e:
            log.error(f"{browser_info} 调用openBrowser接口失败: {e}")
            return None

        if not res or "data" not in res:
            log.error(f"{browser_info} 无法打开浏览器")
            if res:
                log.error(f"{browser_info} 错误响应: {res}")
            return None

        driver_path = res["data"]["driver"]
        debugger_address = res["data"]["http"]
        self.debug_log(
            "info",
            f"驱动路径: {driver_path}, 调试地址: {debugger_address}",
            browser_number,
            browser_id,
        )

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
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-ipc-flooding-protection")

        self.debug_log("info", "Chrome选项已配置", browser_number, browser_id)

        # 检查driver_path是否存在
        try:
            chrome_service = Service(driver_path)
            self.debug_log("info", "Service创建成功", browser_number, browser_id)
        except Exception as e:
            log.error(f"{browser_info} 创建Service失败: {e}")
            return None

        self.debug_log("info", "准备创建WebDriver实例", browser_number, browser_id)
        try:
            driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
            self.debug_log("info", "WebDriver创建成功", browser_number, browser_id)
        except Exception as e:
            log.error(f"{browser_info} 创建WebDriver失败: {e}")
            import traceback
            log.error(f"{browser_info} 详细错误信息: {traceback.format_exc()}")
            return None

        # 等待浏览器完全启动并只保留一个窗口
        self.debug_log("debug", "等待浏览器完全启动...", browser_number, browser_id)
        self.human_like_delay(3, browser_number=browser_number)
        if len(driver.window_handles) > 1:
            # 关闭额外的窗口，只保留第一个窗口
            self.debug_log(
                "debug",
                "检测到多个窗口，关闭额外窗口...",
                browser_number,
                browser_id,
            )
            for handle in driver.window_handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
            self.debug_log(
                "debug", "已关闭额外窗口，保留主窗口", browser_number, browser_id
            )

        self.debug_log("info", "WebDriver创建成功", browser_number, browser_id)
        return driver

    def human_like_delay(self, min_delay=0.5, max_delay=2.0, browser_number=None):
        """
        模拟人类操作的随机延迟
        """
        delay = random.uniform(min_delay, max_delay)
        # self.debug_log("debug", f"等待 {delay:.2f} 秒模拟人类操作", browser_number)
        self.safe_sleep(delay, browser_number=browser_number)

    def open_comment_section(self, driver, wait_time=10, browser_number=None):
        """打开评论区"""
        browser_info = self.get_browser_info(browser_number)
        self.debug_log("info", "尝试打开评论区", browser_number)
        self.check_stop_signal()

        # 使用智能等待查找评论按钮
        wait = WebDriverWait(driver, wait_time)
        try:
            comment_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//*[contains(@class, "fN2jqmuV")]/div[2]')
                )
            )
        except:
            self.debug_log("warning", "评论区按钮未找到，尝试刷新页面...", browser_number)
            driver.refresh()
            # 等待页面刷新完成
            self.human_like_delay(5, 7, browser_number)
            # 再次尝试查找元素
            try:
                comment_button = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//*[contains(@class, "fN2jqmuV")]/div[2]')
                    )
                )
            except:
                self.debug_log(
                    "warning", "刷新后仍未找到评论按钮，跳过打开评论区操作", browser_number
                )
                return False

        # 模拟人类操作
        self.human_like_delay(0.5, 1.0, browser_number)

        comment_button.click()
        self.debug_log("info", "打开评论区成功", browser_number)
        return True

    def switch_to_new_tab(self, driver, url, wait_time=10, browser_number=None):
        """在新标签页中打开链接并切换到新标签页"""
        browser_info = self.get_browser_info(browser_number)
        self.debug_log("info", f"尝试在新标签页中打开链接: {url}", browser_number)
        self.check_stop_signal()

        # 保存当前窗口句柄
        current_window = driver.current_window_handle

        # 模拟人类在新标签页中打开链接
        self.human_like_delay(0.5, 1.5, browser_number)
        driver.execute_script(f"window.open('{url}','_blank');")

        # 等待新标签页打开
        wait = WebDriverWait(driver, wait_time)
        wait.until(lambda d: len(d.window_handles) > 1)

        # 获取所有窗口句柄
        all_windows = driver.window_handles

        # 切换到新打开的标签页（最后一个）
        driver.switch_to.window(all_windows[-1])

        # 模拟页面加载等待
        self.human_like_delay(2, 4, browser_number)

        # 关闭之前的标签页
        driver.switch_to.window(current_window)
        driver.close()

        # 切换回新标签页
        driver.switch_to.window(all_windows[-1])
        self.debug_log("info", f"成功切换到新标签页: {url}", browser_number)

    def extract_douyin_link(self, text):
        """从文本中提取抖音链接"""
        if isinstance(text, str):
            # 匹配抖音链接的正则表达式
            pattern = r"https?://v\.douyin\.com/[^\s]+"
            match = re.search(pattern, text)
            return match.group(0) if match else None
        return None

    def ensure_element_visible(self, driver, element, browser_number=None):
        """
        将指定元素滚动到屏幕中央，解决长评论遮挡问题
        """
        browser_info = self.get_browser_info(browser_number)
        try:
            # 使用 JS 将元素滚动到视口垂直居中位置 (block: 'center')
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center', inline: 'nearest'});",
                                  element)
            time.sleep(0.5)
            return True
        except Exception as e:
            log.warning(f"{browser_info} 元素滚动可见性处理失败: {e}")
            return False

    def visit_user_profile(self, driver, main_window, avatar_element, wait_time, browser_number, browser_id="",
                           profile_follow_probability=0.5, visit_min=2, visit_max=5):
        """
        专门处理进入用户主页的逻辑
        返回: bool (是否成功执行了关注操作)

        Args:
            visit_min: 进入主页后最小等待时间（秒）
            visit_max: 进入主页后最大等待时间（秒）
        """
        browser_info = self.get_browser_info(browser_number)
        handles_before = driver.window_handles

        try:
            # 点击头像
            driver.execute_script("arguments[0].click();", avatar_element)
            self.debug_log("info", "点击头像进入主页", browser_number)
        except Exception as e:
            log.error(f"{browser_info} 点击头像失败: {e}")
            return False

        # 等待新窗口出现
        new_window = None
        try:
            WebDriverWait(driver, wait_time).until(
                lambda d: len(d.window_handles) > len(handles_before)
            )
            # 获取新窗口句柄
            handles_after = driver.window_handles
            new_window = [h for h in handles_after if h not in handles_before][0]
            driver.switch_to.window(new_window)
        except Exception as e:
            log.warning(f"{browser_info} 切换到用户主页窗口失败: {e}")
            # 尝试切回主窗口
            driver.switch_to.window(main_window)
            return False

        # 在新窗口中的操作
        action_success = False
        try:
            # 进入主页后先等待（VISIT_MIN 到 VISIT_MAX 秒）
            visit_wait_time = random.uniform(visit_min, visit_max)
            self.debug_log("info", f"进入主页，等待 {visit_wait_time:.2f} 秒", browser_number)
            self.safe_sleep(visit_wait_time, browser_number=browser_number)

            # 等待结束后再根据概率判断是否关注
            if random.random() < profile_follow_probability:
                follow_btn_css = '#user_detail_element [data-e2e="user-info-follow-btn"]'
                try:
                    follow_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, follow_btn_css))
                    )
                    self.human_like_delay(0.5, 1.0, browser_number)
                    follow_button.click()
                    self.output_json(0, "", "follow", browser_id, "")  # 传递browser_id参数
                    self.debug_log("info", "关注成功", browser_number)
                    action_success = True
                    time.sleep(random.uniform(1, 2))
                except Exception:
                    # 没找到关注按钮或者已经关注了，不算严重错误
                    pass
            else:
                self.debug_log("info", f"根据概率设置 ({profile_follow_probability:.1%})，跳过关注操作", browser_number)

        except Exception as e:
            log.error(f"{browser_info} 主页操作异常: {e}")
        finally:
            # === 关键修正：无论如何都要关闭新窗口并切回 ===
            try:
                if new_window:
                    driver.close()
            except Exception:
                pass  # 窗口可能已经关了

            try:
                driver.switch_to.window(main_window)
            except Exception as e:
                # 如果切回主窗口失败，说明主窗口也崩了，抛出致命错误让外层重启浏览器
                log.error(f"{browser_info} 致命错误：无法切回主窗口")
                raise e

        return action_success

    def reply_to_comment(self, web_driver, target_comment, reply_text, browser_number=None, browser_id=""):
        """
        回复指定评论

        Args:
            web_driver: WebDriver实例
            target_comment: 目标评论元素
            reply_text: 回复内容
            browser_number: 浏览器编号
            browser_id: 浏览器ID

        Returns:
            bool: 是否成功回复
        """
        browser_info = self.get_browser_info(browser_number)
        try:
            # 查找评论的回复按钮
            reply_button = target_comment.find_element(
                By.CSS_SELECTOR,
                'div:nth-child(2) > div > div:nth-child(4) > div > div:nth-child(3) > div'
            )

            # 点击回复按钮
            web_driver.execute_script("arguments[0].click();", reply_button)
            time.sleep(0.5)  # 等待回复框出现

            # 输入回复文本
            ActionChains(web_driver).send_keys(reply_text).perform()
            time.sleep(0.5)

            # 尝试点击发送按钮
            try:
                send_button = web_driver.find_element(
                    By.CSS_SELECTOR,
                    '[data-e2e="comment-post"]'
                )
                web_driver.execute_script("arguments[0].click();", send_button)
                self.debug_log("info", f"成功回复评论: {reply_text[:20]}...", browser_number)
                time.sleep(1)  # 等待发送完成
                return True
            except:
                # 如果找不到发送按钮，尝试按回车键
                ActionChains(web_driver).send_keys(Keys.RETURN).perform()
                self.debug_log("info", f"通过回车键发送回复: {reply_text[:20]}...", browser_number)
                time.sleep(1)
                return True

        except Exception as e:
            log.warning(f"{browser_info} 回复评论失败: {e}")
            return False

    def leave_video_comment(self, driver, comment_text, browser_number=None, browser_id=""):
        """
        在当前视频页面留下评论

        Args:
            driver: WebDriver实例
            comment_text (str): 要发布的评论内容
            browser_number: 浏览器编号
            browser_id: 浏览器ID

        Returns:
            bool: 评论是否成功发布
        """
        browser_info = self.get_browser_info(browser_number, browser_id)
        try:
            # 查找评论输入框 (使用指定的class)
            comment_input = driver.find_element(
                By.CSS_SELECTOR,
                '.GXmFLge7.comment-input-inner-container'
            )

            # 点击评论输入框
            driver.execute_script("arguments[0].click();", comment_input)
            time.sleep(0.5)  # 等待回复框出现

            # 输入评论文本
            ActionChains(driver).send_keys(comment_text).perform()
            time.sleep(0.5)

            # 尝试点击发送按钮
            try:
                send_button = driver.find_element(
                    By.CSS_SELECTOR,
                    '[data-e2e="comment-post"]'
                )
                driver.execute_script("arguments[0].click();", send_button)
                self.debug_log("info", f"成功发布视频评论: {comment_text[:20]}...", browser_number)
                time.sleep(1)  # 等待发送完成
                return True
            except:
                # 如果找不到发送按钮，尝试按回车键
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                self.debug_log("info", f"通过回车键发送视频评论: {comment_text[:20]}...", browser_number)
                time.sleep(1)
                return True

        except Exception as e:
            log.warning(f"{browser_info} 发布视频评论失败: {e}")
            return False

    def process_comment(
            self,
            web_driver,
            main_window,
            comment_index,
            like_count,
            target_like_count,
            wait_time=10,
            like_probability=0.5,
            visit_profile_probability=0.3,
            profile_follow_probability=0.5,
            browser_number=None,
            browser_id="",
            enable_follow=True,
            enable_profile_visit=True,
            enable_like=True,
            enable_search_keywords=False,
            enable_comment_reply=False,
            comment_reply_probability=0.05,
            comment_wait_min=12,
            comment_wait_max=12,
            visit_min=2,
            visit_max=5,
    ):
        """重构后的评论处理函数"""
        browser_info = self.get_browser_info(browser_number)
        self.check_stop_signal()

        # 定位评论容器
        try:
            comments_container = WebDriverWait(web_driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="comment-list"]'))
            )
            comment_items = comments_container.find_elements(By.XPATH, "./div")
            if comment_index >= len(comment_items):
                return False, like_count
            target_comment = comment_items[comment_index]

            # =========================================================
            # 修改点：确保元素可见（解决长评论遮挡问题）
            # =========================================================
            self.ensure_element_visible(web_driver, target_comment, browser_number)

        except Exception as e:
            # 找不到评论不用报错，可能是到底了
            return False, like_count

        # 提取内容和关键词匹配逻辑 (保持不变)
        comment_text = self._extract_comment_text(target_comment)
        norm_comment = self.normalize_text(comment_text)
        keyword_matched = False
        SEARCH_KEYWORDS = self.parse_search_keywords()
        if enable_search_keywords and SEARCH_KEYWORDS:
            for kw in SEARCH_KEYWORDS:
                if self.normalize_text(kw) in norm_comment:
                    keyword_matched = True
                    break

        # 记录关键词日志
        if keyword_matched:
            try:
                snippet = comment_text[:100]
                self.output_json(0, "", "search_keywords", browser_id, keywords=f"关键词匹配: {snippet}")
            except:
                pass

        # 点赞逻辑：关键词命中后直接执行，否则按概率执行
        should_like = enable_like and (like_count < target_like_count) and (
                keyword_matched or (random.random() < like_probability))
        if should_like:
            try:
                like_button = target_comment.find_element(
                    By.XPATH, ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]"
                )
                self.human_like_delay(0.3, 0.8, browser_number)
                web_driver.execute_script("arguments[0].click();", like_button)  # 使用JS点击更稳定
                self.output_json(0, "", "like", browser_id)
                like_count += 1
                time.sleep(random.uniform(0.5, 1.5))
            except Exception:
                pass  # 点赞失败忽略

        # 关注/主页逻辑：关键词命中后直接执行，否则按概率执行
        # 如果关键词匹配，直接执行关注（不受 visit_profile_probability 影响）
        # 如果关键词匹配，关注操作总是执行（不受 profile_follow_probability 影响）
        should_visit = enable_follow and enable_profile_visit and (
                keyword_matched or (random.random() < visit_profile_probability))

        # 如果关键词匹配，强制关注（不受 profile_follow_probability 影响）
        force_follow = keyword_matched

        if should_visit:
            try:
                # 重新获取元素，防止DOM刷新导致StaleElementReferenceException
                comments_container = web_driver.find_element(By.CSS_SELECTOR, '[data-e2e="comment-list"]')
                target_comment_now = comments_container.find_elements(By.XPATH, "./div")[comment_index]

                # 尝试找头像
                avatar = None
                try:
                    avatar = target_comment_now.find_element(By.CSS_SELECTOR, ".comment-item-avatar a")
                except:
                    try:
                        avatar = target_comment_now.find_element(By.CSS_SELECTOR, ".comment-item-avatar")
                    except:
                        pass

                if avatar:
                    # 调用独立的窗口处理函数
                    # 如果关键词匹配，强制关注（传入 1.0 作为概率，确保总是关注）
                    follow_prob = 1.0 if force_follow else profile_follow_probability
                    is_followed = self.visit_user_profile(web_driver, main_window, avatar, wait_time, browser_number,
                                                          browser_id,
                                                          follow_prob, visit_min, visit_max)
                    if is_followed:
                        return "followed", like_count

            except Exception as e:
                # 捕获这里的异常，防止单条评论错误导致整个循环崩溃
                # 但是如果是 session invalid，外层会捕获
                msg = str(e)
                if "invalid session id" in msg or "disconnected" in msg:
                    raise e  # 抛出给外层处理
                log.warning(f"{browser_info} 访问主页过程中出错: {e}")
                # 确保在主窗口
                try:
                    if len(web_driver.window_handles) > 1 and web_driver.current_window_handle != main_window:
                        web_driver.switch_to.window(main_window)
                except:
                    pass

        # 评论回复逻辑：关键词命中后直接执行，否则按概率执行
        COMMENT_REPLIES = self.parse_comment_replies()
        should_reply = enable_comment_reply and COMMENT_REPLIES and (
                keyword_matched or (random.random() < comment_reply_probability))
        if should_reply:
            try:
                # 等待一段时间再回复
                wait_time_before_reply = random.uniform(comment_wait_min, comment_wait_max)
                self.safe_sleep(wait_time_before_reply, browser_number=browser_number)

                # 重新获取元素，防止DOM刷新导致StaleElementReferenceException
                comments_container = web_driver.find_element(By.CSS_SELECTOR, '[data-e2e="comment-list"]')
                target_comment_now = comments_container.find_elements(By.XPATH, "./div")[comment_index]

                # 从回复内容列表中随机选择一条回复
                reply_content = random.choice(COMMENT_REPLIES)

                # 执行回复
                reply_success = self.reply_to_comment(web_driver, target_comment_now, reply_content, browser_number,
                                                      browser_id)
                if reply_success:
                    # 修改输出格式
                    self.output_json(0, "", "comment", browser_id, comment_reply=reply_content)
                    self.debug_log("info", f"成功回复评论，内容: {reply_content[:30]}...", browser_number)
            except Exception as e:
                msg = str(e)
                if "invalid session id" in msg or "disconnected" in msg:
                    raise e  # 抛出给外层处理
                log.warning(f"{browser_info} 回复评论过程中出错: {e}")
                # 确保在主窗口
                try:
                    if len(web_driver.window_handles) > 1 and web_driver.current_window_handle != main_window:
                        web_driver.switch_to.window(main_window)
                except:
                    pass

        return True, like_count

    def run_automation(
            self,
            driver,
            url,
            wait_time=10,
            like_probability=0.5,
            visit_profile_probability=0.3,
            profile_follow_probability=0.5,
            min_follows_per_video=5,
            max_follows_per_video=15,
            min_likes_per_video=5,
            max_likes_per_video=15,
            browser_number=None,
            browser_id="",
            enable_follow=True,
            enable_profile_visit=True,
            enable_like=True,
            enable_search_keywords=False,
            enable_comment_reply=False,
            comment_reply_probability=0.05,
            comment_wait_min=12,
            comment_wait_max=12,
            visit_min=2,
            visit_max=5,
    ):
        """
        运行完整的自动化流程
        """
        browser_info = self.get_browser_info(browser_number)
        self.debug_log("info", f"开始运行自动化流程，访问网页: {url}", browser_number)
        self.check_stop_signal()

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
        if min_follows_per_video > max_follows_per_video:
            min_follows_per_video, max_follows_per_video = (
                max_follows_per_video,
                min_follows_per_video,
            )
        target_follow_count = random.randint(min_follows_per_video, max_follows_per_video)

        video_liked_count = 0
        if min_likes_per_video > max_likes_per_video:
            min_likes_per_video, max_likes_per_video = (
                max_likes_per_video,
                min_likes_per_video,
            )
        target_like_count = random.randint(min_likes_per_video, max_likes_per_video)
        self.debug_log(
            "info",
            f"本视频计划关注 {target_follow_count} 个用户，点赞 {target_like_count} 条评论",
            browser_number,
        )
        # 检查卡密是否仍然有效
        self.safe_check_license()

        try:
            self.debug_log("info", f"访问网页: {url}", browser_number)
            driver.get(url)

            wait = WebDriverWait(driver, wait_time)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            self.human_like_delay(3, 6, browser_number)
            self.human_like_delay(1, 2, browser_number)

            # 视频留言等待时间：在打开链接后、打开评论区前等待
            if config.ENABLE_VIDEO_COMMENT:
                wait_time_before_comment = random.uniform(
                    config.VIDEO_REPLY_WAIT_MIN,
                    config.VIDEO_REPLY_WAIT_MAX
                )
                self.debug_log("info", f"等待 {wait_time_before_comment:.2f} 秒后打开评论区", browser_number)
                self.safe_sleep(wait_time_before_comment, browser_number=browser_number)

            self.debug_log("info", "处理视频评论", browser_number)
            self.debug_log("info", "打开评论区", browser_number)

            # 修改此处：将打开评论区失败视为链接失效而非浏览器崩溃
            try:
                if not self.open_comment_section(driver, wait_time, browser_number):
                    self.debug_log("error", "无法打开评论区，链接可能失效", browser_number)
                    # 返回False表示链接失效，而不是抛出异常
                    return False
            except Exception as e:
                # 即使出现异常，我们也将其视为链接问题而非浏览器问题
                log.error(f"{browser_info} 打开评论区时发生异常: {e}")
                return False

            self.human_like_delay(1, 3, browser_number)

            # 视频留言逻辑：在打开评论区后，处理评论前进行留言
            VIDEO_COMMENTS = self.parse_video_comments()
            if config.ENABLE_VIDEO_COMMENT:
                # 根据概率判断是否留言
                video_reply_probability = config.VIDEO_REPLY_RATE / 100.0
                if random.random() < video_reply_probability:
                    # 从留言列表中随机选择一条
                    if VIDEO_COMMENTS:
                        comment_text = random.choice(VIDEO_COMMENTS)
                        self.debug_log("info", f"开始发布视频留言: {comment_text[:30]}...", browser_number)

                        # 执行留言
                        success = self.leave_video_comment(driver, comment_text, browser_number, browser_id)

                        if success:
                            # 根据DEBUG模式输出
                            if config.DEBUG:
                                self.debug_log("info", f"视频留言成功: {comment_text[:30]}...", browser_number)
                            else:
                                # 非DEBUG模式只输出JSON
                                self.output_json(0, "", "video_commit", browser_id)
                        else:
                            self.debug_log("warning", "视频留言失败", browser_number)
                    else:
                        self.debug_log("warning", "VIDEO_COMMENTS 列表为空，跳过视频留言", browser_number)
                else:
                    self.debug_log("info", f"根据概率设置 ({video_reply_probability:.1%})，跳过视频留言", browser_number)
            else:
                self.debug_log("info", "ENABLE_VIDEO_COMMENT 为 False，跳过视频留言", browser_number)

            main_window = driver.current_window_handle

            processed_comment_count = 0
            scroll_number = 0

            comment_index = 0

            # 初始化评论容器
            comments_container = None
            try:
                comments_container = WebDriverWait(driver, wait_time).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, '[data-e2e="comment-list"]')
                    )
                )
            except Exception as e:
                log.error(f"{browser_info} 无法定位评论容器: {e}")
                # 无法定位评论容器也视为链接问题
                return False

            while True:
                self.check_stop_signal()

                try:
                    self.safe_check_license()  # 使用新的安全检查

                    # =========================================================
                    # 修改点：动态检测是否需要滚动加载更多
                    # =========================================================
                    try:
                        current_items = comments_container.find_elements(By.XPATH, "./div")
                        # 如果当前索引接近底部（剩3条以内），则触发滚动加载
                        if comment_index >= len(current_items) - 3:
                            self.debug_log("info", "接近底部，执行滚动以加载更多评论...", browser_number)
                            scroll_number += 1
                            self.scroll_comments(driver, scroll_number, browser_number)

                            # 滚动后等待加载并重新定位容器
                            self.human_like_delay(2, 3, browser_number)
                            comments_container = WebDriverWait(driver, wait_time).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, '[data-e2e="comment-list"]')
                                )
                            )
                    except Exception as e:
                        pass  # 忽略检测错误，继续尝试处理

                    # 处理单条评论
                    result, video_liked_count = self.process_comment(
                        driver,
                        main_window,
                        comment_index,
                        video_liked_count,
                        target_like_count,
                        wait_time,
                        like_probability,
                        visit_profile_probability,
                        profile_follow_probability,
                        browser_number,
                        browser_id,
                        enable_follow,
                        enable_profile_visit,
                        enable_like,
                        enable_search_keywords,
                        enable_comment_reply,
                        comment_reply_probability,
                        comment_wait_min,
                        comment_wait_max,
                        visit_min,
                        visit_max,
                    )

                    # 如果返回 False，可能是到底了，或者出错
                    if result is False:
                        # 检查是否是真的到底了
                        try:
                            comment_items = comments_container.find_elements(By.XPATH, "./div")
                            if comment_index >= len(comment_items):
                                break
                        except:
                            break

                    processed_comment_count += 1

                    # 每30条评论检测一次是否还有更多评论
                    if processed_comment_count % 30 == 0:
                        try:
                            padding = driver.find_element(
                                By.CSS_SELECTOR, '[data-e2e="comment-list"] > div:last-child'
                            ).text
                            # 如果显示"暂时没有更多评论"就是到底了
                            if padding == "暂时没有更多评论":
                                self.debug_log(
                                    "info",
                                    "已滚动到底部或没有更多评论，结束当前链接操作",
                                    browser_number,
                                )
                                break
                        except Exception as e:
                            log.error(f"{browser_info} 无法检测评论区是否到底: {e}")
                            break

                    if result == "followed":
                        video_followed_count += 1
                        self.debug_log(
                            "info",
                            f"已成功关注用户，当前视频已关注 {video_followed_count} 个用户",
                            browser_number,
                        )

                    if (
                            video_followed_count >= target_follow_count
                            and video_liked_count >= target_like_count
                    ):
                        self.debug_log(
                            "info",
                            f"已达到目标关注数量 {target_follow_count} 和点赞数量 {target_like_count}，切换到下一个链接",
                            browser_number,
                        )
                        break

                    comment_index += 1

                    # 确保焦点在主窗口，避免后续操作出错
                    if driver.current_window_handle != main_window:
                        driver.switch_to.window(main_window)

                    self.human_like_delay(2, 5, browser_number)
                except LicenseException:
                    raise
                except Exception as e:
                    msg = str(e).lower()
                    # 遇到这些致命错误，直接返回False，触发外层的浏览器重启
                    # 浏览器崩溃的情况：会话失效、连接断开、窗口丢失等
                    if ("invalid session id" in msg or
                            "disconnected" in msg or
                            "not connected to devtools" in msg or
                            "no such window" in msg):
                        log.error(f"{self.get_browser_info(browser_number)} 致命错误: {e}")
                        return False

                    log.error(f"{self.get_browser_info(browser_number)} 处理评论异常: {e}")
                    comment_index += 1
                    try:
                        driver.switch_to.window(main_window)
                    except:
                        return False  # 切不回主窗口也视为致命错误
                    continue

            # 结束循环后确保切回主窗口
            try:
                driver.switch_to.window(main_window)
            except:
                pass

            self.debug_log("info", "所有评论处理完成", browser_number)
            return True

        except LicenseException:
            raise
        except Exception as e:
            log.error(f"{browser_info} 程序执行出错: {e}")
            # 如果是外部异常（不是循环内捕获的），返回False让上层决定是否重启
            return False

    def scroll_comments(self, driver, scroll_number=None, browser_number=None):
        """在打开评论区后执行滚动操作"""
        browser_info = self.get_browser_info(browser_number)
        # self.debug_log("debug", "执行评论区滚动操作", browser_number)

        try:
            body = driver.find_element(By.TAG_NAME, "body")
            scroll_origin = ScrollOrigin.from_element(body)
            ActionChains(driver).scroll_from_origin(scroll_origin, 0, 470).perform()
            if scroll_number is not None:
                self.debug_log(
                    "info", f"使用ActionChains完成滑动 (第 {scroll_number} 次)", browser_number
                )
            time.sleep(2)
        except Exception as e:
            log.error(f"{browser_info} 滚动失败: {e}")
        return False

    def init_database(self, db_path=LINKS_DB_PATH):
        """初始化数据库"""
        self.debug_log("info", "初始化数据库")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            )
        """)

        conn.commit()
        conn.close()

    def add_links_cli(self, db_path=LINKS_DB_PATH):
        """命令行接口：添加链接到数据库"""
        log.info(f"启动链接添加工具")
        self.init_database(db_path)

        print("链接添加工具")
        print("输入包含抖音链接的文本（每行一个），输入 'quit' 结束:")

        while True:
            try:
                text = input().strip()
                if text.lower() == "quit":
                    break
                if text:
                    self.add_link_to_db(text, db_path)
                else:
                    self.debug_log("info", "输入不能为空，请重新输入")
            except KeyboardInterrupt:
                log.info("用户中断链接添加工具\n已退出链接添加工具")
                break
            except EOFError:
                log.info("链接添加工具输入结束\n已退出链接添加工具")
                break

    def add_link_to_db(self, url, db_path=LINKS_DB_PATH):
        """向数据库添加链接"""
        log.debug(f"尝试添加链接到数据库: {url}")
        cleaned_url = self.extract_douyin_link(url)
        if not cleaned_url:
            log.warning(f"无效的抖音链接: {url}")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO links (url, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (cleaned_url, "pending", current_time, current_time),
            )
            conn.commit()
            log.info(f"链接已添加到数据库: {cleaned_url}")
        except sqlite3.IntegrityError:
            log.warning(f"链接已存在: {cleaned_url}")
        finally:
            conn.close()

    def check_stop_signal(self):
        """检查是否收到停止信号，如果收到则抛出异常"""
        if self._stop_flag.is_set():
            raise KeyboardInterrupt("收到全局停止信号")

    def get_browser_info(self, browser_number=None, browser_id_param=None):
        """格式化浏览器信息字符串"""
        if browser_number is not None:
            return f"浏览器 #{browser_number}"
        elif browser_id_param is not None:
            return f"浏览器 {browser_id_param}"
        else:
            return "浏览器"

    def debug_log(self, level, message, browser_number=None, browser_id_param=None):
        """条件DEBUG日志输出"""
        if config.DEBUG:
            browser_info = self.get_browser_info(browser_number, browser_id_param)
            if level == "info":
                log.info(f"{browser_info} {message}")
            elif level == "debug":
                log.debug(f"{browser_info} {message}")
            elif level == "warning":
                log.warning(f"{browser_info} {message}")
            elif level == "error":
                log.error(f"{browser_info} {message}")

    def safe_sleep(self, seconds, browser_number=None, check_interval=1.0):
        """安全的睡眠函数，会检查停止信号"""
        elapsed = 0
        while elapsed < seconds:
            self.check_stop_signal()
            wait_time = min(check_interval, seconds - elapsed)
            time.sleep(wait_time)
            elapsed += wait_time

    def force_close_browser(self, browser_id, browser_number=None):
        """
        强制关闭浏览器，通过API直接关闭

        Args:
            browser_id: 浏览器ID
            browser_number: 浏览器编号，用于日志输出
        """
        browser_info = self.get_browser_info(browser_number)
        try:
            closeBrowser(browser_id)
            self.debug_log("info", "已通过API强制关闭浏览器", browser_number)
        except Exception as e:
            log.error(f"{browser_info} 通过API强制关闭浏览器时出错: {e}")

    def reset_url_list_index(self):
        """重置URL列表索引"""
        with self._url_list_lock:
            self._url_list_index = 0

    def get_next_link_from_list(self, urls_list):
        """从URL列表获取下一个待处理的链接（线程安全）"""
        with self._url_list_lock:
            while self._url_list_index < len(urls_list):
                raw_url = urls_list[self._url_list_index]
                url_index = self._url_list_index

                url = self.extract_douyin_link(raw_url)
                if not url:
                    log.warning(f"索引 {url_index} 的URL清洗失败，已跳过: {raw_url}")
                    self._url_list_index += 1
                    continue

                self._url_list_index += 1

                if config.DEBUG:
                    log.info(f"从列表获取到待处理链接: {url}, 索引: {url_index}")
                return None, url, url_index

            return None, None, None

    def get_next_link(self, db_path=LINKS_DB_PATH):
        """从数据库或列表获取下一个待处理的链接"""
        if config.URLS and len(config.URLS) > 0:
            return self.get_next_link_from_list(config.URLS)
        else:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM links ORDER BY id")
            all_link_ids = [row[0] for row in cursor.fetchall()]

            cursor.execute("SELECT id, url FROM links WHERE status = 'pending' LIMIT 1")
            result = cursor.fetchone()

            if result:
                link_id, url = result
                url_index = all_link_ids.index(link_id) if link_id in all_link_ids else 0

                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "UPDATE links SET status = 'processing', updated_at = ? WHERE id = ?",
                    (current_time, link_id),
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

    def mark_link_as_completed(self, link_id, db_path=LINKS_DB_PATH):
        """标记链接为已完成"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE links SET status = 'completed', updated_at = ? WHERE id = ?",
            (current_time, link_id),
        )
        conn.commit()
        conn.close()

    def mark_link_as_failed(self, link_id, db_path=LINKS_DB_PATH):
        """标记链接为处理失败"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "UPDATE links SET status = 'failed', updated_at = ? WHERE id = ?",
            (current_time, link_id),
        )
        conn.commit()
        conn.close()

    def continuous_processing_loop(
            self,
            browser_id,
            wait_time,
            like_probability,
            visit_profile_probability,
            profile_follow_probability,
            min_follows_per_video,
            max_follows_per_video,
            min_likes_per_video,
            max_likes_per_video,
            browser_number,
            db_path=LINKS_DB_PATH,
    ):
        """持续处理循环 (优化版)"""
        browser_info = self.get_browser_info(browser_number)
        self.debug_log("info", "启动持续处理循环", browser_number)

        # 变量初始化
        enable_follow = config.ENABLE_FOLLOW
        enable_profile_visit = config.ENABLE_PROFILE_VISIT
        enable_like = config.ENABLE_LIKE
        enable_search_keywords = config.ENABLE_SEARCH_KEYWORDS
        enable_comment_reply = config.ENABLE_COMMENT_REPLY
        like_probability = like_probability / 100.0
        visit_profile_probability = visit_profile_probability / 100.0
        profile_follow_probability = profile_follow_probability / 100.0
        comment_reply_probability = config.COMMENT_REPLY_PROBABILITY / 100.0
        comment_wait_min = config.COMMENT_WAIT_MIN
        comment_wait_max = config.COMMENT_WAIT_MAX
        visit_min = config.VISIT_MIN
        visit_max = config.VISIT_MAX

        # 验证一次卡密
        self.safe_check_license()

        # 在循环开始前定义
        driver = None

        try:
            while True:
                # 1. 驱动检查与创建
                if driver is None:
                    # 树立项目规范，不主动关闭浏览器实例
                    # self.force_close_browser(browser_id, browser_number)
                    # time.sleep(3)  # 等待释放

                    self.debug_log("info", "正在创建新浏览器实例...", browser_number)
                    driver = self.get_driver(browser_id, browser_number)
                    if driver is None:
                        log.error(f"{self.get_browser_info(browser_number)} 创建失败，30秒后重试")
                        time.sleep(30)
                        continue

                # 2. 获取链接
                link_id, url, url_index = self.get_next_link(db_path)

                if url is None:
                    if config.URLS and len(config.URLS) > 0:
                        self.debug_log("info", "列表中的所有URL已处理完毕", browser_number)
                        break
                    else:
                        self.debug_log("info", "数据库中没有待处理的链接，等待30秒后重试...", browser_number)
                        self.safe_sleep(30, browser_number=browser_number)
                        continue

                self.debug_log("info", f"获取到新链接: {url}", browser_number)

                # 3. 执行任务
                retry_count = 0
                while retry_count < 3:
                    try:
                        # 每次执行前检查驱动是否存活
                        try:
                            _ = driver.window_handles
                        except:
                            raise Exception("disconnected: not connected to DevTools (Pre-check)")

                        success = self.run_automation(
                            driver, url, wait_time, like_probability, visit_profile_probability,
                            profile_follow_probability, min_follows_per_video, max_follows_per_video,
                            min_likes_per_video, max_likes_per_video, browser_number, browser_id,
                            enable_follow, enable_profile_visit, enable_like, enable_search_keywords,
                            enable_comment_reply, comment_reply_probability, comment_wait_min, comment_wait_max,
                            visit_min, visit_max
                        )

                        if success:
                            if link_id is not None:
                                self.mark_link_as_completed(link_id, db_path)
                            self.output_json(0, "", "url_ok", browser_id, url_index)
                            self.debug_log("info", f"链接处理成功: {url}", browser_number)
                            break  # 跳出重试循环
                        else:
                            # run_automation 返回 False 表示链接失效，不是浏览器崩溃
                            # 直接标记为失败并跳出重试循环
                            if link_id is not None:
                                self.mark_link_as_failed(link_id, db_path)
                            self.output_json(1, "链接失效", "url_fail", browser_id, url_index)
                            self.debug_log("error", f"{browser_info} 链接处理失败（链接失效）: {url}", browser_number)
                            break

                    except LicenseException:
                        raise  # 向上抛出退出
                    except Exception as e:
                        retry_count += 1
                        err_msg = str(e).lower()
                        log.error(f"{self.get_browser_info(browser_number)} 任务异常: {e}")

                        # 如果是致命错误，不要重试了，直接销毁driver，跳出重试循环，重新获取链接
                        # 浏览器崩溃的情况包括：连接断开、会话失效、浏览器死亡等
                        if "disconnected" in err_msg or "session" in err_msg or "died" in err_msg:
                            log.warning(f"{self.get_browser_info(browser_number)} 检测到浏览器崩溃，准备重启...")
                            try:
                                driver.quit()  # 尝试正常退出
                            except:
                                pass
                            driver = None  # 标记为None，下一次大循环会重建
                            break  # 跳出 retry loop，但因为 driver is None，大循环会重建浏览器

                        # 标记失败
                        if retry_count >= 3:
                            if link_id is not None:
                                self.mark_link_as_failed(link_id, db_path)
                            self.output_json(1, "链接失效或多次重试失败", "url_fail", browser_id, url_index)
                            self.debug_log("error", f"{browser_info} 链接处理彻底失败: {url}", browser_number)

                        time.sleep(5)

                # Sleep逻辑
                wait_time_between_links = random.uniform(5, 10)
                self.debug_log("info", f"等待 {wait_time_between_links:.2f} 秒后处理下一个链接...", browser_number)
                self.safe_sleep(wait_time_between_links, browser_number=browser_number)

        except KeyboardInterrupt:
            log.info(f"{browser_info} 收到停止信号，正在退出...")
            self.output_json(0, "", "exit", browser_id)
            return
        except Exception as e:
            log.error(f"{browser_info} 程序异常退出: {e}")
            self.output_json(0, "", "exit", browser_id)
            raise

    def print_config_debug(self):
        """打印所有配置参数，用于调试"""
        log.info("=" * 80)
        log.info("📋 配置参数调试信息 (DEBUG MODE)")
        log.info("=" * 80)

        # 定义需要忽略的方法和内部属性
        ignore_attrs = {
            "construct",
            "copy",
            "dict",
            "json",
            "from_orm",
            "model_computed_fields",
            "model_config",
            "model_construct",
            "model_copy",
            "model_dump",
            "model_dump_json",
            "model_extra",
            "model_fields",
            "model_fields_set",
            "model_json_schema",
            "model_dump_json",
            "model_parametrized_name",
            "model_post_init",
            "model_rebuild",
            "model_validate",
            "model_validate_json",
            "model_validate_strings",
            "model_validate_python",
            "parse_obj",
            "parse_raw",
            "parse_file",
            "parse_obj_or_dict",
            "schema",
            "schema_json",
            "update_forward_refs",
            "validate",
        }

        # 动态获取KuSettings的所有属性
        for attr_name in dir(config):
            # 跳过私有属性、方法和需要忽略的属性
            if not attr_name.startswith("_") and attr_name not in ignore_attrs:
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
                                f"  {attr_name}: 共 {len(attr_value)} 项 [{', '.join(map(str, attr_value[:3]))}, ...]"
                            )
                    else:
                        log.info(f"  {attr_name}: {attr_value}")
                except Exception as e:
                    log.info(f"  {attr_name}: 无法获取值 (错误: {e})")

        log.info("=" * 80)

    def set_keep_awake(self, enable=True):
        """
        设置Windows系统防休眠
        :param enable: True=开启(屏幕常亮), False=关闭(恢复默认)
        """
        if os.name != 'nt':
            return

        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002

            if enable:
                # 阻止系统休眠和屏幕关闭
                ctypes.windll.kernel32.SetThreadExecutionState(
                    ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
                )
                if config.DEBUG:
                    log.info("💻 Windows防休眠模式已启用 (屏幕常亮)")
            else:
                # 恢复系统默认状态
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
                if config.DEBUG:
                    log.info("💤 Windows防休眠模式已解除")
        except Exception as e:
            log.warning(f"设置防休眠模式失败: {e}")

    def main_database(self):
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
            self.print_config_debug()

        # 启动定期验证线程
        li.start_periodic_check()

        # ==========================
        # 新增: 开启防休眠
        # ==========================
        self.set_keep_awake(True)

        # 判断使用列表模式还是数据库模式
        use_list_mode = config.URLS and len(config.URLS) > 0

        if use_list_mode:
            cleaned_urls = []
            invalid_count = 0
            for url in config.URLS:
                cleaned_url = self.extract_douyin_link(url)
                if cleaned_url:
                    cleaned_urls.append(cleaned_url)
                else:
                    invalid_count += 1
                    if config.DEBUG:
                        log.warning(f"无效的抖音链接，已跳过: {url}")

            config.URLS = cleaned_urls
            if invalid_count > 0:
                if config.DEBUG:
                    log.warning(f"URLS列表中有 {invalid_count} 个无效链接已跳过")

            if config.DEBUG:
                log.info(f"使用列表模式，共 {len(config.URLS)} 个有效URL")
            self.reset_url_list_index()
        else:
            log.info("使用数据库模式")
            self.init_database()

        if not config.BIT_BROWSER_IDS:
            log.error("请在代码中的 BIT_BROWSER_IDS 列表中配置浏览器ID")
            return

        WAIT_TIME_USED = config.WAIT_TIME
        MAX_WORKERS_USED = len(config.BIT_BROWSER_IDS)
        LIKE_PROBABILITY_USED = config.LIKE_PROBABILITY
        VISIT_PROFILE_PROBABILITY_USED = config.VISIT_ENABLE
        PROFILE_FOLLOW_PROBABILITY_USED = config.PROFILE_FOLLOW_PROBABILITY
        MIN_FOLLOWS_PER_VIDEO_USED = config.MIN_FOLLOWS_PER_VIDEO
        MAX_FOLLOWS_PER_VIDEO_USED = config.MAX_FOLLOWS_PER_VIDEO
        MIN_LIKES_PER_VIDEO_USED = config.COMMENT_LIKE_COUNT_MIN
        MAX_LIKES_PER_VIDEO_USED = config.COMMENT_LIKE_COUNT_MAX

        # 输出版本信息
        version_info = {"code": 0, "data": {"type": "version", "version": f"pc.{config.VERSION}"}}
        output = json.dumps(version_info, ensure_ascii=False)
        log2.info(output)

        # 输出start事件，只输出一次，包含所有浏览器ID
        # 修改为只输出一次，包含所有浏览器ID，不包含urlIndex
        result = {"code": 0, "data": {"type": "start", "id": config.BIT_BROWSER_IDS}}
        output = json.dumps(result, ensure_ascii=False)
        log2.info(output)

        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_USED) as executor:
                futures = []
                for i in range(MAX_WORKERS_USED):
                    browser_id = config.BIT_BROWSER_IDS[i % len(config.BIT_BROWSER_IDS)]

                    future = executor.submit(
                        self.continuous_processing_loop,
                        browser_id,
                        WAIT_TIME_USED,
                        LIKE_PROBABILITY_USED,
                        VISIT_PROFILE_PROBABILITY_USED,
                        PROFILE_FOLLOW_PROBABILITY_USED,
                        MIN_FOLLOWS_PER_VIDEO_USED,
                        MAX_FOLLOWS_PER_VIDEO_USED,
                        MIN_LIKES_PER_VIDEO_USED,
                        MAX_LIKES_PER_VIDEO_USED,
                        i + 1,
                    )
                    futures.append(future)

                    if i < MAX_WORKERS_USED - 1:
                        time.sleep(2.5)

                while futures:
                    try:
                        done, not_done = concurrent.futures.wait(futures, timeout=1)
                        for future in done:
                            try:
                                future.result()
                            except LicenseException:
                                log.error("卡密验证失败，程序终止")
                                raise
                            except Exception as e:
                                log.error(f"线程执行出错: {e}")
                        futures = list(not_done)
                    except KeyboardInterrupt:
                        log.info("收到停止信号，正在关闭所有线程...")
                        self._stop_flag.set()
                        for future in futures:
                            future.cancel()
                        import sys
                        sys.exit(0)
        except LicenseException:
            log.error("卡密验证失败，程序终止")
            raise
        finally:
            # ==========================
            # 新增: 关闭防休眠
            # ==========================
            self.set_keep_awake(False)
            li.stop_periodic_check()

    def clear_database(self, db_path=LINKS_DB_PATH, status=None):
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

    def view_links_in_db(self, db_path=LINKS_DB_PATH):
        """查看数据库中的链接"""
        log.info("查看数据库中的链接")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # 查询所有链接
            cursor.execute(
                "SELECT id, url, status, created_at FROM links ORDER BY created_at"
            )
            links = cursor.fetchall()

            # 查询各种状态的链接数量
            cursor.execute("SELECT status, COUNT(*) FROM links GROUP BY status")
            status_counts = cursor.fetchall()
            status_dict = {status: count for status, count in status_counts}

            total_count = sum(status_dict.values())
            pending_count = status_dict.get("pending", 0)
            processing_count = status_dict.get("processing", 0)
            failed_count = status_dict.get("failed", 0)
            completed_count = status_dict.get("completed", 0)

            if not links:
                log.info("数据库中没有链接")
                return

            log.info(f"数据库中的链接 (共 {len(links)} 条)")
            print(f"数据库中的链接 (共 {len(links)} 条):")

            # 显示统计信息
            print(f"总链接数: {total_count}")
            print(
                f"待处理: {pending_count} | 处理中: {processing_count} | 失败: {failed_count} | 已完成: {completed_count}"
            )

            print("-" * 100)
            print(f"{'ID':<5} {'状态':<12} {'创建时间':<20} {'链接'}")
            print("-" * 100)

            for link in links:
                link_id, url, status, created_at = link
                # 截断长URL以提高可读性
                short_url = (url[:70] + "...") if len(url) > 73 else url
                print(f"{link_id:<5} {status:<12} {created_at:<20} {short_url}")

            # 显示进度条 (已完成+失败+处理中的链接都算作已处理)
            if total_count > 0:
                processed = completed_count + failed_count + processing_count
                progress = processed / total_count
                bar_length = 40
                filled_length = int(bar_length * progress)
                bar = "█" * filled_length + "-" * (bar_length - filled_length)
                print(f"完成进度: |{bar}| {progress:.1%} ({processed}/{total_count})")

        except Exception as e:
            log.error(f"查看链接时出错: {e}")
        finally:
            conn.close()

    def process_urls_thread(
            self,
            browser_id,
            urls,
            wait_time,
            like_probability,
            visit_profile_probability,
            profile_follow_probability,
            min_follows_per_video,
            max_follows_per_video,
            min_likes_per_video,
            max_likes_per_video,
            browser_number,
    ):
        """在线程中处理URL列表"""
        browser_info = self.get_browser_info(browser_number)
        log.info(f"{browser_info} 开始处理任务")

        driver = self.get_driver(browser_id, browser_number)

        if driver is None:
            log.error(f"{browser_info} 无法创建浏览器驱动")
            return

        try:
            self.process_urls(
                driver,
                urls,
                wait_time,
                like_probability,
                visit_profile_probability,
                profile_follow_probability,
                min_follows_per_video,
                max_follows_per_video,
                min_likes_per_video,
                max_likes_per_video,
                browser_number,
            )
        except Exception as e:
            log.error(f"{browser_info} 处理URL时发生异常: {e}")
        finally:
            # 等待并关闭浏览器
            self.human_like_delay(3, 5, browser_number)
            self.force_close_browser(browser_id, browser_number)
            log.info(f"{browser_info} 浏览器已关闭")

    def process_urls(
            self,
            driver,
            urls,
            wait_time=10,
            like_probability=0.5,
            visit_profile_probability=0.3,
            profile_follow_probability=0.5,
            min_follows_per_video=5,
            max_follows_per_video=15,
            min_likes_per_video=5,
            max_likes_per_video=15,
            browser_number=None,
            enable_profile_visit=True,
            enable_like=True,
            enable_search_keywords=False,
            enable_comment_reply=False,
            comment_reply_probability=0.05,
            comment_wait_min=12,
            comment_wait_max=12,
            visit_min=2,
            visit_max=5,
    ):
        """处理URL列表"""
        browser_info = self.get_browser_info(browser_number)
        log.info(f"{browser_info} 开始处理URL列表，共 {len(urls)} 个链接")
        for i, target_url in enumerate(urls):
            self.check_stop_signal()
            log.info(f"{browser_info} 处理第{i + 1}个链接: {target_url}")

            try:
                if i > 0:
                    self.switch_to_new_tab(driver, target_url, wait_time, browser_number)
                else:
                    driver.get(target_url)

                success = self.run_automation(
                    driver,
                    target_url,
                    wait_time,
                    like_probability,
                    visit_profile_probability,
                    profile_follow_probability,
                    min_follows_per_video,
                    max_follows_per_video,
                    min_likes_per_video,
                    max_likes_per_video,
                    browser_number,
                    "",
                    True,  # enable_follow
                    enable_profile_visit,
                    enable_like,
                    enable_search_keywords,
                    enable_comment_reply,
                    comment_reply_probability,
                    comment_wait_min,
                    comment_wait_max,
                    visit_min,
                    visit_max,
                )
                if not success:
                    log.error(f"{browser_info} 处理链接 {target_url} 失败")
            except Exception as e:
                log.error(f"{browser_info} 处理链接 {target_url} 时发生异常: {e}")

            self.human_like_delay(3, 7, browser_number)