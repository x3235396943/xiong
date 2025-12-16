from asyncio import sleep

import aiohttp
import ujson

from .config import get_config

import threading
import time
import requests
import os
from . import log

from .web_client import WSClient


async def verify(ws: WSClient):
    await ws.ready_event.wait()
    config = get_config()
    async with aiohttp.ClientSession(json_serialize=ujson.dumps) as session:
        while True:
            # 检查配置是否已设置
            if not config.SIBERIAN_URL or not config.SIBERIAN_KEY:
                log.warning("SIBERIAN_URL 或 SIBERIAN_KEY 未设置，跳过验证")
                await sleep(180)
                continue

            async with session.post(
                config.SIBERIAN_URL,
                json={
                    "siberian": config.SIBERIAN_KEY,
                    "deviceCode": config.DEVICE_CODE,
                },
            ) as response:
                res = await response.json()
                if res["code"] != 200:
                    raise Exception(res)
            await sleep(180)


class LicenseException(Exception):
    """卡密验证异常类"""

    pass


class LicenseManager:
    """
    卡密管理器类：封装验证逻辑 (同步模式)
    """

    def __init__(self):
        self._valid = True
        self._error_msg = ""
        self._stop_event = threading.Event()
        
        # 延迟导入 config 以避免循环依赖
        from .config import get_config
        config = get_config()

        # 优先从环境变量获取，如果没有则从 config 配置获取
        self.url = os.environ.get("SIBERIAN_URL") or getattr(config, "SIBERIAN_URL", "")
        self.active_url = os.environ.get("ACTIVE_URL") or getattr(config, "ACTIVE_URL", "")
        self.key = os.environ.get("SIBERIAN_KEY") or getattr(config, "SIBERIAN_KEY", "")
        self.code = os.environ.get("DEVICE_CODE") or getattr(config, "DEVICE_CODE", "")
        self.uuid = os.environ.get("UUID") or getattr(config, "UUID", "")
        # 简单的配置检查
        # 不再强制要求任何参数在启动时存在

    def _verify_logic(self, is_initial=False):
        """
        验证核心逻辑 (HTTP POST)
        返回: (bool, msg)
        """
        try:
            # 检查必要参数是否存在
            if not self.url or not self.key:
                return False, "未配置 SIBERIAN_URL 或 SIBERIAN_KEY"

            if not self.code:
                return False, "未配置 DEVICE_CODE"

            # 准备URL和数据
            if is_initial and self.card_url and self.uuid:
                # 初始验证使用CARD_URL并发送UUID
                url = self.card_url
                payload = {
                    "siberian": self.key,
                    "deviceCode": self.code,
                    "uuid": self.uuid
                }
            else:
                # 后续验证使用常规URL，不发送UUID
                url = self.url
                payload = {
                    "siberian": self.key,
                    "deviceCode": self.code,
                }
            
            # 输出调试信息
            log.debug(f"发送验证请求到: {url}")
            log.debug(f"请求数据: {payload}")

            # 发送请求
            response = requests.post(
                url,
                json=payload,
                timeout=15,  # 设置超时防止卡死
            )

            # 输出响应信息
            log.debug(f"响应状态码: {response.status_code}")
            log.debug(f"响应内容: {response.text}")

            # 解析响应
            res = response.json()

            # 校验业务状态码 (同事的逻辑是 code != 200 即为失败)
            if res.get("code") != 200:
                return False, str(res)

            return True, "success"
        except requests.exceptions.ConnectionError:
            return False, "无法连接到验证服务器，请检查网络或联系管理员"
        except Exception as e:
            return False, f"验证过程中发生错误: {type(e).__name__}"

    def _loop(self):
        """后台循环线程，每180秒检查一次"""
        while not self._stop_event.is_set():
            is_valid, msg = self._verify_logic()

            if not is_valid:
                self._valid = False
                self._error_msg = msg
                log.error(f"❌ 卡密验证失败 (后台检查): {msg}")
                # 注意：这里我们只记录状态，主线程通过 check_license_validity 抛出异常
            else:
                self._valid = True
                # log.debug("卡密验证通过 (后台检查)")

            # 休眠180秒
            time.sleep(180)

    def verify_license(self):
        """初始验证，通常在程序启动时调用"""
        config = get_config()
        if config.DEBUG:
            log.info("正在验证卡密...")

        # 输出配置信息来源
        log.debug(f"配置信息来源:")
        log.debug(f"  SIBERIAN_URL: {'环境变量' if os.environ.get('SIBERIAN_URL') else '配置文件'} = {self.url}")
        log.debug(f"  ACTIVE_URL: {'环境变量' if os.environ.get('ACTIVE_URL') else '配置文件'} = {self.active_url}")
        log.debug(f"  SIBERIAN_KEY: {'环境变量' if os.environ.get('SIBERIAN_KEY') else '配置文件'} = {self.key}")
        log.debug(f"  DEVICE_CODE: {'环境变量' if os.environ.get('DEVICE_CODE') else '配置文件'} = {self.code}")
        log.debug(f"  UUID: {'环境变量' if os.environ.get('UUID') else '配置文件'} = {self.uuid}")

        # 如果 URL、KEY、CODE 或 UUID 未设置，则暂时认为验证通过（推迟到服务器配置到达后再验证）
        if not self.url or not self.key or not self.code or not self.uuid:
            if config.DEBUG:
                log.info("✅ 卡密参数尚未接收，推迟验证")
            return True

        is_valid, msg = self._verify_logic(is_initial=True)

        if is_valid:
            self._valid = True
            if config.DEBUG:
                log.info("✅ 卡密验证成功")
            return True
        else:
            self._valid = False
            self._error_msg = msg
            log.error(f"❌ 卡密验证失败: {msg}")
            return False

    def check_license_validity(self):
        """
        主线程在执行关键操作前调用此方法。
        如果后台线程检测到失效，这里会抛出异常，中断操作。
        """
        # 如果 URL、KEY、CODE 或 UUID 未设置，则不进行验证
        if not self.url or not self.key or not self.code or not self.uuid:
            return

        if not self._valid:
            raise LicenseException(f"License Invalid: {self._error_msg}")

    def start_periodic_check(self):
        """启动后台检查线程"""
        if self._stop_event.is_set():
            self._stop_event.clear()

        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop_periodic_check(self):
        """停止后台检查线程"""
        self._stop_event.set()

