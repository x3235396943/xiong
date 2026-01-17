import re
import os
import sys
from pydantic import field_validator, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, Any
import time


# 定义需要验证的字段对
field_pairs = {
    "MAX_FOLLOWS_PER_VIDEO": "MIN_FOLLOWS_PER_VIDEO",
    "COMMENT_LIKE_COUNT_MAX": "COMMENT_LIKE_COUNT_MIN",
    "LIKE_WAIT_MAX": "LIKE_WAIT_MIN",
    "VISIT_MAX": "VISIT_MIN",
    "VIDEO_REPLY_WAIT_MAX": "VIDEO_REPLY_WAIT_MIN",
    "COMMENT_WAIT_MAX": "COMMENT_WAIT_MIN",
}


class BaseConfig(BaseModel):
    LIKE_PROBABILITY: int = 10  # 点赞概率 (0-100)
    VISIT_ENABLE: int = 10  # 进入主页的概率 (0-100)
    PROFILE_FOLLOW_PROBABILITY: int = 10  # 进入主页后关注的概率 (0-100)
    ENABLE_FOLLOW: bool = True  # 是否启用关注功能
    ENABLE_PROFILE_VISIT: bool = True  # 是否启用进入主页功能
    ENABLE_LIKE: bool = True  # 是否启用点赞功能
    ENABLE_SEARCH_KEYWORDS: bool = True  # 是否启用搜索关键字功能
    ENABLE_COMMENT_REPLY: bool = True  # 是否启用评论回复功能
    ENABLE_VIDEO_COMMENT: bool = True  # 是否启用视频留言功能
    ENABLE_COMMENT_TEMPLATES: bool = True  # 是否启用评论话术功能
    COMMENT_REPLIES: str = "牛-&-你好"  # 回复评论的内容
    VIDEO_COMMENTS: str = "好看-&-厉害"  # 视频留言的内容
    COMMENT_FILTER_KEYWORDS: list = []  # 筛选评论区关键字

    # 新增的概率参数
    COMMENT_REPLY_PROBABILITY: int = 1  # 评论回复概率 (0-100)
    VIDEO_REPLY_RATE: int = 10  # 视频留言概率 (0-100)

    MIN_FOLLOWS_PER_VIDEO: int = 5  # 每条视频最少关注数量
    MAX_FOLLOWS_PER_VIDEO: int = 15  # 每条视频最多关注数量

    COMMENT_LIKE_COUNT_MIN: int = 5  # 每条视频最少点赞数量
    COMMENT_LIKE_COUNT_MAX: int = 15  # 每条视频最多点赞数量

    # 等待时间参数
    LIKE_WAIT_MIN: int = 4  # 点赞后最小等待时间（秒）
    LIKE_WAIT_MAX: int = 10  # 点赞后最大等待时间（秒）
    VISIT_MIN: int = 3  # 关注后最小等待时间（秒）
    VISIT_MAX: int = 5  # 关注后最大等待时间（秒）

    # 留言/回复等待时间参数
    VIDEO_REPLY_WAIT_MIN: int = 5  # 视频留言前最小等待时间（秒）
    VIDEO_REPLY_WAIT_MAX: int = 8  # 视频留言前最大等待时间（秒）
    COMMENT_WAIT_MIN: int = 5  # 评论回复前最小等待时间（秒）
    COMMENT_WAIT_MAX: int = 8  # 评论回复前最大等待时间（秒）

    # 私信功能（服务器下发）
    ENABLE_DM: bool = False
    DM_PROBABILITY: int = 10
    DM_WAIT_MIN: int = 5
    DM_WAIT_MAX: int = 12
    DM_MESSAGES: str = "你好-&-在吗"

    # 通过评论时间筛选
    COMMENT_THRESHOLD_ENABLE: bool = False
    COMMENT_THRESHOLD: int = 24 * 60

    BIT_BROWSER_IDS: list = []

    @field_validator(*field_pairs.keys())
    @classmethod
    def validate_min_max_pairs(cls, max_value, info):
        max_name = info.field_name
        min_name = field_pairs[max_name]
        if info.data.get(min_name) > max_value:
            raise ValueError(f"{min_name} 不能大于 {max_name}")
        return max_value


class EnvSettings(BaseSettings, BaseConfig):
    # 添加一个标志用于等待配置初始化
    _config_initialized: bool = False
    # 添加停止信号标志
    _stop_requested: bool = False
    ACTIVE_URL: str  # 开始卡密验证地址
    SIBERIAN_URL: str | None = None
    SIBERIAN_KEY: str | None = None
    DEVICE_CODE: str | None = None  # 设备码
    # WebSocket 配置
    WS_URL: str  # WebSocket 服务器地址
    PLATFORM: str
    RUN_MODE: str
    UUID: str
    LOGS_PATH: str
    CONNECT_KEY: str  # 连接密钥
    # 服务器消息ID，用于发送消息到服务器时的标识符
    SERVER_ID: str = "shebeiid"

    # 本地导入链接
    URLS: list = []
    # 链接索引
    URL_INDEX: list = []
    # 其他设置
    WAIT_TIME: int = 10  # 等待元素出现的时间（秒）
    HEADLESS: bool = False  # 是否以无头模式运行浏览器(T or F)
    DEBUG: bool = True  # 是否输出调试信息（打印所有配置参数）

    VERSION: str | None = "1.5.3"

    # 抖音搜索模式配置（服务器下发）
    KEYWORDS: list = []
    MAX_SCROLL_VIDEO: list = [10, 20]
    MAX_COMMENT: list = [2, 15]

    model_config = SettingsConfigDict(extra="ignore", env_file=".env")

    # 不从.env文件读取配置
    def update_from_dict(self, config_dict: Dict[str, Any]):
        """
        从字典更新配置项

        Args:
            config_dict: 包含配置项的字典
        """
        from .core import log

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
        from .core import log

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
        from .core import log

        log.info("当前配置摘要:")
        log.info(f"  PLATFORM: {self.PLATFORM}")
        log.info(f"  DEVICE_CODE: {self.DEVICE_CODE}")
        log.info(f"  SERVER_ID: {self.SERVER_ID}")
        log.info(f"  ENABLE_FOLLOW: {self.ENABLE_FOLLOW}")
        log.info(f"  ENABLE_LIKE: {self.ENABLE_LIKE}")
        log.info(f"  LIKE_PROBABILITY: {self.LIKE_PROBABILITY}")
        log.info(f"  VISIT_ENABLE: {self.VISIT_ENABLE}")
        log.info(f"  PROFILE_FOLLOW_PROBABILITY: {self.PROFILE_FOLLOW_PROBABILITY}")
        log.info(f"  ENABLE_DM: {self.ENABLE_DM}")
        log.info(f"  DM_PROBABILITY: {self.DM_PROBABILITY}")
        log.info(f"  DM_WAIT_MIN: {self.DM_WAIT_MIN}")
        log.info(f"  DM_WAIT_MAX: {self.DM_WAIT_MAX}")


# 延迟初始化全局配置实例，直到接收到服务器参数
config = None  # type: ignore


def get_config():
    """
    获取全局配置实例，如果尚未初始化则创建一个新实例
    """
    global config
    if config is None:
        # 创建一个部分初始化的配置实例，避免在环境变量缺失时报错
        try:
            config = EnvSettings()  # type: ignore
        except Exception:
            # 如果初始化失败，创建一个空的配置实例
            config = object.__new__(EnvSettings)  # type: ignore
            EnvSettings.__init__(config)  # type: ignore
    return config


class KsConfig(BaseConfig):
    # 快手相关配置参数（使用父类参数的快手特定默认值）

    # 搜索关键词
    KEYWORDS: list = ["美女", "美食", "穿搭", "旅行"]

    # 视频浏览相关参数
    MAX_SCROLL_VIDEO: list = [2, 3]  # 默认视频数量范围
    MAX_COMMENT: list = [2, 5]  # 默认评论滚动范围

    # 视频评论内容列表
    VIDEO_COMMENTS: str = "这个视频不错！-&-内容很棒！-&-支持一下！-&-666-&-好看！-&-不错哦-&-赞一个"  # 视频评论列表，使用-&-分隔
    BIT_BROWSER_IDS: list = [
        "57bd9953b5364d3db5c4ac7cfbb9a1b3",
        "4bbbe30c084a495796aaaff8a7082fda",
    ]  # 默认浏览器ID列表

    # 评论关键词过滤
    COMMENT_FILTER_KEYWORDS: list = ["美女", "帅哥", "喜欢"]

    # 快手特定参数
    KS_DEFAULT_WAIT_TIME: int = 5  # 快手默认等待元素加载时间


class XhsConfig(BaseConfig):
    # 小红书相关配置参数（使用父类参数的快手特定默认值）

    # 搜索关键词
    KEYWORDS: list = ["御姐", "美食", "jk", "美女", "巴黎世家"]

    # 视频浏览相关参数
    MAX_SCROLL_VIDEO: list = [2, 3]  # 默认视频数量范围
    MAX_COMMENT: list = [2, 5]  # 默认评论滚动范围

    # 视频评论内容列表
    VIDEO_COMMENTS: str = (
        "美女！-&-漂亮！-&-好美！-&-666-&-好看！-&-不错哦"  # 视频评论列表，使用-&-分隔
    )
    BIT_BROWSER_IDS: list = [
        "57bd9953b5364d3db5c4ac7cfbb9a1b3",
        "4bbbe30c084a495796aaaff8a7082fda",
    ]  # 默认浏览器ID列表

    # 评论关键词过滤
    COMMENT_FILTER_KEYWORDS: list = ["善"]

    # 功能开关
    ENABLE_COMMENT_REPLY: bool = True
    COMMENT_REPLIES: str = "牛-&-666"  # 小红书回复评论的内容


def extract_version() -> str | None:
    """
    提取出的版本号
    """
    if getattr(sys, "frozen", False):
        # 打包后的环境
        executable_path = sys.executable
    else:
        # 开发环境
        executable_path = __file__

    # 获取文件名（不含路径）
    filename = os.path.basename(executable_path)
    match = re.search(r"(\d+\.\d+\.\d+(?:\.\d+)*)", filename)
    if match:
        return match.group(1)

    return None


env = EnvSettings(VERSION=extract_version())  # type: ignore
