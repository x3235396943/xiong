"""
异步工具模块：提供线程池包装器，用于在协程中执行同步的 Selenium 操作
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Any, List, Dict
import functools


class AsyncSeleniumExecutor:
    """异步 Selenium 执行器：使用线程池在协程中执行同步的 Selenium 操作"""
    
    def __init__(self, max_workers: int = 5):
        """
        初始化异步执行器
        Args:
            max_workers: 线程池最大工作线程数
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.loop = None
    
    def __del__(self):
        """清理资源"""
        if self.executor:
            self.executor.shutdown(wait=False)
    
    async def run_in_thread(self, func: Callable, *args, **kwargs) -> Any:
        """
        在线程池中执行同步函数
        Args:
            func: 要执行的同步函数
            *args: 位置参数
            **kwargs: 关键字参数
        Returns:
            函数的返回值
        """
        if self.loop is None:
            self.loop = asyncio.get_event_loop()
        
        return await self.loop.run_in_executor(
            self.executor,
            functools.partial(func, *args, **kwargs)
        )
    
    async def run_multiple(self, tasks: List[Dict]) -> List[Any]:
        """
        并发执行多个任务
        Args:
            tasks: 任务列表，每个任务格式: {
                'func': 要执行的函数,
                'args': 位置参数列表,
                'kwargs': 关键字参数字典
            }
        Returns:
            每个任务的执行结果列表
        """
        coroutines = []
        for task in tasks:
            func = task['func']
            args = task.get('args', [])
            kwargs = task.get('kwargs', {})
            coroutines.append(self.run_in_thread(func, *args, **kwargs))
        
        return await asyncio.gather(*coroutines, return_exceptions=True)
    
    def shutdown(self, wait: bool = True):
        """关闭线程池"""
        if self.executor:
            self.executor.shutdown(wait=wait)


# 全局异步执行器实例
_global_executor = None


def get_executor(max_workers: int = 5) -> AsyncSeleniumExecutor:
    """
    获取全局异步执行器实例
    Args:
        max_workers: 线程池最大工作线程数（仅在首次创建时生效）
    Returns:
        异步执行器实例
    """
    global _global_executor
    if _global_executor is None:
        _global_executor = AsyncSeleniumExecutor(max_workers=max_workers)
    return _global_executor


async def run_selenium_async(func: Callable, *args, **kwargs) -> Any:
    """
    在协程中执行 Selenium 同步函数
    Args:
        func: 要执行的同步函数
        *args: 位置参数
        **kwargs: 关键字参数
    Returns:
        函数的返回值
    """
    executor = get_executor()
    return await executor.run_in_thread(func, *args, **kwargs)

