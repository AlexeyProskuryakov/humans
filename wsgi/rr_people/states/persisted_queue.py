import logging

from wsgi.rr_people.queue import RedisHandler
from wsgi.properties import states_redis_address, states_redis_port, states_redis_password

log = logging.getLogger("redis_queue")


class RedisQueue(RedisHandler):
    '''
    topic - is topic in redis pub sub
    implement serialise and deserialise
    '''

    def __init__(self, name="?",
                 topic="queue", serialize=lambda x: x.__dict__, deserialize=lambda x: x,
                 host=None, port=None, pwd=None, db=None):
        super(RedisQueue, self).__init__(name, False,
                                         host or states_redis_address,
                                         port or states_redis_port,
                                         pwd or states_redis_password,
                                         db or 0)
        self.topic = topic
        self.serialise = serialize
        self.deserialise = deserialize
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.pubsub.subscribe(self.topic)
        log.info("Initialize redis queue for %s" % name)

    def put(self, object):
        self.redis.publish(self.topic, self.serialise(object))

    def get(self):
        el = self.pubsub.listen().next()
        try:
            result = self.deserialise(el['data'])
            return result
        except Exception as e:
            log.error("can not init result of %s" % el)
            log.exception(e)


if __name__ == '__main__':
    q = RedisQueue(serialize=lambda x: x)
    q.put("my name is alesha")
    print q.get()
