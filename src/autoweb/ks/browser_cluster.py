import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import List, Dict, Callable, Any, Optional
from .selenium_browser import SeleniumBrowser
import time
from functools import partial
from ..tools import log as logger
from ..tools import ks_config as config

class BrowserCluster:
    """浏览器集群控制类：用一个线程控制多个浏览器"""
    
    def __init__(self, max_workers: int = 5):
        """
        初始化浏览器集群
        Args:
            max_workers: 最大并发线程数
        """
        self.browsers: Dict[str, SeleniumBrowser] = {}
        self.max_workers = max_workers
        self.lock = threading.Lock()
    
    def add_browser(self, browser_id: str, browser: Optional[SeleniumBrowser] = None, display_name: Optional[str] = None) -> bool:
        """
        添加浏览器到集群
        Args:
            browser_id: 浏览器唯一标识（可以是账号名或浏览器ID）
            browser: SeleniumBrowser实例，如果为None则创建新实例
        Returns:
            是否添加成功
        """
        try:
            with self.lock:
                if browser_id in self.browsers:
                    logger.info(f"浏览器 '{browser_id}' 已存在")
                    return False
                
                if browser is None:
                    browser = SeleniumBrowser()
                
                self.browsers[browser_id] = browser
                if display_name:
                    browser.display_name = display_name
                elif not getattr(browser, 'display_name', None):
                    browser.display_name = browser_id
                logger.info(f"已添加浏览器 '{browser_id}' 到集群")
                return True
        except Exception as e:
            logger.info(f"添加浏览器失败: {e}")
            return False
    
    def remove_browser(self, browser_id: str, browser_name: Optional[str] = None, close_browser: bool = False) -> bool:
        """
        从集群中移除浏览器
        Args:
            browser_id: 浏览器标识
            close_browser: 是否关闭浏览器
        Returns:
            是否移除成功
        """
        key = str(browser_name) or str(browser_id)
        if not key:
            logger.info("无法移除浏览器：未提供有效的浏览器标识")
            return False
        try:
            with self.lock:
                browser = self.browsers.get(key)
                if not browser:
                    logger.info(f"浏览器 '{key}' 不存在")
                    return False

                if close_browser and browser.id:
                    try:
                        browser._close_control(browser.id)
                    except Exception as close_error:
                        logger.info(f"关闭浏览器 '{key}' 失败: {close_error}")

                del self.browsers[key]
                logger.info(f"已从集群中移除浏览器 '{key}'")
                return True
        except Exception as e:
            logger.info(f"移除浏览器失败: {e}")
            return False
    
    def get_browser(self, browser_id: str) -> Optional[SeleniumBrowser]:
        """获取指定浏览器实例"""
        return self.browsers.get(browser_id)
    
    def list_browsers(self) -> List[str]:
        """获取所有浏览器ID列表"""
        return list(self.browsers.keys())
    
    def get_browser_display_name(self, browser_id: str) -> str:
        """获取浏览器的展示名称"""
        browser = self.browsers.get(browser_id)
        if not browser:
            return browser_id
        display_name = getattr(browser, 'display_name', None)
        return display_name or browser_id
    
    def open_browsers(self, browser_ids: List[str]) -> Dict[str, bool]:
        """
        批量打开浏览器
        Args:
            browser_ids: 浏览器ID列表
        Returns:
            每个浏览器的打开结果
        """
        results = {}
        
        def open_single(browser_id):
            try:
                browser = self.browsers.get(browser_id)
                if browser is None:
                    return browser_id, False, "浏览器不存在"
                time.sleep(3)
                if browser.driver is None:
                    result = browser._open_control(browser_id)
                    return browser_id, result.get('driver') is not None, result.get('message', '')
                else:
                    return browser_id, True, "浏览器已打开"
            except Exception as e:
                return browser_id, False, str(e)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(open_single, bid): bid for bid in browser_ids}
            
            for future in as_completed(futures):
                browser_id, success, message = future.result()
                results[browser_id] = success
                if not success:
                    logger.info(f"打开浏览器 '{browser_id}' 失败: {message}")
        
        return results
    
    def init_browsers_by_names(self, browser_names: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        根据浏览器名称列表初始化并启动多个浏览器
        Args:
            browser_names: 浏览器名称列表，如果为None则从配置中读取
        Returns:
            每个浏览器的初始化结果，包含 name/id/success/message
        """
        
        # 如果没有传入名称列表，从配置中读取
        if browser_names is None:
            browser_names = getattr(config, 'KUAISHOU_BROWSER_NAMES', [])
        
        if not browser_names or len(browser_names) == 0:
            logger.info("未配置浏览器名称列表")
            return {}
        
        logger.info(f"准备初始化浏览器: {browser_names}")
        
        # 获取第一个浏览器实例来调用获取ID列表的方法
        first_browser = None
        if len(self.browsers) > 0:
            first_browser = list(self.browsers.values())[0]
        else:
            first_browser = SeleniumBrowser()
        
        # 获取所有匹配的浏览器ID
        matched_browsers = first_browser.get_browser_ids_by_names(browser_names)
        
        if not matched_browsers:
            logger.info(f"未找到匹配的浏览器，配置的名称: {browser_names}")
            return {}
        
        logger.info(f"找到 {len(matched_browsers)} 个匹配的浏览器")
        
        # 为每个浏览器创建实例并添加到集群
        results: Dict[str, Dict[str, Any]] = {}
        for browser_info in matched_browsers:
            browser_name = browser_info['name']
            browser_id = browser_info['id']
            # 创建新的浏览器实例
            browser = SeleniumBrowser()
            browser.id = browser_id  # 设置浏览器ID
            
            entry = {
                'name': browser_name,
                'id': browser_id,
                'success': False,
                'message': ''
            }
            
            # 添加到集群
            if self.add_browser(browser_name, browser, display_name=browser_name):
                # 打开浏览器
                time.sleep(3)
                result = browser._open_control(browser_id)
                success = result.get('driver') is not None
                entry['success'] = success
                entry['message'] = result.get('message', '')
                
                if success:
                    logger.info(f"✓ 浏览器 '{browser_name}' (ID: {browser_id}) 启动成功")
                else:
                    logger.info(f"✗ 浏览器 '{browser_name}' (ID: {browser_id}) 启动失败: {entry['message']}")
            else:
                entry['message'] = "浏览器已存在于集群"
                logger.info(f"✗ 浏览器 '{browser_name}' (ID: {browser_id}) 添加失败: {entry['message']}")
            
            results[browser_name] = entry
        
        return results

    def init_browsers_by_ids(self, browser_ids: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        根据浏览器ID列表初始化并启动多个浏览器
        Args:
            browser_ids: 浏览器ID列表，如果为None则从配置中读取
        Returns:
            每个浏览器的初始化结果（键为浏览器ID），包含 name/id/success/message
        """
        from ..tools import ks_config as config

        if browser_ids is None:
            browser_ids = getattr(config, 'KUAISHOU_BROWSER_IDS', [])

        cleaned_ids = []
        for browser_id in browser_ids or []:
            browser_id_str = str(browser_id).strip()
            if browser_id_str:
                cleaned_ids.append(browser_id_str)

        if not cleaned_ids:
            logger.info("未配置浏览器ID列表")
            return {}

        logger.info(f"准备根据ID初始化浏览器: {cleaned_ids}")

        # 获取ID到名称的映射
        name_map: Dict[str, Optional[str]] = {}
        info_browser = list(self.browsers.values())[0] if self.browsers else SeleniumBrowser()
        list_result = info_browser.get_list()
        browser_list_data = list_result.get('data', []) if isinstance(list_result, dict) else []
        if isinstance(browser_list_data, dict):
            browser_iterable = browser_list_data.get('list', browser_list_data)
        else:
            browser_iterable = browser_list_data
        if isinstance(browser_iterable, list):
            for browser_info in browser_iterable:
                browser_unique_id = browser_info.get('id') or browser_info.get('_id')
                browser_name = browser_info.get('name')
                if browser_unique_id:
                    name_map[str(browser_unique_id)] = browser_name

        results: Dict[str, Dict[str, Any]] = {}
        for browser_id in cleaned_ids:
            browser = SeleniumBrowser()
            entry = {
                'name': name_map.get(browser_id),
                'id': browser_id,
                'success': False,
                'message': ''
            }
            display_name = entry['name'] or browser_id
            browser.display_name = display_name
            time.sleep(3)
            if self.add_browser(browser_id, browser, display_name=display_name):
                result = browser._open_control(browser_id)
                success = result.get('driver') is not None
                entry['success'] = success
                entry['message'] = result.get('message', '')

                display_name = entry['name'] or browser_id
                if success:
                    logger.info(f"✓ 浏览器 '{display_name}' (ID: {browser_id}) 启动成功")
                else:
                    logger.info(f"✗ 浏览器 '{display_name}' (ID: {browser_id}) 启动失败: {entry['message']}")
            else:
                entry['message'] = "浏览器已存在于集群"
                logger.info(f"✗ 浏览器 (ID: {browser_id}) 添加失败: {entry['message']}")

            results[browser_id] = entry

        return results

    
    def execute_all(self, func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """
        在所有浏览器上执行相同函数
        Args:
            func: 要执行的函数，第一个参数必须是driver或browser
            *args: 函数的位置参数
            **kwargs: 函数的关键字参数
        Returns:
            每个浏览器的执行结果
        """
        results = {}
        
        def execute_single(browser_id, browser):
            try:
                # 如果函数需要driver，传入driver；否则传入browser
                if browser.driver is None:
                    return browser_id, None, "浏览器未打开"
                
                # 检查函数签名，决定传入driver还是browser
                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                
                if len(params) > 0 and params[0] == 'driver':
                    result = func(browser.driver, *args, **kwargs)
                else:
                    result = func(browser, *args, **kwargs)
                
                return browser_id, result, None
            except Exception as e:
                return browser_id, None, str(e)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(execute_single, bid, browser): bid 
                for bid, browser in self.browsers.items()
            }
            
            for future in as_completed(futures):
                browser_id, result, error = future.result()
                if error:
                    logger.info(f"浏览器 '{browser_id}' 执行失败: {error}")
                results[browser_id] = {'result': result, 'error': error}
        
        return results
    
    def execute_batch(self, tasks: List[Dict], timeout: int = 300) -> Dict[str, Any]:
        """
        批量执行不同任务
        Args:
            tasks: 任务列表，每个任务格式: {
                'browser_id': '浏览器ID',
                'func': 要执行的函数,
                'args': 位置参数列表,
                'kwargs': 关键字参数字典,
                'timeout': 可选，单个任务的超时时间（秒）
            }
            timeout: 全局超时时间（秒）
        Returns:
            每个任务的执行结果
        """
        def execute_task(task):
            browser_id = task.get('browser_id')
            func = task.get('func')
            args = task.get('args', [])
            kwargs = task.get('kwargs', {})
            task_timeout = task.get('timeout', timeout)
            
            try:
                with self.lock:
                    browser = self.browsers.get(browser_id)
                    if browser is None:
                        return browser_id, None, f"浏览器 '{browser_id}' 不存在"
                    
                    if browser.driver is None:
                        return browser_id, None, f"浏览器 '{browser_id}' 未打开"
                
                # 使用带超时的函数执行
                try:
                    result = self._execute_with_timeout(
                        func, 
                        browser, 
                        *args, 
                        timeout=task_timeout,
                        **kwargs
                    )
                    return browser_id, result, None
                except TimeoutError:
                    return browser_id, None, f"任务执行超时（{task_timeout}秒）"
                    
            except Exception as e:
                import traceback
                error_msg = f"{str(e)}\n{traceback.format_exc()}"
                return browser_id, None, error_msg
        
        results = {}
        futures = []
        
        # 使用线程池执行任务
        with ThreadPoolExecutor(max_workers=len(tasks) or 1) as executor:
            # 提交所有任务
            for task in tasks:
                future = executor.submit(execute_task, task)
                futures.append(future)
            
            # 等待所有任务完成或超时
            try:
                for future in as_completed(futures, timeout=timeout):
                    browser_id, result, error = future.result()
                    if browser_id:  # 确保browser_id存在
                        if error:
                            logger.info(f"任务执行失败 ({browser_id}): {error}")
                        results[browser_id] = {'result': result, 'error': error}
            except TimeoutError:
                # 处理全局超时
                logger.info(f"警告：全局任务执行超时（{timeout}秒）")
                # 返回已完成的或部分完成的结果
                for f in futures:
                    if f.done() and not f.cancelled():
                        try:
                            browser_id, result, error = f.result()
                            if browser_id:
                                results[browser_id] = {'result': result, 'error': error}
                        except:
                            pass
        
        return results
    
    def _execute_with_timeout(self, func, *args, timeout=300, **kwargs):
        """
        带超时执行的辅助方法
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            timeout: 超时时间（秒）
            **kwargs: 关键字参数
        
        Returns:
            函数执行结果
        
        Raises:
            TimeoutError: 如果函数执行超时
        """
        import concurrent.futures
        import functools
        
        # 创建一个线程池执行器
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            # 提交任务到线程池
            future = executor.submit(functools.partial(func, *args, **kwargs))
            try:
                # 等待任务完成或超时
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                # 取消任务
                future.cancel()
                # 记录超时错误
                error_msg = f"操作超时（{timeout}秒）"
                logger.info(error_msg)
                raise TimeoutError(error_msg)
            except Exception as e:
                # 重新抛出其他异常
                raise

    def close_all(self):
        """关闭所有浏览器"""
        for browser_id, browser in list(self.browsers.items()):
            try:
                if browser.driver and browser.id:
                    browser._close_control(browser.id)
            except Exception as e:
                logger.info(f"关闭浏览器 '{browser_id}' 失败: {e}")
    
    def get_status(self) -> Dict[str, Dict]:
        """
        获取所有浏览器的状态
        Returns:
            浏览器状态字典
        """
        status = {}
        for browser_id, browser in self.browsers.items():
            status[browser_id] = {
                'has_driver': browser.driver is not None,
                'browser_id': browser.id,
                'current_url': browser.driver.current_url if browser.driver else None
            }
        return status
    
    def wait_all_complete(self, timeout: int = 300):
        """
        等待所有浏览器任务完成
        Args:
            timeout: 超时时间（秒）
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            all_idle = True
            for browser in self.browsers.values():
                if browser.driver:
                    # 检查是否有活动窗口
                    try:
                        handles = browser.driver.window_handles
                        if handles:
                            all_idle = False
                            break
                    except:
                        pass
            
            if all_idle:
                break
            time.sleep(1)
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动关闭所有浏览器"""
        self.close_all()
        return False


# 全局集群实例，可以直接导入使用
# 使用示例：
#   from browser_cluster import cluster
#   cluster.add_browser("浏览器ID", SeleniumBrowser())
#   cluster.open_browsers(["浏览器ID"])

# 初始化浏览器集群
cluster = BrowserCluster(max_workers=config.BROWSER_MAX_WORKERS)