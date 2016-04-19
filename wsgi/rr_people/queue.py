import json
import logging

import redis

from wsgi.properties import queue_redis_address, queue_redis_password, queue_redis_port
from wsgi.rr_people import deserialize, S_STOP, serialize

log = logging.getLogger("pq")

QUEUE_PG = lambda x: "pg_queue_%s" % x
QUEUE_CF = lambda x: "cf_queue_%s" % x

POST_ID = lambda x: "post_id_%s" % x

NEED_COMMENT = "need_comment"

QUEUE_FORCE_ACTIONS = lambda x:"fa_queue_%s"%x


class ProductionQueue():
    def __init__(self, name="?", clear=False):
        self.redis = redis.StrictRedis(host=queue_redis_address,
                                       port=queue_redis_port,
                                       password=queue_redis_password,
                                       db=0
                                       )
        if clear:
            self.redis.flushdb()

        log.info("Production Queue inited for [%s]" % name)

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

    def put_post(self, sbrdt, post_hash):
        self.redis.rpush(QUEUE_PG(sbrdt), post_hash)

    def pop_post(self, sbrdt):
        result = self.redis.lpop(QUEUE_PG(sbrdt))
        return result

    def show_all_posts_hashes(self, sbrdt):
        result = self.redis.lrange(QUEUE_PG(sbrdt), 0, -1)
        return result

    def put_force_action(self, human_name, action_data):
        serialized_data = json.dumps(action_data)
        self.redis.rpush(QUEUE_FORCE_ACTIONS(human_name), serialized_data)

    def pop_force_action(self, human_name):
        serialised_data = self.redis.lpop(QUEUE_FORCE_ACTIONS(human_name))
        if serialised_data:
            return json.loads(serialised_data)
