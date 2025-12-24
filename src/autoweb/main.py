import asyncio

from autoweb.dyShare import crawler

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
        self.crawler = []

    @staticmethod
    def create_crawler(platform: str, ws: WSClient) -> AbstractCrawler:
        crawler_class = TaskManager.CRAWLERS.get(platform)
        if not crawler_class:
            raise ValueError(
                "Invalid Media Platform. Currently only supported dy or dys or ks ..."
            )
        return crawler_class(ws)

    async def _start_crawler(self):
        await self.ws.ready_event.wait()

        async with asyncio.TaskGroup() as tg:
            for v in self.ws.config.BIT_BROWSER_IDS:
                crawler = self.create_crawler(config.PLATFORM, self.ws)
                self.crawler.append(crawler)
                tg.create_task(asyncio.to_thread(crawler.start, v))

    async def start(self):
        tasks = [
            asyncio.create_task(self.ws.run()),
            asyncio.create_task(verify(self.ws)),
            asyncio.create_task(self._start_crawler()),
        ]

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in pending:
            task.cancel()

        if pending:
            await asyncio.wait(pending, return_when=asyncio.ALL_COMPLETED)

        try:
            for task in done:
                exc = task.exception()
                if exc:
                    raise exc
        except Exception as e:
            await self.ws.send({"cmd": "ErrReq", "logs": e})
        finally:
            for crawler in self.crawler:
                crawler.stop()
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
