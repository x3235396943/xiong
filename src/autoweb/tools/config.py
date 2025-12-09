from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any, Optional
import time
import threading


class Base(BaseSettings):
    SIBERIAN_URL: Optional[str] = None
    SIBERIAN_KEY: Optional[str] = None
    DEVICE_CODE: Optional[str] = None
    # WebSocket 配置
    WS_URL: str  # WebSocket 服务器地址
    PLATFORM: str = "dys"  # 设备码
    # 服务器消息ID，用于发送消息到服务器时的标识符
    SERVER_ID: str = "shebeiid"


class KuSettings(Base):
    # 添加一个标志用于等待配置初始化
    _config_initialized: bool = False
    # 添加停止信号标志
    _stop_requested: bool = False

    KEYWORDS: list = []
    MAX_SCROLL_VIDEO: list = [10, 20]
    MAX_COMMENT: list = [2, 15]

    LIKE_PROBABILITY: Optional[int] = 30  # 点赞概率 (0-100)
    VISIT_ENABLE: Optional[int] = 10  # 进入主页的概率 (0-100)
    PROFILE_FOLLOW_PROBABILITY: Optional[int] = 10  # 进入主页后关注的概率 (0-100)
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

    BIT_BROWSER_IDS: list = []

    VERSION: str = "1.0.20"






    # 快手bit浏览器设置
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

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    @field_validator('MAX_FOLLOWS_PER_VIDEO', 'COMMENT_LIKE_COUNT_MAX', 'LIKE_WAIT_MAX',
                     'VISIT_MAX', 'VIDEO_REPLY_WAIT_MAX', 'COMMENT_WAIT_MAX')
    @classmethod
    def validate_min_max_pairs(cls, max_value, info):
        # 定义需要验证的字段对：(min_field, max_field)
        field_pairs = {
            'MAX_FOLLOWS_PER_VIDEO': ('MIN_FOLLOWS_PER_VIDEO', 'MAX_FOLLOWS_PER_VIDEO'),
            'COMMENT_LIKE_COUNT_MAX': ('COMMENT_LIKE_COUNT_MIN', 'COMMENT_LIKE_COUNT_MAX'),
            'LIKE_WAIT_MAX': ('LIKE_WAIT_MIN', 'LIKE_WAIT_MAX'),
            'VISIT_MAX': ('VISIT_MIN', 'VISIT_MAX'),
            'VIDEO_REPLY_WAIT_MAX': ('VIDEO_REPLY_WAIT_MIN', 'VIDEO_REPLY_WAIT_MAX'),
            'COMMENT_WAIT_MAX': ('COMMENT_WAIT_MIN', 'COMMENT_WAIT_MAX')
        }

        field_name = info.field_name
        if field_name in field_pairs:
            min_field, max_field = field_pairs[field_name]
            min_value = info.data.get(min_field)
            if min_value is not None and min_value > max_value:
                raise ValueError(f'{min_field} 不能大于 {max_field}')
        return max_value

    # 不从.env文件读取配置
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

        # 标记配置已初始化完成
        self._config_initialized = True

    def wait_for_initialization(self, timeout: int = 300):
        """
        等待配置初始化完成

        Args:
            timeout: 等待超时时间（秒），默认5分钟
        """
        from . import log
        log.info("等待服务器配置初始化...")
        start_time = time.time()
        while not self._config_initialized:
            # 检查是否收到停止信号
            if self._stop_requested:
                raise KeyboardInterrupt("收到停止信号")
            
            if time.time() - start_time > timeout:
                raise TimeoutError(f"等待服务器配置初始化超时 ({timeout}秒)")
            time.sleep(0.1)  # 短暂休眠以减少CPU占用
        log.info("服务器配置初始化完成")
        
    def request_stop(self):
        """请求停止等待"""
        self._stop_requested = True

    def print_config_summary(self):
        """
        打印配置摘要信息
        """
        from . import log
        log.info("当前配置摘要:")
        log.info(f"  PLATFORM: {self.PLATFORM}")
        log.info(f"  DEVICE_CODE: {self.DEVICE_CODE}")
        log.info(f"  SERVER_ID: {self.SERVER_ID}")
        log.info(f"  ENABLE_FOLLOW: {self.ENABLE_FOLLOW}")
        log.info(f"  ENABLE_LIKE: {self.ENABLE_LIKE}")
        log.info(f"  LIKE_PROBABILITY: {self.LIKE_PROBABILITY}")
        log.info(f"  VISIT_ENABLE: {self.VISIT_ENABLE}")
        log.info(f"  PROFILE_FOLLOW_PROBABILITY: {self.PROFILE_FOLLOW_PROBABILITY}")


# 创建全局配置实例
config = KuSettings()  # type: ignore