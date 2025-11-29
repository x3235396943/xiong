#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音分享爬虫具体实现类
继承抽象基类并实现所有抽象方法
"""

import sys
import json
import time
import random
import concurrent.futures
from ..tools.config import KuSettings
from ..tools.verify import LicenseException, LicenseManager
from .base_crawler import BaseDyShareCrawler
from .utils import DyShareUtils


class ConcreteDyShareCrawler(BaseDyShareCrawler):
    """抖音分享爬虫具体实现类"""

    def __init__(self):
        """初始化具体爬虫实现"""
        super().__init__()
        self.config = KuSettings()
        self.utils = DyShareUtils()
        self.license_manager = LicenseManager()

    def initialize_config(self) -> None:
        """初始化配置"""
        # 配置已在__init__中初始化
        pass

    def validate_license(self) -> bool:
        """验证许可证"""
        return self.license_manager.verify_license()

    def prepare_environment(self) -> None:
        """准备运行环境"""
        # 启动定期验证线程
        self.license_manager.start_periodic_check()
        
        # 开启防休眠
        self.utils.set_keep_awake(True)
        
        # 如果启用了调试模式，打印所有配置参数
        if self.config.DEBUG:
            self.utils.print_config_debug()

    def setup_database(self) -> None:
        """设置数据库"""
        # 判断使用列表模式还是数据库模式
        use_list_mode = self.config.URLS and len(self.config.URLS) > 0

        if use_list_mode:
            self._prepare_url_list_mode()
        else:
            print("使用数据库模式")
            # 添加0.2秒延迟
            time.sleep(0.2)
            self.utils.init_database()

        if not self.config.BIT_BROWSER_IDS:
            raise Exception("请在代码中的 BIT_BROWSER_IDS 列表中配置浏览器ID")

    def output_version_info(self) -> None:
        """输出版本信息"""
        # 输出版本信息
        version_info = {"code": 0, "data": {"type": "version", "version": f"pc.{self.config.VERSION}"}}
        output = json.dumps(version_info, ensure_ascii=False)
        print(output)
        # 添加0.2秒延迟
        time.sleep(0.2)

    def process_urls_with_thread_pool(self) -> None:
        """使用线程池处理URL"""
        MAX_WORKERS_USED = len(self.config.BIT_BROWSER_IDS)
        WAIT_TIME_USED = self.config.WAIT_TIME
        LIKE_PROBABILITY_USED = self.config.LIKE_PROBABILITY
        VISIT_PROFILE_PROBABILITY_USED = self.config.VISIT_ENABLE
        PROFILE_FOLLOW_PROBABILITY_USED = self.config.PROFILE_FOLLOW_PROBABILITY
        MIN_FOLLOWS_PER_VIDEO_USED = self.config.MIN_FOLLOWS_PER_VIDEO
        MAX_FOLLOWS_PER_VIDEO_USED = self.config.MAX_FOLLOWS_PER_VIDEO
        MIN_LIKES_PER_VIDEO_USED = self.config.COMMENT_LIKE_COUNT_MIN
        MAX_LIKES_PER_VIDEO_USED = self.config.COMMENT_LIKE_COUNT_MAX

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_USED) as executor:
                futures = []
                for i in range(MAX_WORKERS_USED):
                    browser_id = self.config.BIT_BROWSER_IDS[i % len(self.config.BIT_BROWSER_IDS)]

                    # 为每个浏览器实例单独输出start事件
                    self._output_browser_start_event(browser_id)
                    # 添加0.2秒延迟
                    time.sleep(0.2)

                    future = executor.submit(
                        self.utils.continuous_processing_loop,
                        browser_id,
                        WAIT_TIME_USED,
                        LIKE_PROBABILITY_USED,
                        VISIT_PROFILE_PROBABILITY_USED,
                        PROFILE_FOLLOW_PROBABILITY_USED,
                        MIN_FOLLOWS_PER_VIDEO_USED,
                        MAX_FOLLOWS_PER_VIDEO_USED,
                        MIN_LIKES_PER_VIDEO_USED,
                        MAX_LIKES_PER_VIDEO_USED,
                        i + 1,
                    )
                    futures.append(future)

                    if i < MAX_WORKERS_USED - 1:
                        time.sleep(2.5)

                while futures:
                    try:
                        done, not_done = concurrent.futures.wait(futures, timeout=1)
                        for future in done:
                            try:
                                future.result()
                            except LicenseException:
                                print("卡密验证失败，程序终止")
                                raise
                            except Exception as e:
                                print(f"线程执行出错: {e}")
                        futures = list(not_done)
                    except KeyboardInterrupt:
                        print("收到停止信号，正在关闭所有线程...")
                        self.utils._stop_flag.set()
                        for future in futures:
                            future.cancel()
                        import sys
                        sys.exit(0)
        except LicenseException:
            print("卡密验证失败，程序终止")
            raise

    def cleanup_resources(self) -> None:
        """清理资源"""
        # 关闭防休眠
        self.utils.set_keep_awake(False)
        # 停止许可证检查
        self.license_manager.stop_periodic_check()

    def handle_add_command(self) -> None:
        """处理添加链接命令"""
        self.utils.add_links_cli()

    def handle_look_command(self) -> None:
        """处理查看链接命令"""
        self.utils.view_links_in_db()

    def handle_clear_command(self) -> None:
        """处理清除数据库命令"""
        if len(sys.argv) > 2:
            self.utils.clear_database(status=sys.argv[2])
        else:
            self.utils.clear_database()

    def show_help(self) -> None:
        """显示帮助信息"""
        print("使用方法: python DY_ku.py [run|add|look|clear]")

    def _prepare_url_list_mode(self) -> None:
        """准备URL列表模式"""
        cleaned_urls = []
        invalid_count = 0
        for url in self.config.URLS:
            cleaned_url = self.utils.extract_douyin_link(url)
            if cleaned_url:
                cleaned_urls.append(cleaned_url)
            else:
                invalid_count += 1
                if self.config.DEBUG:
                    print(f"无效的抖音链接，已跳过: {url}")

        self.config.URLS = cleaned_urls
        if invalid_count > 0:
            if self.config.DEBUG:
                print(f"URLS列表中有 {invalid_count} 个无效链接已跳过")

        if self.config.DEBUG:
            print(f"使用列表模式，共 {len(self.config.URLS)} 个有效URL")
        self.utils.reset_url_list_index()

    def _output_browser_start_event(self, browser_id: str) -> None:
        """输出单个浏览器的start事件"""
        result = {"code": 0, "data": {"type": "start", "id": browser_id}}
        output = json.dumps(result, ensure_ascii=False)
        print(output)