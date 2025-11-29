#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音自动化脚本 (已修复滚动逻辑 + 防休眠)
使用抽象类设计模式重构版本
"""

import sys
from ..tools.base import AbstractCrawler
from .concrete_crawler import ConcreteDyShareCrawler


class DouyinShareCrawler(AbstractCrawler):
    """抖音分享爬虫主类"""

    async def start(self):
        """
        主函数 - 控制整体执行流程
        """
        crawler = ConcreteDyShareCrawler()

        try:
            if len(sys.argv) > 1:
                crawler.handle_command(sys.argv[1])
            else:
                # 默认执行主流程
                crawler.execute_main_process()

        except Exception as e:
            print(f"程序执行出错: {e}")
            sys.exit(1)
