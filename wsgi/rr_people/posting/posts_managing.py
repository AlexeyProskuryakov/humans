import logging
import time
from multiprocessing import Process

from wsgi.db import HumanStorage
from wsgi.properties import force_post_manager_sleep_iteration_time
from wsgi.rr_people.posting.posts import PostsStorage, PostSource
from wsgi.rr_people.posting.posts_balancer import PostBalancer
from wsgi.rr_people.posting.youtube_posts import YoutubeChannelsHandler
from wsgi.rr_people.queue import PostRedisHandler

log = logging.getLogger("force_action_handler")


class PostHandler(object):
    def __init__(self, name="?", pq=None, ps=None):
        self.queue = pq or PostRedisHandler("ph %s" % name)
        self.posts_storage = ps or PostsStorage("ph %s" % name)
        self.youtube = YoutubeChannelsHandler(self.posts_storage)
        self.balancer = PostBalancer()

    def add_new_post(self, human_name, post_source, sub, channel_id=None, important=False):
        if isinstance(post_source, PostSource):
            self.posts_storage.add_generated_post(post_source, sub, important=important)
            self.balancer.add_post(post_source.url_hash, channel_id, important=important, human_name=human_name)
        else:
            raise Exception("post_source is not post source!")

    def add_ready_post(self, sub, post_source):
        if isinstance(post_source, PostSource):
            channel_id = self.youtube.get_channel_id(post_source.url)
            self.balancer.add_post(post_source.url_hash, channel_id, sub=sub)
        else:
            raise Exception("post_source is not post source!")

    def get_post(self, human_name):
        url_hash = self.queue.pop_post(human_name)
        if not url_hash:
            log.warn("Not any posts for [%s] at queue" % human_name)
            return
        post_data = self.posts_storage.get_post(url_hash)
        if not post_data:
            log.warn("Not any posts for [%s] at storage" % human_name)
            return
        post, sub = post_data
        if not post.for_sub: post.for_sub = sub
        return post

    def set_post_state(self, url_hash, new_state):
        self.posts_storage.set_post_state(url_hash, new_state)


class YoutubePostSupplier(Process):
    """
    Process which get humans config and retrieve channel_id, after retrieve new posts from it and
    """

    def __init__(self, pq=None, ps=None, ms=None):
        super(YoutubePostSupplier, self).__init__()
        self.queue = pq or PostRedisHandler("fpm")
        self.posts_storage = ps or PostsStorage("fpm")
        self.main_storage = ms or HumanStorage("fpm")
        self.post_handler = PostHandler(self.queue, self.posts_storage)
        self.posts_supplier = YoutubeChannelsHandler(self.posts_storage)

    def run(self):
        while 1:
            for human_data in self.main_storage.get_humans_info(
                    projection={"user": True, "subs": True, "channel_id": True}):
                channel = human_data.get("channel_id")
                if channel:
                    new_posts = self.posts_supplier.get_new_channel_videos(channel)
                    log.info("For [%s] found [%s] new posts:\n%s" % (
                        human_data.get("user"), len(new_posts), '\n'.join([str(post) for post in new_posts])))
                    for post in new_posts:
                        self.post_handler.add_new_post(human_data.get("user"),
                                                       post,
                                                       post.for_sub,
                                                       channel,
                                                       important=True)
            time.sleep(force_post_manager_sleep_iteration_time)
