import json
import logging
import os
from datetime import datetime


class MyFormatter(logging.Formatter):
    def format(self, record):
        record.msg = json.dumps(record.msg)
        return super().format(record)


def init_loging_config1():
    # 创建logs目录
    logs_dir = "logs_path"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # 生成日志文件名（带时间戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(logs_dir, f"douyin_share_{timestamp}.log")

    # 详细日志记录器
    logger = logging.getLogger("detailed_logger")
    logger.setLevel(logging.DEBUG)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setFormatter(console_formatter)
    logger.addHandler(file_handler)

    return logger


log = init_loging_config1()

