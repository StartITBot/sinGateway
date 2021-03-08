import asyncio
import logging
import traceback
from random import randint
from . import Shard

log = logging.getLogger(__name__)


class DistributedShardQueue:
    def __init__(self, client):
        self.client = client
        self.shards = []
        self.polling = False
        self._polling_task = None

    def queue(self, shard):
        if int(shard) in (int(s) for s in self.shards):
            return

        self.shards.append(Shard(self.client, int(shard)))
        return self._pool()

    def _pool(self):
        if self.polling:
            return

        self.polling = True
        self._polling_task = self.client.loop.create_task(self.start_shard())

    async def _wait_until_expire(self):
        while True:
            exp = await self.client.redis.pttl("cluster:start")

            if exp == -1:  # Doesn't expire (?)
                await asyncio.sleep(5.1)
                continue

            if exp == -2:  # Expired
                return

            await asyncio.sleep((exp + randint(100, 300)) / 1000)

    async def start_shard(self):
        while True:
            try:
                if len(self.shards) == 0:
                    self.polling = False
                    return

                next_start = await self.client.redis.set(
                    "cluster:start", int(self.shards[0]), pexpire=5000, exist=self.client.redis.SET_IF_NOT_EXIST
                )

                if not next_start:
                    await self._wait_until_expire()
                    continue

                shard = self.shards.pop(0)

                log.info("Starting shard %i... (%i left)", shard.id, len(self.shards))
                await shard.start()
            except asyncio.CancelledError:
                raise
            except Exception:
                traceback.print_exc()
