import asyncio

from .tools import verify, config, log
from .tools.base import AbstractCrawler
from .dy import DouyinCrawler
from .dyShare import DouyinShareCrawler
# from .ks import KuaishouCrawler

from .tools.web_client import WSClient


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
    # 保留原来的逻辑以防需要
    if config.PLATFORM == "dy" and config.RUN_MODE == "share":
        o = DouyinShareCrawler()
        o.start()
        return

    manager = TaskManager(ws_url=config.WS_URL)
    try:
        asyncio.run(manager.start())
    except KeyboardInterrupt:
        print("✅ Ctrl+C 终止")
    except Exception as e:
        log.debug(e, exc_info=True)


if __name__ == "__main__":
    main()

