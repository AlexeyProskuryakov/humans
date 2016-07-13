# coding=utf-8
import logging
import random
import time
from multiprocessing import Process

from wsgi.db import HumanStorage
from wsgi.properties import force_post_manager_sleep_iteration_time
from wsgi.rr_people.posting.balancer import PostBalancer
from wsgi.rr_people.posting.posts import PostsStorage, PostSource
from wsgi.rr_people.posting.queue import PostRedisQueue
from wsgi.rr_people.posting.youtube_posts import YoutubeChannelsHandler
from wsgi.rr_people.states.processes import ProcessDirector

log = logging.getLogger("posts")


class PostHandler(object):
    def __init__(self, name="?", pq=None, ps=None):
        self.queue = pq or PostRedisQueue("ph %s" % name)
        self.posts_storage = ps or PostsStorage("ph %s" % name)
        self.youtube = YoutubeChannelsHandler(self.posts_storage)
        self.balancer = PostBalancer()

    def add_important_post(self, human_name, post_source, sub, channel_id=None, important=False):
        if isinstance(post_source, PostSource):
            self.posts_storage.add_generated_post(post_source, sub, important=important, channel_id=channel_id)
            self.balancer.add_post(post_source.url_hash, channel_id, important=important, human_name=human_name)
        else:
            raise Exception("post_source is not post source!")

    def move_noise_post_to_balancer(self, sub, post_source):
        if isinstance(post_source, PostSource):
            channel_id = self.youtube.get_channel_id(post_source.url)
            self.posts_storage.set_post_channel_id(post_source.url_hash, channel_id)
            self.balancer.add_post(post_source.url_hash, channel_id, sub=sub)
        else:
            raise Exception("post_source is not post source!")

    def get_prepared_post(self, human_name):
        url_hash = self.queue.pop_post(human_name)
        if not url_hash:
            log.warn("Not any posts for [%s] at queue" % human_name)
            return
        post_data = self.posts_storage.get_good_post(url_hash)
        if not post_data:
            log.warn("Not any good posts for [%s] at storage" % human_name)
            return
        post, sub = post_data
        if not post.for_sub: post.for_sub = sub
        return post

    def set_post_state(self, url_hash, new_state):
        self.posts_storage.set_post_state(url_hash, new_state)


IMPORTANT_POSTS_SUPPLIER_PROCESS_ASPECT = "im_po_su_aspect"


class ImportantYoutubePostSupplier(Process):
    """
    Process which get humans config and retrieve channel_id, after retrieve new posts from it and
    """

    def __init__(self, pq=None, ps=None, ms=None):
        super(ImportantYoutubePostSupplier, self).__init__()
        self.queue = pq or PostRedisQueue("im po su")
        self.posts_storage = ps or PostsStorage("im po su")
        self.main_storage = ms or HumanStorage("im po su")
        self.post_handler = PostHandler(self.queue, self.posts_storage)
        self.posts_supplier = YoutubeChannelsHandler(self.posts_storage)

        self.pd = ProcessDirector("im po su")

        log.info("important post supplier started")

    def load_new_posts_for_human(self, human_name, channel_id):
        try:
            new_posts = self.posts_supplier.get_new_channel_videos(channel_id)
            new_posts = filter(lambda x: x.for_sub is not None, new_posts)
            log.info("At youtube for [%s] found [%s] new posts:\n%s" % (
                human_name, len(new_posts), ' youtube \n'.join([str(post) for post in new_posts])))

            for post in new_posts:
                self.post_handler.add_important_post(human_name, post, post.for_sub, channel_id, important=True)

            return len(new_posts), None

        except Exception as e:
            log.error("Exception at loading youtube new posts %s, for %s at %s" % (e, human_name, channel_id))
            log.exception(e)
            return e.message, e

    def run(self):
        if not self.pd.can_start_aspect(IMPORTANT_POSTS_SUPPLIER_PROCESS_ASPECT, self.pid).get("started"):
            log.info("important posts supplier instance already work")
            return

        while 1:
            humans_data = self.main_storage.get_humans_info(projection={"user": True, "subs": True, "channel_id": True})
            for human_data in humans_data:
                channel_id = human_data.get("channel_id")
                if channel_id:
                    self.load_new_posts_for_human(human_data.get("user"), channel_id)

            time.sleep(force_post_manager_sleep_iteration_time)


class NoisePostsAutoAdder(Process):
    '''
    Must be init and run server if will setting auto removing generated post to balancer

    1) В глобальных конфигах должно быть установлен конфиг с ключем == имени этого дерьма
    2) Данные этого конфига должны быть on == true и after == количеству секунд после которых
    сгенеренные посты в состоянии PS_READY будут засунуты в балансер и определенны их идентификаторы каналов


    '''
    name = "noise_auto_adder"

    def __init__(self):
        super(NoisePostsAutoAdder, self).__init__()
        self.process_director = ProcessDirector("noise pp")
        self.posts_storage = PostsStorage("noise pp")
        self.post_handler = PostHandler("noise pp", ps=self.posts_storage)
        self.main_db = HumanStorage("noise pp")

    def run(self):
        if not self.process_director.can_start_aspect(self.name, self.pid).get("started"):
            log.info("%s instance already work" % self.name)
            return

        while 1:
            cfg = self.main_db.get_global_config(self.name)
            is_on = cfg.get("on")
            if not is_on:
                log.info("in configuration noise posts auto adder is off i go out")
                return

            after = cfg.get("after")
            if not after:
                after = 3600

            counter = 0
            for post in self.posts_storage.get_old_ready_posts(after):
                self.post_handler.move_noise_post_to_balancer(post, post.for_sub)
                counter += 1

            log.info("Auto add to balancer will add %s posts" % counter)
            time.sleep(after / 10)
