from .core import log
from .config import get_config, EnvSettings, env
from .license import LicenseException, LicenseManager
from .douyin_common import (
    DouyinConfigParser,
    DouyinCommentActions,
    DouyinBrowserActions,
)


__all__ = [
    "env",
    "log",
    "config",
    "get_config",
    "EnvSettings",
    "LicenseException",
    "LicenseManager",
    "DouyinConfigParser",
    "DouyinCommentActions",
    "DouyinBrowserActions",
]

# 对外暴露“当前配置实例”（避免 `from .config import config` 的 None 快照问题）
config = get_config()
