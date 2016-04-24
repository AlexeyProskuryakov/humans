import json

from wsgi.db import DBHandler

PS_READY = "ready"
PS_POSTED = "posted"
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
                        data.get("url_hash"))
        return ps

    def __init__(self, url=None, title=None, for_sub=None, at_time=None, url_hash=None):
        self.url = url
        self.title = title
        self.for_sub = for_sub
        self.at_time = at_time
        self.url_hash = url_hash or hash(url)

    def serialize(self):
        return json.dumps(self.__dict__)

    def to_dict(self):
        return self.__dict__

    def __repr__(self):
        result = "url: [%s] title: [%s] " % (self.url, self.title)
        if self.for_sub:
            result = "%sfor sub: [%s] " % (result, self.for_sub)
        if self.at_time:
            result = "%stime: [%s]" % (result, self.at_time)
        if self.url_hash:
            result = "%surl_hash: [%s]" % (result, self.url_hash)
        return result


class PostsStorage(DBHandler):
    def __init__(self, name="?"):
        super(PostsStorage, self).__init__(name=name)
        self.posts = self.db.get_collection("generated_posts")
        if not self.posts:
            self.posts = self.db.create_collection("generated_posts",
                                                   capped=True,
                                                   size=1024 * 1024 * 100)
            self.posts.create_index("url_hash", unique=True)
            self.posts.create_index("sub")
            self.posts.create_index("state")

    # posts
    def set_post_state(self, url_hash, state):
        self.posts.update_one({"url_hash": url_hash}, {"$set": {"state": state}})

    def set_posts_states(self, url_hashes_list, state):
        self.posts.update_many({"url_hash": {"$in": url_hashes_list}}, {"$set": {"state": state}})

    def get_post_state(self, url_hash):
        found = self.posts.find_one({"url_hash": url_hash}, projection={"state": 1})
        if found:
            return found.get("state")

    def get_post(self, url_hash):
        found = self.posts.find_one({"url_hash": url_hash, 'state': {'$ne': PS_BAD}})
        if found:
            return PostSource.from_dict(found), found.get('sub')

    def add_generated_post(self, post, sub, important=False, channel_id=None):
        if isinstance(post, PostSource):
            found = self.get_post(post.url_hash)
            if not found:
                data = post.to_dict()
                data['state'] = PS_READY
                data['sub'] = sub
                if important:
                    data['important'] = important
                self.posts.insert_one(data)

    def get_posts_for_sub(self, sub, state=PS_READY):
        return map(lambda x: PostSource.from_dict(x), self.posts.find({"sub": sub, "state": state}))

    def remove_posts_of_sub(self, subname):
        result = self.posts.delete_many({"sub": subname})
        return result


if __name__ == '__main__':
    ps = PostSource("http://foo.bar.baz?k=100500&w=qwerty&tt=ttrtt", "Foo{bar}Baz", "someSub", 100500600)
    raw = ps.serialize()
    print raw
    ps1 = PostSource.deserialize(raw)
    assert ps.at_time == ps1.at_time
    assert ps.title == ps1.title
    assert ps.url == ps1.url
    assert ps.for_sub == ps1.for_sub
