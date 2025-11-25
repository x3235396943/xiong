import time
import selenium
import random
import threading
import queue
import signal
import sys
from .selenium_browser import SeleniumBrowser
from .selenium_kuaisou import *
from selenium.webdriver.common.by import By
from ..tools import ks_config
from .browser_cluster import BrowserCluster, cluster
from .video_browser import browser_video_loop, browser_video_url_list_loop
from .video_monitor import start_monitoring, stop_monitoring
from selenium import webdriver
import tempfile
import os
import platform
from ..tools import log as logger

# 清理残留进程
def kill_chrome_processes():
    system = platform.system()
    if system == "Windows":
        os.system("taskkill /f /im chrome.exe /t >nul 2>&1")
        os.system("taskkill /f /im chromedriver.exe /t >nul 2>&1")
    elif system in ["Linux", "Darwin"]:
        os.system("pkill -f chrome >/dev/null 2>&1")
        os.system("pkill -f chromedriver >/dev/null 2>&1")

# kill_chrome_processes()

# 根据 USE_BITBROWSER 配置决定是否使用比特浏览器
selenium_browser = None
if config.USE_BITBROWSER and hasattr(config, 'BITBROWSER_URL') and config.BITBROWSER_URL and config.BITBROWSER_URL.strip():
    browser_names = getattr(config, 'BITBROWSER_NAMES', [])
    browser_ids = getattr(config, 'BITBROWSER_IDS', [])

    name_results = {}
    id_results = {}
    has_targets = bool(browser_names or browser_ids)

    if browser_names:
        logger.info(f"使用指纹浏览器模式，准备根据名称启动 {len(browser_names)} 个浏览器: {browser_names}")
        name_results = cluster.init_browsers_by_names(browser_names)

    if browser_ids:
        logger.info(f"使用指纹浏览器模式，准备根据ID启动 {len(browser_ids)} 个浏览器: {browser_ids}")
        id_results = cluster.init_browsers_by_ids(browser_ids)

    combined_results = {**name_results, **id_results}

    if combined_results:
        logger.info("浏览器启动结果:")
        for identifier, result in combined_results.items():
            name = result.get('name')
            browser_id = result.get('id')
            status = "✓ 成功" if result.get('success') else "✗ 失败"
            parts = []
            if name:
                parts.append(name)
            if browser_id:
                parts.append(f"ID: {browser_id}")
            if not parts:
                parts.append(identifier)
            message = result.get('message')
            log_line = f"{' | '.join(parts)} - {status}"
            if message:
                log_line += f" | {message}"
            logger.info(log_line)

        for identifier, result in combined_results.items():
            if not result.get('success'):
                continue
            browser_candidate = cluster.get_browser(identifier)
            if browser_candidate and browser_candidate.driver:
                selenium_browser = browser_candidate
                display_name = result.get('name') or identifier
                logger.info(f"使用 '{display_name}' 作为主浏览器（ID: {result.get('id') or '未知'}）")
                break

        if selenium_browser is None:
            logger.warning("没有成功启动的浏览器")

    if selenium_browser is None:
        reason = "未能通过指纹配置启动浏览器" if has_targets else "未配置浏览器名称或ID，使用单个浏览器模式"
        logger.warning(f"{reason}，尝试使用单个浏览器模式")
        selenium_browser = SeleniumBrowser()
        result = selenium_browser._open_control()
        if result.get('message'):
            logger.info(f"指纹浏览器: {result.get('message')}")
        if selenium_browser.driver:
            browser_name = "single_browser_fallback" if has_targets else "single_browser_default"
            added = cluster.add_browser(browser_name, selenium_browser, display_name=browser_name)
            if added:
                logger.info(f"已将单个浏览器 '{browser_name}' 添加到集群")
            else:
                logger.warning(f"无法将单个浏览器 '{browser_name}' 添加到集群")
else:
    # 使用本地浏览器，根据 PROXIES 配置启动多个实例
    logger.info("使用本地浏览器模式")

    # 优先使用 NETWORK_PROXIES 列表；如果未配置，则回退到单个 NETWORK_PROXY 或无代理
    proxies_list = getattr(config, 'NETWORK_PROXIES', [])
    if proxies_list:
        proxies = proxies_list
    elif getattr(config, 'NETWORK_PROXY', None):
        proxies = [config.NETWORK_PROXY]
    else:
        proxies = [None]

    successful_browsers = 0

    for index, proxy in enumerate(proxies, start=1):
        proxy_display = proxy if proxy else '无代理'
        browser_name = f"local_browser_{index}"
        logger.info(f"启动本地浏览器 {browser_name}，代理: {proxy_display}")

        browser_instance = SeleniumBrowser(proxy=proxy)
        result = browser_instance._open_control(None)
        message = result.get('message')
        if message:
            logger.info(f"{browser_name}: {message}")

        if browser_instance.driver:
            added = cluster.add_browser(browser_name, browser_instance, display_name=browser_name)
            if added:
                successful_browsers += 1
                if selenium_browser is None:
                    selenium_browser = browser_instance
            else:
                logger.warning(f"无法将 {browser_name} 添加到浏览器集群")
        else:
            logger.warning(f"浏览器 {browser_name} 启动失败")

    if selenium_browser is None:
        logger.error("没有成功启动的本地浏览器")
        exit(1)
    else:
        logger.info(f"成功启动 {successful_browsers} 个本地浏览器")



# 获取主浏览器驱动（用于当前的主流程）
driver = selenium_browser.driver if selenium_browser and selenium_browser.driver else None
if not driver:
    logger.error("无法获取浏览器驱动，程序退出")
    exit(1)

# 显示所有已启动的浏览器信息
logger.info(f"{'='*50}")
logger.info("已启动的浏览器列表:")
browser_list = cluster.list_browsers()
for i, browser_key in enumerate(browser_list, 1):
    browser = cluster.get_browser(browser_key)
    status = "✓ 运行中" if browser and browser.driver else "✗ 未启动"
    browser_id = browser.id if browser else "N/A"
    display_name = cluster.get_browser_display_name(browser_key) if browser else browser_key
    if display_name != browser_key:
        logger.info(f"{i}. {display_name} (Key: {browser_key}, ID: {browser_id}) - {status}")
    else:
        logger.info(f"{i}. {display_name} (ID: {browser_id}) - {status}")
logger.info(f"{'='*50}")

# 使用示例：如何控制所有浏览器
# 方法1: 获取特定浏览器
# browser = cluster.get_browser("快手001")
# driver = browser.driver

# 方法2: 在所有浏览器上执行相同操作
# results = cluster.execute_all(kuaishou_search, "关键词", selenium_browser)

# 方法3: 批量执行不同任务
# tasks = [
#     {'browser_id': '快手001', 'func': kuaishou_search, 'args': ['关键词1'], 'kwargs': {}},
#     {'browser_id': '快手002', 'func': kuaishou_search, 'args': ['关键词2'], 'kwargs': {}}
# ]
# results = cluster.execute_batch(tasks)

DEFAULT_SEARCH_KEYWORDS = ["御姐", "美女", "性感", "制服", "清纯", "可爱", "性感", "女神", "模特", "丰满"]
SEARCH_KEYWORDS = config.KUAISHOU_SEARCH_KEYWORDS if config.KUAISHOU_SEARCH_KEYWORDS else DEFAULT_SEARCH_KEYWORDS

# ==================== 主流程循环配置 ====================
# 主流程执行间隔时间范围（秒）
main_loop_interval_min = config.VIDEO_MAIN_LOOP_INTERVAL_MIN
main_loop_interval_max = config.VIDEO_MAIN_LOOP_INTERVAL_MAX

# 操作间隔时间范围（秒）
action_interval_min = config.VIDEO_ACTION_INTERVAL_MIN  # 最小间隔
action_interval_max = config.VIDEO_ACTION_INTERVAL_MAX  # 最大间隔

# 滑动间隔时间范围（秒）
scroll_interval_min = config.VIDEO_SCROLL_INTERVAL_MIN   # 最小间隔
scroll_interval_max = config.VIDEO_SCROLL_INTERVAL_MAX  # 最大间隔

# 每轮最多刷视频数量
videos_per_loop_min = config.VIDEOS_PER_LOOP_MIN  # 每轮最少刷视频数量
videos_per_loop_max = config.VIDEOS_PER_LOOP_MAX  # 每轮最多刷视频数量

# 关注数量
follow_count_min = config.FOLLOW_COUNT_MIN
follow_count_max = config.FOLLOW_COUNT_MAX

# 评论区关键词
comment_keywords = config.KUAISHOU_COMMENT_KEYWORDS if config.KUAISHOU_COMMENT_KEYWORDS else []

# 优先关注评论关键词列表
comment_filter_keywords = config.COMMENT_FILTER_KEYWORDS if config.COMMENT_FILTER_KEYWORDS else []

# 评论区最小操作次数
comment_min_operation_count = config.COMMENT_MIN_OPERATION_COUNT
comment_max_operation_count = config.COMMENT_MAX_OPERATION_COUNT
# 评论区最小元素数量判断
comment_min_elements_count = config.COMMENT_MIN_ELEMENTS_COUNT
# 评论区最大元素数量判断
comment_max_elements_count = config.COMMENT_MAX_ELEMENTS_COUNT

# 全局退出标志
shutdown_event = threading.Event()

def thread_func(browser_name, browser, params, url_queue=None):
    """线程执行函数：运行单个浏览器任务"""
    try:
        # 将退出事件传递给任务函数
        params['shutdown_event'] = shutdown_event
        if params.get("use_video_url_mode"):
            if url_queue is None:
                logger.error(f"[{browser_name}] URL模式需要url_queue，但未提供")
                return
            browser_video_url_list_loop(
                params=params,
                browser=browser,
                url_queue=url_queue
            )
        else:
            browser_video_loop(
                params=params,
                browser=browser
            )
    except KeyboardInterrupt:
        logger.info(f"[{browser_name}] 线程收到中断信号，正在退出...")
        shutdown_event.set()
    except Exception as e:
        logger.error(f"[{browser_name}] 线程任务出错: {e}")

def main():
    """主函数：多线程模式启动浏览器任务"""
    browser_list = cluster.list_browsers()
    if not browser_list:
        logger.error("没有可用的浏览器")
        return
    
    # 监控线程会在 video_browser.py 中创建监控器时自动启动，这里不需要单独启动
    logger.info(f"{'='*50}")
    logger.info("监控线程将在浏览器任务中自动启动")
    
    # 检查视频URL模式（优先使用 URLS，如果没有则使用 KUAISHOU_VIDEO_URL）
    video_urls = getattr(config, 'URLS', None) or getattr(config, 'KUAISHOU_VIDEO_URL', [])
    use_video_url_mode = video_urls and len(video_urls) > 0
    url_queue: queue.Queue | None = queue.Queue() if use_video_url_mode else None
    if use_video_url_mode and url_queue is not None:
        for u in video_urls:
            try:
                url_queue.put_nowait(u)
            except Exception as e:
                logger.error(f"入队URL失败: {u} | {e}")
        
        # 检查URL数量与浏览器数量的关系
        browser_count = len([b for b in browser_list if (browser := cluster.get_browser(b)) and browser.driver])
        if len(video_urls) < browser_count:
            logger.warning(f"⚠ URL数量({len(video_urls)})少于浏览器数量({browser_count})，部分浏览器将无法分配到URL")
            logger.warning(f"   只有前 {len(video_urls)} 个浏览器会处理URL，其余浏览器将立即结束任务")
        elif len(video_urls) == browser_count:
            logger.info(f"✓ URL数量({len(video_urls)})等于浏览器数量({browser_count})，每个浏览器将处理一个URL")
        else:
            logger.info(f"✓ URL数量({len(video_urls)})大于浏览器数量({browser_count})，浏览器将依次处理多个URL")
    
    # 为每个浏览器创建线程
    threads = []
    for browser_key in browser_list:
        browser = cluster.get_browser(browser_key)
        if not (browser and browser.driver):
            continue
        display_name = cluster.get_browser_display_name(browser_key)
        
        # 封装参数（新增use_video_url_mode标识）
        follow_count = random.randint(follow_count_min, follow_count_max)
        browser_id = browser.id
        params = {
            "browser_name": display_name,
            "id": browser_id,
            "search_keywords": SEARCH_KEYWORDS,
            "main_loop_interval_min": main_loop_interval_min,
            "main_loop_interval_max": main_loop_interval_max,
            "action_interval_min": action_interval_min,
            "action_interval_max": action_interval_max,
            "scroll_interval_min": scroll_interval_min,
            "scroll_interval_max": scroll_interval_max,
            "videos_per_loop_min": videos_per_loop_min,
            "videos_per_loop_max": videos_per_loop_max,
            "follow_count": follow_count,
            "comment_keywords": comment_keywords,
            "comment_filter_keywords": comment_filter_keywords,  # 优先关注评论关键词列表
            "use_video_url_mode": use_video_url_mode,  # 新增：标识是否为URL模式
            "comment_min_operation_count": comment_min_operation_count,
            "comment_max_operation_count": comment_max_operation_count,
            "comment_min_elements_count": comment_min_elements_count,
            "comment_max_elements_count": comment_max_elements_count,
        }
        
        # 创建线程，目标函数为thread_func，传入参数
        # 设置为 daemon 线程，这样主程序退出时线程也会退出
        thread = threading.Thread(
            target=thread_func,
            args=(display_name, browser, params, url_queue),
            name=f"BrowserThread-{browser_key}",
            daemon=True  # 设置为守护线程，主程序退出时自动退出
        )
        threads.append(thread)
        thread.start()
        logger.info(f"[{display_name}] 线程已启动")
    
    if not threads:
        logger.error("没有可用的浏览器线程任务")
        return
    
    # 等待所有线程完成（使用超时，避免无限等待）
    try:
        while any(thread.is_alive() for thread in threads):
            # 检查是否有线程还在运行
            for thread in threads:
                if thread.is_alive():
                    thread.join(timeout=1)  # 每次等待1秒
                    if not thread.is_alive():
                        logger.info(f"线程 {thread.name} 已结束")
            # 如果所有线程都结束了，退出循环
            if not any(thread.is_alive() for thread in threads):
                break
    except KeyboardInterrupt:
        logger.warning("收到中断信号，正在停止所有线程...")
        shutdown_event.set()
        # 等待线程退出，最多等待5秒
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=5)
                if thread.is_alive():
                    logger.warning(f"线程 {thread.name} 未能及时退出（将强制退出）")
                else:
                    logger.info(f"线程 {thread.name} 已退出")


# ==================== 启动主流程 ====================
def signal_handler(signum, frame):
    """信号处理函数"""
    logger.warning("收到退出信号，正在关闭程序...")
    shutdown_event.set()
    kill_chrome_processes()
    sys.exit(0)

class KuaishouCrawler:
    def __init__(self):
        pass
    
    async def start(self):
        try:
            main()
        except KeyboardInterrupt:
            logger.warning("程序被用户中断（KeyboardInterrupt）")
            shutdown_event.set()
            kill_chrome_processes()
        except Exception as e:
            logger.error(f"程序发生错误: {e}")
            shutdown_event.set()
            kill_chrome_processes()
        finally:
            logger.info("正在清理资源...")
            shutdown_event.set()
            kill_chrome_processes()
            logger.info("程序已退出")

if __name__ == "__main__":
    # 注册信号处理器（Windows 不支持 SIGTERM，只支持 SIGINT）
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGTERM, signal_handler)  # Linux/Mac 支持
    except (AttributeError, ValueError):
        # Windows 不支持 SIGTERM，忽略错误
        pass
    
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("程序被用户中断（KeyboardInterrupt）")
        shutdown_event.set()
        kill_chrome_processes()
    except Exception as e:
        logger.error(f"程序发生错误: {e}")
        shutdown_event.set()
        kill_chrome_processes()
    finally:
        logger.info("正在清理资源...")
        shutdown_event.set()
        kill_chrome_processes()
        logger.info("程序已退出")
