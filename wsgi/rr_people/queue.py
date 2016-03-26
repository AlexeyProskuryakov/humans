import logging
import redis

from wsgi.properties import c_queue_redis_addres, c_queue_redis_password, c_queue_redis_port
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


class ProductionQueue():
    def __init__(self, clear=False):
        self.redis = redis.StrictRedis(host=c_queue_redis_addres,
                                       port=c_queue_redis_port,
                                       password=c_queue_redis_password,
                                       db=0
                                       )

        log.info("Production Queue inited!")

    def put_comment(self, sbrdt, post_fn, text):
        key = serialize(post_fn, text)
        log.debug("redis: push to %s \nthis:%s" % (sbrdt, key))
        self.redis.rpush(QUEUE_CF(sbrdt), key)

    def get_comment(self, sbrdt):
        result = self.redis.lpop(QUEUE_CF(sbrdt))
        log.debug("redis: get by %s\nthis: %s" % (sbrdt, result))
        return deserialize(result)

    def show_all_comments(self, sbrdt):
        result = self.redis.lrange(QUEUE_CF(sbrdt), 0, -1)
        return dict(map(lambda x: deserialize(x), result))

    def del_post(self, sbrdt, post_hash):
        post_raw = self.redis.get(POST_ID(post_hash))
        if post_raw:
            p = self.redis.pipeline()
            p.delete(POST_ID(post_hash))
            p.lrem(QUEUE_PG(sbrdt), 0, post_raw)
            p.execute()

    def put_post(self, sbrdt, post):
        if not post.hash:
            p_hash = hash(post.title)
            post.hash = p_hash
        else:
            p_hash = post.hash

        post_raw = post.serialize()

        p = self.redis.pipeline()

        p.rpush(QUEUE_PG(sbrdt), post_raw)
        p.set(POST_ID(p_hash), post_raw)
        p.execute()
        return p_hash

    def pop_post(self, sbrdt):
        result = self.redis.lpop(QUEUE_PG(sbrdt))
        if result:
            post = PostSource.deserialize(result)
            if post.hash:
                self.redis.delete(POST_ID(post.hash))
            return post

    def show_all_posts(self, sbrdt):
        result = self.redis.lrange(QUEUE_PG(sbrdt), 0, -1)
        return map(lambda x: PostSource.deserialize(x), result)

    def set_comment_founder_state(self, sbrdt, state, ex=None):
        pipe = self.redis.pipeline()
        pipe.hset(HASH_STATES_CF, sbrdt, state)
        pipe.set(STATE_CF(sbrdt), state, ex=ex or 3600)
        pipe.execute()

    def get_comment_founder_state(self, sbrdt):
        return self.redis.get(sbrdt)

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
        return self.redis.get(sbrdt)

    def get_posts_generator_states(self):
        result = self.redis.hgetall(HASH_STATES_PG)
        for k, v in result.iteritems():
            ks = self.get_posts_generator_state(k)
            if v is None or ks is None:
                result[k] = S_STOP
        return result

if __name__ == '__main__':
    q = ProductionQueue()
    for post in q.show_all_posts("funny"):
        print q.redis.get(POST_ID(post.hash))
