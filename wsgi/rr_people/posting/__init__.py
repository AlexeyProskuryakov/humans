import logging
import random
from threading import Thread

from multiprocessing import Process

import time

import pymongo

from wsgi.db import DBHandler
from wsgi.rr_people import S_WORK, S_SLEEP
from wsgi.rr_people.queue import ProductionQueue
from wsgi.properties import default_post_generators, DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA

log = logging.getLogger("post_generator")

IMGUR = "imgur"
YOUTUBE = "youtube"

pp_objects = {}

class Generator(object):
    def __init__(self, name):
        self.__name = name

    @property
    def name(self):
        return self.__name

    def generate_data(self, subreddit):
        raise NotImplementedError

class PostsGeneratorsStorage(DBHandler):
    def __init__(self):
        super(PostsGeneratorsStorage, self).__init__()
        self.generators = self.db.get_collection("generators")
        if not self.generators:
            self.generators = self.db.create_collection('generators')
            self.generators.create_index([("sub", pymongo.ASCENDING)], unque=True)

    def set_subreddit_generator(self, sub, generator_name):
        self.generators.update_one({"sub":sub}, {"$addToSet":{"gens":generator_name}}, upsert=True)

    def get_subreddit_genearators(self, sub):
        found = self.generators.find_one({"sub":sub})
        if found:
            return found.get("gens")
        return default_post_generators

class PostsGenerator(object):
    def __init__(self, posts_providers=None):
        self.queue = ProductionQueue()
        self.storage = PostsGeneratorsStorage()
        self.subs = {}

    def generate_posts(self, subreddit):
        gens = self.storage.get_subreddit_genearators(subreddit)
        gens = map(lambda x:x(), filter(lambda x:x, map(lambda x: pp_objects.get(x), gens)))
        while 1:
            gen = random.choice(gens)
            for url, title in gen.get_data(subreddit):
                yield url, title

    def start_generate_posts(self, subrreddit):
        def f():
            self.queue.set_comment_founder_state(subrreddit, S_WORK)
            start = time.time()
            log.info("Will start find comments for [%s]" % (subrreddit))
            for url, title in self.generate_posts(subrreddit):
                self.queue.put_post(subrreddit, url, title)
            end = time.time()
            sleep_time = random.randint(DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA / 5,
                                        DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA)
            log.info(
                    "Was generate posts which found for [%s] at %s seconds... Will trying next after %s" % (
                        subrreddit, end - start, sleep_time))
            self.queue.set_comment_founder_state(subrreddit, S_SLEEP, ex=sleep_time + 1)
            time.sleep(sleep_time)

        ps = Process(name="[%s] posts generator" % subrreddit, target=f)
        ps.start()
        self.subs[subrreddit] = ps