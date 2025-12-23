import asyncio

from .tools import verify, config, log
from .tools.core import AbstractCrawler
from .dy import DouyinCrawler
from .dyShare import DouyinShareCrawler
# from .ks import KuaishouCrawler

from .tools.ws_client import WSClient


class TaskManager:
    CRAWLERS = {"dy": DouyinCrawler}  # , "ks": KuaishouCrawler

    def __init__(self, ws_url: str):
        self.ws = WSClient(url=ws_url)

    @staticmethod
    async def create_crawler(platform: str, ws: WSClient) -> AbstractCrawler:
        crawler_class = TaskManager.CRAWLERS.get(platform)
        if not crawler_class:
            raise ValueError(
                "Invalid Media Platform. Currently only supported dy or dys or ks ..."
            )
        crawler = crawler_class(ws)
        return crawler

    async def _start_crawler(self):
        await self.ws.ready_event.wait()

        crawler = await self.create_crawler(config.PLATFORM, self.ws)
        await crawler.start()

    async def start(self):
        tasks = [
            asyncio.create_task(self.ws.run()),
            asyncio.create_task(verify(self.ws)),
            asyncio.create_task(self._start_crawler()),
        ]

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()

        for task in done:
            exc = task.exception()
            if exc:
                await self.ws.send({"cmd": "ErrReq", "logs": exc})
                await self.ws.close()
                raise exc
        else:
            await self.ws.close()


def main():
    # 根据平台和运行模式选择执行方式
    if config.PLATFORM == "dy":
        if config.RUN_MODE == "share":
            # 运行分享模式
            o = DouyinShareCrawler()
            o.start()
            return
        elif config.RUN_MODE == "search":
            # 运行搜索模式（异步模式）
            manager = TaskManager(ws_url=config.WS_URL)
            try:
                asyncio.run(manager.start())
            except KeyboardInterrupt:
                print("✅ Ctrl+C 终止")
            except Exception as e:
                log.debug(e, exc_info=True)
            return
        else:
            print(f"❌ 错误：不支持的模式 '{config.RUN_MODE}'。")
            return
    else:
        print(f"❌ 错误：不支持的平台 '{config.PLATFORM}'。")
        return

if __name__ == "__main__":
    main()

