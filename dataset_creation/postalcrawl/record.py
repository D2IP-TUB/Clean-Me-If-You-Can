from typing import TypedDict


class Record[T](TypedDict):
    crawl_metadata: dict
    data: T
