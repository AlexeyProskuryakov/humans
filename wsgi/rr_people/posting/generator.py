# coding=utf-8
class Generator(object):
    def __init__(self, name):
        self.__name = name

    @property
    def name(self):
        return self.__name

    def generate_data(self, subreddit, key_words):
        raise NotImplementedError


