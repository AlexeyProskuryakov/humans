import logging
import random
from threading import Thread

from multiprocessing import Process

import time

from wsgi.rr_people import S_WORK
from wsgi.rr_people.posting.imgur import ImgurPostsProvider
from wsgi.rr_people.queue import ProductionQueue
from wsgi.properties import default_post_providers

log = logging.getLogger("post_generator")

pp_objects = {'imgur':ImgurPostsProvider}

class PostsGenerator(object):
    def __init__(self, posts_providers=None):



        self.queue = ProductionQueue()
        self.subs = {}

    def generate_posts(self, subreddit):
        provider = random.choice(self.providers)
        for url, title in provider.get_data(subreddit):
            yield url, title

    def start_generate_posts(self, subrreddit):
        def f():
            self.queue.set_comment_founder_state(subrreddit, S_WORK)
            start = time.time()
            log.info("Will start find comments for [%s]" % (subrreddit))
            for url, title in self.generate_posts(subrreddit):
                self.queue.put_post(subrreddit, url, title)

        ps = Process(name="[%s] comment founder" % subrreddit, target=f)
        ps.start()
        self.subs[subrreddit] = ps