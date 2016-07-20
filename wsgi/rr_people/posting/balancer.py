import json
import logging
import random
import time

from collections import defaultdict
from multiprocessing import Process

from wsgi.db import DBHandler, HumanStorage
from wsgi.rr_people import Singleton
from wsgi.rr_people.posting.posts import PS_AT_QUEUE, PostsStorage, PS_AT_BALANCER
from wsgi.rr_people.posting.queue import PostRedisQueue
from wsgi.rr_people.states.persisted_queue import RedisQueue
from wsgi.rr_people.states.processes import ProcessDirector

MAX_BATCH_SIZE = 10
BATCH_TTL = 60
log = logging.getLogger("balancer")


class BatchStorage(DBHandler):
    def __init__(self, name="?", ):
        super(BatchStorage, self).__init__("batch storage %s" % name)
        self.batches = self.db.get_collection("humans_posts_batches")
        if not self.batches:
            self.batches = self.db.create_collection("humans_posts_batches")
            self.batches.create_index("human_name")
            self.batches.create_index("count")

        self.cache = defaultdict(list)  # it is not cache as you think. it is used in batches and consistent.

    def get_human_post_batches(self, human_name):
        if human_name not in self.cache:
            self.cache[human_name] = list(self.batches.find({"human_name": human_name}).sort("count", -1))

        for id, bulk in enumerate(self.cache[human_name]):
            yield PostBatch(self, bulk, id)


class PostBatch():
    def __init__(self, store, data, cache_id):
        if isinstance(store, BatchStorage):
            self.store = store
        else:
            raise Exception("store is not bulk store")

        self.channels = set(data.get("channels"))
        self.human_name = data.get("human_name")
        self.batch_id = data.get("_id")
        self.data = data.get("url_hashes")
        self.cache_id = cache_id

    @property
    def hashes(self):
        return self.data

    @property
    def to_data(self):
        return {"channels": list(self.channels),
                "human_name": self.human_name,
                "_id": self.batch_id,
                "url_hashes": self.data}

    @property
    def size(self):
        return len(self.data)



BALANCER_PROCESS_ASPECT = "post_balancer"



class BalancerTask(object):
    def __init__(self, url_hash, channel_id, important=False, human_name=None, sub=None):
        self.url_hash = url_hash
        self.channel_id = channel_id
        self.important = important
        self.human_name = human_name
        self.sub = sub

    def __repr__(self):
        return "%s" % self.__dict__


def deserialise(data):
    kwargs = json.loads(data)
    return BalancerTask(**kwargs)


def serialise(object):
    return json.dumps(object.__dict__)


balancer_queue = RedisQueue(name="balancer",
                            serialize=serialise,
                            deserialize=deserialise,
                            topic="balancer_queue")



class PostBalancer(object):
    '''
    This class only add posts and after you can see them in post queue @PostRedisQueue class.

    '''

    def __init__(self):
        self.queue = balancer_queue

    def add_post(self, url_hash, channel_id, important=False, human_name=None, sub=None):
        task = BalancerTask(url_hash, channel_id, important, human_name, sub)
        self.queue.put(task)
