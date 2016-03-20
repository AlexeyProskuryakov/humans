import logging
import random
import time
from multiprocessing import Process

from wsgi.db import DBHandler
from wsgi.properties import DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA
from wsgi.rr_people import S_WORK, S_SLEEP
from wsgi.rr_people.posting import POST_GENERATOR_OBJECTS
from wsgi.rr_people.queue import ProductionQueue

log = logging.getLogger("post_generator")

class PostsGeneratorsStorage(DBHandler):
    def __init__(self, name="?"):
        super(PostsGeneratorsStorage, self).__init__(name=name)
        self.generators = self.db.get_collection("generators")
        if not self.generators:
            self.generators = self.db.create_collection('generators')
            self.generators.create_index([("sub", 1)], unque=True)

    def set_subreddit_generator(self, sub, generators, key_words):
        self.generators.update_one({"sub": sub}, {"$set": {"gens": generators, "key_words": key_words}}, upsert=True)

    def get_subreddit_generators(self, sub):
        found = self.generators.find_one({"sub": sub})
        if found:
            return dict(found)
        return {"gens": [], "key_words": []}


class PostsGenerator(object):
    def __init__(self):
        self.queue = ProductionQueue()
        self.storage = PostsGeneratorsStorage(name="posts generator")
        self.sub_gens = {}
        self.sub_process = {}

    def generate_posts(self, subreddit):
        if subreddit not in self.sub_gens:
            gen_config = self.storage.get_subreddit_generators(subreddit)

            gens = map(lambda x: x().generate_data(subreddit, gen_config.get("key_words")),
                       filter(lambda x: x,
                              map(lambda x: POST_GENERATOR_OBJECTS.get(x),
                                  gen_config.get('gens'))))
            self.sub_gens[subreddit] = gens
            log.info("for [%s] have this generators: %s"%(subreddit, gen_config.get("gens")))
        else:
            gens = self.sub_gens[subreddit]
        stopped = set()
        while 1:
            for gen in gens:
                try:
                    post = gen.next()
                    log.info("[%s] generate this post: %s"%(subreddit, post))
                    yield post
                except StopIteration:
                    stopped.add(hash(gen))

            if len(stopped) == len(gens):
                break

            random.shuffle(gens)

    def start_generate_posts(self, subrreddit):
        if subrreddit in self.sub_process and self.sub_process[subrreddit].is_alive():
            return

        def f():
            while 1:
                self.queue.set_posts_generator_state(subrreddit, S_WORK)
                start = time.time()
                log.info("Will start find posts for [%s] or another" % (subrreddit))
                counter = 0
                for post in self.generate_posts(subrreddit):
                    counter+=1
                    self.queue.put_post(subrreddit, post)
                end = time.time()
                sleep_time = random.randint(DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA / 5,
                                            DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA)
                log.info(
                        "Was generate [%s] posts which found for [%s] at %s seconds... \nWill trying next after %s" % (
                            counter, subrreddit, end - start, sleep_time))
                self.queue.set_posts_generator_state(subrreddit, S_SLEEP, ex=sleep_time + 1)
                time.sleep(sleep_time)

        ps = Process(name="[%s] posts generator" % subrreddit, target=f)
        ps.start()
        self.sub_process[subrreddit] = ps

if __name__ == '__main__':
    pg = PostsGenerator()
    pg.start_generate_posts("videos")