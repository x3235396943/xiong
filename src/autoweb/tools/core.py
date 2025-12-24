#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
核心工具收口模块（减少文件数量）

合并来源：
- base.py: AbstractCrawler
- common.py: DataReporter
- log.py: 日志初始化
- bit_api.py: openBrowser/closeBrowser（只保留业务实际使用的 API）
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict

import requests

from .config import get_config


# ----------------------------
# AbstractCrawler（原 base.py）
# ----------------------------
class AbstractCrawler(ABC):
    @abstractmethod
    def start(self, _):
        """
        start crawler
        """
        raise NotImplementedError


# ----------------------------
# 日志（原 log.py，做了更安全的兜底）
# ----------------------------
def init_logging_config() -> logging.Logger:
    logger = logging.getLogger("logger")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # 延迟获取配置，避免在配置初始化前访问导致异常
    logs_dir = "logs"
    try:
        cfg = get_config()
        logs_dir = getattr(cfg, "LOGS_PATH", logs_dir) or logs_dir
    except Exception:
        pass

    try:
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
    except Exception:
        # 最后兜底：不影响程序继续运行
        logs_dir = "."

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    try:
        cfg = get_config()
        platform = getattr(cfg, "PLATFORM", "pc")
        run_mode = getattr(cfg, "RUN_MODE", "run")
    except Exception:
        platform = "pc"
        run_mode = "run"

    log_filename = os.path.join(logs_dir, f"pc_{platform}_{run_mode}_{timestamp}.log")
    try:
        file_handler = logging.FileHandler(log_filename, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # 不能写文件也不影响控制台输出
        pass

    return logger


log = init_logging_config()


# ----------------------------
# DataReporter（原 common.py）
# ----------------------------
class DataReporter:
    """
    数据报告器
    负责跟踪统计数据，检测变化并自动发送到服务器
    """

    def __init__(
        self,
        device_code: str,
        browser_id: str,
        send_ws_message_func: Callable[[Dict[str, Any]], None] | None = None,
    ):
        self.device_code = device_code
        self.browser_id = browser_id
        self.send_ws_message_func = send_ws_message_func

        self._stats = {
            "comment": 0,
            "follow": 0,
            "like": 0,
            "urlFail": 0,
            "urlOk": 0,
            "video": 0,
            "videoComment": 0,
            "urlIndex": 0,
        }

        self._lock = threading.Lock()

        self._total_links = 0
        self._completed_links = 0
        # 显式完成态覆盖：用于某些业务（如 dyShare 分摊任务）按"每浏览器线程结束"上报完成
        self._completed_override: bool | None = None

        self._send_queue: "queue.Queue[dict | None]" = queue.Queue()
        self._send_thread = None
        self._send_thread_running = False
        self._start_send_thread()

    def _start_send_thread(self):
        if self._send_thread_running:
            return

        self._send_thread_running = True

        def send_worker():
            while self._send_thread_running:
                try:
                    message = self._send_queue.get(timeout=1.0)
                    if message is None:
                        break

                    if self.send_ws_message_func:
                        try:
                            self.send_ws_message_func(message)
                        except Exception:
                            pass

                    self._send_queue.task_done()
                except queue.Empty:
                    continue
                except Exception:
                    continue

        self._send_thread = threading.Thread(target=send_worker, daemon=True)
        self._send_thread.start()

    def _stop_send_thread(self):
        self._send_thread_running = False
        if self._send_thread:
            try:
                self._send_queue.put(None, timeout=1.0)
                self._send_thread.join(timeout=2.0)
            except Exception:
                pass

    def set_total_links(self, total: int):
        with self._lock:
            self._total_links = total

    def update_completed_links(self, completed: int):
        with self._lock:
            self._completed_links = completed

    def set_completed(self, completed: bool = True):
        """
        显式设置完成态（覆盖 isCompleted 计算逻辑），并立即上报一次。

        - dyShare：每个浏览器线程结束时调用 set_completed(True) 上报完成
        - 其他场景不调用则不影响原有行为
        """
        with self._lock:
            self._completed_override = completed
        self._check_and_report()

    def _check_and_report(self):
        try:
            with self._lock:
                is_completed = False
                if self._completed_override is not None:
                    is_completed = self._completed_override
                elif self._total_links > 0:
                    processed_links = self._stats["urlOk"] + self._stats["urlFail"]
                    is_completed = processed_links >= self._total_links

                stats = self._stats
                device_code = self.device_code
                browser_id = self.browser_id
        except Exception:
            return

        try:
            message = {
                "cmd": "PcDataReq",
                "data": {
                    "browserId": browser_id,
                    "comment": stats["comment"],
                    "deviceType": "pc",
                    "follow": stats["follow"],
                    "id": device_code,
                    "isCompleted": is_completed,
                    "urlIndex": stats["urlIndex"],
                    "like": stats["like"],
                    "urlFail": stats["urlFail"],
                    "urlOk": stats["urlOk"],
                    "video": stats["video"],
                    "videoComment": stats["videoComment"],
                },
                "id": device_code,
            }

            if self._send_thread_running:
                try:
                    self._send_queue.put_nowait(message)
                except Exception:
                    pass
        except Exception:
            pass

    def increment_comment(self, count: int = 1):
        with self._lock:
            old_value = self._stats["comment"]
            self._stats["comment"] += count
            need_report = self._stats["comment"] > old_value
        if need_report:
            self._check_and_report()

    def increment_follow(self, count: int = 1):
        with self._lock:
            old_value = self._stats["follow"]
            self._stats["follow"] += count
            need_report = self._stats["follow"] > old_value
        if need_report:
            self._check_and_report()

    def increment_like(self, count: int = 1):
        with self._lock:
            old_value = self._stats["like"]
            self._stats["like"] += count
            need_report = self._stats["like"] > old_value
        if need_report:
            self._check_and_report()

    def increment_url_fail(self, count: int = 1):
        with self._lock:
            old_value = self._stats["urlFail"]
            self._stats["urlFail"] += count
            need_report = self._stats["urlFail"] > old_value
        if need_report:
            self._check_and_report()

    def increment_url_ok(self, count: int = 1):
        with self._lock:
            old_value = self._stats["urlOk"]
            self._stats["urlOk"] += count
            need_report = self._stats["urlOk"] > old_value
        if need_report:
            self._check_and_report()

    def increment_video(self, count: int = 1):
        with self._lock:
            old_value = self._stats["video"]
            self._stats["video"] += count
            need_report = self._stats["video"] > old_value
        if need_report:
            self._check_and_report()

    def increment_video_comment(self, count: int = 1):
        with self._lock:
            old_value = self._stats["videoComment"]
            self._stats["videoComment"] += count
            need_report = self._stats["videoComment"] > old_value
        if need_report:
            self._check_and_report()

    def update_url_index(self, index: int):
        with self._lock:
            old_value = self._stats["urlIndex"]
            self._stats["urlIndex"] = index
            need_report = self._stats["urlIndex"] != old_value
        if need_report:
            self._check_and_report()

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return self._stats.copy()

    def force_report(self):
        self._check_and_report()

    def __del__(self):
        self._stop_send_thread()


# ----------------------------
# BitBrowser API（原 bit_api.py，收敛到业务实际使用的两个函数）
# ----------------------------
_BIT_API_URL = "http://127.0.0.1:54345"
_BIT_HEADERS = {"Content-Type": "application/json"}


def openBrowser(browser_id: str) -> dict:
    cfg = get_config()
    json_data: Dict[str, Any] = {"id": f"{browser_id}"}
    if getattr(cfg, "HEADLESS", False):
        json_data["args"] = ["--headless"]
        json_data["queue"] = True
        json_data["ignoreDefaultUrls"] = True

    res = requests.post(
        f"{_BIT_API_URL}/browser/open", data=json.dumps(json_data), headers=_BIT_HEADERS
    ).json()
    return res


def closeBrowser(browser_id: str) -> None:
    json_data = {"id": f"{browser_id}"}
    requests.post(
        f"{_BIT_API_URL}/browser/close",
        data=json.dumps(json_data),
        headers=_BIT_HEADERS,
    ).json()
