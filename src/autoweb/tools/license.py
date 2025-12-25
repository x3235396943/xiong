"""
卡密/验证相关逻辑收口模块（减少文件数量）

合并来源：tools/verify.py
"""

from __future__ import annotations

import os
import threading
import time
import requests

from .core import log
from .config import env, get_config


class LicenseException(Exception):
    """卡密验证异常类"""


class LicenseManager:
    """
    卡密管理器类：封装验证逻辑 (同步模式)
    """

    def __init__(self):
        self._valid = True
        self._error_msg = ""
        self._stop_event = threading.Event()
        self._stop_callback = None

        cfg = get_config()

        self.url = os.environ.get("SIBERIAN_URL") or getattr(cfg, "SIBERIAN_URL", "")
        self.active_url = os.environ.get("ACTIVE_URL") or getattr(cfg, "ACTIVE_URL", "")
        self.key = os.environ.get("SIBERIAN_KEY") or getattr(cfg, "SIBERIAN_KEY", "")
        self.code = os.environ.get("DEVICE_CODE") or getattr(cfg, "DEVICE_CODE", "")
        self.uuid = os.environ.get("UUID") or getattr(cfg, "UUID", "")

    def _verify_logic(self, is_initial=False):
        try:
            if not self.url or not self.key:
                return False, "未配置 SIBERIAN_URL 或 SIBERIAN_KEY"

            if not self.code:
                return False, "未配置 DEVICE_CODE"

            if is_initial and self.active_url and self.uuid:
                url = self.active_url
                payload = {
                    "siberian": self.key,
                    "deviceCode": self.code,
                    "uuid": self.uuid,
                }
            else:
                url = self.url
                payload = {
                    "siberian": self.key,
                    "deviceCode": self.code,
                }

            log.debug(f"发送验证请求到: {url}")
            log.debug(f"请求数据: {payload}")

            response = requests.post(url, json=payload, timeout=15)

            log.debug(f"响应状态码: {response.status_code}")
            log.debug(f"响应内容: {response.text}")

            res = response.json()
            if res.get("code") != 200:
                return False, str(res)

            return True, "success"
        except requests.exceptions.ConnectionError:
            return False, "无法连接到验证服务器，请检查网络或联系管理员"
        except Exception as e:
            return False, f"验证过程中发生错误: {type(e).__name__}"

    def _loop(self):
        while not self._stop_event.is_set():
            is_valid, msg = self._verify_logic()

            if not is_valid:
                self._valid = False
                self._error_msg = msg
                log.error(f"❌ 卡密验证失败 (后台检查): {msg}")
                if self._stop_callback:
                    try:
                        log.error("卡密已过期，正在停止程序...")
                        self._stop_callback()
                    except Exception as e:
                        log.error(f"执行停止回调时出错: {e}")
                break
            else:
                self._valid = True

            time.sleep(180)

    def verify_license(self):
        cfg = get_config()
        if getattr(cfg, "DEBUG", False):
            log.info("正在验证卡密...")

        log.debug("配置信息来源:")
        log.debug(
            f"  SIBERIAN_URL: {'环境变量' if os.environ.get('SIBERIAN_URL') else '配置文件'} = {self.url}"
        )
        log.debug(
            f"  ACTIVE_URL: {'环境变量' if os.environ.get('ACTIVE_URL') else '配置文件'} = {self.active_url}"
        )
        log.debug(
            f"  SIBERIAN_KEY: {'环境变量' if os.environ.get('SIBERIAN_KEY') else '配置文件'} = {self.key}"
        )
        log.debug(
            f"  DEVICE_CODE: {'环境变量' if os.environ.get('DEVICE_CODE') else '配置文件'} = {self.code}"
        )
        log.debug(
            f"  UUID: {'环境变量' if os.environ.get('UUID') else '配置文件'} = {self.uuid}"
        )

        if not self.url or not self.key or not self.code or not self.uuid:
            if getattr(cfg, "DEBUG", False):
                log.info("✅ 卡密参数尚未接收，推迟验证")
            return True

        is_valid, msg = self._verify_logic(is_initial=True)

        if is_valid:
            self._valid = True
            if getattr(cfg, "DEBUG", False):
                log.info("✅ 卡密验证成功")
            return True

        self._valid = False
        self._error_msg = msg
        log.error(f"❌ 卡密验证失败: {msg}")
        return False

    def check_license_validity(self):
        if not self.url or not self.key or not self.code or not self.uuid:
            return

        if not self._valid:
            raise LicenseException(f"许可证无效: {self._error_msg}")

    def start_periodic_check(self):
        if self._stop_event.is_set():
            self._stop_event.clear()

        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop_periodic_check(self):
        self._stop_event.set()

    def set_stop_callback(self, callback):
        self._stop_callback = callback


