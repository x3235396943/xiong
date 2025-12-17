#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音自动化公共工具类
提取 dy 和 dyShare 两个模块中的相似功能
"""

import json
import re
import sys
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.common.by import By

from .core import log


class DouyinConfigParser:
    """配置解析工具类"""
    
    @staticmethod
    def parse_keywords(raw_config):
        """
        解析关键字配置
        
        Args:
            raw_config: 原始配置，可以是字符串或列表
            
        Returns:
            list: 解析后的关键词列表
        """
        raw = raw_config or []
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
    
    @staticmethod
    def parse_video_comments(raw_config):
        """
        解析视频留言内容列表，使用 -&- 作为分隔符
        
        Args:
            raw_config: 原始配置，可以是字符串或列表
            
        Returns:
            list: 解析后的评论列表
        """
        raw = raw_config or ''
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
                # 不是JSON，按 -&- 分隔符分割
                comments = [x.strip() for x in s.split("-&-") if x.strip()]
        elif isinstance(raw, list):
            comments = [str(x).strip() for x in raw if str(x).strip()]
        return comments if comments else []
    
    @staticmethod
    def parse_comment_replies(raw_config):
        """
        解析评论回复内容列表，使用 -&- 作为分隔符
        
        Args:
            raw_config: 原始配置，可以是字符串或列表
            
        Returns:
            list: 解析后的回复列表
        """
        raw = raw_config or ''
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
                # 不是JSON，按 -&- 分隔符分割
                replies = [x.strip() for x in s.split("-&-") if x.strip()]
        elif isinstance(raw, list):
            replies = [str(x).strip() for x in raw if str(x).strip()]
        return replies if replies else []
    
    @staticmethod
    def normalize_text(text):
        """
        文本标准化（转小写、去除多余空格）
        
        Args:
            text: 原始文本
            
        Returns:
            str: 标准化后的文本
        """
        try:
            s = str(text).lower()
            s = re.sub(r"\s+", " ", s).strip()
            return s
        except Exception:
            return str(text)


class DouyinCommentActions:
    """评论操作工具类"""
    
    @staticmethod
    def extract_comment_text(comment_element):
        """
        提取评论文本
        
        Args:
            comment_element: 评论元素
            
        Returns:
            str: 评论文本
        """
        selectors = [
            ".C7LroK_h span span span",
            '[data-e2e="comment-text"]',
            ".comment-text",
            "span",
        ]
        for css in selectors:
            try:
                t = comment_element.find_element(By.CSS_SELECTOR, css).text
                if t:
                    return t
            except Exception:
                pass
        try:
            return comment_element.text
        except Exception:
            return ""
    
    @staticmethod
    async def leave_video_comment_async(driver, comment_text, active_element=None, ws_push_func=None):
        """
        在当前视频页面留下评论（异步版本）
        
        Args:
            driver: WebDriver实例
            comment_text: 评论内容
            active_element: 活动视频元素（可选，用于dy模块）
            ws_push_func: WebSocket推送函数（可选）
            
        Returns:
            bool: 是否成功发布
        """
        from asyncio import sleep
        
        try:
            # 查找评论输入框
            if active_element:
                # dy模块使用active元素查找
                comment_input = active_element.find_element(
                    By.CSS_SELECTOR,
                    '.GXmFLge7.comment-input-inner-container'
                )
                container = active_element
            else:
                # dyShare模块直接从driver查找
                comment_input = driver.find_element(
                    By.CSS_SELECTOR,
                    '.GXmFLge7.comment-input-inner-container'
                )
                container = driver
            
            # 点击评论输入框
            driver.execute_script("arguments[0].click();", comment_input)
            await sleep(0.5)
            
            # 输入评论文本
            ActionChains(driver).send_keys(comment_text).perform()
            await sleep(0.5)
            
            # 尝试点击发送按钮
            try:
                send_button = container.find_element(
                    By.CSS_SELECTOR,
                    '[data-e2e="comment-post"]'
                )
                driver.execute_script("arguments[0].click();", send_button)
                log.debug(f"成功发布视频评论: {comment_text[:20]}...")
                await sleep(1)
                if ws_push_func:
                    await ws_push_func(videoComment=1)
                return True
            except:
                # 如果找不到发送按钮，尝试按回车键
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                log.debug(f"通过回车键发送视频评论: {comment_text[:20]}...")
                await sleep(1)
                if ws_push_func:
                    await ws_push_func(videoComment=1)
                return True
        except Exception as e:
            log.debug(f"发布视频评论失败: {e}")
            return False
    
    @staticmethod
    def leave_video_comment_sync(driver, comment_text, browser_number=None, browser_id="", debug_log_func=None, check_stop_func=None):
        """
        在当前视频页面留下评论（同步版本）
        
        Args:
            driver: WebDriver实例
            comment_text: 评论内容
            browser_number: 浏览器编号（可选）
            browser_id: 浏览器ID（可选）
            debug_log_func: 调试日志函数（可选）
            check_stop_func: 停止信号检查函数（可选）
            
        Returns:
            bool: 是否成功发布
        """
        import time
        
        try:
            if check_stop_func:
                check_stop_func()
            
            # 查找评论输入框
            comment_input = driver.find_element(
                By.CSS_SELECTOR,
                '.GXmFLge7.comment-input-inner-container'
            )
            
            # 点击评论输入框
            driver.execute_script("arguments[0].click();", comment_input)
            time.sleep(0.5)
            
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
                if debug_log_func:
                    debug_log_func("info", f"成功发布视频评论: {comment_text[:20]}...", browser_number)
                else:
                    log.info(f"成功发布视频评论: {comment_text[:20]}...")
                time.sleep(1)
                return True
            except:
                # 如果找不到发送按钮，尝试按回车键
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                if debug_log_func:
                    debug_log_func("info", f"通过回车键发送视频评论: {comment_text[:20]}...", browser_number)
                else:
                    log.info(f"通过回车键发送视频评论: {comment_text[:20]}...")
                time.sleep(1)
                return True
        except Exception as e:
            browser_info = f"浏览器 #{browser_number}" if browser_number else "浏览器"
            log.warning(f"{browser_info} 发布视频评论失败: {e}")
            return False
    
    @staticmethod
    async def reply_to_comment_async(driver, target_comment, reply_text, active_element=None, ws_push_func=None):
        """
        回复指定评论（异步版本）
        
        Args:
            driver: WebDriver实例
            target_comment: 目标评论元素
            reply_text: 回复内容
            active_element: 活动视频元素（可选，用于dy模块）
            ws_push_func: WebSocket推送函数（可选）
            
        Returns:
            bool: 是否成功回复
        """
        from asyncio import sleep
        
        try:
            # 查找评论的回复按钮
            reply_button = target_comment.find_element(
                By.CSS_SELECTOR,
                'div:nth-child(2) > div > div:nth-child(4) > div > div:nth-child(3) > div'
            )
            
            # 点击回复按钮
            driver.execute_script("arguments[0].click();", reply_button)
            await sleep(0.5)
            
            # 输入回复文本
            ActionChains(driver).send_keys(reply_text).perform()
            await sleep(0.5)
            
            # 尝试点击发送按钮
            try:
                if active_element:
                    send_button = active_element.find_element(
                        By.CSS_SELECTOR,
                        '[data-e2e="comment-post"]'
                    )
                else:
                    send_button = driver.find_element(
                        By.CSS_SELECTOR,
                        '[data-e2e="comment-post"]'
                    )
                driver.execute_script("arguments[0].click();", send_button)
                log.debug(f"成功回复评论: {reply_text[:20]}...")
                await sleep(1)
                if ws_push_func:
                    await ws_push_func(comment=1)
                return True
            except:
                # 如果找不到发送按钮，尝试按回车键
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                log.debug(f"通过回车键发送回复: {reply_text[:20]}...")
                await sleep(1)
                if ws_push_func:
                    await ws_push_func(comment=1)
                return True
        except Exception as e:
            log.debug(f"回复评论失败: {e}")
            return False
    
    @staticmethod
    def reply_to_comment_sync(driver, target_comment, reply_text, browser_number=None, browser_id="", debug_log_func=None, check_stop_func=None):
        """
        回复指定评论（同步版本）
        
        Args:
            driver: WebDriver实例
            target_comment: 目标评论元素
            reply_text: 回复内容
            browser_number: 浏览器编号（可选）
            browser_id: 浏览器ID（可选）
            debug_log_func: 调试日志函数（可选）
            check_stop_func: 停止信号检查函数（可选）
            
        Returns:
            bool: 是否成功回复
        """
        import time
        
        try:
            if check_stop_func:
                check_stop_func()
            
            # 查找评论的回复按钮
            reply_button = target_comment.find_element(
                By.CSS_SELECTOR,
                'div:nth-child(2) > div > div:nth-child(4) > div > div:nth-child(3) > div'
            )
            
            # 点击回复按钮
            driver.execute_script("arguments[0].click();", reply_button)
            time.sleep(0.5)
            
            # 输入回复文本
            ActionChains(driver).send_keys(reply_text).perform()
            time.sleep(0.5)
            
            # 尝试点击发送按钮
            try:
                send_button = driver.find_element(
                    By.CSS_SELECTOR,
                    '[data-e2e="comment-post"]'
                )
                driver.execute_script("arguments[0].click();", send_button)
                if debug_log_func:
                    debug_log_func("info", f"成功回复评论: {reply_text[:20]}...", browser_number)
                else:
                    log.info(f"成功回复评论: {reply_text[:20]}...")
                time.sleep(1)
                return True
            except:
                # 如果找不到发送按钮，尝试按回车键
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                if debug_log_func:
                    debug_log_func("info", f"通过回车键发送回复: {reply_text[:20]}...", browser_number)
                else:
                    log.info(f"通过回车键发送回复: {reply_text[:20]}...")
                time.sleep(1)
                return True
        except Exception as e:
            browser_info = f"浏览器 #{browser_number}" if browser_number else "浏览器"
            log.warning(f"{browser_info} 回复评论失败: {e}")
            return False


class DouyinBrowserActions:
    """浏览器操作工具类"""
    
    @staticmethod
    def clear_input(element, driver=None):
        """
        清空输入框（跨平台）
        
        Args:
            element: 输入框元素
            driver: WebDriver实例（可选，用于某些特殊情况）
        """
        if sys.platform == "win32":
            element.send_keys(Keys.CONTROL, "a")
        elif sys.platform == "darwin":  # Mac
            element.send_keys(Keys.COMMAND, "a")
        else:  # Linux
            element.send_keys(Keys.CONTROL, "a")
        element.send_keys(Keys.BACKSPACE)
    
    @staticmethod
    async def scroll_element_async(driver, element, delta_y=200, sleep_time=2):
        """
        滚动元素（异步版本）
        
        Args:
            driver: WebDriver实例
            element: 要滚动的元素
            delta_y: 垂直滚动距离
            sleep_time: 滚动后等待时间（秒）
        """
        from asyncio import sleep
        
        ActionChains(driver).scroll_from_origin(
            ScrollOrigin.from_element(element), 0, delta_y
        ).perform()
        await sleep(sleep_time)
    
    @staticmethod
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
            log.error(f"滚动失败: {e}")

