#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
抖音分享爬虫抽象基类
定义爬虫的基本行为和执行顺序
"""

from abc import ABC, abstractmethod
import sys
import json
import time
import concurrent.futures
from typing import List, Dict, Any, Optional


class BaseDyShareCrawler(ABC):
    """抖音分享爬虫抽象基类"""

    def __init__(self):
        """初始化爬虫"""
        self.config = None
        self.utils = None

    @abstractmethod
    def initialize_config(self) -> None:
        """初始化配置"""
        pass

    @abstractmethod
    def validate_license(self) -> bool:
        """验证卡密"""
        pass

    @abstractmethod
    def prepare_environment(self) -> None:
        """准备运行环境"""
        pass

    @abstractmethod
    def setup_database(self) -> None:
        """设置数据库"""
        pass

    @abstractmethod
    def output_version_info(self) -> None:
        """输出版本信息"""
        pass

    @abstractmethod
    def process_urls_with_thread_pool(self) -> None:
        """使用线程池处理URL"""
        pass

    @abstractmethod
    def cleanup_resources(self) -> None:
        """清理资源"""
        pass

    def execute_main_process(self) -> None:
        """
        执行主流程 - 定义执行顺序
        这是一个模板方法，定义了爬虫执行的标准流程
        """
        try:
            # 1. 初始化配置
            self.initialize_config()
            
            # 2. 验证卡密
            if not self.validate_license():
                print("❌ 卡密验证失败！")
                return
            
            # 3. 准备运行环境
            self.prepare_environment()
            
            # 4. 设置数据库
            self.setup_database()
            
            # 5. 输出版本信息
            self.output_version_info()
            
            # 6. 处理URL
            self.process_urls_with_thread_pool()
            
        except KeyboardInterrupt:
            print("程序已被用户中断")
            sys.exit(0)
        except Exception as e:
            print(f"程序执行出错: {e}")
            sys.exit(1)
        finally:
            # 7. 清理资源
            self.cleanup_resources()

    def handle_command(self, command: str) -> None:
        """
        处理命令行指令
        """
        if command == "add":
            self.handle_add_command()
        elif command == "run":
            self.execute_main_process()
        elif command == "look":
            self.handle_look_command()
        elif command == "clear":
            self.handle_clear_command()
        elif command == "help":
            self.show_help()
        else:
            # 默认执行主流程
            self.execute_main_process()

    @abstractmethod
    def handle_add_command(self) -> None:
        """处理添加链接命令"""
        pass

    @abstractmethod
    def handle_look_command(self) -> None:
        """处理查看链接命令"""
        pass

    @abstractmethod
    def handle_clear_command(self) -> None:
        """处理清除数据库命令"""
        pass

    @abstractmethod
    def show_help(self) -> None:
        """显示帮助信息"""
        pass