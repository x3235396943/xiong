from .tools import config, log
from .dyShare import DouyinShareCrawler
from .dySearch import DouyinSearchCrawler
from .ks.ksShare import main as ks_share_main
from .ks.ksSearch import main as ks_search_main
from .xhs.xhsShare import main as xhs_share_main
from .xhs.xhsSearch import main as xhs_search_main


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
            ks_share_main()
            return
        if config.RUN_MODE == "search":
            ks_search_main()
            return
        print(f"❌ 错误：不支持的模式 '{config.RUN_MODE}'.")
        return

    if config.PLATFORM == "xhs":
        if config.RUN_MODE == "share":
            xhs_share_main()
            return
        if config.RUN_MODE == "search":
            xhs_search_main()
            return
        print(f"❌ 错误：不支持的模式 '{config.RUN_MODE}'.")
        return
    return


if __name__ == "__main__":
    main()
