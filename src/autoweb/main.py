from .tools import config, log
from .dyShare import DouyinShareCrawler
from .dySearch import DouyinSearchCrawler
from .ksShare import KuaishouShareCrawler
from .ksSearch import KuaishouSearchCrawler


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

    if config.PLATFORM == "ks":
        if config.RUN_MODE == "share":
            o = KuaishouShareCrawler()
            o.start()
            return
        if config.RUN_MODE == "search":
            o = KuaishouSearchCrawler()
            o.start()
            return
        print(f"❌ 错误：不支持的模式 '{config.RUN_MODE}'.")
        return

    print(f"❌ 错误：不支持的平台 '{config.PLATFORM}'.")
    return


if __name__ == "__main__":
    main()
