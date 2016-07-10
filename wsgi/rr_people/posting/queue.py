from wsgi.properties import posts_redis_address, posts_redis_port, posts_redis_password
from wsgi.rr_people.queue import RedisHandler

QUEUE_PG = lambda x: "pg_queue_%s" % x
POST_ID = lambda x: "post_id_%s" % x


class PostRedisQueue(RedisHandler):
    def __init__(self, name="?", clear=False, host=None, port=None, pwd=None, db=None):
        super(PostRedisQueue, self).__init__("post queue %s" % name, clear,
                                             posts_redis_address,
                                             posts_redis_port,
                                             posts_redis_password,
                                             0)
        if clear:
            self.redis.flushall()

    def put_post(self, human_name, url_hash):
        self.redis.rpush(QUEUE_PG(human_name), url_hash)

    def pop_post(self, human_name):
        result = self.redis.lpop(QUEUE_PG(human_name))
        return result

    def show_all_posts_hashes(self, human_name):
        result = self.redis.lrange(QUEUE_PG(human_name), 0, -1)
        return result
