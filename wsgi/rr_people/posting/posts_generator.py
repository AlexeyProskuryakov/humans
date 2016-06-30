import logging
import random
import time
from multiprocessing import Process

from wsgi.db import DBHandler
from wsgi.rr_people import S_WORK, S_SUSPEND
from wsgi.rr_people.posting import POST_GENERATOR_OBJECTS
from wsgi.rr_people.posting.posts import PostsStorage
from wsgi.rr_people.states.entity_states import StatesHandler

log = logging.getLogger("post_generator")


class PostsGeneratorsStorage(DBHandler):
    def __init__(self, name="?"):
        super(PostsGeneratorsStorage, self).__init__(name=name)
        collection_names = self.db.collection_names(include_system_collections=False)
        if "generators" not in collection_names:
            self.generators = self.db.create_collection('generators')
            self.generators.create_index([("sub", 1)], unque=True)
        else:
            self.generators = self.db.get_collection("generators")

    def set_sub_gen_info(self, sub, generators, key_words):
        self.generators.update_one({"sub": sub}, {"$set": {"gens": generators, "key_words": key_words}}, upsert=True)

    def get_sub_gen_info(self, sub):
        found = self.generators.find_one({"sub": sub})
        if found:
            return dict(found)
        return {"gens": [], "key_words": []}


class PostsGenerator(object):
    def __init__(self):
        self.states_handler = StatesHandler(name="post generator")
        self.generators_storage = PostsGeneratorsStorage(name="pg gens")
        self.posts_storage = PostsStorage(name="pg posts")
        self.sub_gens = {}
        self.sub_process = {}

        for sub, state in self.states_handler.get_posts_generator_states().iteritems():
            if S_WORK in state:
                self.start_generate_posts(sub)

    def generate_posts(self, subreddit):
        if subreddit not in self.sub_gens:
            gen_config = self.generators_storage.get_sub_gen_info(subreddit)

            gens = map(lambda x: x().generate_data(subreddit, gen_config.get("key_words")),
                       filter(lambda x: x,
                              map(lambda x: POST_GENERATOR_OBJECTS.get(x),
                                  gen_config.get('gens'))))
            self.sub_gens[subreddit] = gens
            log.info("for [%s] have this generators: %s" % (subreddit, gen_config.get("gens")))
        else:
            gens = self.sub_gens[subreddit]
        stopped = set()
        while 1:
            for gen in gens:
                try:
                    post = gen.next()
                    log.info("[%s] generate this post: %s" % (subreddit, post))
                    yield post
                except StopIteration:
                    stopped.add(hash(gen))

            if len(stopped) == len(gens):
                break

            random.shuffle(gens)

    def terminate_generate_posts(self, sub_name):
        if sub_name in self.sub_process:
            log.info("will terminate generating posts for [%s]" % sub_name)
            self.sub_process[sub_name].terminate()

    def start_generate_posts(self, subrreddit):
        if subrreddit in self.sub_process and self.sub_process[subrreddit].is_alive():
            return

        def set_state(state, ex=None):
            if self.states_handler.get_posts_generator_state(subrreddit) == S_SUSPEND:
                return False
            else:
                self.states_handler.set_posts_generator_state(subrreddit, state, ex=ex)
                return True

        def f():
            try:
                if set_state(S_WORK):
                    start = time.time()
                    log.info("Will start generate posts in [%s]" % (subrreddit))
                    counter = 0
                    for _ in self.generate_posts(subrreddit):
                        counter += 1
                        if not set_state("%s %s generated" % (S_WORK, counter)):
                            break

                    end = time.time()
                    log.info("Was generate [%s] posts in [%s] at %s seconds..." % (counter, subrreddit, end - start))
                else:
                    log.info("Generators for [%s] is suspend")

            except Exception as e:
                log.error("Was error at generating for sub: %s" % subrreddit)
                log.exception(e)
            finally:
                set_state(S_SUSPEND)

        ps = Process(name="[%s] posts generator" % subrreddit, target=f)
        ps.start()
        self.sub_process[subrreddit] = ps


if __name__ == '__main__':
    pg = PostsGenerator()
    pg.start_generate_posts("videos")
