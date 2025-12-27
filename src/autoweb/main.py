import asyncio
from .tools import config, log
from .dyShare import DouyinShareCrawler
from .dySearch import DouyinSearchCrawler
from .ks.main import KuaishouCrawler


def main():
    # 根据平台和运行模式选择执行方式
    if config.PLATFORM == "dy":
        if config.RUN_MODE == "share":
            o = DouyinShareCrawler()
            o.start()
            return
        if config.RUN_MODE == "search":
            o = DouyinSearchCrawler()
            o.start()
            return
        print(f"❌ 错误：不支持的模式 '{config.RUN_MODE}'.")
        return
    elif config.PLATFORM == "ks":
        # 快手平台
        o = KuaishouCrawler()
        asyncio.run(o.start())
        return
    else:
        print(f"❌ 错误：不支持的平台 '{config.PLATFORM}'.")
        return


if __name__ == "__main__":
    main()
