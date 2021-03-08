import logging

import aiohttp as aiohttp
import aioredis as aioredis
import singyeong
from aioredis import Redis

from . import ClientConfig, DistributedShardQueue

log = logging.getLogger(__name__)


class Gateway:
    DISCORD_GATEWAY = "https://discord.com/api/v8"

    def __init__(self, config: ClientConfig, loop=None, *, cluster_id=None):
        self.config = config
        self.loop = loop
        self.cluster_id = cluster_id
        self.gateway_information = {}

        self.singyeong = singyeong.Client(config.singyeong_dsn, loop=loop)
        self.singyeong.on_ready = self.on_ready

        # --------------------------------
        # Run function self.on_close() on singyeong close:

        super_ = self.singyeong._close

        async def decorator():
            await super_()
            await self.on_close()

        self.singyeong._close = decorator

        # --------------------------------

        self._closing = False

        self.queue = None
        self.redis: Redis = None
        self.shards = None
        self.shard_count = None

    async def on_ready(self):
        log.info("Singyeong is ready.")

    async def connect(self):
        await self.singyeong.wait_until_ready()

        self.redis = await aioredis.create_redis_pool(self.config.redis_dsn)
        log.info("Created redis connection.")

        async with aiohttp.ClientSession(headers={"Authorization": f"Bot {self.config.token}"}) as session:
            bot_information_req = await session.get(
                self.DISCORD_GATEWAY + "/gateway/bot",
                raise_for_status=True
            )
            self.gateway_information = await bot_information_req.json()

        if self.config.cluster_enabled and self.cluster_id is not None:
            self.shards = list(range(
                self.cluster_id * self.config.cluster_shards,
                (self.cluster_id + 1) * self.config.cluster_shards
            ))
            self.shard_count = self.config.cluster_count * self.config.cluster_shards
        else:
            self.shards = list(range(0, self.gateway_information.get("shards", 1)))
            self.shard_count = self.gateway_information.get("shards", 1)

        self.queue = DistributedShardQueue(self)

        for shard in self.shards:
            self.queue.queue(shard)

    async def on_close(self):
        if self.redis:
            self.redis.close()
            await self.redis.wait_closed()
            log.info("Closed redis connection.")
