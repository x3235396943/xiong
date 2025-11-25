import asyncio

from .tools import verify, config
from .tools.base import AbstractCrawler
from .dy import DouyinCrawler
from .dyShare import DouyinShareCrawler
from .ks import KuaishouCrawler


class CrawlerFactory:
    CRAWLERS = {"dy": DouyinCrawler, "dys": DouyinShareCrawler, "ks": KuaishouCrawler}

    @staticmethod
    def create_crawler(platform: str) -> AbstractCrawler:
        crawler_class = CrawlerFactory.CRAWLERS.get(platform)
        if not crawler_class:
            raise ValueError(
                "Invalid Media Platform Currently only supported dy or dys or ks ..."
            )
        return crawler_class()


async def run():
    crawler = CrawlerFactory.create_crawler(platform=config.PLATFORM)
    await crawler.start()


async def startTask():
    await asyncio.wait(
        [asyncio.create_task(verify()), asyncio.create_task(run())],
        return_when=asyncio.FIRST_COMPLETED,
    )


def main():
    asyncio.run(startTask())


if __name__ == "__main__":
    main()
