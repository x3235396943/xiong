from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Base(BaseSettings):
    SIBERIAN_URL: str
    SIBERIAN_KEY: str
    DEVICE_CODE: str
    PLATFORM: str


class KuSettings(Base):
    LIKE_PROBABILITY: int = 30  # 点赞概率 (0-100)
    VISIT_ENABLE: int = 10  # 进入主页的概率 (0-100)
    PROFILE_FOLLOW_PROBABILITY: int = 10  # 进入主页后关注的概率 (0-100)
    ENABLE_FOLLOW: bool = True  # 是否启用关注功能
    ENABLE_LIKE: bool = False  # 是否启用点赞功能
    ENABLE_SEARCH_KEYWORDS: bool = False  # 是否启用搜索关键字功能
    ENABLE_COMMENT_REPLY: bool = False  # 是否启用评论回复功能
    ENABLE_VIDEO_COMMENT: bool = False  # 是否启用视频留言功能
    ENABLE_COMMENT_TEMPLATES: bool = False  # 是否启用评论话术功能
    COMMENT_REPLIES: str  # 回复评论的内容
    VIDEO_COMMENTS: str  # 视频留言的内容
    COMMENT_FILTER_KEYWORDS: list = []  # 筛选评论区关键字

    # 新增的概率参数
    COMMENT_REPLY_PROBABILITY: int = 5  # 评论回复概率 (0-100)
    VIDEO_REPLY_RATE: int = 20  # 视频留言概率 (0-100)

    MIN_FOLLOWS_PER_VIDEO: int = 5  # 每条视频最少关注数量
    MAX_FOLLOWS_PER_VIDEO: int = 15  # 每条视频最多关注数量

    COMMENT_LIKE_COUNT_MIN: int = 5  # 每条视频最少点赞数量
    COMMENT_LIKE_COUNT_MAX: int = 15  # 每条视频最多点赞数量

    # 等待时间参数
    LIKE_WAIT_MIN: int = 4  # 点赞后最小等待时间（秒）
    LIKE_WAIT_MAX: int = 10  # 点赞后最大等待时间（秒）
    VISIT_MIN: int = 2  # 关注后最小等待时间（秒）
    VISIT_MAX: int = 5  # 关注后最大等待时间（秒）

    # 留言/回复等待时间参数
    VIDEO_REPLY_WAIT_MIN: int = 12  # 视频留言前最小等待时间（秒）
    VIDEO_REPLY_WAIT_MAX: int = 12  # 视频留言前最大等待时间（秒）
    COMMENT_WAIT_MIN: int = 12  # 评论回复前最小等待时间（秒）
    COMMENT_WAIT_MAX: int = 12  # 评论回复前最大等待时间（秒）

    # 数据库路径
    LINKS_DB_PATH: str = "links.db"
    # 本地导入链接
    URLS: list = []
    # 链接索引
    URL_INDEX: list = []
    # 其他设置
    WAIT_TIME: int = 10  # 等待元素出现的时间（秒）
    HEADLESS: bool = False  # 是否以无头模式运行浏览器(T or F)
    DEBUG: bool = False  # 是否输出调试信息（打印所有配置参数）

    BIT_BROWSER_IDS: list = []

    VERSION: str = "1.1.2"

    @field_validator(
        "MIN_FOLLOWS_PER_VIDEO",
        "MAX_FOLLOWS_PER_VIDEO",
        "COMMENT_LIKE_COUNT_MIN",
        "COMMENT_LIKE_COUNT_MAX",
        mode="after",
    )
    @classmethod
    def validate_min_max_pairs(cls, v, info):
        # 验证关注和点赞的最小最大值对
        field_name = info.field_name
        if field_name == "MAX_FOLLOWS_PER_VIDEO" and hasattr(
            cls, "MIN_FOLLOWS_PER_VIDEO"
        ):
            if v < cls.MIN_FOLLOWS_PER_VIDEO:
                raise ValueError(
                    f"MAX_FOLLOWS_PER_VIDEO ({v}) must be greater than or equal to MIN_FOLLOWS_PER_VIDEO ({cls.MIN_FOLLOWS_PER_VIDEO})"
                )
        elif field_name == "COMMENT_LIKE_COUNT_MAX" and hasattr(
            cls, "COMMENT_LIKE_COUNT_MIN"
        ):
            if v < cls.COMMENT_LIKE_COUNT_MIN:
                raise ValueError(
                    f"COMMENT_LIKE_COUNT_MAX ({v}) must be greater than or equal to COMMENT_LIKE_COUNT_MIN ({cls.COMMENT_LIKE_COUNT_MIN})"
                )
        return v

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")


config = KuSettings()  # type: ignore




import os
import json
import ast
from pathlib import Path
from typing import Any

def _parse_list_env(env_value: str | None, *, item_type=str) -> list:
    """解析环境变量中的列表字符串，支持 JSON、Python 列表或逗号分隔格式"""
    if not env_value:
        return []

    value = env_value.strip()
    if not value:
        return []
    if value.lower() in {'none', 'null'}:
        return []

    # 优先尝试解析 JSON 格式
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [item_type(item) if item_type is not str else str(item) for item in parsed]
        if isinstance(parsed, (str, int, float)):
            return [item_type(parsed) if item_type is not str else str(parsed)]
    except Exception:
        pass

    # 尝试解析 Python 字面量列表
    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, list):
            return [item_type(item) if item_type is not str else str(item) for item in parsed]
        if isinstance(parsed, (str, int, float)):
            return [item_type(parsed) if item_type is not str else str(parsed)]
    except Exception:
        pass

    # 回退到逗号分隔
    items = [item.strip() for item in value.split(',') if item.strip()]
    if item_type is not str:
        converted = []
        for item in items:
            try:
                converted.append(item_type(item))
            except Exception:
                continue
        return converted
    return items


def _get_env_value(key: str, default=None):
    """从环境变量读取配置值"""
    value = os.getenv(key)
    if value is None:
        return default
    return value


def _to_int(value, default: int) -> int:
    """将值转换为整数类型"""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float) -> float:
    """将值转换为浮点数类型"""
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value, default: bool) -> bool:
    """将值转换为布尔类型"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value_lower = value.strip().lower()
        if value_lower in {'true', 'yes', 'on', '1'}:
            return True
        if value_lower in {'false', 'no', 'off', '0', ''}:
            return False
    return default


class Config:
    """配置类：从 .env 环境变量读取配置"""
    
    # ==================== 卡密验证配置 ====================
    SIBERIAN_URL = str(_get_env_value('SIBERIAN_URL', '') or '')
    SIBERIAN_KEY = str(_get_env_value('SIBERIAN_KEY', '') or '')
    DEVICE_CODE = str(_get_env_value('DEVICE_CODE', '') or '')
    
    # ==================== 网页路径配置 ====================
    DEFAULT_PATH = str(_get_env_value('DEFAULT_PATH', '') or '')
    SEARCH_PATH = str(_get_env_value('SEARCH_PATH', '') or '')
    
    # ==================== BitBrowser 配置 ====================
    # 是否使用比特浏览器功能
    USE_BITBROWSER = _to_bool(_get_env_value('USE_BITBROWSER', None), False)
    
    BITBROWSER_URL = str(_get_env_value('BITBROWSER_URL', '') or '')
    
    # 浏览器名称列表（BITBROWSER_NAMES），格式: '快手002,快手003' 或 '["快手002","快手003"]'
    _browser_names_source = _get_env_value('BITBROWSER_NAMES', None)
    if isinstance(_browser_names_source, list):
        BITBROWSER_NAMES = [str(name).strip() for name in _browser_names_source if str(name).strip()]
    else:
        _browser_names_env = str(_browser_names_source or '')
        if _browser_names_env.strip():
            try:
                BITBROWSER_NAMES = json.loads(_browser_names_env)
                if not isinstance(BITBROWSER_NAMES, list):
                    BITBROWSER_NAMES = [BITBROWSER_NAMES]
            except Exception:
                BITBROWSER_NAMES = [name.strip() for name in _browser_names_env.split(',') if name.strip()]
        else:
            BITBROWSER_NAMES = []

    # 浏览器ID列表（BIT_BROWSER_IDS），支持 JSON、Python 列表或逗号分隔字符串
    _browser_ids_source = _get_env_value('BIT_BROWSER_IDS', None)
    if isinstance(_browser_ids_source, list):
        BIT_BROWSER_IDS = [str(browser_id).strip() for browser_id in _browser_ids_source if str(browser_id).strip()]
    else:
        _browser_ids_env = str(_browser_ids_source or '')
        if _browser_ids_env.strip():
            BIT_BROWSER_IDS = _parse_list_env(_browser_ids_env, item_type=str)
            BIT_BROWSER_IDS = [browser_id.strip() for browser_id in BIT_BROWSER_IDS if browser_id.strip()]
        else:
            BIT_BROWSER_IDS = []
    
    # ==================== 浏览器基础配置 ====================
    BROWSER_SAVE_DIR = str(_get_env_value('BROWSER_SAVE_DIR', 'browser_sessions') or 'browser_sessions')
    BROWSER_MAX_WORKERS = _to_int(_get_env_value('BROWSER_MAX_WORKERS', None), 5)
    RUN_BROWSER_IN_BACKGROUND = _to_bool(_get_env_value('RUN_BROWSER_IN_BACKGROUND', None), False)
    
    # ==================== 网络代理配置 ====================
    # 单个代理（兼容旧配置）
    _network_proxy_value = _get_env_value('NETWORK_PROXY', None)
    if isinstance(_network_proxy_value, str):
        _network_proxy_value = _network_proxy_value.strip()
    NETWORK_PROXY = _network_proxy_value if _network_proxy_value else None
    
    # 多个代理配置，支持列表、JSON 或逗号分隔
    _network_proxies_source = _get_env_value('NETWORK_PROXIES', None)
    if isinstance(_network_proxies_source, list):
        raw_proxies = list(_network_proxies_source)
    else:
        raw_proxies = _parse_list_env(str(_network_proxies_source), item_type=str) if _network_proxies_source else []

    cleaned_proxies = []
    for item in raw_proxies:
        if item is None:
            cleaned_proxies.append(None)
            continue
        item_str = str(item).strip()
        if not item_str or item_str == '0':
            cleaned_proxies.append(None)
        else:
            cleaned_proxies.append(item_str)
    NETWORK_PROXIES = cleaned_proxies
    
    # ==================== 驱动配置 ====================
    DRIVER_CHROMEDRIVER_PATH = str(_get_env_value('DRIVER_CHROMEDRIVER_PATH', '') or '').strip()
    if not DRIVER_CHROMEDRIVER_PATH:
        DRIVER_CHROMEDRIVER_PATH = None
    
    # ==================== 快手基础配置 ====================
    KUAISHOU_URL = str(_get_env_value('KUAISHOU_URL', 'https://www.kuaishou.com') or 'https://www.kuaishou.com')
    
    # ==================== 视频浏览时间配置（单位：秒） ====================
    VIDEO_INPUT_DELAY_MIN = _to_float(_get_env_value('VIDEO_INPUT_DELAY_MIN', None), 0.1)
    VIDEO_INPUT_DELAY_MAX = _to_float(_get_env_value('VIDEO_INPUT_DELAY_MAX', None), 0.3)
    VIDEO_IMPLICIT_WAIT = _to_int(_get_env_value('VIDEO_IMPLICIT_WAIT', None), 10)
    VIDEO_PAGE_LOAD_WAIT = _to_int(_get_env_value('VIDEO_PAGE_LOAD_WAIT', None), 2)
    VIDEO_MAIN_LOOP_INTERVAL_MIN = _to_float(_get_env_value('VIDEO_MAIN_LOOP_INTERVAL_MIN', None), 3600)
    VIDEO_MAIN_LOOP_INTERVAL_MAX = _to_float(_get_env_value('VIDEO_MAIN_LOOP_INTERVAL_MAX', None), 3601)
    VIDEO_ACTION_INTERVAL_MIN = _to_float(_get_env_value('VIDEO_ACTION_INTERVAL_MIN', None), 15)
    VIDEO_ACTION_INTERVAL_MAX = _to_float(_get_env_value('VIDEO_ACTION_INTERVAL_MAX', None), 30)
    VIDEO_SCROLL_INTERVAL_MIN = _to_float(_get_env_value('VIDEO_SCROLL_INTERVAL_MIN', None), 1)
    VIDEO_SCROLL_INTERVAL_MAX = _to_float(_get_env_value('VIDEO_SCROLL_INTERVAL_MAX', None), 10)
    
    # ==================== 快手关键词配置 ====================
    # 搜索关键词列表，支持 JSON、Python 列表或逗号分隔字符串
    _search_keywords_source = _get_env_value('KEYWORDS', None)
    if isinstance(_search_keywords_source, list):
        KEYWORDS = [str(kw).strip() for kw in _search_keywords_source if str(kw).strip()]
    else:
        _search_keywords_env = str(_search_keywords_source or '')
        if _search_keywords_env.strip():
            KEYWORDS = _parse_list_env(_search_keywords_env, item_type=str)
            KEYWORDS = [kw.strip() for kw in KEYWORDS if kw.strip()]
        else:
            KEYWORDS = []
    
    # 评论关键词列表，支持 JSON、Python 列表或逗号分隔字符串
    _comment_keywords_source = _get_env_value('KUAISHOU_COMMENT_KEYWORDS', None)
    if isinstance(_comment_keywords_source, list):
        KUAISHOU_COMMENT_KEYWORDS = [str(kw).strip() for kw in _comment_keywords_source if str(kw).strip()]
    else:
        _comment_keywords_env = str(_comment_keywords_source or '')
        if _comment_keywords_env.strip():
            KUAISHOU_COMMENT_KEYWORDS = _parse_list_env(_comment_keywords_env, item_type=str)
            KUAISHOU_COMMENT_KEYWORDS = [kw.strip() for kw in KUAISHOU_COMMENT_KEYWORDS if kw.strip()]
        else:
            KUAISHOU_COMMENT_KEYWORDS = []
    
    # 优先关注评论关键词列表，支持 JSON、Python 列表或逗号分隔字符串，如果评论中包含这些关键词则优先关注
    _comment_filter_keywords_source = _get_env_value('COMMENT_FILTER_KEYWORDS', None)
    if isinstance(_comment_filter_keywords_source, list):
        COMMENT_FILTER_KEYWORDS = [str(kw).strip() for kw in _comment_filter_keywords_source if str(kw).strip()]
    else:
        _comment_filter_keywords_env = str(_comment_filter_keywords_source or '')
        if _comment_filter_keywords_env.strip():
            COMMENT_FILTER_KEYWORDS = _parse_list_env(_comment_filter_keywords_env, item_type=str)
            COMMENT_FILTER_KEYWORDS = [kw.strip() for kw in COMMENT_FILTER_KEYWORDS if kw.strip()]
        else:
            COMMENT_FILTER_KEYWORDS = []
    
    # ==================== 评论区配置 ====================
    COMMENT_MIN_OPERATION_COUNT = _to_int(_get_env_value('COMMENT_MIN_OPERATION_COUNT', None), 3)
    COMMENT_MAX_OPERATION_COUNT = _to_int(_get_env_value('COMMENT_MAX_OPERATION_COUNT', None), 5)
    # 评论区数量判断
    COMMENT_MIN_ELEMENTS_COUNT = _to_int(_get_env_value('COMMENT_MIN_ELEMENTS_COUNT', None), 3)
    COMMENT_MAX_ELEMENTS_COUNT = _to_int(_get_env_value('COMMENT_MAX_ELEMENTS_COUNT', None), 5)
    
    # ==================== 快手关注配置 ====================
    FOLLOW_INTERVAL_MIN = _to_float(_get_env_value('FOLLOW_INTERVAL_MIN', None), 3)
    FOLLOW_INTERVAL_MAX = _to_float(_get_env_value('FOLLOW_INTERVAL_MAX', None), 10)
    FOLLOW_PROBABILITY = _to_float(_get_env_value('FOLLOW_PROBABILITY', None), 4)
    FOLLOW_COUNT_MIN = _to_int(_get_env_value('FOLLOW_COUNT_MIN', None), 170)
    FOLLOW_COUNT_MAX = _to_int(_get_env_value('FOLLOW_COUNT_MAX', None), 195)
    
    # ==================== 快手视频数量配置 ====================
    VIDEOS_PER_LOOP_MIN = _to_int(_get_env_value('VIDEOS_PER_LOOP_MIN', None), 15)
    VIDEOS_PER_LOOP_MAX = _to_int(_get_env_value('VIDEOS_PER_LOOP_MAX', None), 30)
    
    # ==================== 网页链接内容 ====================
    WEB_LINK_CONTENT = str(_get_env_value('WEB_LINK_CONTENT', '') or '')
    
    # ==================== 快手视频URL配置 ====================
    # 优先使用 URLS 配置，如果没有则使用 KUAISHOU_VIDEO_URL（向后兼容）
    # 支持 JSON 格式、Python 列表或逗号分隔格式
    # 会自动去掉每个URL中?及其后面的参数
    _urls_source = _get_env_value('URLS', None)
    _video_urls_source = _get_env_value('KUAISHOU_VIDEO_URL', None)
    
    # 优先使用 URLS，如果没有则使用 KUAISHOU_VIDEO_URL
    _final_urls_source = _urls_source if _urls_source else _video_urls_source
    
    if isinstance(_final_urls_source, list):
        raw_video_urls = [str(url).strip() for url in _final_urls_source if str(url).strip()]
    else:
        raw_video_urls = _parse_list_env(str(_final_urls_source)) if _final_urls_source else []
    
    # 处理每个URL，去掉?及其后面的参数
    KUAISHOU_VIDEO_URL = []
    for url in raw_video_urls:
        url_str = str(url).strip()
        if url_str:
            # 找到?的位置，如果存在则截取?之前的部分
            if '?' in url_str:
                url_str = url_str.split('?')[0]
            KUAISHOU_VIDEO_URL.append(url_str)
    
    # 同时提供 URLS 作为别名（与 KUAISHOU_VIDEO_URL 相同）
    URLS = KUAISHOU_VIDEO_URL
    
    # ==================== 兼容性属性（向后兼容） ====================
    # 为了兼容旧代码，提供一些别名
    @property
    def BITBROWSER_NAME(self):
        """兼容旧属性名"""
        return self.BITBROWSER_NAMES
    
    @property
    def PROXY(self):
        """兼容旧属性名"""
        return self.NETWORK_PROXY
    
    @property
    def PROXIES(self):
        """兼容旧属性名"""
        return self.NETWORK_PROXIES
    
    @property
    def CHROMEDRIVER_PATH(self):
        """兼容旧属性名"""
        return self.DRIVER_CHROMEDRIVER_PATH
    
    @property
    def INPUT_DELAY_MIN(self):
        """兼容旧属性名"""
        return self.VIDEO_INPUT_DELAY_MIN
    
    @property
    def INPUT_DELAY_MAX(self):
        """兼容旧属性名"""
        return self.VIDEO_INPUT_DELAY_MAX
    
    @property
    def IMPLICIT_WAIT(self):
        """兼容旧属性名"""
        return self.VIDEO_IMPLICIT_WAIT
    
    @property
    def PAGE_LOAD_WAIT(self):
        """兼容旧属性名"""
        return self.VIDEO_PAGE_LOAD_WAIT
    
    @property
    def MAIN_LOOP_INTERVAL_MIN(self):
        """兼容旧属性名"""
        return self.VIDEO_MAIN_LOOP_INTERVAL_MIN
    
    @property
    def MAIN_LOOP_INTERVAL_MAX(self):
        """兼容旧属性名"""
        return self.VIDEO_MAIN_LOOP_INTERVAL_MAX
    
    @property
    def ACTION_INTERVAL_MIN(self):
        """兼容旧属性名"""
        return self.VIDEO_ACTION_INTERVAL_MIN
    
    @property
    def ACTION_INTERVAL_MAX(self):
        """兼容旧属性名"""
        return self.VIDEO_ACTION_INTERVAL_MAX
    
    @property
    def SCROLL_INTERVAL_MIN(self):
        """兼容旧属性名"""
        return self.VIDEO_SCROLL_INTERVAL_MIN
    
    @property
    def SCROLL_INTERVAL_MAX(self):
        """兼容旧属性名"""
        return self.VIDEO_SCROLL_INTERVAL_MAX
    
    @property
    def COMMENT_KEYWORDS(self):
        """兼容旧属性名"""
        return self.KUAISHOU_COMMENT_KEYWORDS
    
    @property
    def FOLLOW_L(self):
        """兼容旧属性名"""
        return self.FOLLOW_PROBABILITY
    

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")
# 创建全局配置实例
# 使用方式: from config import config
# 然后通过 config.BITBROWSER_URL, config.KEYWORDS 等方式访问
ks_config = Config()



