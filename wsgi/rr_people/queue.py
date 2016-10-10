import logging

import redis

from wsgi import ConfigManager

log = logging.getLogger("queue")


class RedisHandler(object):
    def __init__(self, name="?", clear=False, host=None, port=None, pwd=None, db=None):
        cm = ConfigManager()
        self.redis = redis.StrictRedis(host=host or cm.get('comment_redis_address'),
                                       port=port or cm.get('comment_redis_port'),
                                       password=pwd or cm.get('comment_redis_password'),
                                       db=db or 0
                                       )
        if clear:
            self.redis.flushdb()

        log.info("Production Queue inited for [%s]" % name)
