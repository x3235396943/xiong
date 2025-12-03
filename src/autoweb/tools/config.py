from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any


class Base(BaseSettings):
    SIBERIAN_URL: str = "http://139.159.230.186/api/siberianNitraria/verifyActivate"
    SIBERIAN_KEY: str = "kjG7GGbNDqvrHSZ1Zin5zvWVyBjkiiggCFiAVyC3AsQ="
    DEVICE_CODE: str = "111222"
    WEBSOCKET_URL: str = "ws://192.168.2.9:11221/ws/"
    PLATFORM: str = "dys"

    # 不从.env文件读取配置
    model_config = SettingsConfigDict(extra="ignore")


class KuSettings(Base):
    KEYWORDS: list = []
    MAX_SCROLL_VIDEO: list = [10, 20]
    MAX_COMMENT: list = [2, 15]

    LIKE_PROBABILITY: int = 30  # 点赞概率 (0-100)
    VISIT_ENABLE: int = 10  # 进入主页的概率 (0-100)
    PROFILE_FOLLOW_PROBABILITY: int = 10  # 进入主页后关注的概率 (0-100)
    ENABLE_FOLLOW: bool = True  # 是否启用关注功能
    ENABLE_PROFILE_VISIT: bool = True  # 是否启用进入主页功能
    ENABLE_LIKE: bool = True  # 是否启用点赞功能
    ENABLE_SEARCH_KEYWORDS: bool = True  # 是否启用搜索关键字功能
    ENABLE_COMMENT_REPLY: bool = True  # 是否启用评论回复功能
    ENABLE_VIDEO_COMMENT: bool = True  # 是否启用视频留言功能
    ENABLE_COMMENT_TEMPLATES: bool = True  # 是否启用评论话术功能
    COMMENT_REPLIES: str = ""  # 回复评论的内容
    VIDEO_COMMENTS: str = ""  # 视频留言的内容
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
    VIDEO_REPLY_WAIT_MIN: int = 5  # 视频留言前最小等待时间（秒）
    VIDEO_REPLY_WAIT_MAX: int = 8  # 视频留言前最大等待时间（秒）
    COMMENT_WAIT_MIN: int = 5  # 评论回复前最小等待时间（秒）
    COMMENT_WAIT_MAX: int = 8  # 评论回复前最大等待时间（秒）

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

    BIT_BROWSER_IDS: list = ["4bbbe30c084a495796aaaff8a7082fda"]

    VERSION: str = "1.0.18"

    # bit浏览器设置
    BROWSER_SAVE_DIR: str = "browser_sessions"
    BROWSER_MAX_WORKERS: int = 5

    # 快手操作设置
    VIDEO_INPUT_DELAY_MIN: float = 0.1
    VIDEO_INPUT_DELAY_MAX: float = 0.3
    VIDEO_IMPLICIT_WAIT: int = 10
    VIDEO_PAGE_LOAD_WAIT: int = 2
    VIDEO_MAIN_LOOP_INTERVAL_MIN: float = 3600
    VIDEO_MAIN_LOOP_INTERVAL_MAX: float = 3601
    VIDEO_ACTION_INTERVAL_MIN: float = 15
    VIDEO_ACTION_INTERVAL_MAX: float = 30
    VIDEO_SCROLL_INTERVAL_MIN: float = 1
    VIDEO_SCROLL_INTERVAL_MAX: float = 10
    VIDEOS_PER_LOOP_MIN: int = 15
    VIDEOS_PER_LOOP_MAX: int = 30
    FOLLOW_COUNT_MIN: int = 170
    FOLLOW_COUNT_MAX: int = 195
    COMMENT_MIN_OPERATION_COUNT: int = 3
    COMMENT_MAX_OPERATION_COUNT: int = 5
    COMMENT_MIN_ELEMENTS_COUNT: int = 3
    COMMENT_MAX_ELEMENTS_COUNT: int = 5
    FOLLOW_INTERVAL_MIN: float = 3
    FOLLOW_INTERVAL_MAX: float = 10
    FOLLOW_PROBABILITY: float = 4
    COMMENT_KEYWORDS: list = []

    # 不从.env文件读取配置
    model_config = SettingsConfigDict(extra="ignore")

    def update_from_dict(self, config_dict: Dict[str, Any]):
        """
        从字典更新配置项
        
        Args:
            config_dict: 包含配置项的字典
        """
        from . import log
        for key, value in config_dict.items():
            if hasattr(self, key):
                old_value = getattr(self, key)
                setattr(self, key, value)
                # 记录配置变更日志
                if old_value != value:
                    log.info(f"配置变更: {key} 从 {old_value} 更新为 {value}")

    def print_config_summary(self):
        """
        打印配置摘要信息
        """
        from . import log
        log.info("当前配置摘要:")
        log.info(f"  PLATFORM: {self.PLATFORM}")
        log.info(f"  DEVICE_CODE: {self.DEVICE_CODE}")
        log.info(f"  ENABLE_FOLLOW: {self.ENABLE_FOLLOW}")
        log.info(f"  ENABLE_LIKE: {self.ENABLE_LIKE}")
        log.info(f"  LIKE_PROBABILITY: {self.LIKE_PROBABILITY}")
        log.info(f"  VISIT_ENABLE: {self.VISIT_ENABLE}")
        log.info(f"  PROFILE_FOLLOW_PROBABILITY: {self.PROFILE_FOLLOW_PROBABILITY}")


# 创建全局配置实例
config = KuSettings()  # type: ignore




import os
import json
import ast
from pathlib import Path
from typing import Any




#     # ==================== 快手关键词配置 ====================
#     # 搜索关键词列表，支持 JSON、Python 列表或逗号分隔字符串
#     _search_keywords_source = _get_env_value('KEYWORDS', None)
#     if isinstance(_search_keywords_source, list):
#         KEYWORDS = [str(kw).strip() for kw in _search_keywords_source if str(kw).strip()]
#     else:
#         _search_keywords_env = str(_search_keywords_source or '')
#         if _search_keywords_env.strip():
#             KEYWORDS = _parse_list_env(_search_keywords_env, item_type=str)
#             KEYWORDS = [kw.strip() for kw in KEYWORDS if kw.strip()]
#         else:
#             KEYWORDS = []



#     # ==================== 评论区配置 ====================
#     COMMENT_MIN_OPERATION_COUNT = _to_int(_get_env_value('COMMENT_MIN_OPERATION_COUNT', None), 3)
#     COMMENT_MAX_OPERATION_COUNT = _to_int(_get_env_value('COMMENT_MAX_OPERATION_COUNT', None), 5)
#     # 评论区数量判断
#     COMMENT_MIN_ELEMENTS_COUNT = _to_int(_get_env_value('COMMENT_MIN_ELEMENTS_COUNT', None), 3)
#     COMMENT_MAX_ELEMENTS_COUNT = _to_int(_get_env_value('COMMENT_MAX_ELEMENTS_COUNT', None), 5)

#     # ==================== 快手关注配置 ====================
#     FOLLOW_INTERVAL_MIN = _to_float(_get_env_value('FOLLOW_INTERVAL_MIN', None), 3)
#     FOLLOW_INTERVAL_MAX = _to_float(_get_env_value('FOLLOW_INTERVAL_MAX', None), 10)
#     FOLLOW_PROBABILITY = _to_float(_get_env_value('FOLLOW_PROBABILITY', None), 4)
#     FOLLOW_COUNT_MIN = _to_int(_get_env_value('FOLLOW_COUNT_MIN', None), 170)

#     # ==================== 快手视频数量配置 ====================
#     VIDEOS_PER_LOOP_MIN = _to_int(_get_env_value('VIDEOS_PER_LOOP_MIN', None), 15)
#     VIDEOS_PER_LOOP_MAX = _to_int(_get_env_value('VIDEOS_PER_LOOP_MAX', None), 30)

#     # ==================== 网页链接内容 ====================
#     WEB_LINK_CONTENT = str(_get_env_value('WEB_LINK_CONTENT', '') or '')

#     # ==================== 快手视频URL配置 ====================
#     # 优先使用 URLS 配置，如果没有则使用 KUAISHOU_VIDEO_URL（向后兼容）
#     # 支持 JSON 格式、Python 列表或逗号分隔格式
#     # 会自动去掉每个URL中?及其后面的参数
#     _urls_source = _get_env_value('URLS', None)
#     _video_urls_source = _get_env_value('KUAISHOU_VIDEO_URL', None)

#     # 优先使用 URLS，如果没有则使用 KUAISHOU_VIDEO_URL
#     _final_urls_source = _urls_source if _urls_source else _video_urls_source

#     if isinstance(_final_urls_source, list):
#         raw_video_urls = [str(url).strip() for url in _final_urls_source if str(url).strip()]
#     else:
#         raw_video_urls = _parse_list_env(str(_final_urls_source)) if _final_urls_source else []

#     # 处理每个URL，去掉?及其后面的参数
#     KUAISHOU_VIDEO_URL = []
#     for url in raw_video_urls:
#         url_str = str(url).strip()
#         if url_str:
#             # 找到?的位置，如果存在则截取?之前的部分
#             if '?' in url_str:
#                 url_str = url_str.split('?')[0]
#             KUAISHOU_VIDEO_URL.append(url_str)

#     # 同时提供 URLS 作为别名（与 KUAISHOU_VIDEO_URL 相同）
#     URLS = KUAISHOU_VIDEO_URL


#     @property
#     def PROXY(self):
#         """兼容旧属性名"""
#         return self.NETWORK_PROXY

#     @property
#     def PROXIES(self):
#         """兼容旧属性名"""
#         return self.NETWORK_PROXIES

#     @property
#     def CHROMEDRIVER_PATH(self):
#         """兼容旧属性名"""
#         return self.DRIVER_CHROMEDRIVER_PATH

#     @property
#     def INPUT_DELAY_MIN(self):
#         """兼容旧属性名"""
#         return self.VIDEO_INPUT_DELAY_MIN

#     @property
#     def INPUT_DELAY_MAX(self):
#         """兼容旧属性名"""
#         return self.VIDEO_INPUT_DELAY_MAX

#     @property
#     def IMPLICIT_WAIT(self):
#         """兼容旧属性名"""
#         return self.VIDEO_IMPLICIT_WAIT

#     @property
#     def PAGE_LOAD_WAIT(self):
#         """兼容旧属性名"""
#         return self.VIDEO_PAGE_LOAD_WAIT

#     @property
#     def MAIN_LOOP_INTERVAL_MIN(self):
#         """兼容旧属性名"""
#         return self.VIDEO_MAIN_LOOP_INTERVAL_MIN

#     @property
#     def MAIN_LOOP_INTERVAL_MAX(self):
#         """兼容旧属性名"""
#         return self.VIDEO_MAIN_LOOP_INTERVAL_MAX

#     @property
#     def ACTION_INTERVAL_MIN(self):
#         """兼容旧属性名"""
#         return self.VIDEO_ACTION_INTERVAL_MIN

#     @property
#     def ACTION_INTERVAL_MAX(self):
#         """兼容旧属性名"""
#         return self.VIDEO_ACTION_INTERVAL_MAX

#     @property
#     def SCROLL_INTERVAL_MIN(self):
#         """兼容旧属性名"""
#         return self.VIDEO_SCROLL_INTERVAL_MIN

#     @property
#     def SCROLL_INTERVAL_MAX(self):
#         """兼容旧属性名"""
#         return self.VIDEO_SCROLL_INTERVAL_MAX


#     @property
#     def FOLLOW_L(self):
#         """兼容旧属性名"""
#         return self.FOLLOW_PROBABILITY


#     model_config = SettingsConfigDict(extra="ignore")
# 创建全局配置实例
# 使用方式: from config import config
# 然后通过 config.BITBROWSER_URL, config.KEYWORDS 等方式访问




