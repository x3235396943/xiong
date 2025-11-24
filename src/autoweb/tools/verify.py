from asyncio import sleep

import aiohttp
import ujson

from .config import config


async def verify():
    async with aiohttp.ClientSession(json_serialize=ujson.dumps) as session:
        while True:
            async with session.post(
                config.SIBERIAN_URL,
                json={
                    "siberian": config.SIBERIAN_KEY,
                    "deviceCode": config.DEVICE_CODE,
                },
            ) as response:
                res = await response.json()
                if res["code"] != 200:
                    raise Exception(res)
            await sleep(180)
