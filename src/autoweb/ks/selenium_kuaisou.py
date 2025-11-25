import time
import random
import re
from selenium.webdriver.common.by import By
from ..tools import ks_config as config
from ..tools import log as logger
from .selenium_common import (
    scroll_page,
    scroll_to_element,
    scroll_to_bottom,
    scroll_element_down,
    scroll_element_down_js,
    scroll_element_inner,
    safe_click,
    human_type,
    is_element_visible
)


def kuaishou_search(driver, keyword, selenium_browser):
    """快手搜索，输入关键词，点击搜索"""

    if "https://www.kuaishou.com/short-video" not in driver.current_url:
        # 确保标签页
        try:
            # 先保存当前窗口句柄，避免在关闭窗口后失效
            current_handle = driver.current_window_handle
            all_handles = driver.window_handles
            
            if len(all_handles) > 1:
                for handle in all_handles:
                    if handle != current_handle:
                        try:
                            driver.switch_to.window(handle)
                            driver.close()
                        except Exception as e:
                            logger.info(f"关闭标签页失败: {e}")
                
                # 关闭后，确保切换回原始窗口（如果还存在）
                remaining_handles = driver.window_handles
                if current_handle in remaining_handles:
                    driver.switch_to.window(current_handle)
                elif remaining_handles:
                    # 如果原始窗口不存在，切换到第一个可用窗口
                    driver.switch_to.window(remaining_handles[0])
                else:
                    logger.info("警告：所有窗口都已关闭")
        except Exception as e:
            logger.info(f"清理标签页时出错: {e}")
            # 尝试切换到第一个可用窗口
            try:
                all_handles = driver.window_handles
                if all_handles:
                    driver.switch_to.window(all_handles[0])
            except:
                pass
    else:
        safe_click(driver, driver.find_element(By.CLASS_NAME, 'close-page'))
    img = None
    try:
        driver.implicitly_wait(10)
        input = driver.find_element(By.CLASS_NAME, 'search-input')
        img = driver.find_element(By.CLASS_NAME, 'search-icon')
    except Exception as e:
        if driver.current_url != 'https://www.kuaishou.com/new-reco':
            driver.get('https://www.kuaishou.com/new-reco')

        driver.implicitly_wait(10)
        input = driver.find_element(By.CLASS_NAME, 'input')
    
    # 使用通用的人类输入函数
    human_type(input, keyword)
    icon_element = None
    try:
        search_element = driver.find_element(By.CLASS_NAME, 'search')
        icon_element = search_element.find_element(By.CLASS_NAME, 'icon')
    except Exception as e:
        if 'https://www.kuaishou.com/?isHome' in driver.current_url:
            icon_element = driver.find_element(By.CLASS_NAME, 'search-icon')
    if icon_element:
        try:
            if not img:
                img = icon_element.find_element(By.TAG_NAME, 'img')
            # 滚动到元素位置
            time.sleep(0.5)
            # 使用通用的安全点击函数
            safe_click(driver, img)
        except Exception as e:
            logger.info(f"找到 icon 元素失败: {e}")
        logger.info("找到搜索按钮")
        selenium_browser.switch_to_new_tab("search", close_others=True)
    else:
        logger.info("没找到搜索按钮")

def click_video(driver):
    """搜索后随机点击视频"""
    driver.implicitly_wait(10)
    time.sleep(random.uniform(2, 5))
    if "search" not in driver.current_url:
        logger.info("不是搜索页面")
        return False
    try:
        # 等待网站加载完成
        video_element = driver.find_element(By.CLASS_NAME, 'video-container')
        if not video_element:
            logger.info("没有视频元素")
            return False
        video_items = video_element.find_elements(By.CLASS_NAME, 'video-item')
        if not video_items:
            logger.info("没有视频项元素")
            return False
        random_index = random.randint(0, len(video_items) - 1)
        video_item = video_items[random_index]
        if not video_item:
            logger.info("没有视频项元素")
            return False
        video_item.click()
        time.sleep(0.5)
        try:
            driver.find_element(By.CLASS_NAME, 'video-interactive-area').click()
        except Exception as e:
            logger.info(f"点击视频交互区域失败: {e}")
            return True
        return True
    except Exception as e:
        logger.info(f"点击视频失败: {e}")
        return False

def click_comment_like(driver):
    """视频随机评论点赞"""
    # 使用 CSS 选择器来匹配多个类名
    driver.implicitly_wait(10)
    comment_elements = driver.find_elements(By.CSS_SELECTOR, '.comment-item.comment-list-item.dark-mode')
    if not comment_elements:
        logger.info("没有评论")
        return False
    
    # 使用 is_element_visible 过滤出可视范围内的评论元素
    visible_comment_elements = is_element_visible(driver, comment_elements)
    if not visible_comment_elements:
        logger.info("没有可视的评论元素")
        return False
    
    # 从可视的评论元素中随机选择一个
    random_index = random.randint(0, len(visible_comment_elements) - 1)
    comment_element = visible_comment_elements[random_index]
    try:
        # 获取点赞数元素（使用 CSS 选择器匹配多个类名）
        like_count_element = comment_element.find_element(By.CSS_SELECTOR, '.comment-item-operation-op.likeop')
        
        # 获取点赞前的点赞数文本
        like_count_text_before = like_count_element.text.strip()
        # 尝试解析点赞数（可能包含数字和单位，如"1"、"1.2万"等）
        like_count_before = 0
        if like_count_text_before:
            # 提取数字部分
            numbers = re.findall(r'\d+\.?\d*', like_count_text_before)
            if numbers:
                like_count_before = float(numbers[0])
                # 如果有"万"字，乘以10000
                if '万' in like_count_text_before:
                    like_count_before *= 10000
        
        # 点击点赞按钮
        like_element = comment_element.find_element(By.CLASS_NAME, 'comment-item-likeicon')
        safe_click(driver, like_element)
        
        # 等待一下，让点赞操作生效
        time.sleep(0.5)
        
        # 再次获取点赞数文本
        like_count_text_after = like_count_element.text.strip()
        
        # 如果点赞数包含"万"字，不需要检查点赞是否增加（因为增加1个点赞可能不会导致显示数字变化）
        if '万' in like_count_text_before or '万' in like_count_text_after:
            logger.info(f"点赞数包含'万'字，跳过检查：点赞前={like_count_text_before}，点赞后={like_count_text_after}")
            return True
        
        like_count_after = 0
        if like_count_text_after:
            # 提取数字部分
            numbers = re.findall(r'\d+\.?\d*', like_count_text_after)
            if numbers:
                like_count_after = float(numbers[0])
        
        # 检查点赞数是否增加
        if like_count_after == like_count_before:
            logger.info(f"点赞失败或取消点赞：点赞前={like_count_text_before}，点赞后={like_count_text_after}")
            return False
        elif like_count_after < like_count_before:
            logger.info(f'点赞数减少，重新点赞')
            safe_click(driver, like_element)
            return False
        
        logger.info(f"点赞成功：点赞前={like_count_text_before}，点赞后={like_count_text_after}")
        return True
    except Exception as e:
        logger.info(f"查找点赞元素失败: {e}")
        return False
def _extract_comment_text(comment_element):
    """
    提取评论文本内容，兼容 comment-item-content 下可能存在的多层 span
    """
    try:
        content_element = comment_element.find_element(By.CSS_SELECTOR, '.comment-item-content')
        text = content_element.text.strip()
        if text:
            return text
    except Exception:
        pass
    try:
        return comment_element.text.strip()
    except Exception:
        return ""


def click_comment_follow(driver, selenium_browser, should_follow=True):
    """
    评论区随机查看个人信息操作(切回视频页面)
    Args:
        driver: Selenium WebDriver 对象
        selenium_browser: SeleniumBrowser 实例
        should_follow: 是否执行关注操作，True=关注，False=仅查看个人信息
    Returns:
        bool: 操作是否成功
    """
    driver.implicitly_wait(10)
    comment_elements = driver.find_elements(By.CSS_SELECTOR, '.comment-item.comment-list-item.dark-mode')
    if not comment_elements:
        logger.info("没有评论")
        return False
    
    # 预处理评论元素
    visible_comment_elements = is_element_visible(driver, comment_elements)
    visible_comment_ids = {element.id for element in visible_comment_elements}

    comment_keywords = [
        kw.strip() for kw in getattr(config, 'COMMENT_KEYWORDS', []) or [] if isinstance(kw, str) and kw.strip()
    ]
    keyword_lower = [kw.lower() for kw in comment_keywords]

    prioritized_candidates = []
    fallback_visible = []

    for element in comment_elements:
        text = _extract_comment_text(element)
        if not text:
            continue
        is_visible = element.id in visible_comment_ids
        if is_visible:
            fallback_visible.append(element)

        is_match = False
        if keyword_lower:
            text_lower = text.lower()
            is_match = any(keyword in text_lower for keyword in keyword_lower)

        if is_match:
            prioritized_candidates.append({
                'element': element,
                'text': text,
                'visible': is_visible
            })

    # 选择目标评论：优先匹配关键词且已可见，其次匹配关键词但需滚动，最后随机可见评论
    comment_element = None
    selected_comment_text = ""

    if prioritized_candidates:
        visible_prioritized = [item for item in prioritized_candidates if item['visible']]
        if visible_prioritized:
            selected_candidate = random.choice(visible_prioritized)
            comment_element = selected_candidate['element']
            selected_comment_text = selected_candidate['text']
            logger.info(f"优先选择可视范围内的关键词评论: {selected_comment_text}")
        else:
            for candidate in prioritized_candidates:
                try:
                    scroll_to_element(driver, candidate['element'])
                    time.sleep(random.uniform(0.3, 0.6))
                    if candidate['element'].is_displayed():
                        comment_element = candidate['element']
                        selected_comment_text = candidate['text']
                        logger.info("已滚动使关键词评论可视，准备执行关注")
                        break
                except Exception as e:
                    logger.info(f"滚动关键词评论失败: {e}")
            if comment_element is None:
                comment_element = prioritized_candidates[0]['element']
                selected_comment_text = prioritized_candidates[0]['text']
                logger.info("关键词评论仍不可见，尝试直接操作首个匹配评论")

    if comment_element is None:
        if not fallback_visible:
            logger.info("没有可视的评论元素")
            return False
        comment_element = random.choice(fallback_visible)
        selected_comment_text = _extract_comment_text(comment_element)
        logger.info("未找到匹配关键词的评论，随机选择可视评论执行操作")

    if not selected_comment_text:
        selected_comment_text = _extract_comment_text(comment_element)

    # 确保目标评论在可视范围内
    try:
        scroll_to_element(driver, comment_element)
        time.sleep(random.uniform(0.2, 0.4))
    except Exception as e:
        logger.info(f"滚动至目标评论失败，继续尝试点击: {e}")
    original_handle = None
    try:
        # 保存当前窗口句柄（视频页面）
        original_handle = driver.current_window_handle
        
        follow_element = comment_element.find_element(By.CLASS_NAME, 'author-name')
        safe_click(driver, follow_element)
        driver = selenium_browser.switch_to_new_tab("profile")

        # 根据参数决定是否执行关注操作
        if should_follow:
            btn_words_element = driver.find_element(By.CLASS_NAME, 'btn-words')
            if btn_words_element.is_displayed() and btn_words_element.text == '关注':
                safe_click(driver, btn_words_element)
            else:
                logger.info("关注按钮不可见或已关注")
                if 'profile' in driver.current_url:
                    driver.close()
                    # 切换回原来的视频页面
                    all_handles = driver.window_handles
                    if original_handle in all_handles:
                        driver.switch_to.window(original_handle)
                    elif all_handles:
                        # 如果原始窗口不存在，切换到第一个可用窗口
                        driver.switch_to.window(all_handles[0])
                    else:
                        logger.info("警告：所有窗口都已关闭")
                return False
            time.sleep(3)
        else:
            # 仅查看个人信息，随机等待3-5秒
            time.sleep(random.uniform(3, 5))
        
        # 关闭 profile 标签页
        if 'profile' in driver.current_url:
            driver.close()
        
        
        # 切换回原来的视频页面
        all_handles = driver.window_handles
        if original_handle in all_handles:
            driver.switch_to.window(original_handle)
        elif all_handles:
            # 如果原始窗口不存在，切换到第一个可用窗口
            driver.switch_to.window(all_handles[0])
        else:
            logger.info("警告：所有窗口都已关闭")
            
    except Exception as e:
        operation_name = "关注" if should_follow else "查看个人信息"
        logger.info(f"{operation_name} 操作失败: {e}")
        if 'profile' in driver.current_url:
            # 尝试切换回原始窗口
            driver.close()
            # 切换回原来的视频页面
            all_handles = driver.window_handles
            if original_handle in all_handles:
                driver.switch_to.window(original_handle)
            elif all_handles:
                # 如果原始窗口不存在，切换到第一个可用窗口
                driver.switch_to.window(all_handles[0])
            else:
                logger.info("警告：所有窗口都已关闭")
        return False
        
    return True
