import logging

from wsgi.rr_people import A_POST
from wsgi.rr_people.posting.posts import PostsStorage, PostSource
from wsgi.rr_people.queue import ProductionQueue

log = logging.getLogger("force_action_handler")


class ForceActionHandler(object):
    def __init__(self):
        self.queue = ProductionQueue("fah")
        self.posts_storage = PostsStorage("fah")

    def add_force_post(self, human_name, sub, post_source):
        if isinstance(post_source, PostSource):
            self.posts_storage.add_generated_post(post_source, sub)
            self.queue.put_force_action(human_name, {"action": A_POST, "sub": sub, "url_hash": post_source.url_hash})
        else:
            raise Exception("post_source is not post source!")