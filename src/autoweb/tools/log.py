import json
import logging


class MyFormatter(logging.Formatter):
    def format(self, record):
        record.msg = json.dumps(record.msg)
        return super().format(record)


def init_loging_config1():
    logger1 = logging.getLogger("detailed_logger")
    logger1.setLevel(logging.DEBUG)
    handler1 = logging.StreamHandler()
    formatter1 = logging.Formatter(
        "%(asctime)s %(levelname)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler1.setFormatter(formatter1)
    logger1.addHandler(handler1)

    logger2 = logging.getLogger("simple_logger")
    logger2.setLevel(logging.DEBUG)
    handler2 = logging.StreamHandler()
    formatter2 = MyFormatter()
    handler2.setFormatter(formatter2)
    logger2.addHandler(handler2)
    return logger1, logger2


log1, log2 = init_loging_config1()
