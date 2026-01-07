#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音自动化脚本
使用抽象类设计模式重构版本
"""

import sys
from .crawler import ConcreteDyShareCrawler


class DouyinShareCrawler:
    """抖音自动化主类"""

    def start(self):
        """
        主函数 - 控制整体执行流程
        """
        crawler = ConcreteDyShareCrawler()

        try:
            # 仅保留默认运行（列表模式）。忽略所有命令行参数。
            crawler.execute_main_process()

        except Exception as e:
            print(f"程序执行出错: {e}")
            sys.exit(1)
