import logging
import random
from collections import defaultdict
from multiprocessing import Process, Queue

import time

from wsgi.db import DBHandler, HumanStorage
from wsgi.rr_people import Singleton
from wsgi.rr_people.posting.posts import PS_AT_QUEUE, PostsStorage
from wsgi.rr_people.queue import PostRedisQueue
from wsgi.rr_people.states.persisted_queue import RedisQueue
from wsgi.rr_people.states.processes import ProcessDirector

MAX_BATCH_SIZE = 10

log = logging.getLogger("balancer")


class BatchStorage(DBHandler):
    def __init__(self, name="?", ):
        super(BatchStorage, self).__init__("batch storage %s" % name)
        self.batches = self.db.get_collection("humans_posts_batches")
        if not self.batches:
            self.batches = self.db.create_collection("humans_posts_batches")
            self.batches.create_index("human_name")
            self.batches.create_index("count")

        self.cache = defaultdict(list)

    def get_human_post_batches(self, human_name):
        if human_name not in self.cache:
            self.cache[human_name] = list(self.batches.find({"human_name": human_name}).sort("count", -1))
        for id, bulk in enumerate(self.cache[human_name]):
            yield PostBatch(self, bulk, id)

    def init_new_batch(self, human_name, url_hash, channel_id):
        data = {"human_name": human_name,
                "channels": [channel_id],
                "url_hashes": [url_hash]}
        result = self.batches.insert_one(data)
        data["_id"] = result.inserted_id
        self.cache[human_name].insert(0, data)


class PostBatch():
    def __init__(self, store, data, cache_id):
        if isinstance(store, BatchStorage):
            self.store = store
        else:
            raise Exception("store is not bulk store")

        self.channels = set(data.get("channels"))
        self.human_name = data.get("human_name")
        self.bulk_id = data.get("_id")
        self.data = data.get("url_hashes")
        self.cache_id = cache_id

    @property
    def to_data(self):
        return {"channels": list(self.channels),
                "human_name": self.human_name,
                "_id": self.bulk_id,
                "url_hashes": self.data}

    @property
    def size(self):
        return len(self.data)

    def have_not(self, url_hash, channel_id):
        if url_hash not in self.data:
            if not channel_id: return True
            return channel_id not in self.channels
        return False

    def add(self, url_hash, channel_id, to_start=False):
        self.channels.add(channel_id)
        modify = {"$addToSet": {"channels": channel_id}}
        if not to_start:
            modify["$push"] = {"url_hashes": url_hash}
            self.data.append(url_hash)
        else:
            modify["$push"] = {"url_hashes": {"$each": [url_hash], "$position": 0}}
            self.data.insert(0, url_hash)

        self.store.batches.update_one({"_id": self.bulk_id}, modify)
        self.store.cache[self.human_name][self.cache_id] = self.to_data

    def delete(self):
        self.store.batches.delete_one({"_id": self.bulk_id})
        cache = self.store.cache[self.human_name]
        self.store.cache[self.human_name] = cache[:self.cache_id] + cache[self.cache_id + 1:]


class PostBalancerEngine(Process):
    __metaclass__ = Singleton

    def __init__(self, post_queue, post_storage, out_queue):
        super(PostBalancerEngine, self).__init__()
        self.batch_storage = BatchStorage("balancer bs")
        self.human_storage = HumanStorage("balancer hs")

        self.post_queue = post_queue
        self.posts_storage = post_storage

        self.sub_humans = self._load_human_sub_mapping()

        self.out_queue = out_queue

        self.process_director = ProcessDirector("balancer")

        log.info("post balancer inited")

    def _load_human_sub_mapping(self):
        result = defaultdict(list)
        for human_info in self.human_storage.get_humans_info(projection={"user": True, "subs": True}):
            for sub in human_info.get("subs"):
                result[sub].append(human_info.get("user"))
        return result

    def _get_human_name(self, sub):
        if sub in self.sub_humans:
            return random.choice(self.sub_humans[sub])

    def _flush_batch_to_queue(self, batch):
        for url_hash in batch.data:
            self.post_queue.put_post(batch.human_name, url_hash)
        self.posts_storage.set_posts_states(batch.data, PS_AT_QUEUE)
        batch.delete()

    def add_post(self, url_hash, channel_id, important=False, human_name=None, sub=None):
        if not sub and not human_name:
            return
        human_name = human_name or self._get_human_name(sub)
        if human_name is None:
            return

        for batch in self.batch_storage.get_human_post_batches(human_name):
            if batch.have_not(url_hash, channel_id):
                batch.add(url_hash, channel_id, important)
                if batch.size >= MAX_BATCH_SIZE:
                    self._flush_batch_to_queue(batch)
                return

        self.batch_storage.init_new_batch(human_name, url_hash, channel_id)

    def run(self):
        if not self.process_director.can_start_aspect("post_balancer", self.pid):
            log.info("another balancer worked")
            return

        log.info("post balancer started")
        while 1:
            try:
                task = self.out_queue.get()
                if not isinstance(task, BalancerTask):
                    raise Exception("task is not task :( ")
                log.info("here i have task %s" % task)
            except Exception as e:
                log.exception(e)
                time.sleep(1)
                continue

            self.add_post(**task.__dict__)


class BalancerTask(object):
    def __init__(self, url_hash, channel_id, important=False, human_name=None, sub=None):
        self.url_hash = url_hash
        self.channel_id = channel_id
        self.important = important
        self.human_name = human_name
        self.sub = sub

    def __repr__(self):
        return "%s" % self.__dict__


post_queue = PostRedisQueue("balancer")
post_storage = PostsStorage("balancer ps")
balancer_queue = RedisQueue(name="balancer", deserialize=lambda x: BalancerTask(**x), topic="balancer_queue")

balancer = PostBalancerEngine(post_queue, post_storage, balancer_queue)
balancer.daemon = True
balancer.start()


class PostBalancer(object):
    def __init__(self):
        self.queue = balancer_queue

    def add_post(self, url_hash, channel_id, important=False, human_name=None, sub=None):
        task = BalancerTask(url_hash, channel_id, important, human_name, sub)
        self.queue.put(task)
