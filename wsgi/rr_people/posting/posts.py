import json

import time

from wsgi.db import DBHandler

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

    def __init__(self, url, title, for_sub=None, at_time=None, url_hash=None, important=False):
        self.url = url
        self.title = title
        self.for_sub = for_sub
        self.at_time = at_time
        self.url_hash = url_hash or str(hash(url))
        self.important = important

    def serialize(self):
        return json.dumps(self.__dict__)

    def to_dict(self):
        return self.__dict__

    def __repr__(self):
        result = "url: [%s] title: [%s] url_hash: [%s]" % (self.url, self.title, self.url_hash)
        if self.for_sub:
            result = "%sfor sub: [%s] " % (result, self.for_sub)
        if self.at_time:
            result = "%stime: [%s]" % (result, self.at_time)
        return result


class PostsStorage(DBHandler):
    def __init__(self, name="?", drop=False, **kwargs):
        super(PostsStorage, self).__init__(name=name, **kwargs)
        collection_name = "generated_posts"
        collection_names = self.db.collection_names(include_system_collections=False)
        if drop:
            self.db.drop_collection(collection_name)
            collection_names.remove(collection_name)

        if collection_name not in collection_names:
            self.posts = self.db.create_collection(collection_name)
            self.posts.create_index("url_hash", unique=True)
            self.posts.create_index("sub")
            self.posts.create_index("human")
            self.posts.create_index("state")
            self.posts.create_index("time")
            self.posts.create_index("_lock", sparse=True)
        else:
            self.posts = self.db.get_collection(collection_name)

    # posts
    def get_post_state(self, url_hash):
        found = self.posts.find_one({"url_hash": str(url_hash)}, projection={"state": 1})
        if found:
            return found.get("state")

    def get_post(self, url_hash, projection=None):
        _projection = projection or {"_id": False}
        found = self.posts.find_one({"url_hash": str(url_hash)}, projection=_projection)
        if found:
            return PostSource.from_dict(found), found
        return None, None

    def add_generated_post(self, post, sub, important=False, channel_id=None, human=None, state=PS_READY):
        if isinstance(post, PostSource):
            found, _ = self.get_post(post.url_hash, projection={"_id": True})
            if not found:
                data = post.to_dict()
                data['state'] = state
                data['sub'] = sub
                data['time'] = time.time()

                if important:
                    data['important'] = important
                if channel_id:
                    data["channel_id"] = channel_id
                if human:
                    data["human"] = human
                return self.posts.insert_one(data)

    def get_posts_for_sub(self, sub, state=PS_READY):
        return map(lambda x: PostSource.from_dict(x), self.posts.find({"sub": sub, "state": state}))

    def remove_posts_of_sub(self, subname):
        result = self.posts.delete_many({"sub": subname})
        return result

    def get_queued_post(self, human=None, sub=None):
        lock_id = time.time()
        q = {}
        if human:
            q['human'] = human
        if sub:
            q['sub'] = sub
        if not q:
            raise Exception("add argument please human or sub")
        q["state"] = PS_READY
        q["_lock"] = {"$exists": False}

        result = self.posts.update_one(q, {"$set": {"state": PS_AT_QUEUE, "_lock": lock_id}})
        if result.modified_count == 1:
            post = self.posts.find_one({"_lock": lock_id})
            return post

    def get_all_queued_posts(self, human):
        q = {"human": human, "state": PS_READY}
        for post in self.posts.find(q):
            yield post

    def set_queued_post_used(self, state, post):
        q = {}
        if '_id' in post:
            q['_id'] = post['_id']
        if '_lock' in post:
            q['_lock'] = post['_lock']
        if not q:
            raise Exception("add argument please _lock or _id")
        self.posts.update_one(q, {"$set": {"state": state}, "$unset": {"_lock": ""}})
