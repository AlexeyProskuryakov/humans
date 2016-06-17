import logging

import redis

from wsgi.properties import comment_redis_address, comment_redis_password, comment_redis_port, posts_redis_address, \
    posts_redis_port, posts_redis_password

log = logging.getLogger("queue")

class RedisHandler(object):
    def __init__(self, name="?", clear=False, host=None, port=None, pwd=None, db=None):
        self.redis = redis.StrictRedis(host=host or comment_redis_address,
                                       port=port or comment_redis_port,
                                       password=pwd or comment_redis_password,
                                       db=db or 0
                                       )
        if clear:
            self.redis.flushdb()

        log.info("Production Queue inited for [%s]" % name)

