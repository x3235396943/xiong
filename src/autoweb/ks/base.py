from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import random
import time
import re


class KuaishouUtils:
    """快手自动化工具类"""
    
    @staticmethod
    def scroll_ks_comment_container(driver, times=5, step=500, sleep=1.5):
        """滚动快手评论容器"""
        css = "div.comment-container.vertical-comment"
        container = driver.find_element(By.CSS_SELECTOR, css)
        from selenium.webdriver.common.actions.wheel_input import ScrollOrigin

        for _ in range(times):
            ActionChains(driver).move_to_element(container).pause(0.05).scroll_from_origin(
                ScrollOrigin.from_element(container), 0, step
            ).perform()
            time.sleep(sleep)
        return True

    @staticmethod
    def normalize_text(text):
        """文本标准化（转小写、去除多余空格）"""
        try:
            s = str(text).lower()
            s = re.sub(r"\s+", " ", s).strip()
            return s
        except Exception:
            return str(text)

    @staticmethod
    def check_comment_contains_keywords(comment_text, keywords):
        """检查评论是否包含指定关键词"""
        keyword_list = [x.strip() for x in keywords.split("-&-") if x.strip()]
        norm_comment = KuaishouUtils.normalize_text(comment_text)
        for kw in keyword_list:
            if KuaishouUtils.normalize_text(kw) in norm_comment:
                return True
        return False

    @staticmethod
    def leave_video_comment(driver, video_comment_wait_min, video_comment_wait_max, log_prefix):
        """在当前视频页面留下评论"""
        try:
            # 等待视频加载并等待一段时间后进行评论
            wait_time = random.uniform(video_comment_wait_min, video_comment_wait_max)
            print(f"{log_prefix} 等待 {wait_time:.2f} 秒后进行视频留言")
            time.sleep(wait_time)
            
            # 查找评论输入框
            comment_input = KuaishouUtils.el(driver, ".pl-textarea")
            if comment_input:
                # 点击输入框
                KuaishouUtils.click(driver, comment_input)
                time.sleep(0.5)
                
                # 输入评论内容
                comment_text = random.choice(["这个视频不错！", "内容很棒！", "支持一下！", "666", "好看！"])
                comment_input.send_keys(comment_text)
                time.sleep(0.5)
                
                # 尝试找到并点击发送按钮
                send_button = (KuaishouUtils.el(driver, ".pl-send-btn") or 
                              KuaishouUtils.el(driver, ".send-btn") or 
                              KuaishouUtils.el(driver, ".comment-send-btn"))
                if send_button:
                    KuaishouUtils.click(driver, send_button)
                    print(f"{log_prefix} 已留言: {comment_text}")
                    return True
                else:
                    # 如果没有找到发送按钮，尝试按回车键
                    comment_input.send_keys(Keys.RETURN)
                    print(f"{log_prefix} 已留言: {comment_text}")
                    return True
            else:
                print(f"{log_prefix} 未找到评论输入框")
                return False
        except Exception as e:
            print(f"{log_prefix} 留言失败: {e}")
            return False

    @staticmethod
    def el(driver, css, root=None):
        """查找单个元素"""
        try:
            return (root or driver).find_element(By.CSS_SELECTOR, css)
        except Exception:
            return None

    @staticmethod
    def els(driver, css, root=None):
        """查找多个元素"""
        try:
            return (root or driver).find_elements(By.CSS_SELECTOR, css)
        except Exception:
            return []

    @staticmethod
    def click(driver, x):
        """模拟点击操作"""
        if not x:
            return False
        try:
            driver.execute_script("arguments[0].click();", x)
            KuaishouUtils.human_like_delay()  # 点击后添加随机等待
            return True
        except Exception:
            try:
                x.click()
                KuaishouUtils.human_like_delay()  # 点击后添加随机等待
                return True
            except Exception:
                return False

    @staticmethod
    def human_like_delay(min_delay=0.3, max_delay=0.8):
        """模拟人工点击的随机延迟"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)