#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音自动化脚本 (已修复滚动逻辑 + 防休眠)

环境变量配置说明:
    SIBERIAN_KEY: 卡密密钥，用于验证脚本使用权限
    DEVICE_CODE: 设备码，标识当前设备

使用方法:
    1. 在Windows命令行中设置环境变量:
       set SIBERIAN_KEY=你的卡密
       set DEVICE_CODE=设备标识

    2. 在Linux/Mac终端中设置环境变量:
       export SIBERIAN_KEY=你的卡密
       export DEVICE_CODE=设备标识

    3. 或者在运行脚本前直接指定环境变量:
       SIBERIAN_KEY=你的卡密 DEVICE_CODE=设备标识

注意事项:
    - 服务器端可以随时使卡密失效，失效后脚本将停止运行
    - 脚本每3分钟验证一次卡密有效性
"""

import sys
from ..tools.base import AbstractCrawler
from ..tools.verify import LicenseException
from .utils import DyShareUtils

# 实例化工厂
dy_utils = DyShareUtils()


class DouyinShareCrawler(AbstractCrawler):
    async def start(self):
        """
        主函数
        """
        try:
            if len(sys.argv) > 1:
                if sys.argv[1] == "add":
                    dy_utils.add_links_cli()
                    return
                elif sys.argv[1] == "run":
                    dy_utils.main_database()
                    return
                elif sys.argv[1] == "look":
                    dy_utils.view_links_in_db()
                    return
                elif sys.argv[1] == "clear":
                    if len(sys.argv) > 2:
                        dy_utils.clear_database(status=sys.argv[2])
                    else:
                        dy_utils.clear_database()
                    return
                elif sys.argv[1] == "help":
                    print("使用方法: python DY_ku.py [run|add|look|clear]")
                    return

            # 默认执行主数据库流程
            dy_utils.main_database()

        except LicenseException:
            print("卡密验证失败，程序即将退出")
            sys.exit(1)
        except KeyboardInterrupt:
            print("程序已被用户中断")
            sys.exit(0)