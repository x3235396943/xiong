import json
import logging
import os
from datetime import datetime
from .config import get_config


class MyFormatter(logging.Formatter):
    def format(self, record):
        record.msg = json.dumps(record.msg)
        return super().format(record)


def init_loging_config():
    logger = logging.getLogger("logger")
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # 延迟获取配置，避免在配置初始化前访问
    config = get_config()

    logs_dir = config.LOGS_PATH
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # 生成日志文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = os.path.join(
        logs_dir, f"pc_{config.PLATFORM}_{config.RUN_MODE}_{timestamp}.log"
    )

    # 文件处理器
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


log = init_loging_config()
