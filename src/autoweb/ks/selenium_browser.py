from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import selenium
import requests
import requests.exceptions
import json
import os
import shutil
import platform
from datetime import datetime
from typing import Optional, Dict, Any
from ..tools import config
from ..tools import log as logger

class SeleniumBrowser:
    def __init__(self, save_dir='browser_sessions', proxy=None, chromedriver_path=None):
        """
        初始化浏览器控制器
        Args:
            save_dir: 保存登录状态的目录
            proxy: 代理配置，格式如 'http://host:port' 或 'socks5://host:port' 或 'http://user:pass@host:port'，None表示不使用代理（本地网络）
            chromedriver_path: ChromeDriver 的路径，如果为 None 则自动查找
        """
        self.driver = None
        self.id = None
        self.display_name: Optional[str] = None
        self.headers = {'Content-Type': 'application/json'}
        self.save_dir = save_dir
        # 创建 requests Session 以复用连接，解决连接池满的问题
        # pool_connections: 每个主机的连接池数量
        # pool_maxsize: 每个连接池的最大连接数
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        self.session = requests.Session()
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            pool_connections=10,  # 每个主机的连接池数量
            pool_maxsize=50,     # 每个连接池的最大连接数（增加到50以支持更多并发）
            max_retries=retry_strategy
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(self.headers)
        # 优先使用传入的proxy，其次从配置文件读取，最后为None（不使用代理）
        if proxy is not None:
            self.proxy = proxy
        elif hasattr(config, 'PROXY'):
            self.proxy = config.PROXY
        else:
            self.proxy = None
        # ChromeDriver 路径：优先使用传入的，其次从配置文件读取，最后自动查找
        if chromedriver_path:
            self.chromedriver_path = chromedriver_path
        elif hasattr(config, 'CHROMEDRIVER_PATH') and config.CHROMEDRIVER_PATH:
            self.chromedriver_path = config.CHROMEDRIVER_PATH
        else:
            self.chromedriver_path = None
        # 判断是否使用本地浏览器：如果 USE_BITBROWSER 为 False，或者 BITBROWSER_URL 为空，则使用本地浏览器
        use_bitbrowser = getattr(config, 'USE_BITBROWSER', False)
        # 确保保存目录存在
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
    
    def _find_chromedriver(self):
        """
        查找系统中的 ChromeDriver
        Returns:
            ChromeDriver 的路径，如果找不到返回 None
        """
        # 方法1: 检查系统 PATH 中是否有 chromedriver
        chromedriver_name = 'chromedriver.exe' if platform.system() == 'Windows' else 'chromedriver'
        chromedriver_path = shutil.which(chromedriver_name)
        if chromedriver_path and os.path.exists(chromedriver_path):
            logger.info(f"在系统 PATH 中找到 ChromeDriver: {chromedriver_path}")
            return chromedriver_path
        
        # 方法2: 检查项目目录
        project_dir = os.path.dirname(os.path.abspath(__file__))
        project_chromedriver = os.path.join(project_dir, chromedriver_name)
        if os.path.exists(project_chromedriver):
            logger.info(f"在项目目录中找到 ChromeDriver: {project_chromedriver}")
            return project_chromedriver
        
        # 方法3: 检查常见的 ChromeDriver 安装位置（Windows）
        if platform.system() == 'Windows':
            common_paths = [
                os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'chromedriver', chromedriver_name),
                os.path.join('C:', 'chromedriver', chromedriver_name),
                os.path.join('C:', 'Windows', 'System32', chromedriver_name),
            ]
            for path in common_paths:
                if os.path.exists(path):
                    logger.info(f"在常见位置找到 ChromeDriver: {path}")
                    return path
        
        return None

    def _create_local_browser(self, proxy=None):
        """
        创建本地浏览器实例
        Args:
            proxy: 代理配置，格式如 'http://host:port' 或 'socks5://host:port' 或 'http://user:pass@host:port'，None表示不使用代理
        Returns:
            webdriver.Chrome 实例
        """
        try:
            chrome_options = webdriver.ChromeOptions()
            
            # 添加代理配置
            if proxy:
                chrome_options.add_argument(f'--proxy-server={proxy}')
                logger.info(f"已配置代理: {proxy}")
            else:
                logger.info("使用本地网络（无代理）")
            
            # 使用轻量级启动参数
            # 禁用GPU加速（非图形界面环境必加，避免显卡资源浪费）
            chrome_options.add_argument("--disable-gpu")
            # 禁用扩展和插件（减少启动时的加载项）
            chrome_options.add_argument("--disable-extensions")
            # 禁用沙箱（Linux环境必填，Windows可选，提升启动速度）
            chrome_options.add_argument("--no-sandbox")
            # 禁用/dev/shm临时文件（解决内存限制导致的卡顿）
            chrome_options.add_argument("--disable-dev-shm-usage")
            # 关闭不必要的日志输出（减少IO操作）
            chrome_options.add_argument("--log-level=3")  # 只显示严重错误
            # 禁用首次运行检查（跳过浏览器首次启动的配置步骤）
            chrome_options.add_argument("--no-first-run")
            # 禁用默认应用（避免加载默认插件如PDF查看器）
            chrome_options.add_argument("--disable-default-apps")

            # 添加一些常用的Chrome选项
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # 尝试创建浏览器实例
            # 优先使用手动指定的路径，其次查找系统已有的，最后尝试自动下载
            driver_created = False
            chromedriver_path = self.chromedriver_path
            
            # 方法1: 使用手动指定的 ChromeDriver 路径
            if chromedriver_path and os.path.exists(chromedriver_path):
                try:
                    chrome_service = Service(chromedriver_path)
                    self.driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
                    logger.info(f"本地浏览器创建成功（使用指定的 ChromeDriver: {chromedriver_path}）")
                    driver_created = True
                except Exception as e:
                    logger.info(f"使用指定的 ChromeDriver 路径失败: {e}")
            
            # 方法2: 自动查找系统中的 ChromeDriver
            if not driver_created:
                found_path = self._find_chromedriver()
                if found_path:
                    try:
                        chrome_service = Service(found_path)
                        self.driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
                        logger.info(f"本地浏览器创建成功（使用找到的 ChromeDriver: {found_path}）")
                        driver_created = True
                    except Exception as e:
                        logger.info(f"使用找到的 ChromeDriver 失败: {e}")
            
            # 方法3: 尝试使用 Selenium 的内置驱动管理器（Selenium Manager）
            if not driver_created:
                try:
                    # Selenium 4.6+ 会自动下载和管理 ChromeDriver（需要网络）
                    self.driver = webdriver.Chrome(options=chrome_options)
                    logger.info("本地浏览器创建成功（使用 Selenium Manager）")
                    driver_created = True
                except Exception as e1:
                    logger.info(f"Selenium Manager 无法获取驱动: {e1}")
                    # 方法4: 尝试使用 webdriver-manager（需要网络）
                    try:
                        from webdriver_manager.chrome import ChromeDriverManager  # type: ignore[import]
                        chrome_service = Service(ChromeDriverManager().install())
                        self.driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
                        logger.info("本地浏览器创建成功（使用 webdriver-manager）")
                        driver_created = True
                    except ImportError:
                        pass  # webdriver-manager 未安装，跳过
                    except Exception as e2:
                        pass  # webdriver-manager 也失败，跳过
            
            # 如果所有方法都失败，提供清晰的错误提示
            if not driver_created:
                logger.info("\n" + "="*60)
                logger.info("错误: 无法创建浏览器，找不到 ChromeDriver")
                logger.info("="*60)
                logger.info("解决方案（选择其一）:")
                logger.info("  1. 手动下载 ChromeDriver:")
                logger.info("     - 访问: https://googlechromelabs.github.io/chrome-for-testing/")
                logger.info("     - 下载与您的 Chrome 版本匹配的驱动")
                logger.info("     - 将 chromedriver.exe 放到项目目录或添加到系统 PATH")
                logger.info("  2. 在代码中指定 ChromeDriver 路径:")
                logger.info("     selenium_browser = SeleniumBrowser(chromedriver_path='C:/path/to/chromedriver.exe')")
                logger.info("  3. 在 .env 文件中配置:")
                logger.info("     CHROMEDRIVER_PATH=C:/path/to/chromedriver.exe")
                logger.info("="*60 + "\n")
                raise Exception("无法创建浏览器: 找不到 ChromeDriver。请手动下载并配置 ChromeDriver。")
            
            return self.driver
        except Exception as e:
            logger.info(f"创建本地浏览器失败: {e}")
            raise

    def _open_control(self, id=None, proxy=None):
        """
        打开浏览器控制
        Args:
            id: 浏览器ID（使用指纹浏览器时需要）
            proxy: 代理配置（使用本地浏览器时生效），格式如 'http://host:port' 或 'socks5://host:port' 或 'http://user:pass@host:port'，None表示不使用代理
        Returns:
            包含driver和message的字典
        """
        # 使用指纹浏览器接口
        try:
            # 如果没有传入ID，从get_list获取列表并根据名称匹配
            browser_id = id
            if not browser_id:
                logger.info("未提供浏览器ID，正在从列表获取浏览器...")
                list_result = self.get_list()
                browser_list_data = list_result.get('data', [])
                
                if not browser_list_data or len(browser_list_data) == 0:
                    return {
                        'message': '未找到可用的浏览器，请先创建浏览器或提供浏览器ID'
                    }
                
                # 获取浏览器列表（可能是嵌套结构）
                if isinstance(browser_list_data, dict):
                    browser_list = browser_list_data.get('list', browser_list_data)
                else:
                    browser_list = browser_list_data
                
                if not browser_list or len(browser_list) == 0:
                    return {
                        'message': '浏览器列表为空，请先创建浏览器或提供浏览器ID'
                    }
                
                # 如果配置了浏览器名称列表，根据名称匹配
                browser_names = getattr(config, 'BITBROWSER_NAMES', [])
                if browser_names and len(browser_names) > 0:
                    logger.info(f"根据配置的浏览器名称列表查找: {browser_names}")
                    # 遍历浏览器列表，查找匹配名称的浏览器
                    for browser in browser_list:
                        browser_name = browser.get('name', '')
                        if browser_name in browser_names:
                            browser_id = browser.get('id') or browser.get('_id')
                            if browser_id:
                                logger.info(f"找到匹配的浏览器: {browser_name}, ID: {browser_id}")
                                break
                    
                    if not browser_id:
                        return {
                            'message': f'未找到匹配的浏览器，配置的名称: {browser_names}'
                        }
                else:
                    # 如果没有配置名称列表，使用第一个浏览器
                    first_browser = browser_list[0]
                    if isinstance(first_browser, dict):
                        browser_id = first_browser.get('id') or first_browser.get('_id')
                    else:
                        browser_id = str(first_browser)
                    
                    if not browser_id:
                        return {
                            'message': '无法从浏览器列表中获取ID'
                        }
                    
                    logger.info(f"使用列表中的第一个浏览器，ID: {browser_id}")
                
                self.id = browser_id
            
            json_data: Dict[str, Any] = {"id": f'{browser_id}'}
            # json_data["args"] = ["--headless"]
            json_data["queue"] = True
            json_data["ignoreDefaultUrls"] = True
            try:
                with self.session.post(f"http://127.0.0.1:54345/browser/open",
                                        data=json.dumps(json_data), timeout=10) as resp:
                    resp.raise_for_status()  # 抛出 HTTP 错误（4xx/5xx）
                    res = resp.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"打开浏览器请求失败: {e}")
                raise
            if 'msg' in res:
                logger.info(f"浏览器ID: {browser_id}, 错误信息: {res['msg']}")
                exit(1)
            driverPath = res['data']['driver']
            debuggerAddress = res['data']['http']

            # selenium 连接代码
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option("debuggerAddress", debuggerAddress)

            chrome_service = Service(driverPath)
            self.driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
            self.id = browser_id  # 保存浏览器ID
            return {
                'driver': self.driver,
                'name': res['data']['name'],
                'id': browser_id,
                'debuggerAddress': debuggerAddress,
                'driverPath': driverPath,
                'message': f'打开控制成功，浏览器ID: {browser_id}'
            }
        except Exception as e:
            logger.info(f"打开控制失败: {e}")
            return {
                'message': f'打开控制失败: {e},需求selenium版本到4.0及以上，请升级selenium版本'
            }

    def _close_control(self, id=None):
        """
        关闭浏览器控制
        Args:
            id: 浏览器ID（使用指纹浏览器时需要，本地浏览器时不需要）
        Returns:
            包含message的字典
        """
        # 使用指纹浏览器接口
        try:
            if not id:
                return {
                    'message': '使用指纹浏览器时需要提供浏览器ID'
                }
            
            json_data = {"id": f'{id}'}
            try:
                with self.session.post(f"http://127.0.0.1:54345/browser/close",
                                        data=json.dumps(json_data), timeout=10) as resp:
                    resp.raise_for_status()  # 抛出 HTTP 错误（4xx/5xx）
                    resp.json()  # 读取响应以确保连接关闭
            except requests.exceptions.RequestException as e:
                logger.error(f"关闭浏览器请求失败: {e}")
                # 即使请求失败，也返回成功消息，因为可能是浏览器已经关闭
            return {
                'message': '关闭控制成功'
            }
        except Exception as e:
            logger.info(f"关闭控制失败: {e}")
            return {
                'message': f'关闭控制失败: {e}'
            }

    def get_list(self):
        """
        获取浏览器列表（仅在使用指纹浏览器时有效）
        Returns:
            包含data和message的字典
        """
        
        try:
            json_data = {'page': 0, 'pageSize': 100}
            try:
                with self.session.post(f"http://127.0.0.1:54345/browser/list",
                                      data=json.dumps(json_data), timeout=10) as resp:
                    resp.raise_for_status()  # 抛出 HTTP 错误（4xx/5xx）
                    res = resp.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"获取浏览器列表请求失败: {e}")
                raise
            return {
                'data': res.get('data', None),
                'message': '获取浏览器列表成功'
            }
        except Exception as e:
            logger.info(f"获取浏览器列表失败: {e}")
            return {
                'data': None,
                'message': f'获取浏览器列表失败: {e}'
            }
    
    def get_browser_ids_by_names(self, browser_names: Optional[list] = None):
        """
        根据浏览器名称列表获取所有匹配的浏览器ID列表
        Args:
            browser_names: 浏览器名称列表，如果为None则从配置中读取
        Returns:
            匹配的浏览器ID列表，格式: [{'name': '浏览器名', 'id': '浏览器ID'}, ...]
        """
        try:
            # 如果没有传入名称列表，从配置中读取
            if browser_names is None:
                browser_names = getattr(config, 'BITBROWSER_NAMES', [])
            
            if not browser_names or len(browser_names) == 0:
                return []
            
            # 获取浏览器列表
            list_result = self.get_list()
            browser_list_data = list_result.get('data', [])
            
            if not browser_list_data:
                return []
            
            # 获取浏览器列表（可能是嵌套结构）
            if isinstance(browser_list_data, dict):
                browser_list = browser_list_data.get('list', browser_list_data)
            else:
                browser_list = browser_list_data
            
            if not browser_list:
                return []
            
            # 查找所有匹配的浏览器
            matched_browsers = []
            for browser in browser_list:
                browser_name = browser.get('name', '')
                if browser_name in browser_names:
                    browser_id = browser.get('id') or browser.get('_id')
                    if browser_id:
                        matched_browsers.append({
                            'name': browser_name,
                            'id': browser_id
                        })
            
            return matched_browsers
        except Exception as e:
            logger.info(f"获取浏览器ID列表失败: {e}")
            return []

    def close_tab(self, handle):
        """
        关闭指定句柄的标签页
        Args:
            handle: 要关闭的窗口句柄
        Returns:
            bool: 是否成功关闭标签页
        """
        try:
            if self.driver is None:
                logger.info("浏览器驱动未初始化")
                return False
            
            # 获取所有窗口句柄
            all_handles = self.driver.window_handles
            
            # 检查句柄是否存在
            if handle not in all_handles:
                logger.info(f"窗口句柄不存在: {handle}")
                return False
            
            # 如果只有一个窗口，不能关闭（会关闭整个浏览器）
            if len(all_handles) == 1:
                logger.info("不能关闭最后一个标签页")
                return False
            
            # 获取当前窗口句柄
            current_handle = self.driver.current_window_handle
            
            # 切换到要关闭的窗口
            self.driver.switch_to.window(handle)
            
            # 关闭当前窗口
            self.driver.close()
            
            # 如果关闭的不是当前窗口，需要切换回原来的窗口
            # 如果关闭的是当前窗口，需要切换到其他窗口
            remaining_handles = self.driver.window_handles
            if remaining_handles:
                # 如果原来的窗口还在，切换回去；否则切换到第一个可用窗口
                if current_handle in remaining_handles and current_handle != handle:
                    self.driver.switch_to.window(current_handle)
                else:
                    self.driver.switch_to.window(remaining_handles[0])
            
            logger.info(f"已关闭标签页: {handle}")
            return True
        except Exception as e:
            logger.info(f"关闭标签页失败: {e}")
            # 尝试切换回其他窗口，避免浏览器会话丢失
            try:
                if self.driver is not None:
                    remaining_handles = self.driver.window_handles
                    if remaining_handles:
                        self.driver.switch_to.window(remaining_handles[0])
            except:
                pass
            return False

    def switch_to_new_tab(self, path, wait_time=2, close_others=False):
        """
        切换到新打开的标签页
        Args:
            path: 需要切换的标签页路径内容
            wait_time: 等待新标签页打开的时间
            close_others: 是否关闭其他不匹配的标签页
        Returns:
            bool: 是否成功切换到新标签页
        """
        try:
            if self.driver is None:
                logger.info("浏览器驱动未初始化")
                return self.driver
            
            # 等待新标签页打开
            time.sleep(wait_time)
            
            # 获取所有窗口句柄
            all_handles = self.driver.window_handles
            current_handle = self.driver.current_window_handle
            
            # 如果有新标签页（窗口句柄数量大于1）
            if len(all_handles) > 1:
                found_tab = None
                handles_info = []
                
                # 遍历所有标签页，记录URL并寻找目标
                for handle in all_handles:
                    current_url = ""
                    try:
                        self.driver.switch_to.window(handle)
                        current_url = self.driver.current_url or ""
                    except Exception:
                        current_url = ""
                    handles_info.append((handle, current_url))
                    
                    if not found_tab and path in current_url:
                        found_tab = handle
                        logger.info(f"已找到包含 '{path}' 的标签页: {current_url}")
                
                # 如果找到了匹配的标签页
                if found_tab:
                    # 切换到目标标签页
                    self.driver.switch_to.window(found_tab)
                    logger.info(f"已切换到包含 '{path}' 的标签页")
                    
                    # 如果需要关闭其他不匹配的标签页
                    if close_others:
                        tabs_to_close = []
                        for handle, url in handles_info:
                            if handle == found_tab:
                                continue
                            if path not in url:
                                tabs_to_close.append(handle)
                        
                        for tab in tabs_to_close:
                            try:
                                self.close_tab(tab)
                            except Exception:
                                pass
                        
                        # 关闭后确保仍在目标标签页
                        try:
                            self.driver.switch_to.window(found_tab)
                        except Exception:
                            remaining = self.driver.window_handles
                            if remaining:
                                self.driver.switch_to.window(remaining[0])
                    
                    return self.driver
                else:
                    # 如果没有找到匹配的标签页，切换回原始窗口
                    if current_handle in all_handles:
                        self.driver.switch_to.window(current_handle)
                    logger.info(f"未找到包含 '{path}' 的标签页")
                    return self.driver
            else:
                logger.info("没有找到新标签页")
                return self.driver
        except Exception as e:
            logger.info(f"切换标签页失败: {e}")
            # 尝试切换回原始窗口
            try:
                if self.driver:
                    all_handles = self.driver.window_handles
                    if all_handles:
                        self.driver.switch_to.window(all_handles[0])
            except:
                pass
            return self.driver
    
    def save_login_state(self, domain: Optional[str] = None, browser_id: Optional[str] = None) -> bool:
        """
        保存当前浏览器的登录状态（Cookie和LocalStorage）
        Args:
            domain: 要保存的域名（如 'kuaishou.com'），如果为None则保存所有Cookie
            browser_id: 浏览器ID，用于生成保存文件名，如果为None则使用self.id
        Returns:
            是否保存成功
        """
        try:
            if self.driver is None:
                logger.info("浏览器驱动未初始化")
                return False
            
            browser_id = browser_id or self.id or "default"
            save_data = {
                'browser_id': browser_id,
                'domain': domain,
                'saved_at': datetime.now().isoformat(),
                'cookies': [],
                'local_storage': {},
                'session_storage': {}
            }
            
            # 保存 Cookie
            if domain:
                # 只保存指定域名的Cookie
                cookies = self.driver.get_cookies()
                for cookie in cookies:
                    if domain in cookie.get('domain', ''):
                        save_data['cookies'].append(cookie)
            else:
                # 保存所有Cookie
                save_data['cookies'] = self.driver.get_cookies()
            
            # 保存 LocalStorage 和 SessionStorage
            try:
                # 获取当前URL的域名
                current_url = self.driver.current_url
                if current_url and current_url.startswith('http'):
                    from urllib.parse import urlparse
                    parsed = urlparse(current_url)
                    target_domain = parsed.netloc
                    
                    # 执行JavaScript获取LocalStorage和SessionStorage
                    local_storage = self.driver.execute_script(
                        "return Object.keys(localStorage).reduce((obj, key) => {"
                        "  obj[key] = localStorage.getItem(key);"
                        "  return obj;"
                        "}, {});"
                    )
                    session_storage = self.driver.execute_script(
                        "return Object.keys(sessionStorage).reduce((obj, key) => {"
                        "  obj[key] = sessionStorage.getItem(key);"
                        "  return obj;"
                        "}, {});"
                    )
                    
                    save_data['local_storage'] = local_storage or {}
                    save_data['session_storage'] = session_storage or {}
                    save_data['target_domain'] = target_domain
            except Exception as e:
                logger.info(f"保存LocalStorage/SessionStorage失败: {e}")
            
            # 保存到文件
            filename = f"{browser_id}_{domain or 'all'}.json"
            filepath = os.path.join(self.save_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"登录状态已保存到: {filepath}")
            logger.info(f"保存了 {len(save_data['cookies'])} 个Cookie")
            return True
            
        except Exception as e:
            logger.info(f"保存登录状态失败: {e}")
            return False
    
    def restore_login_state(self, domain: Optional[str] = None, browser_id: Optional[str] = None) -> bool:
        """
        恢复浏览器的登录状态
        Args:
            domain: 要恢复的域名，如果为None则尝试恢复所有
            browser_id: 浏览器ID，用于查找保存的文件，如果为None则使用self.id
        Returns:
            是否恢复成功
        """
        try:
            if self.driver is None:
                logger.info("浏览器驱动未初始化")
                return False
            
            browser_id = browser_id or self.id or "default"
            filename = f"{browser_id}_{domain or 'all'}.json"
            filepath = os.path.join(self.save_dir, filename)
            
            if not os.path.exists(filepath):
                logger.info(f"未找到保存的登录状态文件: {filepath}")
                return False
            
            # 读取保存的数据
            with open(filepath, 'r', encoding='utf-8') as f:
                save_data = json.load(f)
            
            # 恢复Cookie
            cookies_restored = 0
            target_domain = save_data.get('target_domain')
            
            # 如果保存了目标域名，先导航到该域名（必须先访问域名才能添加Cookie）
            if target_domain:
                try:
                    # 尝试使用https，如果失败则使用http
                    try:
                        self.driver.get(f"https://{target_domain}")
                    except:
                        self.driver.get(f"http://{target_domain}")
                    time.sleep(1)
                except Exception as e:
                    logger.info(f"导航到目标域名失败: {e}")
                    # 如果无法导航，尝试从Cookie中获取域名
                    if save_data.get('cookies'):
                        first_cookie = save_data['cookies'][0]
                        cookie_domain = first_cookie.get('domain', '')
                        if cookie_domain:
                            try:
                                self.driver.get(f"https://{cookie_domain.lstrip('.')}")
                                time.sleep(1)
                            except:
                                pass
            
            for cookie in save_data.get('cookies', []):
                try:
                    # 移除可能导致问题的字段
                    cookie_to_add = cookie.copy()
                    # 移除这些字段，Selenium会自动处理
                    cookie_to_add.pop('sameSite', None)
                    cookie_to_add.pop('storeId', None)
                    
                    self.driver.add_cookie(cookie_to_add)
                    cookies_restored += 1
                except Exception as e:
                    logger.info(f"恢复Cookie失败: {cookie.get('name', 'unknown')} - {e}")
            
            # 恢复LocalStorage和SessionStorage
            try:
                local_storage = save_data.get('local_storage', {})
                session_storage = save_data.get('session_storage', {})
                
                if local_storage:
                    for key, value in local_storage.items():
                        try:
                            self.driver.execute_script(
                                f"localStorage.setItem('{key}', {json.dumps(value)});"
                            )
                        except:
                            # 如果值不是JSON格式，直接作为字符串
                            self.driver.execute_script(
                                f"localStorage.setItem('{key}', {json.dumps(str(value))});"
                            )
                
                if session_storage:
                    for key, value in session_storage.items():
                        try:
                            self.driver.execute_script(
                                f"sessionStorage.setItem('{key}', {json.dumps(value)});"
                            )
                        except:
                            self.driver.execute_script(
                                f"sessionStorage.setItem('{key}', {json.dumps(str(value))});"
                            )
            except Exception as e:
                logger.info(f"恢复LocalStorage/SessionStorage失败: {e}")
            
            # 刷新页面使Cookie生效
            if target_domain:
                try:
                    self.driver.refresh()
                    time.sleep(1)
                except:
                    pass
            
            logger.info(f"已恢复登录状态: {cookies_restored} 个Cookie")
            return True
            
        except Exception as e:
            logger.info(f"恢复登录状态失败: {e}")
            return False
    
    def check_login_status(self, login_indicator: Optional[str] = None) -> bool:
        """
        检查是否已登录
        Args:
            login_indicator: 登录状态的标识（如特定的URL、元素等），如果为None则检查当前URL
        Returns:
            是否已登录
        """
        try:
            if self.driver is None:
                return False
            
            current_url = self.driver.current_url
            
            # 如果提供了登录标识，检查是否包含
            if login_indicator:
                return login_indicator in current_url
            
            # 默认检查：如果不在登录页面，可能已登录
            login_keywords = ['login', 'signin', 'sign-in', '登录']
            return not any(keyword in current_url.lower() for keyword in login_keywords)
            
        except Exception as e:
            logger.info(f"检查登录状态失败: {e}")
            return False

