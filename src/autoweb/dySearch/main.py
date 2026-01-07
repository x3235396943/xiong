import sys

from ..tools import log
from ..tools import config as tools_config
from ..dySearch.crawler import ConcreteDySearchCrawler


class DouyinSearchCrawler:
    def start(self):
        if getattr(tools_config, "RUN_MODE", "") != "search":
            log.warning(
                f"当前 RUN_MODE={getattr(tools_config, 'RUN_MODE', None)}，仅用于 search"
            )
        crawler = ConcreteDySearchCrawler()
        try:
            crawler.execute_main_process()
        except Exception as e:
            print(f"程序执行出错: {e}")
            sys.exit(1)
