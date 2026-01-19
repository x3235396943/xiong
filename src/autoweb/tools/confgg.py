from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AfterValidator, BaseModel
from pydantic_settings import BaseSettings


def range_validator(v):
    if len(v) != 2:
        raise ValueError("must have exactly 2 elements")
    if v[0] > v[1]:
        raise ValueError("first element must be <= second element")
    return v


RangeList = Annotated[list[int], AfterValidator(range_validator)]


class EnvConfig(BaseSettings):
    ANDROID_SERIAL: str
    DEVICE_CODE: str
    WS_URL: str
    VERSION: str | None
    DEBUG: bool = False
    LOGS_PATH: str
    CONNECT_KEY: str
    PLATFORM: str
    RUN_MODE: str
    SIBERIAN_KEY: str
    ACTIVE_URL: str
    UUID: str


class BaseConfig(BaseModel):
    SIBERIAN_URL: str

    MAX_COMMENT: RangeList = [2, 15]  # 评论区最大滚动次数
    MAX_FOLLOW: RangeList = [1, 3]
    MAX_COMMENT_LIKE: RangeList = [3, 8]
    FOLLOW_INTERVAL: RangeList = [12, 60]
    FOLLOW_L: int = 12
    COMMENT_LIKE_INTERVAL: RangeList = [12, 60]
    COMMENT_LIKE_L: int = 12
    COMMENT_KEYWORDS: list = []
    LIKE: bool = True
    FOLLOW: bool = True

    VIDEO_REPLY_ENABLE: bool = True
    VIDEO_REPLY_INTERVAL: RangeList = [12, 60]
    VIDEO_REPLY_L: int = 12
    VIDEO_REPLY: list = []

    COMMENT_REPLY_ENABLE: bool = True
    COMMENT_REPLY_INTERVAL: RangeList = [12, 60]
    COMMENT_REPLY_L: int = 12
    COMMENT_REPLY: list = []
    COMMENT_REPLY_MAX: int = 10

    PHOTO_LIKE_ENABLE: bool = True
    PHOTO_LIKE_INTERVAL: RangeList = [12, 60]
    PHOTO_LIKE_L: int = 12
    MAX_PHOTO_LIKE: RangeList = [3, 8]  # 每个视频最大头像点赞次数

    DM_ENABLE: bool = True
    DM_INTERVAL: RangeList = [12, 40]  # 私信发送间隔
    DM_L: int = 12  # 概率
    MAX_DM: RangeList = [1, 5]  # 每个视频最大发送私信数量
    DM_CONTENT: list = []  # 私信话术库

    COMMENT_THRESHOLD_ENABLE: bool = True
    COMMENT_THRESHOLD: int = 3 * 24 * 60  # 通过评论时间筛选（分钟）


class SearchConfig(BaseConfig):
    KEYWORDS: list = []
    MAX_SCROLL_VIDEO: RangeList = [10, 20]


class ShareConfig(BaseConfig):
    URLS: list
