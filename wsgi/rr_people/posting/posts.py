import json
import random

import time
from datetime import datetime

from bson.objectid import ObjectId

from wsgi.db import DBHandler, HumanStorage
from wsgi.rr_people.ae import time_hash

PS_READY = "ready"
PS_POSTED = "posted"
PS_NO_POSTS = "no_posts"
PS_BAD = "bad"
PS_AT_QUEUE = "at_queue"
PS_ERROR = "error"


class PostSource(object):
    @staticmethod
    def deserialize(raw_data):
        data = json.loads(raw_data)
        return PostSource.from_dict(data)

    @staticmethod
    def from_dict(data):
        ps = PostSource(data.get("url"),
                        data.get("title"),
                        data.get("for_sub"),
                        data.get("at_time"),
                        data.get("url_hash"),
                        data.get("important")
                        )
        return ps

    def __init__(self, url, title, for_sub=None, at_time=None, url_hash=None, important=False, video_id=None):
        self.url = url
        self.title = title
        self.for_sub = for_sub
        self.at_time = at_time
        self.url_hash = url_hash or str(hash(url))
        self.important = important
        self.video_id = video_id

    def serialize(self):
        return json.dumps(self.__dict__)

    def to_dict(self):
        return self.__dict__

    def __repr__(self):
        result = "url: [%s] title: [%s] url_hash: [%s]" % (self.url, self.title, self.url_hash)
        if self.for_sub:
            result = "%s for sub: [%s] " % (result, self.for_sub)
        if self.at_time:
            result = "%s time: [%s]" % (result, self.at_time)
        return result


class PostsStorage(DBHandler):
    def __init__(self, name="?", drop=False, hs=None, **kwargs):
        super(PostsStorage, self).__init__(name=name, **kwargs)
        collection_name = "generated_posts"
        collection_names = self.db.collection_names(include_system_collections=False)
        if drop:
            self.db.drop_collection(collection_name)
            collection_names.remove(collection_name)

        if collection_name not in collection_names:
            self.posts = self.db.create_collection(collection_name)
            self.posts.create_index("url_hash", unique=True)
            self.posts.create_index("human", sparse=True)
            self.posts.create_index("sub")
            self.posts.create_index("important")
            self.posts.create_index("state")
            self.posts.create_index("time")
            self.posts.create_index("video_id")
            self.posts.create_index("_lock", sparse=True)
        else:
            self.posts = self.db.get_collection(collection_name)

        if "posts_counters" not in collection_names:
            self.posts_counters = self.db.create_collection("posts_counters")
            self.posts_counters.create_index("human", unique=True)
        else:
            self.posts_counters = self.db.get_collection("posts_counters")

        self.hs = hs or HumanStorage("ps %s" % name)

    # posts
    def get_post_state(self, url_hash):
        found = self.posts.find_one({"url_hash": str(url_hash)}, projection={"state": 1, "_id": 1})
        if found:
            return found.get("state"), found.get("_id")
        return None, None

    def is_video_id_present(self, video_id):
        return self.posts.find_one({"video_id": video_id})

    def get_post(self, url_hash, projection=None):
        _projection = projection or {"_id": False}
        found = self.posts.find_one({"url_hash": str(url_hash)}, projection=_projection)
        if found:
            return PostSource.from_dict(found), found
        return None, None

    def check_post_hash_exists(self, url_hash):
        found = self.posts.find_one({"url_hash": url_hash}, projection={"id": 1})
        if found: return True
        return False

    def add_generated_post(self, post, sub, important=False, human=None, state=PS_READY, video_id=None):
        if isinstance(post, PostSource):
            if not self.check_post_hash_exists(post.url_hash):
                data = post.to_dict()
                data['state'] = state
                data['sub'] = sub
                data['important'] = important
                data['human'] = human or random.choice(self.hs.get_humans_of_sub(sub))
                data['time'] = time.time()
                if video_id or post.video_id is not None:
                    data["video_id"] = video_id
                return self.posts.insert_one(data)

    def increment_counter(self, human, counter_type):
        self.posts_counters.update_one({"human": human}, {"$inc": {counter_type: 1}}, upsert=True)

    def get_counters(self, human):
        found = self.posts_counters.find_one({"human": human}, projection={"_id": False})
        return found or {}

    def get_queued_post(self, human, important=False):
        lock_id = time.time()

        q = {'human': human}
        q["state"] = PS_READY
        q["_lock"] = {"$exists": False}
        q["important"] = important

        result = self.posts.update_one(q, {"$set": {"state": PS_AT_QUEUE, "_lock": lock_id}})
        if result.modified_count == 1:
            q = {"_lock": lock_id, "important": important, "state": PS_AT_QUEUE}
            post = self.posts.find_one(q)
            return post

    def get_all_queued_posts(self, human):
        q = {"human": human, "state": PS_READY}
        for post in self.posts.find(q):
            yield post

    def set_queued_post_used(self, post, state=PS_POSTED, error_info=None):
        q = {}
        if '_id' in post:
            q['_id'] = post['_id']
        if '_lock' in post:
            q['_lock'] = post['_lock']

        to_set = {"state": state}
        if error_info:
            to_set = {"error_info": error_info}

        self.posts.update_one(q, {"$set": to_set, "$unset": {"_lock": ""}})

    def delete_post(self, post_id):
        return self.posts.delete_one({"_id": ObjectId(post_id)})


CNT_NOISE = "noise"
CNT_IMPORTANT = "important"
EVERY = 9


class PostsBalancer(object):
    def __init__(self, human_name, post_store=None):
        self.post_store = post_store or PostsStorage(name="posts manager")

        self.human = human_name
        self._post_type_in_fly = None

    def start_post(self):
        if self._post_type_in_fly:
            raise Exception("Have not ended posts for %s" % self.human)

        counters = self.post_store.get_counters(self.human)
        noise = int(counters.get(CNT_NOISE, 0))
        important = int(counters.get(CNT_IMPORTANT, 0))

        if important == 0 or (noise % EVERY == 0 and noise / EVERY >= important):
            post = self.post_store.get_queued_post(human=self.human, important=True)
            if post:
                self._post_type_in_fly = CNT_IMPORTANT
                return post

        post = self.post_store.get_queued_post(human=self.human, important=False)
        if post:
            self._post_type_in_fly = CNT_NOISE

        return post

    def end_post(self, post, result_state, error_info=None):
        if not self._post_type_in_fly:
            raise Exception("Have not started posts %s" % self.human)

        if result_state == PS_POSTED:
            self.post_store.increment_counter(self.human, self._post_type_in_fly)

        self.post_store.set_queued_post_used(post, result_state, error_info)
        self._post_type_in_fly = None
