import os
import requests
import threading
import time
from . import log
from dotenv import load_dotenv

load_dotenv()


class LicenseException(Exception):
    """卡密验证异常类"""

    pass


class LicenseManager:
    """
    卡密管理器类，用于处理卡密验证相关的功能，包括定期验证机制
    """

    def __init__(self):
        """
        初始化卡密管理器
        """
        self.license_valid = True
        self.license_check_stop = False
        self.check_thread = None
        # 添加缓存机制，避免频繁请求
        self.last_check_time = 0  # 上次验证的时间戳
        self.check_interval = 180  # 验证间隔（秒），默认3分钟

    def verify_license(self, siberian_key=None, device_code=None):
        """
        验证卡密是否有效，可从参数或环境变量获取卡密信息

        Args:
            siberian_key (str, optional): 卡密密钥，如果不提供则从环境变量获取
            device_code (str, optional): 设备码，如果不提供则从环境变量获取

        Returns:
            bool: 验证是否成功
        """
        # 从参数或环境变量获取卡密信息
        siberian_key = siberian_key or os.environ.get("SIBERIAN_KEY")
        device_code = device_code or os.environ.get("DEVICE_CODE")

        # 检查参数或环境变量是否设置
        if not siberian_key or not device_code:
            log.error("❌ 未设置卡密参数或环境变量 SIBERIAN_KEY 和 DEVICE_CODE")
            return False

        # log.info("正在进行卡密验证...")
        # 从环境变量获取验证URL
        siberian_url = os.environ.get("SIBERIAN_URL")
        data = {"siberian": siberian_key, "deviceCode": device_code}

        try:
            response = requests.post(siberian_url, json=data)
            if response.status_code == 200:
                result = response.json()
                # 添加调试信息，打印完整的响应内容
                log.debug(f"卡密验证服务器响应: {result}")
                if result.get("code") == 200:
                    # log.info("卡密验证成功")
                    return True
                else:
                    log.error(f"卡密验证失败: {result.get('message', '未知错误')}")
                    return False
            else:
                log.error(f"卡密验证请求失败，HTTP状态码: {response.status_code}")
                return False
        except Exception as e:
            log.error(f"卡密验证请求异常: {e}")
            return False

    def check_license_validity(self):
        """
        检查卡密有效性，如果无效则抛出异常
        使用缓存机制，避免频繁发送HTTP请求
        """
        current_time = time.time()

        # 如果距离上次验证时间超过间隔时间，才真正验证
        if current_time - self.last_check_time >= self.check_interval:
            # 主动验证许可证
            if not self.verify_license():
                self.license_valid = False
            else:
                self.license_valid = True
            # 更新上次验证时间
            self.last_check_time = current_time

        # 检查缓存的状态，如果无效则抛出异常
        if not self.is_license_valid():
            log.error("卡密验证失败，程序终止")
            raise LicenseException("卡密验证失败")

    def periodic_license_check(self):
        """
        定期检查卡密有效性，从环境变量获取卡密信息

        环境变量:
            SIBERIAN_KEY: 卡密密钥
            DEVICE_CODE: 设备码
        """
        while not self.license_check_stop:
            # 每3分钟检查一次
            time.sleep(180)

            if not self.verify_license():
                log.error("❌ 卡密不存在！")
                self.license_valid = False
                # 更新验证时间，避免立即再次验证
                self.last_check_time = time.time()
                break
            else:
                # 更新验证时间
                self.last_check_time = time.time()

    def start_periodic_check(self):
        """
        启动定期验证线程
        """
        self.check_thread = threading.Thread(
            target=self.periodic_license_check, daemon=True
        )
        self.check_thread.start()

    def stop_periodic_check(self):
        """
        停止定期验证
        """
        self.license_check_stop = True

    def is_license_valid(self):
        """
        检查卡密是否有效

        Returns:
            bool: 卡密是否有效
        """
        return self.license_valid

