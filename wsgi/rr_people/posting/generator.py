# coding=utf-8
import json
import re


class Generator(object):
    def __init__(self, name):
        self.__name = name

    @property
    def name(self):
        return self.__name

    def generate_data(self, subreddit, key_words):
        raise NotImplementedError


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


if __name__ == '__main__':
    ps = PostSource("http://foo.bar.baz?k=100500&w=qwerty&tt=ttrtt", "Foo{bar}Baz", "someSub", 100500600)
    raw = ps.serialize()
    print raw
    ps1 = PostSource.deserialize(raw)
    assert ps.at_time == ps1.at_time
    assert ps.title == ps1.title
    assert ps.url == ps1.url
    assert ps.for_sub == ps1.for_sub
