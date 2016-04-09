import logging
import redis

from wsgi.properties import queue_redis_address, queue_redis_password, queue_redis_port
from wsgi.rr_people import deserialize, S_STOP, serialize
from wsgi.rr_people.posting.posts import PostSource

log = logging.getLogger("pq")

QUEUE_PG = lambda x: "pg_queue_%s" % x
QUEUE_CF = lambda x: "cf_queue_%s" % x

POST_ID = lambda x: "post_id_%s" % x

HASH_STATES_CF = "cf_states_hashset"
HASH_STATES_PG = "pg_states_hashset"

STATE_CF = lambda x: "cf_state_%s" % x
STATE_PG = lambda x: "pg_state_%s" % x

NEED_COMMENT = "need_comment"


class ProductionQueue():
    def __init__(self, name="?", clear=False):
        self.redis = redis.StrictRedis(host=queue_redis_address,
                                       port=queue_redis_port,
                                       password=queue_redis_password,
                                       db=0
                                       )
        if clear:
            self.redis.flushdb()

        log.info("Production Queue inited for [%s]"%name)

    def need_comment(self, sbrdt):
        self.redis.publish(NEED_COMMENT, sbrdt)

    def get_who_needs_comments(self):
        pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(NEED_COMMENT)
        for el in pubsub.listen():
            yield el

    def put_comment(self, sbrdt, post_fn, text):
        key = serialize(post_fn, text)
        log.debug("redis: push to %s \nthis:%s" % (sbrdt, key))
        self.redis.rpush(QUEUE_CF(sbrdt), key)

    def pop_comment(self, sbrdt):
        result = self.redis.lpop(QUEUE_CF(sbrdt))
        log.debug("redis: get by %s\nthis: %s" % (sbrdt, result))
        return deserialize(result)

    def show_all_comments(self, sbrdt):
        result = self.redis.lrange(QUEUE_CF(sbrdt), 0, -1)
        return dict(map(lambda x: deserialize(x), result))

    def put_post_hash(self, sbrdt, post_hash):
        self.redis.rpush(QUEUE_PG(sbrdt), post_hash)

    def pop_post_hash(self, sbrdt):
        result = self.redis.lpop(QUEUE_PG(sbrdt))
        return result

    def show_all_posts_hashes(self, sbrdt):
        result = self.redis.lrange(QUEUE_PG(sbrdt), 0, -1)
        return result

    def set_comment_founder_state(self, sbrdt, state, ex=None):
        pipe = self.redis.pipeline()
        pipe.hset(HASH_STATES_CF, sbrdt, state)
        pipe.set(STATE_CF(sbrdt), state, ex=ex or 3600)
        pipe.execute()

    def get_comment_founder_state(self, sbrdt):
        return self.redis.get(STATE_CF(sbrdt))

    def get_comment_founders_states(self):
        result = self.redis.hgetall(HASH_STATES_CF)
        for k, v in result.iteritems():
            ks = self.get_comment_founder_state(k)
            if v is None or ks is None:
                result[k] = S_STOP
        return result

    def set_posts_generator_state(self, sbrdt, state, ex=None):
        pipe = self.redis.pipeline()
        pipe.hset(HASH_STATES_PG, sbrdt, state)
        pipe.set(STATE_PG(sbrdt), state, ex=ex or 3600)
        pipe.execute()

    def get_posts_generator_state(self, sbrdt):
        return self.redis.get(STATE_PG(sbrdt))

    def remove_post_generator(self, sbrdt):
        pipe = self.redis.pipeline()
        pipe.hdel(HASH_STATES_PG, sbrdt)
        pipe.delete(STATE_PG(sbrdt))
        pipe.execute()

    def get_posts_generator_states(self):
        result = self.redis.hgetall(HASH_STATES_PG)
        for k, v in result.iteritems():
            ks = self.get_posts_generator_state(k)
            if v is None or ks is None:
                result[k] = S_STOP
        return result


if __name__ == '__main__':
    q = ProductionQueue()
    for post in q.show_all_posts_hashes("funny"):
        print q.redis.get(POST_ID(post.hash))
