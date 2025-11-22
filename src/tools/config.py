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
