import logging
import random
import re

import praw
import time
from praw.objects import MoreComments
from stemming.porter2 import stem

from wsgi import properties

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36"

USER_AGENTS = [
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0; chromeframe/12.0.742.112)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0; .NET CLR 3.5.30729; .NET CLR 3.0.30729; .NET CLR 2.0.50727; Media Center PC 6.0)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64; x64; Trident/5.0; .NET CLR 3.5.30729; .NET CLR 3.0.30729; .NET CLR 2.0.50727; Media Center PC 6.0)",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Win64; x64; Trident/5.0",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; ru; rv:1.9.1.2) Gecko/20090729 Firefox/3.5.2",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30618; In",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; SHC-KIOSK; SHC-Mac-5FE3; SHC-Unit-K0816; SHC-KMT; .NET C",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; Trident/4.0; SLCC1; .NET CLR 2.0.50727; Media Center PC 5.0; InfoPath",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30618; In",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; .NET CLR 2.0.50727)",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0; SLCC1; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30618; In",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/533.16 (KHTML, like Gecko) Version/5.0 Safari/533.16",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; Trident/4.0; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; Trident/4.0; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.9.2.4) Gecko/20100611 Firefox/3.6.4 GTB7.0",
    "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR",
]

A_PRODUCE = "produce"

A_POST = "post"
A_VOTE = "vote"
A_COMMENT = "comment"

A_CONSUME = "consume"

A_SUBSCRIBE = "subscribe"
A_FRIEND = "friend"

A_SLEEP = "sleep"


S_BAN = "ban"
S_WORK = "work"
S_SLEEP = "sleep"
S_UNKNOWN = "unknown"
S_STOP = "stop"
S_SUSPEND = "suspend"

re_url = re.compile("https?://[^\s/$.?#].[^\s]*")
re_crying_chars = re.compile("[A-Z!]{2,}")

log = logging.getLogger("man")

WORDS_HASH = "words_hash"

POSTS_TTL = 60 * 5


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class _RedditPostsCache():
    __metaclass__ = Singleton

    def __init__(self):
        self._posts_cache = {}
        self._posts_cache_timings = {}

    def get_posts(self, sub):
        if sub in self._posts_cache:
            if (self._posts_cache_timings.get(sub) - time.time()) < POSTS_TTL:
                return self._posts_cache[sub]
            else:
                del self._posts_cache[sub]
                del self._posts_cache_timings[sub]
                return None
        else:
            return None

    def set_posts(self, sub, posts):
        self._posts_cache[sub] = posts
        self._posts_cache_timings[sub] = time.time()


class RedditHandler(object):
    def __init__(self, user_agent=None):
        self.reddit = praw.Reddit(user_agent=user_agent or random.choice(USER_AGENTS))
        self.subreddits_cache = {}
        self.posts_cache = _RedditPostsCache()

    def get_subreddit(self, name):
        if name not in self.subreddits_cache:
            subreddit = self.reddit.get_subreddit(name)
            self.subreddits_cache[name] = subreddit
        else:
            subreddit = self.subreddits_cache.get(name)
        return subreddit

    def get_hot_and_new(self, subreddit_name, sort=None, limit=properties.DEFAULT_LIMIT):
        try:
            result = self.posts_cache.get_posts(subreddit_name)
            if not result:
                subreddit = self.get_subreddit(subreddit_name)
                hot = list(subreddit.get_hot(limit=limit))
                log.info("[%s] hot loaded limit: %s, result: %s" % (subreddit_name, limit, len(hot)))
                new = list(subreddit.get_new(limit=limit))
                log.info("[%s] new loaded limit: %s, result: %s" % (subreddit_name, limit, len(new)))
                result_dict = dict(map(lambda x: (x.fullname, x), hot), **dict(map(lambda x: (x.fullname, x), new)))
                log.info("[%s] all with intersection: %s" % (subreddit_name, len(result_dict)))

                result = result_dict.values()
                self.posts_cache.set_posts(subreddit_name, result)

            if sort:
                result.sort(cmp=sort)

            return result
        except Exception as e:
            log.exception(e)
            return []

    def comments_sequence(self, comments):
        sequence = list(comments)
        position = 0
        while 1:
            to_add = []
            for i in xrange(position, len(sequence)):
                position = i
                comment = sequence[i]
                if isinstance(comment, MoreComments):
                    to_add = comment.comments()
                    break
                else:
                    yield comment

            if to_add:
                sequence.pop(position)
                for el in reversed(to_add):
                    sequence.insert(position, el)

            if position >= len(sequence) - 1:
                break

    def search(self, query):
        copies = list(self.reddit.search(query))
        return copies


token_reg = re.compile("[\\W\\d]+")


def normalize(comment_body, serialise=lambda x: " ".join(x)):
    res = []
    if isinstance(comment_body, (str, unicode)):
        tokens = token_reg.split(comment_body.lower().strip())
        for token in tokens:
            if len(token) > 2:
                res.append(stem(token))
    return serialise(res)


def tokens_equals(tokens, another_tokens, more_than_perc=50):
    o = set(tokens)
    t = set(another_tokens)
    intersection = o.intersection(t)
    return float(len(intersection)) >= ((float(len(o) + len(t)) / 2) * more_than_perc) / 100


CQ_SEP = "$:$"


def deserialize(key):
    if isinstance(key, (str, unicode)) and CQ_SEP in key:
        splitted = key.split(CQ_SEP)
        if len(splitted) == 2:
            return tuple(splitted)
    return None


serialize = lambda pfn, ct: "%s%s%s" % (pfn, CQ_SEP, ct)


def cmp_by_created_utc(x, y):
    return int(x.created_utc - y.created_utc)


def cmp_by_comments_count(x, y):
    return x.num_comments - y.num_comments


def post_to_dict(post):
    return {
        "created_utc": post.created_utc,
        "fullname": post.fullname,
        "num_comments": post.num_comments,
    }


if __name__ == '__main__':

    rh = RedditHandler()
    posts = rh.get_hot_and_new("videos", limit=10)
    for post in posts:
        print post.fullname
