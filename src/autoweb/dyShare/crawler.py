#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
dyShare 逻辑收口文件（减少文件数量）

合并来源：
- dyShare/base_crawler.py
- dyShare/utils.py
- dyShare/concrete_crawler.py
"""

from __future__ import annotations

# ----------------------------
# base_crawler.py
# ----------------------------
from abc import ABC, abstractmethod
import sys


class BaseDyShareCrawler(ABC):
    """抖音自动化抽象基类"""

    def __init__(self):
        self.config = None
        self.utils = None

    @abstractmethod
    def initialize_config(self) -> None:
        """初始化配置"""

    @abstractmethod
    def validate_license(self) -> bool:
        """验证卡密"""

    @abstractmethod
    def prepare_environment(self) -> None:
        """准备运行环境"""

    @abstractmethod
    def setup_database(self) -> None:
        """准备待处理链接（列表模式）"""

    @abstractmethod
    def output_version_info(self) -> None:
        """输出版本信息"""

    @abstractmethod
    def process_urls_with_thread_pool(self) -> None:
        """使用线程池处理URL"""

    @abstractmethod
    def cleanup_resources(self) -> None:
        """清理资源"""

    def execute_main_process(self) -> None:
        """模板方法：定义主流程"""
        try:
            self.initialize_config()

            if not self.validate_license():
                print("❌ 卡密验证失败！")
                return

            self.prepare_environment()
            self.setup_database()
            self.output_version_info()
            self.process_urls_with_thread_pool()

        except KeyboardInterrupt:
            print("程序已被用户中断")
            sys.exit(0)
        except Exception as e:
            print(f"程序执行出错: {e}")
            sys.exit(1)
        finally:
            self.cleanup_resources()


# ----------------------------
# utils.py（原样合并，修正 config 初始化顺序）
# ----------------------------
import json
import os
import random
import re
import threading
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..tools import log
from ..tools.config import EnvSettings, get_config, env
from ..tools.core import closeBrowser, openBrowser
from ..tools.douyin_common import (
    DouyinBrowserActions,
    DouyinCommentActions,
    DouyinConfigParser,
    parse_comment_dt,
    within_threshold,
)
from ..tools.license import LicenseException, LicenseManager

# 全局配置与卡密管理器（确保先 get_config 再使用字段）
config: EnvSettings = get_config()  # type: ignore
li = LicenseManager()


class DyShareUtils:
    def __init__(self):
        self.scroll_count_total = 0
        self.previous_comment_count = 0
        self.no_new_comments_count = 0
        self.global_followed_count = 0
        self.global_liked_count = 0
        self.global_comment_reply_count = 0
        self.global_url_opened_count = 0
        self.global_video_comment_count = 0
        self._url_list_index = 0
        self._url_list_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._stop_flag = threading.Event()
        self._browser_start_indices = {}

    def safe_check_license(self):
        try:
            li.check_license_validity()
            return True
        except LicenseException:
            raise
        except Exception as e:
            log.warning(f"状态检查异常: {e}")
            return True

    def parse_search_keywords(self):
        raw = config.COMMENT_FILTER_KEYWORDS or []
        return DouyinConfigParser.parse_keywords(raw)

    def parse_comment_replies(self):
        raw = getattr(config, "COMMENT_REPLIES", "") or ""
        return DouyinConfigParser.parse_comment_replies(raw)

    def parse_video_comments(self):
        raw = getattr(config, "VIDEO_COMMENTS", "") or ""
        return DouyinConfigParser.parse_video_comments(raw)

    def normalize_text(self, t):
        return DouyinConfigParser.normalize_text(t)

    def _extract_comment_text(self, element):
        return DouyinCommentActions.extract_comment_text(element)

    def output_json(
        self,
        code,
        msg="",
        data_type="",
        browser_id="",
        url_index=None,
        comment_reply=None,
        keywords=None,
        count=None,
    ):
        result = {"code": code, "data": {"type": data_type, "id": browser_id}}
        if msg:
            result["msg"] = msg
        if url_index is not None and data_type != "follow":
            result["urlIndex"] = url_index
        if comment_reply is not None:
            result["data"]["comment_reply"] = comment_reply
        if keywords is not None:
            result["keywords"] = keywords
        if count is not None:
            result["count"] = count
        output = json.dumps(result, ensure_ascii=False)
        print(output)
        sys.stdout.flush()

    def get_driver(self, browser_id, browser_number=None):
        browser_info = self.get_browser_info(browser_number, browser_id)
        self.debug_log("info", "开始创建WebDriver实例", browser_number, browser_id)
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

        if not driver_path:
            log.error(f"{browser_info} 驱动路径为空")
            return None
        if not debugger_address:
            log.error(f"{browser_info} 调试地址为空")
            return None

        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", debugger_address)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-ipc-flooding-protection")

        self.debug_log("info", "Chrome选项已配置", browser_number, browser_id)

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

        self.debug_log("debug", "等待浏览器完全启动...", browser_number, browser_id)
        self.human_like_delay(3, browser_number=browser_number)
        if len(driver.window_handles) > 1:
            self.debug_log(
                "debug", "检测到多个窗口，关闭额外窗口...", browser_number, browser_id
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
        delay = random.uniform(min_delay, max_delay)
        self.safe_sleep(delay, browser_number=browser_number)

    def open_comment_section(self, driver, wait_time=10, browser_number=None):
        self.debug_log("info", "尝试打开评论区", browser_number)
        self.check_stop_signal()
        try:
            _ = driver.find_element(By.CSS_SELECTOR, '[data-e2e="comment-list"]')
            self.debug_log("info", "评论区已打开", browser_number)
            return True
        except Exception:
            pass
        wait = WebDriverWait(driver, wait_time)
        try:
            comment_button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//*[contains(@class, "fN2jqmuV")]/div[2]')
                )
            )
            self.human_like_delay(0.5, 1.0, browser_number)
            comment_button.click()
            self.debug_log("info", "打开评论区成功", browser_number)
            return True
        except Exception:
            try:
                alt_btn = wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, '[data-e2e="feed-comment-icon"]')
                    )
                )
                self.human_like_delay(0.5, 1.0, browser_number)
                alt_btn.click()
                self.debug_log("info", "打开评论区成功(搜索页入口)", browser_number)
                return True
            except Exception:
                self.debug_log("warning", "评论区按钮未找到", browser_number)
                return False

    def switch_to_new_tab(self, driver, url, wait_time=10, browser_number=None):
        self.debug_log("info", f"尝试在新标签页中打开链接: {url}", browser_number)
        self.check_stop_signal()

        current_window = driver.current_window_handle
        self.human_like_delay(0.5, 1.5, browser_number)
        driver.execute_script(f"window.open('{url}','_blank');")

        wait = WebDriverWait(driver, wait_time)
        wait.until(lambda d: len(d.window_handles) > 1)

        all_windows = driver.window_handles
        driver.switch_to.window(all_windows[-1])
        self.human_like_delay(2, 4, browser_number)

        driver.switch_to.window(current_window)
        driver.close()
        driver.switch_to.window(all_windows[-1])
        self.debug_log("info", f"成功切换到新标签页: {url}", browser_number)

    def extract_douyin_link(self, text):
        if isinstance(text, str):
            pattern = r"https?://v\.douyin\.com/[^\s]+"
            match = re.search(pattern, text)
            return match.group(0) if match else None
        return None

    def ensure_element_visible(self, driver, element, browser_number=None):
        browser_info = self.get_browser_info(browser_number)
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'auto', block: 'center', inline: 'nearest'});",
                element,
            )
            time.sleep(0.5)
            return True
        except Exception as e:
            log.warning(f"{browser_info} 元素滚动可见性处理失败: {e}")
            return False

    def visit_user_profile(
        self,
        driver,
        main_window,
        avatar_element,
        wait_time,
        browser_number,
        browser_id="",
        profile_follow_probability=0.5,
        visit_min=2,
        visit_max=5,
        reporter=None,
        force_dm=False,
    ):
        handles_before = driver.window_handles
        browser_info = self.get_browser_info(browser_number)

        try:
            self.check_stop_signal()
            driver.execute_script("arguments[0].click();", avatar_element)
            self.debug_log("info", "点击头像进入主页", browser_number)
        except Exception as e:
            log.error(f"{browser_info} 点击头像失败: {e}")
            return False

        new_window = None
        try:
            WebDriverWait(driver, wait_time).until(
                lambda d: len(d.window_handles) > len(handles_before)
            )
            handles_after = driver.window_handles
            new_window = [h for h in handles_after if h not in handles_before][0]
            driver.switch_to.window(new_window)
        except Exception as e:
            log.warning(f"{browser_info} 切换到用户主页窗口失败: {e}")
            driver.switch_to.window(main_window)
            return False

        action_success = False
        try:
            self.check_stop_signal()
            visit_wait_time = random.uniform(visit_min, visit_max)
            self.debug_log(
                "info", f"进入主页，等待 {visit_wait_time:.2f} 秒", browser_number
            )
            self.safe_sleep(visit_wait_time, browser_number=browser_number)

            if random.random() < profile_follow_probability:
                follow_btn_css = (
                    '#user_detail_element [data-e2e="user-info-follow-btn"]'
                )
                try:
                    follow_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, follow_btn_css))
                    )

                    # 检查关注按钮状态，避免重复关注
                    try:
                        button_text = follow_button.text.strip()
                        if "已关注" in button_text:
                            self.debug_log(
                                "info", "用户已被关注，跳过关注操作", browser_number
                            )
                        else:
                            self.human_like_delay(0.5, 1.0, browser_number)
                            follow_button.click()
                            if reporter:
                                reporter.set_action("follow")
                            if reporter:
                                reporter.increment_follow()
                            self.debug_log("info", "关注成功", browser_number)
                            action_success = True
                            time.sleep(random.uniform(1, 2))
                    except Exception:
                        # 无法获取按钮文本，输出该用户不存在
                        self.debug_log("warning", "该用户不存在", browser_number)

                except Exception:
                    # 按钮不存在或其他异常，输出该用户不存在
                    self.debug_log("warning", "该用户不存在", browser_number)
            else:
                self.debug_log(
                    "info",
                    f"根据概率设置 ({profile_follow_probability:.1%})，跳过关注操作",
                    browser_number,
                )
            try:
                if getattr(config, "ENABLE_DM", True):
                    dm_list = DouyinConfigParser.parse_dm_messages(
                        getattr(config, "DM_MESSAGES", "") or ""
                    )
                    if not dm_list:
                        self.debug_log(
                            "warning", "DM_MESSAGES 列表为空，跳过私信", browser_number
                        )
                    else:
                        if force_dm:
                            dm_text = random.choice(dm_list)
                            ok = self.send_direct_message(
                                driver,
                                dm_text,
                                getattr(config, "DM_WAIT_MIN", 5),
                                getattr(config, "DM_WAIT_MAX", 12),
                                browser_number,
                            )
                            if ok and reporter:
                                reporter.set_action("dm")
                                reporter.increment_dm(1)
                                self.debug_log("info", "私信发送成功", browser_number)
                        else:
                            dm_prob = (
                                float(getattr(config, "DM_PROBABILITY", 0)) / 100.0
                            )
                            if random.random() < dm_prob:
                                dm_text = random.choice(dm_list)
                                ok = self.send_direct_message(
                                    driver,
                                    dm_text,
                                    getattr(config, "DM_WAIT_MIN", 5),
                                    getattr(config, "DM_WAIT_MAX", 12),
                                    browser_number,
                                )
                                if ok and reporter:
                                    reporter.set_action("dm")
                                    reporter.increment_dm(1)
                                    self.debug_log(
                                        "info", "私信发送成功", browser_number
                                    )
                            else:
                                self.debug_log(
                                    "info",
                                    f"根据概率设置 ({dm_prob:.1%})，跳过私信",
                                    browser_number,
                                )
            except Exception as e:
                log.warning(f"{browser_info} 执行私信逻辑时出错: {e}")
        except Exception as e:
            log.error(f"{browser_info} 主页操作异常: {e}")
        finally:
            try:
                if new_window:
                    driver.close()
            except Exception:
                pass
            try:
                driver.switch_to.window(main_window)
            except Exception as e:
                log.error(f"{browser_info} 致命错误：无法切回主窗口")
                raise e

        return action_success

    def reply_to_comment(
        self, web_driver, target_comment, reply_text, browser_number=None, browser_id=""
    ):
        return DouyinCommentActions.reply_to_comment_sync(
            web_driver,
            target_comment,
            reply_text,
            browser_number=browser_number,
            browser_id=browser_id,
            debug_log_func=self.debug_log,
            check_stop_func=self.check_stop_signal,
        )

    def leave_video_comment(
        self, driver, comment_text, browser_number=None, browser_id=""
    ):
        return DouyinCommentActions.leave_video_comment_sync(
            driver,
            comment_text,
            browser_number=browser_number,
            browser_id=browser_id,
            debug_log_func=self.debug_log,
            check_stop_func=self.check_stop_signal,
        )

    def send_direct_message(
        self, driver, message_text, wait_min=5, wait_max=12, browser_number=None
    ):
        browser_info = self.get_browser_info(browser_number)
        try:
            self.check_stop_signal()
            try:
                btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".K8kpIsJm"))
                )
            except Exception:
                try:
                    btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "//button[contains(., '私信')]")
                        )
                    )
                except Exception:
                    try:
                        btn = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable(
                                (By.XPATH, "//div[contains(@class,'K8kpIsJm')]")
                            )
                        )
                    except Exception:
                        self.debug_log("warning", "未找到私信按钮", browser_number)
                        return False
            self.human_like_delay(0.5, 1.0, browser_number)
            driver.execute_script("arguments[0].click();", btn)
            self.debug_log("info", "已点击私信按钮", browser_number)
            self.human_like_delay(0.5, 1.5, browser_number)

            try:
                editor = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'div[contenteditable="true"]')
                    )
                )
            except Exception:
                try:
                    editor = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located(
                            (
                                By.CSS_SELECTOR,
                                ".public-DraftStyleDefault-block, .dn-DraftEditor-content",
                            )
                        )
                    )
                except Exception:
                    self.debug_log("warning", "未找到聊天输入框", browser_number)
                    return False

            try:
                driver.execute_script("arguments[0].click();", editor)
            except Exception:
                pass
            ActionChains(driver).send_keys(message_text).perform()
            self.debug_log(
                "info", f"输入私信内容: {message_text[:30]}...", browser_number
            )
            self.human_like_delay(0.3, 0.8, browser_number)

            sent = False
            try:
                send_btn = driver.find_element(
                    By.CSS_SELECTOR, '[class*="send-msg-btn"]'
                )
                try:
                    DouyinBrowserActions.ensure_element_centered(
                        driver, send_btn, sleep=self.safe_sleep
                    )
                except Exception:
                    pass
                driver.execute_script("arguments[0].click();", send_btn)
                sent = True
                self.debug_log("info", "已点击发送按钮", browser_number)
            except Exception:
                try:
                    send_btn = driver.find_element(
                        By.CSS_SELECTOR, '[data-e2e*="send"]'
                    )
                    driver.execute_script("arguments[0].click();", send_btn)
                    sent = True
                    self.debug_log("info", "已点击备用发送按钮", browser_number)
                except Exception:
                    pass

            if not sent:
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                sent = True
                self.debug_log("info", "通过回车发送私信", browser_number)

            wait_sec = random.uniform(wait_min, wait_max)
            self.safe_sleep(wait_sec, browser_number=browser_number)
            return True
        except Exception as e:
            msg = str(e).lower()
            if (
                "invalid session id" in msg
                or "disconnected" in msg
                or "not connected to devtools" in msg
            ):
                log.error(f"{browser_info} 私信流程致命错误: {e}")
                return False
            log.warning(f"{browser_info} 私信流程异常: {e}")
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
        comment_wait_min=7,
        comment_wait_max=12,
        visit_min=2,
        visit_max=5,
        reporter=None,
    ):
        """重构后的评论处理函数"""
        browser_info = self.get_browser_info(browser_number)
        self.check_stop_signal()

        try:
            comments_container = WebDriverWait(web_driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, '[data-e2e="comment-list"]')
                )
            )
            comment_items = comments_container.find_elements(By.XPATH, "./div")
            if comment_index >= len(comment_items):
                return False, like_count, 0
            target_comment = comment_items[comment_index]
            self.ensure_element_visible(web_driver, target_comment, browser_number)
        except Exception:
            return False, like_count, 0

        threshold_enabled = getattr(config, "COMMENT_THRESHOLD_ENABLE", False)
        time_matched = False
        try:
            dt = parse_comment_dt(target_comment)
            if within_threshold(dt):
                time_matched = True
            else:
                if threshold_enabled and config.DEBUG:
                    self.debug_log(
                        "info",
                        f"评论时间未命中阈值，跳过当前评论: dt={dt}, threshold={getattr(config, 'COMMENT_THRESHOLD', None)}",
                        browser_number,
                    )
                if threshold_enabled:
                    return False, like_count, 0
        except Exception:
            if threshold_enabled:
                if config.DEBUG:
                    self.debug_log(
                        "warning", "评论时间解析失败，跳过当前评论", browser_number
                    )
                return False, like_count, 0

        comment_text = self._extract_comment_text(target_comment)
        norm_comment = self.normalize_text(comment_text)
        keyword_matched = False
        SEARCH_KEYWORDS = self.parse_search_keywords()
        if enable_search_keywords and SEARCH_KEYWORDS:
            for kw in SEARCH_KEYWORDS:
                if self.normalize_text(kw) in norm_comment:
                    keyword_matched = True
                    break

        if keyword_matched and config.DEBUG:
            try:
                snippet = comment_text[:100]
                self.debug_log("info", f"关键词匹配: {snippet}", browser_number)
            except Exception:
                pass

        if threshold_enabled and time_matched:
            should_like = enable_like and (like_count < target_like_count)
        else:
            should_like = (
                enable_like
                and (like_count < target_like_count)
                and (keyword_matched or (random.random() < like_probability))
            )
        if should_like:
            try:
                like_button = target_comment.find_element(
                    By.XPATH,
                    ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]",
                )
                self.human_like_delay(0.3, 0.8, browser_number)
                web_driver.execute_script("arguments[0].click();", like_button)
                if reporter:
                    reporter.set_action("like")
                    if reporter:
                        reporter.increment_like()
                like_count += 1
                time.sleep(random.uniform(0.5, 1.5))
            except Exception:
                pass

        if threshold_enabled and time_matched:
            should_visit = enable_follow and enable_profile_visit
            force_follow = True
        else:
            should_visit = (
                enable_follow
                and enable_profile_visit
                and (keyword_matched or (random.random() < visit_profile_probability))
            )
            force_follow = keyword_matched

        if should_visit:
            try:
                comments_container = web_driver.find_element(
                    By.CSS_SELECTOR, '[data-e2e="comment-list"]'
                )
                target_comment_now = comments_container.find_elements(
                    By.XPATH, "./div"
                )[comment_index]

                avatar = None
                try:
                    avatar = target_comment_now.find_element(
                        By.CSS_SELECTOR, ".comment-item-avatar a"
                    )
                except Exception:
                    try:
                        avatar = target_comment_now.find_element(
                            By.CSS_SELECTOR, ".comment-item-avatar"
                        )
                    except Exception:
                        pass

                if avatar:
                    follow_prob = 1.0 if force_follow else profile_follow_probability
                    is_followed = self.visit_user_profile(
                        web_driver,
                        main_window,
                        avatar,
                        wait_time,
                        browser_number,
                        browser_id,
                        follow_prob,
                        visit_min,
                        visit_max,
                        reporter,
                        force_dm=bool(threshold_enabled and time_matched),
                    )
                    if is_followed:
                        return "followed", like_count, 0

            except Exception as e:
                msg = str(e)
                if "invalid session id" in msg or "disconnected" in msg:
                    raise e
                log.warning(f"{browser_info} 访问主页过程中出错: {e}")
                try:
                    if (
                        len(web_driver.window_handles) > 1
                        and web_driver.current_window_handle != main_window
                    ):
                        web_driver.switch_to.window(main_window)
                except Exception:
                    pass

        reply_count = 0
        COMMENT_REPLIES = self.parse_comment_replies()
        if threshold_enabled and time_matched:
            should_reply = enable_comment_reply and COMMENT_REPLIES
        else:
            should_reply = (
                enable_comment_reply
                and COMMENT_REPLIES
                and (keyword_matched or (random.random() < comment_reply_probability))
            )
        if should_reply:
            try:
                wait_time_before_reply = random.uniform(
                    comment_wait_min, comment_wait_max
                )
                self.safe_sleep(wait_time_before_reply, browser_number=browser_number)

                comments_container = web_driver.find_element(
                    By.CSS_SELECTOR, '[data-e2e="comment-list"]'
                )
                target_comment_now = comments_container.find_elements(
                    By.XPATH, "./div"
                )[comment_index]

                reply_content = random.choice(COMMENT_REPLIES)
                reply_success = self.reply_to_comment(
                    web_driver,
                    target_comment_now,
                    reply_content,
                    browser_number,
                    browser_id,
                )
                if reply_success:
                    if reporter:
                        reporter.set_action("comment")
                    if reporter:
                        reporter.increment_comment()
                    self.debug_log(
                        "info",
                        f"成功回复评论，内容: {reply_content[:30]}...",
                        browser_number,
                    )
                    reply_count = 1
            except Exception as e:
                msg = str(e)
                if "invalid session id" in msg or "disconnected" in msg:
                    raise e
                log.warning(f"{browser_info} 回复评论过程中出错: {e}")
                try:
                    if (
                        len(web_driver.window_handles) > 1
                        and web_driver.current_window_handle != main_window
                    ):
                        web_driver.switch_to.window(main_window)
                except Exception:
                    pass

        return True, like_count, reply_count

    def run_automation(
        self,
        driver,
        url,
        wait_time,
        like_probability,
        visit_profile_probability,
        profile_follow_probability,
        min_follows_per_video,
        max_follows_per_video,
        min_likes_per_video,
        max_likes_per_video,
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
        navigate=True,
        url_index=None,
        reporter=None,
    ):
        browser_info = self.get_browser_info(browser_number)
        self.debug_log("info", f"开始运行自动化流程，访问网页: {url}", browser_number)

        try:
            self.check_stop_signal()
        except KeyboardInterrupt:
            self.debug_log("info", "收到停止信号，退出自动化流程", browser_number)
            raise

        try:
            self.check_stop_signal()
            driver.current_url
        except KeyboardInterrupt:
            raise
        except Exception as e:
            if "invalid session id" in str(e):
                log.error(f"{browser_info} 浏览器会话已失效: {e}")
                return False
            raise e

        video_followed_count = 0
        if min_follows_per_video > max_follows_per_video:
            min_follows_per_video, max_follows_per_video = (
                max_follows_per_video,
                min_follows_per_video,
            )
        target_follow_count = random.randint(
            min_follows_per_video, max_follows_per_video
        )

        video_liked_count = 0
        if min_likes_per_video > max_likes_per_video:
            min_likes_per_video, max_likes_per_video = (
                max_likes_per_video,
                min_likes_per_video,
            )
        target_like_count = random.randint(min_likes_per_video, max_likes_per_video)

        video_comment_reply_count = 0
        video_comment_count = 0
        self.debug_log(
            "info",
            f"本视频计划关注 {target_follow_count} 个用户，点赞 {target_like_count} 条评论",
            browser_number,
        )

        self.safe_check_license()

        try:
            self.check_stop_signal()
            if navigate:
                self.debug_log("info", f"访问网页: {url}", browser_number)
                try:
                    driver.set_page_load_timeout(wait_time)
                except Exception:
                    pass
                driver.get(url)
                self.check_stop_signal()
                wait = WebDriverWait(driver, wait_time)
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                self.human_like_delay(3, 6, browser_number)
                self.human_like_delay(1, 2, browser_number)

            if config.ENABLE_VIDEO_COMMENT:
                wait_time_before_comment = random.uniform(
                    config.VIDEO_REPLY_WAIT_MIN, config.VIDEO_REPLY_WAIT_MAX
                )
                self.debug_log(
                    "info",
                    f"等待 {wait_time_before_comment:.2f} 秒后打开评论区",
                    browser_number,
                )
                self.safe_sleep(wait_time_before_comment, browser_number=browser_number)

            self.debug_log("info", "处理视频评论", browser_number)
            self.debug_log("info", "打开评论区", browser_number)

            try:
                if not self.open_comment_section(driver, wait_time, browser_number):
                    self.debug_log(
                        "error", "无法打开评论区，链接可能失效", browser_number
                    )
                    return False
            except Exception as e:
                log.error(f"{browser_info} 打开评论区时发生异常: {e}")
                return False

            self.human_like_delay(1, 3, browser_number)

            VIDEO_COMMENTS = self.parse_video_comments()
            if config.ENABLE_VIDEO_COMMENT:
                video_reply_probability = config.VIDEO_REPLY_RATE / 100.0
                if random.random() < video_reply_probability:
                    if VIDEO_COMMENTS:
                        comment_text = random.choice(VIDEO_COMMENTS)
                        self.debug_log(
                            "info",
                            f"开始发布视频留言: {comment_text[:30]}...",
                            browser_number,
                        )
                        success = self.leave_video_comment(
                            driver, comment_text, browser_number, browser_id
                        )
                        if success:
                            video_comment_count += 1
                            if reporter:
                                reporter.set_action("videoComment")
                            if reporter:
                                reporter.increment_video_comment()
                            self.debug_log(
                                "info",
                                f"视频留言成功: {comment_text[:30]}...",
                                browser_number,
                            )
                        else:
                            self.debug_log("warning", "视频留言失败", browser_number)
                    else:
                        self.debug_log(
                            "warning",
                            "VIDEO_COMMENTS 列表为空，跳过视频留言",
                            browser_number,
                        )
                else:
                    self.debug_log(
                        "info",
                        f"根据概率设置 ({video_reply_probability:.1%})，跳过视频留言",
                        browser_number,
                    )
            else:
                self.debug_log(
                    "info",
                    "ENABLE_VIDEO_COMMENT 为 False，跳过视频留言",
                    browser_number,
                )

            main_window = driver.current_window_handle

            processed_comment_count = 0
            scroll_number = 0
            comment_index = 0

            try:
                comments_container = WebDriverWait(driver, wait_time).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, '[data-e2e="comment-list"]')
                    )
                )
            except Exception as e:
                log.error(f"{browser_info} 无法定位评论容器: {e}")
                return False

            while True:
                self.check_stop_signal()
                try:
                    self.safe_check_license()

                    try:
                        current_items = comments_container.find_elements(
                            By.XPATH, "./div"
                        )
                        if comment_index >= len(current_items) - 3:
                            self.debug_log(
                                "info",
                                "接近底部，执行滚动以加载更多评论...",
                                browser_number,
                            )
                            scroll_number += 1
                            self.scroll_comments(driver, scroll_number, browser_number)
                            self.human_like_delay(2, 3, browser_number)
                            try:
                                if (
                                    getattr(config, "COMMENT_THRESHOLD_ENABLE", False)
                                    and scroll_number >= 20
                                ):
                                    self.debug_log(
                                        "info",
                                        "评论区滚动已达上限（20次），切换到下一个链接",
                                        browser_number,
                                    )
                                    break
                            except Exception:
                                pass
                            comments_container = WebDriverWait(driver, wait_time).until(
                                EC.presence_of_element_located(
                                    (By.CSS_SELECTOR, '[data-e2e="comment-list"]')
                                )
                            )
                    except Exception:
                        pass

                    result, video_liked_count, reply_count = self.process_comment(
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
                        reporter,
                    )

                    if reply_count > 0:
                        video_comment_reply_count += reply_count

                    if result is False:
                        try:
                            comment_items = comments_container.find_elements(
                                By.XPATH, "./div"
                            )
                            if comment_index >= len(comment_items):
                                break
                        except Exception:
                            break

                    processed_comment_count += 1

                    if processed_comment_count % 40 == 0:
                        try:
                            padding = driver.find_element(
                                By.CSS_SELECTOR,
                                '[data-e2e="comment-list"] > div:last-child',
                            ).text
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

                    if driver.current_window_handle != main_window:
                        driver.switch_to.window(main_window)

                    self.human_like_delay(2, 5, browser_number)
                except LicenseException:
                    raise
                except Exception as e:
                    msg = str(e).lower()
                    if (
                        "invalid session id" in msg
                        or "disconnected" in msg
                        or "not connected to devtools" in msg
                        or "no such window" in msg
                    ):
                        log.error(
                            f"{self.get_browser_info(browser_number)} 致命错误: {e}"
                        )
                        return False

                    log.error(
                        f"{self.get_browser_info(browser_number)} 处理评论异常: {e}"
                    )
                    comment_index += 1
                    try:
                        driver.switch_to.window(main_window)
                    except Exception:
                        return False
                    continue

            try:
                driver.switch_to.window(main_window)
            except Exception:
                pass

            self.debug_log("info", "所有评论处理完成", browser_number)

            if reporter:
                reporter.force_report()

            with self._stats_lock:
                self.global_followed_count += video_followed_count
                self.global_liked_count += video_liked_count
                self.global_comment_reply_count += video_comment_reply_count
                self.global_video_comment_count += video_comment_count

            return True

        except KeyboardInterrupt:
            raise
        except LicenseException:
            raise
        except Exception as e:
            if self._stop_flag.is_set():
                raise KeyboardInterrupt("收到全局停止信号")
            log.error(f"{browser_info} 程序执行出错: {e}")
            return False

    def scroll_comments(self, driver, scroll_number=None, browser_number=None):
        browser_info = self.get_browser_info(browser_number)
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            DouyinBrowserActions.scroll_element_sync(
                driver, body, delta_y=400, sleep_time=2
            )
            if scroll_number is not None:
                self.debug_log(
                    "info",
                    f"使用ActionChains完成滑动 (第 {scroll_number} 次)",
                    browser_number,
                )
        except Exception as e:
            log.error(f"{browser_info} 滚动失败: {e}")
        return False

    def check_stop_signal(self):
        if self._stop_flag.is_set():
            raise KeyboardInterrupt("收到全局停止信号")

    def get_browser_info(self, browser_number=None, browser_id_param=None):
        if browser_number is not None:
            return f"浏览器 #{browser_number}"
        if browser_id_param is not None:
            return f"浏览器 {browser_id_param}"
        return "浏览器"

    def debug_log(self, level, message, browser_number=None, browser_id_param=None):
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
        elapsed = 0
        while elapsed < seconds:
            self.check_stop_signal()
            wait_time = min(check_interval, seconds - elapsed)
            time.sleep(wait_time)
            elapsed += wait_time

    def force_close_browser(self, browser_id, browser_number=None):
        browser_info = self.get_browser_info(browser_number)
        try:
            closeBrowser(browser_id)
            self.debug_log("info", "已通过API强制关闭浏览器", browser_number)
        except Exception as e:
            log.error(f"{browser_info} 通过API强制关闭浏览器时出错: {e}")

    def reset_url_list_index(self):
        with self._url_list_lock:
            self._url_list_index = 0
            self._browser_start_indices = {}
            if config.URL_INDEX and isinstance(config.URL_INDEX, list):
                for i, start_index in enumerate(config.URL_INDEX):
                    if i < len(config.BIT_BROWSER_IDS):
                        browser_id = config.BIT_BROWSER_IDS[i]
                        self._browser_start_indices[browser_id] = start_index
                        if config.DEBUG:
                            log.info(
                                f"浏览器 {browser_id} 起始索引设置为: {start_index}"
                            )

    def get_next_link_from_list(self, urls_list, browser_id=None):
        with self._url_list_lock:
            start_index = 0
            if browser_id and browser_id in self._browser_start_indices:
                start_index = self._browser_start_indices[browser_id]

            if self._url_list_index == 0 and start_index > 0:
                self._url_list_index = start_index

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

    def get_next_link(self, browser_id=None):
        """仅列表模式：从 config.URLS 中获取下一个待处理链接。"""
        urls_list = config.URLS or []
        return self.get_next_link_from_list(urls_list, browser_id)

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
        browser_number=None,
        reporter=None,
    ):
        cfg = get_config()
        browser_info = self.get_browser_info(browser_number)
        self.debug_log("info", "启动持续处理循环", browser_number)
        sent_completion_report = False

        if reporter:
            reporter.set_total_links(len(cfg.URLS or []))

        self.safe_check_license()
        driver = None

        try:
            while True:
                if self._stop_flag.is_set():
                    log.info(f"{browser_info} 收到全局停止信号，正在退出...")
                    break

                enable_follow = cfg.ENABLE_FOLLOW
                enable_profile_visit = cfg.ENABLE_PROFILE_VISIT
                enable_like = cfg.ENABLE_LIKE
                enable_search_keywords = cfg.ENABLE_SEARCH_KEYWORDS
                enable_comment_reply = cfg.ENABLE_COMMENT_REPLY
                like_probability_val = cfg.LIKE_PROBABILITY / 100.0
                visit_profile_probability_val = cfg.VISIT_ENABLE / 100.0
                profile_follow_probability_val = cfg.PROFILE_FOLLOW_PROBABILITY / 100.0
                comment_reply_probability_val = cfg.COMMENT_REPLY_PROBABILITY / 100.0
                comment_wait_min_val = cfg.COMMENT_WAIT_MIN
                comment_wait_max_val = cfg.COMMENT_WAIT_MAX
                visit_min_val = cfg.VISIT_MIN
                visit_max_val = cfg.VISIT_MAX

                if driver is None:
                    self.debug_log("info", "正在创建新浏览器实例...", browser_number)
                    driver = self.get_driver(browser_id, browser_number)
                    if driver is None:
                        log.error(
                            f"{self.get_browser_info(browser_number)} 创建失败，程序即将退出"
                        )
                        raise Exception("浏览器创建失败，无法继续执行")

                _, url, url_index = self.get_next_link(browser_id)

                if url is None:
                    self.debug_log("info", "列表中的所有URL已处理完毕", browser_number)
                    # 列表模式：按“每个浏览器线程结束”上报完成态
                    if reporter:
                        try:
                            reporter.set_completed(True)
                            sent_completion_report = True
                        except Exception as e:
                            log.warning(f"{browser_info} 上报 isCompleted 失败: {e}")
                    break

                self.debug_log("info", f"获取到新链接: {url}", browser_number)

                with self._stats_lock:
                    self.global_url_opened_count += 1

                retry_count = 0
                while retry_count < 3:
                    if self._stop_flag.is_set():
                        log.info(f"{browser_info} 收到全局停止信号，正在退出...")
                        break

                    try:
                        self.check_stop_signal()

                        try:
                            _ = driver.window_handles
                        except Exception:
                            raise Exception(
                                "disconnected: not connected to DevTools (Pre-check)"
                            )

                        success = self.run_automation(
                            driver,
                            url,
                            wait_time,
                            like_probability_val,
                            visit_profile_probability_val,
                            profile_follow_probability_val,
                            min_follows_per_video,
                            max_follows_per_video,
                            min_likes_per_video,
                            max_likes_per_video,
                            browser_number,
                            browser_id,
                            enable_follow,
                            enable_profile_visit,
                            enable_like,
                            enable_search_keywords,
                            enable_comment_reply,
                            comment_reply_probability_val,
                            comment_wait_min_val,
                            comment_wait_max_val,
                            visit_min_val,
                            visit_max_val,
                            navigate=True,
                            url_index=url_index,
                            reporter=reporter,
                        )

                        if success:
                            if reporter:
                                reporter.increment_keywords_ok()
                                reporter.update_url_index(url_index)
                                reporter.increment_url_ok()
                            self.debug_log(
                                "info", f"链接处理成功: {url}", browser_number
                            )
                            break

                        if reporter:
                            reporter.increment_keywords_ok()
                            reporter.update_url_index(url_index)
                            reporter.increment_url_fail()
                        self.debug_log(
                            "error",
                            f"{browser_info} 链接处理失败（链接失效）: {url}",
                            browser_number,
                        )
                        break

                    except KeyboardInterrupt:
                        log.info(f"{browser_info} 收到停止信号，正在退出...")
                        raise
                    except LicenseException:
                        raise
                    except Exception as e:
                        if self._stop_flag.is_set():
                            log.info(f"{browser_info} 检测到停止信号，正在退出...")
                            raise KeyboardInterrupt("收到全局停止信号")
                        retry_count += 1
                        err_msg = str(e).lower()
                        log.error(
                            f"{self.get_browser_info(browser_number)} 任务异常: {e}"
                        )

                        if (
                            "disconnected" in err_msg
                            or "session" in err_msg
                            or "died" in err_msg
                        ):
                            log.warning(
                                f"{self.get_browser_info(browser_number)} 检测到浏览器崩溃，准备重启..."
                            )
                            try:
                                driver.quit()
                            except Exception:
                                pass
                            driver = None
                            break

                        if retry_count >= 3:
                            if reporter:
                                reporter.increment_keywords_ok()
                                reporter.update_url_index(url_index)
                                reporter.increment_url_fail()
                            self.debug_log(
                                "error",
                                f"{browser_info} 链接处理彻底失败: {url}",
                                browser_number,
                            )

                        self.check_stop_signal()
                        self.safe_sleep(5, browser_number=browser_number)

                if self._stop_flag.is_set():
                    log.info(f"{browser_info} 收到全局停止信号，正在退出...")
                    break

                wait_time_between_links = random.uniform(5, 10)
                self.debug_log(
                    "info",
                    f"等待 {wait_time_between_links:.2f} 秒后处理下一个链接...",
                    browser_number,
                )
                self.safe_sleep(wait_time_between_links, browser_number=browser_number)

        except KeyboardInterrupt:
            log.info(f"{browser_info} 收到停止信号，正在退出...")
        except Exception as e:
            log.error(f"{browser_info} 程序异常退出: {e}")
        finally:
            # 列表模式结束时若已显式上报完成态，则避免再次 force_report 造成重复 PcDataReq
            if reporter and not sent_completion_report:
                reporter.force_report()
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def print_config_debug(self):
        log.info("=" * 80)
        log.info("📋 配置参数调试信息 (DEBUG MODE)")
        log.info("=" * 80)

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

        for attr_name in dir(config):
            if not attr_name.startswith("_") and attr_name not in ignore_attrs:
                try:
                    attr_value = getattr(config, attr_name)
                    if callable(attr_value):
                        continue

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
        if os.name != "nt":
            return

        try:
            import ctypes

            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002

            if enable:
                ctypes.windll.kernel32.SetThreadExecutionState(
                    ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
                )
                if config.DEBUG:
                    log.info("💻 Windows防休眠模式已启用 (屏幕常亮)")
            else:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
                if config.DEBUG:
                    log.info("💤 Windows防休眠模式已解除")
        except Exception as e:
            log.warning(f"设置防休眠模式失败: {e}")

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
        browser_info = self.get_browser_info(browser_number)
        log.info(f"{browser_info} 开始处理URL列表，共 {len(urls)} 个链接")
        for i, target_url in enumerate(urls):
            self.check_stop_signal()
            log.info(f"{browser_info} 处理第{i + 1}个链接: {target_url}")

            try:
                if i > 0:
                    self.switch_to_new_tab(
                        driver, target_url, wait_time, browser_number
                    )
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
                    True,
                    enable_profile_visit,
                    enable_like,
                    enable_search_keywords,
                    enable_comment_reply,
                    comment_reply_probability,
                    comment_wait_min,
                    comment_wait_max,
                    visit_min,
                    visit_max,
                    navigate=True,
                    url_index=i,
                )
                if not success:
                    log.error(f"{browser_info} 处理链接 {target_url} 失败")
            except Exception as e:
                log.error(f"{browser_info} 处理链接 {target_url} 时发生异常: {e}")

            self.human_like_delay(3, 7, browser_number)

    def get_license_manager(self):
        """获取卡密管理器实例"""
        return li


# ----------------------------
# concrete_crawler.py（在同一文件内）
# ----------------------------
import concurrent.futures
import asyncio

from ..tools.license import LicenseManager
from ..tools.core import DataReporter


class ConcreteDyShareCrawler(BaseDyShareCrawler):
    """抖音自动化具体实现类"""

    def __init__(self):
        super().__init__()
        self.config = get_config()
        self.utils = DyShareUtils()
        self.license_manager = LicenseManager()
        self.ws_client = None
        self.ws_thread = None
        self.ws_loop = None
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 3
        self.heartbeat_task = None
        self.heartbeat_timeout_count = 0
        self.max_heartbeat_timeouts = 3
        self.pong_received = asyncio.Event()
        self.data_reporters = {}

    def initialize_config(self) -> None:
        self._start_websocket_client()
        self._send_login_req()

        try:
            self.config.wait_for_initialization()
        except TimeoutError as e:
            log.error(f"配置初始化超时: {e}")
            sys.exit(1)

    def validate_license(self) -> bool:
        return self.license_manager.verify_license()

    def prepare_environment(self) -> None:
        self.license_manager.set_stop_callback(self._on_license_invalid)
        self.license_manager.start_periodic_check()
        self.utils.set_keep_awake(True)
        if self.config.DEBUG:
            self.utils.print_config_debug()

    def setup_database(self) -> None:
        # 仅列表模式：URLS 由服务器下发或本地配置提供
        self._prepare_url_list_mode()
        if not self.config.URLS or len(self.config.URLS) == 0:
            raise Exception("URLS 为空：请通过服务器下发或本地配置提供待处理链接")

        if not self.config.BIT_BROWSER_IDS:
            raise Exception("请在代码中的 BIT_BROWSER_IDS 列表中配置浏览器ID")

    def output_version_info(self) -> None:
        version = env.VERSION or self.config.VERSION
        version_info = {
            "code": 0,
            "data": {"type": "version", "version": f"pc.{version}"},
        }
        output = json.dumps(version_info, ensure_ascii=False)
        print(output)
        time.sleep(0.2)

    def process_urls_with_thread_pool(self) -> None:
        MAX_WORKERS_USED = len(self.config.BIT_BROWSER_IDS)
        WAIT_TIME_USED = self.config.WAIT_TIME
        LIKE_PROBABILITY_USED = self.config.LIKE_PROBABILITY
        VISIT_PROFILE_PROBABILITY_USED = self.config.VISIT_ENABLE
        PROFILE_FOLLOW_PROBABILITY_USED = self.config.PROFILE_FOLLOW_PROBABILITY
        MIN_FOLLOWS_PER_VIDEO_USED = self.config.MIN_FOLLOWS_PER_VIDEO
        MAX_FOLLOWS_PER_VIDEO_USED = self.config.MAX_FOLLOWS_PER_VIDEO
        MIN_LIKES_PER_VIDEO_USED = self.config.COMMENT_LIKE_COUNT_MIN
        MAX_LIKES_PER_VIDEO_USED = self.config.COMMENT_LIKE_COUNT_MAX

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=MAX_WORKERS_USED
            ) as executor:
                futures = []
                for i in range(MAX_WORKERS_USED):
                    browser_id = self.config.BIT_BROWSER_IDS[
                        i % len(self.config.BIT_BROWSER_IDS)
                    ]
                    self._output_browser_start_event(browser_id)
                    reporter = self.data_reporters.get(browser_id)
                    time.sleep(0.2)
                    future = executor.submit(
                        self.utils.continuous_processing_loop,
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
                        reporter,
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

                        if self._check_stop_signal():
                            log.info("=" * 50)
                            log.info("主循环检测到停止信号，正在尝试关闭所有线程...")
                            log.info("=" * 50)
                            self.utils._stop_flag.set()
                            log.info("✓ 已确认设置 _stop_flag")
                            for future in futures:
                                future.cancel()
                            log.info(f"✓ 已取消 {len(futures)} 个任务")
                            break
                    except KeyboardInterrupt:
                        log.info("收到停止信号，正在关闭所有线程...")
                        self.utils._stop_flag.set()
                        for future in futures:
                            future.cancel()
                        sys.exit(0)
        except LicenseException:
            log.error("卡密验证失败，程序终止")
            raise

    def cleanup_resources(self) -> None:
        self._stop_websocket_client()
        self.utils.set_keep_awake(False)
        self.license_manager.stop_periodic_check()

    def _prepare_url_list_mode(self) -> None:
        cleaned_urls = []
        invalid_count = 0
        for url in self.config.URLS:
            cleaned_url = self.utils.extract_douyin_link(url)
            if cleaned_url:
                cleaned_urls.append(cleaned_url)
            else:
                invalid_count += 1
                if self.config.DEBUG:
                    log.warning(f"无效的抖音链接，已跳过: {url}")

        self.config.URLS = cleaned_urls
        if invalid_count > 0 and self.config.DEBUG:
            log.warning(f"URLS列表中有 {invalid_count} 个无效链接已跳过")
        if self.config.DEBUG:
            log.info(f"使用列表模式，共 {len(self.config.URLS)} 个有效URL")
        self.utils.reset_url_list_index()

    def _output_browser_start_event(self, browser_id: str) -> None:
        reporter = DataReporter(
            device_code=self.config.DEVICE_CODE,
            browser_id=browser_id,
            send_ws_message_func=self._send_ws_message_for_reporter,
        )
        self.data_reporters[browser_id] = reporter
        sta = "running" if len(browser_id) == 32 else "error"
        self._send_ws_message(
            {
                "browserId": browser_id,
                "cmd": "RunStateReq",
                "id": self.config.DEVICE_CODE,
                "state": sta,
            }
        )

    def _send_heartbeat(self):
        self._send_ws_message(
            {
                "cmd": "HeartbeatReq",
                "id": self.config.DEVICE_CODE,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    def _handle_heartbeat_response(self, data: dict):
        if isinstance(data, dict) and data.get("cmd") == "HeartbeatRes":
            self.pong_received.set()
            self.heartbeat_timeout_count = 0
            log.info(f"[{datetime.now()}] 收到心跳响应")

    async def _heartbeat_task(self):
        while not self.utils._stop_flag.is_set():
            try:
                self._send_heartbeat()
                try:
                    await asyncio.wait_for(self.pong_received.wait(), timeout=5.0)
                    self.heartbeat_timeout_count = 0
                    self.pong_received.clear()
                except asyncio.TimeoutError:
                    log.warning(f"[{datetime.now()}] 心跳响应超时")
                    self.heartbeat_timeout_count += 1
                    if self.heartbeat_timeout_count >= self.max_heartbeat_timeouts:
                        log.error(
                            f"心跳连续 {self.max_heartbeat_timeouts} 次超时，准备停止程序"
                        )
                        self.utils._stop_flag.set()
                        if self.ws_client:
                            self.ws_client.stop_requested = True
                        self._on_stop_signal_received()
                        break

                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"发送心跳包时出错: {e}")
                break

    def _start_websocket_client(self):
        from ..tools.ws_client import (
            create_websocket_client,
            start_websocket_client_in_thread,
        )

        self.ws_client = create_websocket_client(self.config)
        if self.ws_client:
            self.ws_client.set_external_send_func(self._send_ws_message)
            self.ws_client.set_config_update_handler(self._handle_config_update)

        self.ws_thread = start_websocket_client_in_thread(
            self.ws_client, self._on_stop_signal_received
        )
        self.ws_client.register_command_handler(
            "LoginRes", self._handle_login_res_command
        )
        self.ws_client.register_command_handler(
            "HeartbeatRes", self._handle_heartbeat_response
        )

        max_wait_time = 5
        wait_interval = 0.1
        waited_time = 0
        while waited_time < max_wait_time:
            if self.ws_client.event_loop is not None:
                self.ws_loop = self.ws_client.event_loop
                log.info("✓ 已获取 WebSocket 事件循环引用")
                break
            time.sleep(wait_interval)
            waited_time += wait_interval
        else:
            log.warning("⚠ 等待 WebSocket 事件循环超时，消息发送可能失败")
            self.ws_loop = None

        if self.ws_loop and self.ws_loop.is_running():
            self.heartbeat_task = asyncio.run_coroutine_threadsafe(
                self._heartbeat_task(), self.ws_loop
            )
            log.info("心跳任务已启动")

    def _stop_websocket_client(self):
        try:
            if self.heartbeat_task:
                self.heartbeat_task.cancel()

            if self.ws_client:
                self.ws_client.stop_requested = True
                event_loop = self.ws_client.event_loop or self.ws_loop
                if event_loop is not None and event_loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.ws_client.close(), event_loop)

            if self.ws_thread is not None and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=5.0)

            log.info("WebSocket客户端已关闭")
        except Exception as e:
            log.error(f"关闭WebSocket客户端时出错: {e}")

    def _send_ws_message(self, message_dict):
        log.info(
            f"发送到服务器的消息: {json.dumps(message_dict, ensure_ascii=False, indent=2)}"
        )

        if not self.ws_client:
            log.warning("WebSocket客户端未准备好，无法发送消息（ws_client 为 None）")
            self._on_stop_signal_received()
            return

        if self.ws_client.stop_requested:
            log.warning("WebSocket客户端已请求停止，无法发送消息")
            return

        if not self.ws_client._running:
            log.warning("WebSocket客户端未运行，无法发送消息")
            self._on_stop_signal_received()
            return

        if not (hasattr(self.ws_client, "ws") and self.ws_client.ws):
            log.warning("WebSocket连接对象不存在，无法发送消息")
            self._on_stop_signal_received()
            return

        event_loop = self.ws_client.event_loop or self.ws_loop
        if event_loop is None:
            log.warning("WebSocket事件循环未准备好，无法发送消息")
            self._on_stop_signal_received()
            return

        if not event_loop.is_running():
            log.warning("WebSocket事件循环未运行，无法发送消息")
            self._on_stop_signal_received()
            return

        try:
            asyncio.run_coroutine_threadsafe(
                self.ws_client.send_queue.put(
                    json.dumps(message_dict, ensure_ascii=False)
                ),
                event_loop,
            )
            log.info("✓ 消息已放入发送队列")
        except Exception as e:
            log.error(f"发送WebSocket消息失败: {e}", exc_info=True)
            self._on_stop_signal_received()

    def _send_ws_message_for_reporter(self, message_dict):
        self._send_ws_message(message_dict)

    def _check_stop_signal(self):
        if self.ws_client and self.ws_client.stop_requested:
            log.info("_check_stop_signal() 检测到停止信号")
            return True
        if self.utils._stop_flag.is_set():
            log.info("_check_stop_signal() 检测到 _stop_flag 已设置")
            return True
        return False

    def _on_stop_signal_received(self):
        log.info("=" * 50)
        log.info("收到WebSocket停止信号，设置停止标志...")
        log.info("=" * 50)
        self.utils._stop_flag.set()
        self.config.request_stop()
        log.info(f"✓ 已设置 _stop_flag，当前状态: {self.utils._stop_flag.is_set()}")
        log.info(
            f"✓ WebSocket stop_requested 状态: {self.ws_client.stop_requested if self.ws_client else 'N/A'}"
        )

    def _on_license_invalid(self):
        log.error("=" * 50)
        log.error("卡密已失效，正在停止程序...")
        log.error("=" * 50)
        self._on_stop_signal_received()

    def _handle_login_res_command(self, data: dict):
        if isinstance(data, dict) and data.get("cmd") == "StopReq":
            log.info("收到 StopReq 指令")
            self._on_stop_signal_received()
            return

        if isinstance(data, dict) and data.get("cmd") == "StopPubForce":
            log.info("收到 StopPubForce 指令")
            self._on_stop_signal_received()
            return

        if isinstance(data, dict) and "data" in data:
            config_data = data.get("data", {})
            if config_data:
                self._handle_config_update(config_data)

    def _handle_config_update(self, config_data: dict):
        try:
            # log.info(f"收到配置更新: {config_data}")
            cfg = get_config()
            cfg.update_from_dict(config_data)
            if "SIBERIAN_URL" in config_data:
                self.license_manager.url = config_data["SIBERIAN_URL"]
            if "SIBERIAN_KEY" in config_data:
                self.license_manager.key = config_data["SIBERIAN_KEY"]
            if "DEVICE_CODE" in config_data:
                self.license_manager.code = config_data["DEVICE_CODE"]
            log.info("配置已更新")
            cfg.print_config_summary()
        except Exception as e:
            log.error(f"配置更新失败: {e}")

    def _reconnect_websocket(self):
        for attempt in range(self.max_reconnect_attempts):
            try:
                log.info(
                    f"尝试重新连接WebSocket (第 {attempt + 1}/{self.max_reconnect_attempts} 次)"
                )
                self._stop_websocket_client()
                time.sleep(self.reconnect_delay)
                self._start_websocket_client()
                if self.ws_client:
                    log.info("WebSocket重新连接成功")
                    return True
            except Exception as e:
                log.error(
                    f"重新连接失败 (尝试 {attempt + 1}/{self.max_reconnect_attempts}): {e}"
                )

        log.error("达到最大重连次数，无法重新连接")
        return False

    def _send_login_req(self):
        from urllib.parse import parse_qs, urlparse

        parsed_url = urlparse(self.config.WS_URL)
        query_params = parse_qs(parsed_url.query)
        device_id = query_params.get("id", [self.config.DEVICE_CODE])[0]

        self._send_ws_message(
            {
                "cmd": "LoginReq",
                "id": device_id,
                "mode": "pc",
                "version": env.VERSION or self.config.VERSION,
            }
        )
        time.sleep(0.2)
