import json
import logging

import redis

from wsgi.properties import comment_redis_address, comment_redis_password, comment_redis_port, posts_redis_address, \
    posts_redis_port, posts_redis_password
from wsgi.rr_people import deserialize, serialize

log = logging.getLogger("pq")

QUEUE_PG = lambda x: "pg_queue_%s" % x
QUEUE_CF = lambda x: "cf_queue_%s" % x

POST_ID = lambda x: "post_id_%s" % x

NEED_COMMENT = "need_comment"


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


class CommentRedisHandler(RedisHandler):
    def __init__(self, name="?", clear=False, host=None, port=None, pwd=None, db=None):
        super(CommentRedisHandler, self).__init__("comment queue %s" % name, clear,
                                                  comment_redis_address,
                                                  comment_redis_port,
                                                  comment_redis_password,
                                                  0)

    def need_comment(self, sbrdt):
        self.redis.publish(NEED_COMMENT, sbrdt)

    def get_who_needs_comments(self):
        pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(NEED_COMMENT)
        for el in pubsub.listen():
            yield el

    def put_comment_hash(self, sbrdt, post_fn, comment_id):
        key = serialize(post_fn, comment_id)
        log.debug("redis: push to %s \nthis:%s" % (sbrdt, key))
        self.redis.rpush(QUEUE_CF(sbrdt), key)

    def pop_comment_hash(self, sbrdt):
        result = self.redis.lpop(QUEUE_CF(sbrdt))
        log.debug("redis: get by %s\nthis: %s" % (sbrdt, result))
        return deserialize(result)

    def get_all_comments(self, sbrdt):
        result = self.redis.lrange(QUEUE_CF(sbrdt), 0, -1)
        return dict(map(lambda x: deserialize(x), result))


class PostRedisHandler(RedisHandler):
    def __init__(self, name="?", clear=False, host=None, port=None, pwd=None, db=None):
        super(PostRedisHandler, self).__init__("post queue %s" % name, clear,
                                               posts_redis_address,
                                               posts_redis_port,
                                               posts_redis_password,
                                               0)

    def put_post(self, human_name, url_hash):
        self.redis.rpush(QUEUE_PG(human_name), url_hash)

    def pop_post(self, human_name):
        result = self.redis.lpop(QUEUE_PG(human_name))
        return result

    def show_all_posts_hashes(self, human_name):
        result = self.redis.lrange(QUEUE_PG(human_name), 0, -1)
        return result
