import json

from wsgi.db import DBHandler

PS_READY = "ready"
PS_POSTED = "posted"


class PostSource(object):
    @staticmethod
    def deserialize(raw_data):
        data_dict = json.loads(raw_data)
        ps = PostSource()
        ps.__dict__ = data_dict
        return ps

    def __init__(self, url=None, title=None, for_sub=None, at_time=None):
        self.url = url
        self.title = title
        self.for_sub = for_sub
        self.at_time = at_time

    def serialize(self):
        return json.dumps(self.__dict__)

    def __repr__(self):
        result = "url: %s \ntitle: %s\n" % (self.url, self.title)
        if self.for_sub:
            result = "%sfor sub: %s\n" % (result, self.for_sub)
        if self.at_time:
            result = "%stime: %s" % (result, self.at_time)
        return result


class PostChecker(DBHandler):
    def __init__(self):
        super(PostChecker, self).__init__()
        self.posts = self.db.get_collection("generated_posts")
        if not self.posts:
            self.posts = self.db.create_collection("generated_posts",
                                                   capped=True,
                                                   size=1024 * 1024 * 100)
            self.posts.create_index("url_hash", unique=True)
            self.posts.create_index("state")

    def set_post_state(self, url_hash, state):
        self.posts.update_one({"url_hash": url_hash}, {"$set": {"state": state}}, upsert=True)

    def get_post_state(self, url_hash):
        found = self.posts.find_one({"url_hash": url_hash})
        if found:
            return found.get("state")


if __name__ == '__main__':
    ps = PostSource("http://foo.bar.baz?k=100500&w=qwerty&tt=ttrtt", "Foo{bar}Baz", "someSub", 100500600)
    raw = ps.serialize()
    print raw
    ps1 = PostSource.deserialize(raw)
    assert ps.at_time == ps1.at_time
    assert ps.title == ps1.title
    assert ps.url == ps1.url
    assert ps.for_sub == ps1.for_sub
