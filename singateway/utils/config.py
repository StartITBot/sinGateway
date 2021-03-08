import os

from . import Serializer


class ClientConfig(dict):
    @classmethod
    def from_file(cls, path):
        inst = cls()

        with open(path, 'r') as f:
            data = f.read()

        _, ext = os.path.splitext(path)
        Serializer.check_format(ext[1:])
        inst.update(Serializer.loads(ext[1:], data))
        return inst

    @property
    def singyeong_dsn(self):
        if 'singyeongDSN' not in self:
            raise ValueError('Specify "singyeongDSN" variable in config.yml')
        return self.get('singyeongDSN')

    @property
    def redis_dsn(self):
        if 'redisDSN' not in self:
            raise ValueError('Specify "redisDSN" variable in config.yml')
        return self.get('redisDSN')

    @property
    def token(self):
        if 'token' not in self:
            raise ValueError('Specify "token" variable in config.yml')
        return self.get('token')

    @property
    def logging_level(self):
        return self.get('loggingLevel') or 'INFO'

    @property
    def forwarding(self):
        if 'forwarding' not in self:
            raise ValueError('Specify "forwarding" variable in config.yml')

        forward = self.get('forwarding')
        return forward if isinstance(forward, list) else [forward]

    @property
    def intents(self):
        return int(self.get('intents') or 513)

    @property
    def cluster_enabled(self):
        return bool(self.get('clustering', {}).get("enabled"))

    @property
    def cluster_count(self):
        return int(self.get('clustering', {}).get("clusterCount"))

    @property
    def cluster_shards(self):
        return int(self.get('clustering', {}).get("clusterShards"))
