"""
The CLI module is a small utility that can be used as an easy entry point for
creating and running bots/clients.
"""
from __future__ import print_function

import logging
import os
import argparse
import warnings
from asyncio import get_event_loop

from . import ClientConfig, Gateway

parser = argparse.ArgumentParser()
parser.add_argument('--config', help='Configuration file', default=None)
parser.add_argument('--cluster', help='The id of the cluster (starting from 0).', default=None)


def singateway_main():
    # Parse out all our command line arguments
    args = parser.parse_args()

    # Create the base configuration object
    if args.config:
        config = ClientConfig.from_file(args.config)
    else:

        if os.path.exists('config.json'):
            config = ClientConfig.from_file('config.json')
        elif os.path.exists('config.yaml'):
            config = ClientConfig.from_file('config.yaml')
        elif os.path.exists('config.yml'):
            config = ClientConfig.from_file('config.yml')
        else:
            config = ClientConfig()

    warnings.simplefilter('always', DeprecationWarning)
    logging.captureWarnings(True)

    logging.basicConfig(level=getattr(logging, config.logging_level.upper()))

    loop = get_event_loop()

    client = Gateway(config, loop, cluster_id=args.cluster and int(args.cluster))
    loop.create_task(client.connect())
    client.singyeong.run()


if __name__ == '__main__':
    singateway_main()
