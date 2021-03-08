# sinGateway
> _**This script is work in progress and may be unstable and broken**_ \
> We don't recommend using it at this state of development.

Discord Gateway that sends events straight to [신경](https://github.com/queer/singyeong)

## Requirements

- Python 3.6 and up
- Access to [신경](https://github.com/queer/singyeong) server
- Access to [Redis](https://redis.io/download) server

## Configuration

Create `config.yaml`/`config.json` in your working directory or specify the path to this file in `--config` argument:

```shell
python3 -m singateway --config /etc/singyeong.yml
```

### Sharding
Our library automatically shards the connection when it's needed. The number of shards is downloaded from [/gateway/bot](https://discord.com/developers/docs/topics/gateway#get-gateway-bot) endpoint.

### Clustering
Do you want more freedom over shard management?
This feature gives you ability to split gateway into multiple processes and/or servers.

Just go to config section and set:
```yaml
clustering:
  enabled: true

  # The number of processes:
  clusterCount: 2
  
  # The number of shards running in single process:
  clusterShards: 4
```

You can now run your bot with commands:

```shell
python3 -m singateway --cluster 0
python3 -m singateway --cluster 1
```

### Example config

```yaml
token: "YOUR_BOT_TOKEN"
redisDSN: "redis://localhost"
singyeongDSN: "singyeong://gateway@localhost:4567"

loggingLevel: "INFO"

intents: 513 

clustering:
  enabled: true
  clusterCount: 2  # How many clusters?
  clusterShards: 4  # How many shards per cluster?

forwarding:
  - type: "send"
    target:
      application: "worker"
      ops:
        - path: "/events",
          op: "$in",
          to:
            value: "{{EVENT}}"
    events:
      - "READY"
      
      # GUILDS intent  (1 << 0)
      - "GUILD_CREATE"
      - "GUILD_UPDATE"
      - "GUILD_DELETE"
      - "GUILD_ROLE_CREATE"
      - "GUILD_ROLE_UPDATE"
      - "GUILD_ROLE_DELETE"
      - "CHANNEL_CREATE"
      - "CHANNEL_UPDATE"
      - "CHANNEL_DELETE"
      - "CHANNEL_PINS_UPDATE"
      
      # GUILD_MESSAGES intent  (1 << 9)
      - "MESSAGE_CREATE"
      - "MESSAGE_UPDATE"
      - "MESSAGE_DELETE"
      - "MESSAGE_DELETE_BULK"
```
#### token
`token` - Discord bot token


#### redisDSN
`redisDSN` - Redis URI. [More info...](https://www.iana.org/assignments/uri-schemes/prov/redis)

> Example: `redis://:password@localhost:6379/0`

#### singyeongDSN
`singyeongDSN` - Singyeong DSN. [More info...](https://github.com/queer/singyeong/blob/master/PROTOCOL.md#basic-%EC%8B%A0%EA%B2%BD-lifecycle)

> Example: `singyeong://gateway:pass@localhost:21312?encoding=json`

#### loggingLevel

`loggingLevel` (default: INFO) - Logs a message with specified level on the root logger. 
  - `CRITICAL` - Sends to console only critical messages.
  - `ERROR` - Sends to console errors.
  - `WARNING` - Sends to console only errors & warnings.
  - `INFO` - Logger enabled (default)
  - `DEBUG` - Sends to console (too much) messages. Use in development to trace bugs.

#### intents

`intents` (default: `513`) - parameter which allows you to conditionally subscribe to pre-defined "intents", groups of events defined by Discord. You can calc this value like that: `1 << 0 | 1 << 1 | 1 << 9 == 515` [More info...](http://discord.dev/topics/gateway#gateway-intents)


#### clustering

`clustering.enabled` (default: false) - Is clustering enabled?

`clustering.clusterCount` (default: false) - How many clusters ?

`clustering.clusterShards` (default: false) - Is clustering enabled?


#### forwarding
`forwarding.type` - may be "send" or "broadcast" (check out 신경 docks)

`forwarding.target` - object compatible with [신경 query language](https://github.com/queer/singyeong/blob/master/PROTOCOL.md#query-formatting). 
You can use variables:
  - `{{SHARD}}` - number of this shard
  - `{{CLUSTER}}` - number of this cluster
  - `{{EVENT}}` - name of gateway event  e.g. MESSAGE_CREATE

`forwarding.events` - List of [Gateway events](https://discord.com/developers/docs/topics/gateway#commands-and-events-gateway-events) to forward. Each event must be UPPERCASE with gaps underscored.
