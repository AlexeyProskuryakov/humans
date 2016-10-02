# coding:utf-8
import logging
import redis
import time
from threading import Thread

from wsgi.properties import process_director_redis_address, process_director_redis_port, \
    process_director_redis_password

log = logging.getLogger("process_director")

PREFIX_ALLOC = lambda x: "PD_%s" % x

TIME_TO_STATE_LIVE = 10


class ProcessTracked(object):
    def __init__(self, aspect):
        self.tsh = TimeStateHandler(aspect)
        self.tsh.start()


class TimeStateHandler(Thread):
    def __init__(self, aspect, pd=None):
        super(TimeStateHandler, self).__init__()
        self.pd = pd or ProcessDirector(name="TSH %s" % aspect)
        self.aspect = aspect

    def run(self):
        while 1:
            try:
                self.pd.set_timed_state(self.aspect)
            except Exception as e:
                log.exception(e)

            time.sleep(TIME_TO_STATE_LIVE)


class ProcessDirector(object):
    def __init__(self, name="?", clear=False, max_connections=2):
        self.redis = redis.StrictRedis(host=process_director_redis_address,
                                       port=process_director_redis_port,
                                       password=process_director_redis_password,
                                       db=0,
                                       max_connections=max_connections
                                       )
        if clear:
            self.redis.flushdb()

        log.info("Process director [%s] inited." % name)

    def start_aspect(self, aspect):
        alloc = self.redis.setnx(PREFIX_ALLOC(aspect), time.time())
        if not alloc:
            time.sleep(TIME_TO_STATE_LIVE * 2)
            alloc = self.redis.setnx(PREFIX_ALLOC(aspect), time.time())
        return alloc

    def set_timed_state(self, aspect):
        self.redis.set(PREFIX_ALLOC(aspect), time.time(), ex=TIME_TO_STATE_LIVE)

    def is_aspect_work(self, aspect):
        alloc = self.redis.get(PREFIX_ALLOC(aspect))
        return alloc if alloc is not None else False
