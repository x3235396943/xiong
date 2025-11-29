#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import json
import concurrent.futures
import time
from ..tools.base import AbstractCrawler
from ..tools.verify import LicenseException
from ..tools.config import KuSettings
from .utils import DyShareUtils

# 实例化工具类和配置
dy_utils = DyShareUtils()
config = KuSettings()

class DouyinShareCrawler(AbstractCrawler):
    async def start(self):
        """
        主函数 - 控制整体执行流程
        """
        try:
            if len(sys.argv) > 1:
                if sys.argv[1] == "add":
                    self._handle_add_command()
                    return
                elif sys.argv[1] == "run":
                    await self._handle_run_command()
                    return
                elif sys.argv[1] == "look":
                    self._handle_look_command()
                    return
                elif sys.argv[1] == "clear":
                    self._handle_clear_command()
                    return
                elif sys.argv[1] == "help":
                    self._show_help()
                    return

            # 默认执行主数据库流程
            await self._handle_run_command()

        except LicenseException:
            print("卡密验证失败，程序即将退出")
            sys.exit(1)
        except KeyboardInterrupt:
            print("程序已被用户中断")
            sys.exit(0)

    def _handle_add_command(self):
        """处理添加链接命令"""
        dy_utils.add_links_cli()

    async def _handle_run_command(self):
        """处理运行命令"""
        await self._execute_main_process()

    def _handle_look_command(self):
        """处理查看链接命令"""
        dy_utils.view_links_in_db()

    def _handle_clear_command(self):
        """处理清除数据库命令"""
        if len(sys.argv) > 2:
            dy_utils.clear_database(status=sys.argv[2])
        else:
            dy_utils.clear_database()

    def _show_help(self):
        """显示帮助信息"""
        print("使用方法: python DY_ku.py [run|add|look|clear]")

    async def _execute_main_process(self):
        """执行主流程"""
        # 首先验证卡密
        li = dy_utils.get_license_manager()  # 获取许可证管理器实例
        if not li.verify_license():
            print("❌ 卡密不存在！")
            return

        # 如果启用了调试模式，打印所有配置参数
        if config.DEBUG:
            dy_utils.print_config_debug()

        # 启动定期验证线程
        li.start_periodic_check()

        # 开启防休眠
        dy_utils.set_keep_awake(True)

        # 判断使用列表模式还是数据库模式
        use_list_mode = config.URLS and len(config.URLS) > 0

        if use_list_mode:
            self._prepare_url_list_mode()
        else:
            print("使用数据库模式")
            # 添加0.2秒延迟
            time.sleep(0.2)
            dy_utils.init_database()

        if not config.BIT_BROWSER_IDS:
            print("请在代码中的 BIT_BROWSER_IDS 列表中配置浏览器ID")
            return

        # 输出版本信息
        version_info = {"code": 0, "data": {"type": "version", "version": f"pc.{config.VERSION}"}}
        output = json.dumps(version_info, ensure_ascii=False)
        print(output)
        # 添加0.2秒延迟
        time.sleep(0.2)

        # 执行主要处理流程
        try:
            await self._process_with_thread_pool()
        except LicenseException:
            print("卡密验证失败，程序终止")
            raise
        finally:
            # 关闭防休眠
            dy_utils.set_keep_awake(False)
            li.stop_periodic_check()

    def _prepare_url_list_mode(self):
        """准备URL列表模式"""
        cleaned_urls = []
        invalid_count = 0
        for url in config.URLS:
            cleaned_url = dy_utils.extract_douyin_link(url)
            if cleaned_url:
                cleaned_urls.append(cleaned_url)
            else:
                invalid_count += 1
                if config.DEBUG:
                    print(f"无效的抖音链接，已跳过: {url}")

        config.URLS = cleaned_urls
        if invalid_count > 0:
            if config.DEBUG:
                print(f"URLS列表中有 {invalid_count} 个无效链接已跳过")

        if config.DEBUG:
            print(f"使用列表模式，共 {len(config.URLS)} 个有效URL")
        dy_utils.reset_url_list_index()

    async def _process_with_thread_pool(self):
        """使用线程池处理任务"""
        MAX_WORKERS_USED = len(config.BIT_BROWSER_IDS)
        WAIT_TIME_USED = config.WAIT_TIME
        LIKE_PROBABILITY_USED = config.LIKE_PROBABILITY
        VISIT_PROFILE_PROBABILITY_USED = config.VISIT_ENABLE
        PROFILE_FOLLOW_PROBABILITY_USED = config.PROFILE_FOLLOW_PROBABILITY
        MIN_FOLLOWS_PER_VIDEO_USED = config.MIN_FOLLOWS_PER_VIDEO
        MAX_FOLLOWS_PER_VIDEO_USED = config.MAX_FOLLOWS_PER_VIDEO
        MIN_LIKES_PER_VIDEO_USED = config.COMMENT_LIKE_COUNT_MIN
        MAX_LIKES_PER_VIDEO_USED = config.COMMENT_LIKE_COUNT_MAX

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_USED) as executor:
                futures = []
                for i in range(MAX_WORKERS_USED):
                    browser_id = config.BIT_BROWSER_IDS[i % len(config.BIT_BROWSER_IDS)]

                    # 为每个浏览器实例单独输出start事件
                    self._output_browser_start_event(browser_id)
                    # 添加0.2秒延迟
                    time.sleep(0.2)

                    future = executor.submit(
                        dy_utils.continuous_processing_loop,
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
                        dy_utils._stop_flag.set()
                        for future in futures:
                            future.cancel()
                        import sys
                        sys.exit(0)
        except LicenseException:
            print("卡密验证失败，程序终止")
            raise

    def _output_browser_start_event(self, browser_id):
        """输出单个浏览器的start事件"""
        result = {"code": 0, "data": {"type": "start", "id": browser_id}}
        output = json.dumps(result, ensure_ascii=False)
        print(output)