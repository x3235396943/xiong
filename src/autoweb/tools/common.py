#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
公共工具类
包含数据报告和统计功能
"""

import json
import threading
import queue
from typing import Callable, Optional, Dict, Any


class DataReporter:
    """
    数据报告器
    负责跟踪统计数据，检测变化并自动输出和发送到服务器
    """
    
    def __init__(
        self,
        device_code: str,
        browser_id: str,
        send_ws_message_func: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        初始化数据报告器
        
        Args:
            device_code: 设备码
            browser_id: 浏览器ID
            send_ws_message_func: WebSocket消息发送函数
        """
        self.device_code = device_code
        self.browser_id = browser_id
        self.send_ws_message_func = send_ws_message_func
        
        # 统计数据（每个浏览器实例独立）
        self._stats = {
            "comment": 0,           # 评论回复数量
            "follow": 0,            # 关注数量
            "like": 0,              # 点赞数量
            "urlFail": 0,           # 处理失败的URL数量
            "urlOk": 0,             # 处理成功的URL数量
            "video": 0,             # 处理的链接数量
            "videoComment": 0,      # 视频留言数量
            "keywordsIndex": -1,    # 当前处理的链接索引
        }
        
        # 线程锁，保护统计数据
        self._lock = threading.Lock()
        
        # 总链接数（用于判断isCompleted）
        self._total_links = 0
        self._completed_links = 0
        
        # 异步发送队列和线程（用于非阻塞发送）
        self._send_queue = queue.Queue()
        self._send_thread = None
        self._send_thread_running = False
        self._start_send_thread()
    
    def _start_send_thread(self):
        """启动异步发送线程"""
        if self._send_thread_running:
            return
        
        self._send_thread_running = True
        
        def send_worker():
            """异步发送工作线程（只发送到服务器，不打印）"""
            while self._send_thread_running:
                try:
                    # 从队列获取消息，超时1秒，避免无限阻塞
                    message = self._send_queue.get(timeout=1.0)
                    if message is None:  # None 作为停止信号
                        break
                    
                    # 只发送消息到服务器，不打印到控制台（避免阻塞）
                    if self.send_ws_message_func:
                        try:
                            self.send_ws_message_func(message)
                        except Exception:
                            # 静默忽略发送错误
                            pass
                    
                    self._send_queue.task_done()
                except queue.Empty:
                    # 超时继续循环
                    continue
                except Exception:
                    # 忽略所有错误，继续运行
                    continue
        
        self._send_thread = threading.Thread(target=send_worker, daemon=True)
        self._send_thread.start()
    
    def _stop_send_thread(self):
        """停止异步发送线程"""
        self._send_thread_running = False
        if self._send_thread:
            try:
                self._send_queue.put(None, timeout=1.0)  # 发送停止信号
                self._send_thread.join(timeout=2.0)
            except:
                pass
    
    def set_total_links(self, total: int):
        """
        设置总链接数
        
        Args:
            total: 总链接数
        """
        with self._lock:
            self._total_links = total
    
    def update_completed_links(self, completed: int):
        """
        更新已完成链接数
        
        Args:
            completed: 已完成链接数
        """
        with self._lock:
            self._completed_links = completed
    
    def _check_and_report(self):
        """
        检查统计数据是否有变化，如果有则输出并发送
        注意：此方法应该快速执行，不应该阻塞
        所有耗时操作都放到后台线程执行
        """
        # 在锁内快速读取数据，然后释放锁
        try:
            with self._lock:
                # 判断是否完成：当前浏览器实例处理完所有链接（成功+失败 >= 总链接数）
                is_completed = False
                if self._total_links > 0:
                    # 当前浏览器实例处理的链接数（成功+失败）
                    processed_links = self._stats["urlOk"] + self._stats["urlFail"]
                    is_completed = (processed_links >= self._total_links)
                
                # 复制统计数据（避免在锁外访问）
                stats_copy = self._stats.copy()
                device_code = self.device_code
                browser_id = self.browser_id
        except Exception:
            # 如果读取数据失败，直接返回，不影响主流程
            return
        
        # 将消息构造和发送都放到队列中，由后台线程异步处理
        # 这样主线程完全不会被阻塞
        try:
            # 快速构造消息数据（不进行 JSON 序列化，避免阻塞）
            message_data = {
                "cmd": "PcDataReq",
                "data": {
                    "browserId": browser_id,
                    "comment": stats_copy["comment"],
                    "deviceType": "pc",
                    "follow": stats_copy["follow"],
                    "id": device_code,
                    "isCompleted": is_completed,
                    "keywordsIndex": stats_copy["keywordsIndex"],
                    "like": stats_copy["like"],
                    "urlFail": stats_copy["urlFail"],
                    "urlOk": stats_copy["urlOk"],
                    "video": stats_copy["video"],
                    "videoComment": stats_copy["videoComment"]
                },
                "id": device_code
            }
            
            # 将消息放入队列，由后台线程处理打印和发送（完全异步，不阻塞）
            if self._send_thread_running:
                try:
                    self._send_queue.put_nowait(message_data)
                except queue.Full:
                    # 队列满了，跳过这次发送（不影响主流程）
                    pass
                except Exception:
                    # 忽略所有错误
                    pass
        except Exception:
            # 完全忽略所有错误，确保不影响主流程
            pass
    
    def increment_comment(self, count: int = 1):
        """
        增加评论回复数量
        
        Args:
            count: 增加的数量，默认为1
        """
        with self._lock:
            self._stats["comment"] += count
        # 不自动触发报告，避免阻塞
    
    def increment_follow(self, count: int = 1):
        """
        增加关注数量
        
        Args:
            count: 增加的数量，默认为1
        """
        with self._lock:
            self._stats["follow"] += count
        # 不自动触发报告，避免阻塞
    
    def increment_like(self, count: int = 1):
        """
        增加点赞数量
        
        Args:
            count: 增加的数量，默认为1
        """
        with self._lock:
            self._stats["like"] += count
        # 不自动触发报告，避免阻塞
    
    def increment_url_fail(self, count: int = 1):
        """
        增加处理失败的URL数量
        
        Args:
            count: 增加的数量，默认为1
        """
        with self._lock:
            self._stats["urlFail"] += count
        # 不自动触发报告，避免阻塞
    
    def increment_url_ok(self, count: int = 1):
        """
        增加处理成功的URL数量
        
        Args:
            count: 增加的数量，默认为1
        """
        with self._lock:
            self._stats["urlOk"] += count
        # 不自动触发报告，避免阻塞
    
    def increment_video(self, count: int = 1):
        """
        增加处理的链接数量
        
        Args:
            count: 增加的数量，默认为1
        """
        with self._lock:
            self._stats["video"] += count
        # 不自动触发报告，避免阻塞
    
    def increment_video_comment(self, count: int = 1):
        """
        增加视频留言数量
        
        Args:
            count: 增加的数量，默认为1
        """
        with self._lock:
            self._stats["videoComment"] += count
        # 不自动触发报告，避免阻塞
    
    def update_keywords_index(self, index: int):
        """
        更新当前处理的链接索引
        
        Args:
            index: 链接索引
        """
        with self._lock:
            self._stats["keywordsIndex"] = index
        # 不自动触发报告，避免阻塞
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取当前统计数据（只读）
        
        Returns:
            统计数据字典
        """
        with self._lock:
            return self._stats.copy()
    
    def force_report(self):
        """
        强制输出当前统计数据（即使没有变化）
        """
        self._check_and_report()
    
    def __del__(self):
        """析构函数，清理资源"""
        self._stop_send_thread()

