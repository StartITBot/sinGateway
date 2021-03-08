import asyncio
import logging
import time
import traceback

from aioredis import Redis
from singyeong import Client

from .enums import OpCode

try:
    import ujson as json
except ImportError:
    import json

import sys
import zlib

from . import __version__, to_json
import aiohttp


log = logging.getLogger(__name__)


class DiscordClientWebSocketResponse(aiohttp.ClientWebSocketResponse):
    async def close(self, *, code: int = 4000, message: bytes = b'') -> bool:
        return await super().close(code=code, message=message)


class WebSocketClosure(Exception):
    """An exception to make up for the fact that aiohttp doesn't signal closure."""
    def __init__(self, code, reason):
        self.code = code
        self.reason = reason


class ReconnectWebSocket(Exception):
    """Signals to safely reconnect the websocket."""
    def __init__(self, shard_id, *, resume=True):
        self.shard_id = shard_id
        self.resume = resume
        self.op = 'RESUME' if resume else 'IDENTIFY'


class Shard:

    def __init__(self, client, id_):
        self.client = client
        self.socket = None
        self.id = int(id_)
        self.buffer = bytearray()
        self.inflator = zlib.decompressobj()

        self._poll_task = None
        self._keep_alive_task = None
        self.__session = None
        self.__sequence = None

        user_agent = 'DiscordBot (https://github.com/StartITBot/SinGateway {0}) Python/{1[0]}.{1[1]} aiohttp/{2}'

        self.user_agent = user_agent.format(__version__, sys.version_info, aiohttp.__version__)

    def __int__(self):
        return self.id

    def __hash__(self):
        return self.id

    def __eq__(self, other):
        return int(self) == int(other)

    async def start(self):
        await self.ensure_closed()

        url = self.client.gateway_information.get('url') or 'wss://gateway.discord.gg'

        self.__session = aiohttp.ClientSession(
            ws_response_class=DiscordClientWebSocketResponse
        )

        self.socket = await self.__session.ws_connect(
            f"{url}?encoding=json&v=8&compress=zlib-stream",
            max_msg_size=0,
            timeout=30.0,
            autoclose=False,
            headers={
                'User-Agent': self.user_agent,
            },
            compress=0
        )

        await self.poll_event()

        await self.identify()

        self._poll_task = self.client.loop.create_task(
            self.worker()
        )

    async def identify(self):
        session_id, sequence = await self.fetch_session()

        if session_id is not None:
            self.__sequence = int(sequence.decode())

            payload = {
                'op': OpCode.RESUME,
                'd': {
                    'token': self.client.config.token,
                    'session_id': session_id.decode(),
                    'seq': self.__sequence,
                }
            }
            await self.send_as_json(payload)
            log.info('!%i!An RESUME request has been sent', self.id)
        else:
            await self.clear_session()

            payload = {
                'op': OpCode.IDENTIFY,
                'd': {
                    'token': self.client.config.token,
                    'properties': {
                        '$os': sys.platform,
                        '$browser': 'SinGateway',
                        '$device': 'SinGateway'
                    },
                    'intents': self.client.config.intents,
                    'compress': True,
                    'large_threshold': 250,
                    'shard': [self.id, self.client.shard_count]
                }
            }
            await self.send_as_json(payload)
            log.info('!%i!An IDENTIFY request has been sent.', self.id)

    async def fetch_session(self):
        session_id, heartbeat, sequence = await asyncio.gather(
            self.client.redis.get(f"shard:{self.id}:session_id"),
            self.client.redis.get(f"shard:{self.id}:last_heartbeat_ack"),
            self.client.redis.get(f"shard:{self.id}:seq")
        )

        if session_id is None or heartbeat is None or sequence is None:
            return None, None

        # noinspection PyUnresolvedReferences
        timestamp = int(heartbeat.decode()) + 60000
        if timestamp < time.time() * 1000:
            return None, None

        return session_id, sequence

    async def clear_session(self):
        r: Redis = self.client.redis
        await r.delete(f"shard:{self.id}:session_id", f"shard:{self.id}:seq", f"shard:{self.id}:last_heartbeat_ack")

    async def worker(self):
        while True:
            await self.poll_event()

    async def heartbeat_worker(self, interval):
        while True:
            await asyncio.sleep(interval)
            await self.make_heartbeat()

    async def make_heartbeat(self):
        asyncio.ensure_future(self.client.redis.set(f"shard:{self.id}:last_heartbeat", int(time.time() * 1000)))

        if self.__sequence is None:
            asyncio.ensure_future(self.client.redis.delete(f"shard:{self.id}:seq"))
        else:
            asyncio.ensure_future(self.client.redis.set(f"shard:{self.id}:seq", self.__sequence))

        await self.send(to_json({
            "op": OpCode.HEARTBEAT,
            "d": self.__sequence
        }), bypass_ratelimit=True)

    async def poll_event(self):
        try:
            msg = await self.socket.receive(timeout=60.0)
            if msg.type is aiohttp.WSMsgType.TEXT:
                asyncio.ensure_future(self.received_message(msg.data))

            elif msg.type is aiohttp.WSMsgType.BINARY:

                self.buffer.extend(msg.data)

                if len(msg.data) < 4 or msg.data[-4:] != b'\x00\x00\xff\xff':
                    return

                message = await self.client.loop.run_in_executor(None, self.inflator.decompress, self.buffer)
                message = message.decode('utf-8')
                self.buffer.clear()

                asyncio.ensure_future(self.received_message(message))
            elif msg.type is aiohttp.WSMsgType.ERROR:
                log.debug('!%i!Received %s', self.id, msg)
                raise msg.data
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSE):
                log.debug('!%i!Received %s', self.id, msg)
                raise WebSocketClosure(msg.data, msg.extra)
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                await self.ensure_closed()
                raise

            if isinstance(e, asyncio.TimeoutError):
                log.info('!%i!Timed out receiving packet. Attempting a reconnect.', self.id)
            elif isinstance(e, WebSocketClosure):
                log.info('!%i!Websocket closed with %s ("%s"), attempting a reconnect.',
                         self.id, self.socket.close_code, e.reason)
            else:
                log.error("!%i!Reconnecting due to error occurred in poll_event():\n%s",
                          self.id, ''.join(traceback.format_exc()))

            self.client.queue.queue(self.id)
            await self.ensure_closed()

    async def send(self, data, *, bypass_ratelimit=False):
        if not bypass_ratelimit:
            ...  # TODO rate limiter

        try:
            await self.socket.send_str(data)
        except (RuntimeError, ConnectionError):
            log.info('!%s!Error occurred while trying to send payload. Reconnecting.', self.id)
            self.client.queue.queue(self.id)
            await self.ensure_closed()

    async def send_as_json(self, data):
        await self.send(to_json(data))

    async def ensure_closed(self, code=4000):
        if self.__sequence is None:
            asyncio.ensure_future(self.client.redis.delete(f"shard:{self.id}:seq"))
        else:
            asyncio.ensure_future(self.client.redis.set(f"shard:{self.id}:seq", self.__sequence))

        if self.socket and not self.socket.closed:
            try:
                await asyncio.wait_for(self.socket.close(code=code), 5)
            except TimeoutError:
                pass

        if self.__session:
            await self.__session.close()

        if self._poll_task and not self._poll_task.done():
            try:
                self._poll_task.cancel()
            except AssertionError:  # yield from wasn't used with future
                pass

            await self._poll_task
            self._poll_task = None

        if self._keep_alive_task and not self._keep_alive_task.done():
            try:
                self._keep_alive_task.cancel()
            except AssertionError:  # yield from wasn't used with future
                pass

            await self._keep_alive_task
            self._keep_alive_task = None

    def format_target(self, target, *, event=None):
        if isinstance(target, dict):
            return {k: self.format_target(v, event=event) for k, v in target.items()}

        if isinstance(target, list):
            return [self.format_target(v, event=event) for v in target]

        if isinstance(target, str):
            cluster_id = self.client.cluster_id

            target = target.replace("{{SHARD}}", f'self.client.id')
            target = target.replace("{{CLUSTER}}", "0" if cluster_id is None else str(cluster_id))
            target = target.replace("{{EVENT}}", event or '')

        return target

    async def received_message(self, msg):
        msg = json.loads(msg)

        log.debug('For Shard ID %s: WebSocket Event: %s', self.id, msg)
        op = msg.get('op')
        data = msg.get('d')
        seq = msg.get('s')

        if seq is not None:
            self.__sequence = seq

        if op != OpCode.DISPATCH:
            if op == OpCode.RECONNECT:
                log.info('!%i!Received RECONNECT opcode', self.id)
                self.client.queue.queue(self.id)
                return await self.ensure_closed()

            elif op == OpCode.HEARTBEAT_ACK:
                now_ms = int(time.time() * 1000)
                start_ms_r = await self.client.redis.get(f"shard:{self.id}:last_heartbeat")
                start_ms = start_ms_r and int(start_ms_r.decode())

                return await asyncio.gather(
                    self.client.redis.set(f"shard:{self.id}:latency", now_ms - start_ms if start_ms else -1),
                    self.client.redis.set(f"shard:{self.id}:last_heartbeat_ack", now_ms),
                )

            elif op == OpCode.HEARTBEAT:
                return await self.make_heartbeat()

            elif op == OpCode.HELLO:
                interval = data['heartbeat_interval'] / 1000.0

                if self._keep_alive_task and not self._keep_alive_task.done():
                    self._keep_alive_task.cancel()

                self._keep_alive_task = self.client.loop.create_task(
                    self.heartbeat_worker(interval)
                )
                return

            elif op == OpCode.INVALIDATE_SESSION:
                if data is True:
                    log.info('!%i!Received INVALIDATE_SESSION opcode. Resuming...', self.id)
                    self.client.queue.queue(self.id)
                    return await self.ensure_closed()

                log.info('!%i!Received INVALIDATE_SESSION opcode.', self.id)
                self.client.queue.queue(self.id)
                return await self.ensure_closed(code=1000)

            log.warning('Unknown OP code %s.', op)
            return

        event = msg.get('t')

        if event == 'READY':
            asyncio.ensure_future(self.client.redis.set(f"shard:{self.id}:session_id", data['session_id']))
            asyncio.ensure_future(self.client.redis.set(f"shard:{self.id}:last_heartbeat_ack", int(time.time() * 1000)))
            log.info('!%i!Received READY opcode, session: %s.', self.id, data['session_id'])

        elif event == 'RESUMED':
            session_id = await self.client.redis.get(f"shard:{self.id}:session_id")
            log.info('!%i!Received RESUMED opcode, session: %s.', self.id, session_id.decode())
            asyncio.ensure_future(self.client.redis.set(f"shard:{self.id}:last_heartbeat_ack", int(time.time() * 1000)))

        singyeong: Client = self.client.singyeong

        for rule in self.client.config.forwarding:
            if event not in rule.get("events", []):
                continue

            target = self.format_target(rule.get("target", {}), event=event)
            if rule.get("type", "").lower() == "broadcast":
                await singyeong.broadcast(target, msg)
                log.info('!%i!New BROADCAST for %s event to: %s', self.id, event, repr(target))
            else:
                await singyeong.send(target, msg)
                log.info('!%i!New SEND for %s event to: %s', self.id, event, repr(target))
