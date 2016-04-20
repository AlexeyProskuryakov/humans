# coding=utf-8
import json
import logging
import random
import time
from datetime import datetime
from multiprocessing import Process

import redis

from wsgi.db import DBHandler
from wsgi.properties import DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA, min_copy_count, \
    shift_copy_comments_part, min_donor_comment_ups, max_donor_comment_ups, \
    comments_mongo_uri, comments_db_name, DEFAULT_LIMIT, redis_max_connections, states_redis_address, \
    states_redis_port, states_redis_password
from wsgi.rr_people import RedditHandler, cmp_by_created_utc, post_to_dict
from wsgi.rr_people import re_url, normalize, S_WORK, S_SLEEP, re_crying_chars
from wsgi.rr_people.queue import CommentQueue
from wsgi.rr_people.states import StatesHandler

log = logging.getLogger("reader")


def _so_long(created, min_time):
    return (datetime.utcnow() - datetime.fromtimestamp(created)).total_seconds() > min_time


def is_good_text(text):
    return len(re_url.findall(text)) == 0 and \
           len(text) > 15 and \
           len(text) < 120 and \
           "Edit" not in text


PERSIST_STATE = lambda x: "load_state_%s" % x

START_TIME = "t_start"
END_TIME = "t_end"
LOADED_COUNT = "loaded_count"

PREV_START_TIME = "p_t_start"
PREV_END_TIME = "p_t_end"
PREV_LOADED_COUNT = "p_loaded_count"

IS_ENDED = "ended"
IS_STARTED = "started"
PROCESSED_COUNT = "processed_count"
CURRENT = "current"


class CommentFounderStateStorage(object):
    def __init__(self, name="?", clear=False, max_connections=redis_max_connections):
        self.redis = redis.StrictRedis(host=states_redis_address,
                                       port=states_redis_port,
                                       password=states_redis_password,
                                       db=0,
                                       max_connections=max_connections,
                                       )
        if clear:
            self.redis.flushdb()

        log.info("Comment founder state storage for %s inited!" % name)

    def persist_load_state(self, sub, start, stop, count):
        p = self.redis.pipeline()

        key = PERSIST_STATE(sub)
        persisted_state = self.redis.hgetall(key)
        if persisted_state:
            p.hset(key, PREV_START_TIME, persisted_state.get(START_TIME))
            p.hset(key, PREV_END_TIME, persisted_state.get(END_TIME))
            p.hset(key, PREV_LOADED_COUNT, persisted_state.get(LOADED_COUNT))
            p.hset(key, PROCESSED_COUNT, 0)
            p.hset(key, CURRENT, json.dumps({}))

        p.hset(key, START_TIME, start)
        p.hset(key, END_TIME, stop)
        p.hset(key, LOADED_COUNT, count)
        p.execute()

    def set_ended(self, sub):
        p = self.redis.pipeline()
        p.hset(PERSIST_STATE(sub), IS_ENDED, True)
        p.hset(PERSIST_STATE(sub), IS_STARTED, False)
        p.execute()

    def set_started(self, sub):
        p = self.redis.pipeline()
        p.hset(PERSIST_STATE(sub), IS_ENDED, False)
        p.hset(PERSIST_STATE(sub), IS_STARTED, True)
        p.execute()

    def is_ended(self, sub):
        return self.redis.hget(PERSIST_STATE(sub), IS_ENDED)

    def is_started(self, sub):
        return self.redis.hget(PERSIST_STATE(sub), IS_STARTED)

    def set_current(self, sub, current):
        p = self.redis.pipeline()

        p.hset(PERSIST_STATE(sub), CURRENT, json.dumps(current))
        p.hincrby(PERSIST_STATE(sub), PROCESSED_COUNT, 1)
        p.execute()

    def get_current(self, sub):
        data = self.redis.hget(PERSIST_STATE(sub), CURRENT)
        if data:
            return json.loads(data)

    def get_proc_count(self, sub):
        return self.redis.hget(PERSIST_STATE(sub), PROCESSED_COUNT)

    def get_state(self, sub):
        return self.redis.hgetall(PERSIST_STATE(sub))


class CommentsStorage(DBHandler):
    def __init__(self, name="?"):
        super(CommentsStorage, self).__init__(name=name, uri=comments_mongo_uri, db_name=comments_db_name)
        self.comments = self.db.get_collection("comments")
        if not self.comments:
            self.comments = self.db.create_collection(
                "comments",
                capped=True,
                size=1024 * 1024 * 256,
            )
            self.comments.drop_indexes()

            self.comments.create_index([("fullname", 1)], unique=True)
            self.comments.create_index([("commented", 1)], sparse=True)
            self.comments.create_index([("ready_for_comment", 1)], sparse=True)
            self.comments.create_index([("text_hash", 1)], sparse=True)

    def set_post_commented(self, post_fullname, by, hash):
        found = self.comments.find_one({"fullname": post_fullname, "commented": {"$exists": False}})
        if not found:
            to_add = {"fullname": post_fullname, "commented": True, "time": time.time(), "text_hash": hash, "by": by}
            self.comments.insert_one(to_add)
        else:
            to_set = {"commented": True, "text_hash": hash, "by": by, "time": time.time()}

            self.comments.update_one({"fullname": post_fullname}, {"$set": to_set, "$unset": {"comment_body": 1}}, )

    def can_comment_post(self, who, post_fullname, hash):
        q = {"by": who, "commented": True, "$or": [{"fullname": post_fullname}, {"text_hash": hash}]}
        found = self.comments.find_one(q)
        return found is None

    def set_post_ready_for_comment(self, post_fullname, comment_text):
        found = self.comments.find_one({"fullname": post_fullname})
        if found and found.get("commented"):
            return
        elif found:
            return self.comments.update_one(found,
                                            {"$set": {"ready_for_comment": True, "comment_body": comment_text}})
        else:
            return self.comments.insert_one(
                {"fullname": post_fullname, "ready_for_comment": True, "comment_body": comment_text})

    def get_text(self, comment_id):
        self.comments.find({"_id":comment_id})

    def get_posts_ready_for_comment(self):
        return list(self.comments.find({"ready_for_comment": True, "commented": {"$exists": False}}))

    def get_post(self, post_fullname):
        found = self.comments.find_one({"fullname": post_fullname})
        return found

    def get_posts_commented(self, by=None):
        q = {"commented": True}
        if by:
            q["by"] = by
        return list(self.comments.find(q))


class CommentSearcher(RedditHandler):
    def __init__(self, user_agent=None, add_authors=False, start_worked=True):
        """
        :param user_agent: for reddit non auth and non oauth client
        :param lcp: low copies posts if persisted
        :param cp:  commented posts if persisted
        :return:
        """
        super(CommentSearcher, self).__init__(user_agent)
        self.db = CommentsStorage(name="comment searcher")
        self.comment_queue = CommentQueue(name="comment searcher")
        self.states_handler = StatesHandler(name="comment searcher")
        self.subs = {}

        self.add_authors = add_authors
        if self.add_authors:
            from wsgi.rr_people.ae import ActionGeneratorDataFormer
            self.agdf = ActionGeneratorDataFormer()

        self.state_storage = CommentFounderStateStorage()
        self.start_supply_comments()

        if start_worked:
            for sub, state in self.states_handler.get_comment_founders_states().iteritems():
                if S_WORK in state:
                    self.start_find_comments(sub)
                    time.sleep(60 * 5)
        log.info("Read human inited!")

    def comment_retrieve_iteration(self, sub, sleep=True):
        self.states_handler.set_comment_founder_state(sub, S_WORK)
        start = time.time()
        log.info("Will start find comments for [%s]" % (sub))
        for pfn, ct_id in self.find_comment(sub):
            self.comment_queue.put_comment_hash(sub, pfn, ct_id)
        end = time.time()
        sleep_time = random.randint(DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA / 5,
                                    DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA)
        self.states_handler.set_comment_founder_state(sub, S_SLEEP, ex=sleep_time + 1)
        if sleep:
            log.info(
                "Was get all comments which found for [%s] at %s seconds... Will trying next after %s" % (
                    sub, end - start, sleep_time))
            time.sleep(sleep_time)

    def start_find_comments(self, sub):
        if sub in self.subs and self.subs[sub].is_alive():
            return

        def f():
            while 1:
                self.comment_retrieve_iteration(sub)

        ps = Process(name="[%s] comment founder" % sub, target=f)
        ps.start()
        self.subs[sub] = ps

    def start_supply_comments(self):
        log.info("start supplying comments")

        def f():
            for message in self.comment_queue.get_who_needs_comments():
                nc_sub = message.get("data")
                log.info("receive need comments for sub [%s]" % nc_sub)
                founder_state = self.states_handler.get_comment_founder_state(nc_sub)
                if not founder_state or founder_state is S_SLEEP:
                    log.info("will forced start found comments for [%s]" % (nc_sub))
                    self.comment_retrieve_iteration(nc_sub, sleep=False)

        process = Process(name="comment supplier", target=f)
        process.daemon = True
        process.start()

    def get_posts(self, sub):
        state = self.state_storage.get_state(sub)
        limit = DEFAULT_LIMIT
        if state:
            if state.get(IS_ENDED) == "True":
                end = float(state.get(END_TIME))
                start = float(state.get(START_TIME))
                loaded_count = float(state.get(LOADED_COUNT))

                _limit = ((time.time() - end) * loaded_count) / ((end - start) or 1.0)
                if _limit < 1:
                    _limit = 25
            else:
                _limit = int(state.get(LOADED_COUNT, DEFAULT_LIMIT)) - int(state.get(PROCESSED_COUNT, 0))

            limit = _limit if _limit < DEFAULT_LIMIT else DEFAULT_LIMIT

        posts = self.get_hot_and_new(sub, sort=cmp_by_created_utc, limit=limit)
        current = self.state_storage.get_current(sub)
        if current:
            posts = filter(lambda x: x.created_utc > current.get("created_utc"), posts)
        self.state_storage.persist_load_state(sub, posts[0].created_utc, posts[-1].created_utc, len(posts))
        return posts

    def get_acceptor(self, posts):
        posts.sort(cmp_by_created_utc)
        half_avg = float(reduce(lambda x, y: x + y.num_comments, posts, 0)) / (len(posts) * 2)
        for post in posts:
            if not post.archived and post.num_comments < half_avg:
                log.info("found acceptor old: %s, comments: %s, between: \n%s" % (
                    datetime.utcfromtimestamp(post.created_utc), post.num_comments, '\n'.join(
                        ["[%s]\t%s" % (datetime.utcfromtimestamp(post.created_utc), post.num_comments) for post in
                         posts])))
                return post

    def find_comment(self, sub, add_authors=False):
        # todo вынести загрузку всех постов в отдельную хуйню чтоб не делать это много раз
        log.info("Start finding comments to sub %s" % sub)
        posts = self.get_posts(sub)
        self.states_handler.set_comment_founder_state(sub, "%s found %s" % (S_WORK, len(posts)), ex=len(posts) * 2)
        self.state_storage.set_started(sub)

        for post in posts:
            self.state_storage.set_current(sub, post_to_dict(post))

            try:
                copies = self.get_post_copies(post)
                if len(copies) >= min_copy_count:
                    post = self.get_acceptor(copies)
                    comment = None
                    for copy in copies:
                        if copy.subreddit != post.subreddit and copy.fullname != post.fullname:
                            comment = self._retrieve_interested_comment(copy, post)
                            if comment:
                                log.info("Find comment: [%s] in post: [%s] at subreddit: [%s]" % (
                                    comment, post.fullname, sub))
                                break

                    if comment:
                        comment_result_info = self.db.set_post_ready_for_comment(post.fullname, comment.body)
                        comment_id = comment_result_info.upserted_id or comment_result_info.inserted_id
                        yield post.fullname, comment_id

            except Exception as e:
                log.exception(e)

            if add_authors or self.add_authors:
                self.agdf.add_author_data(post.author.name)

        self.state_storage.set_ended(sub)

    def get_post_copies(self, post):
        search_request = "url:\'%s\'" % post.url
        copies = list(self.reddit.search(search_request)) + [post]
        return list(copies)

    def _retrieve_interested_comment(self, copy, post):
        # prepare comments from donor to selection
        after = copy.num_comments / shift_copy_comments_part
        if not after:
            return
        if after > 34:
            after = 34
        for i, comment in enumerate(self.comments_sequence(copy.comments)):
            if i < after:
                continue
            if comment.ups >= min_donor_comment_ups and \
                            comment.ups <= max_donor_comment_ups and \
                            post.author != comment.author and \
                    self.check_comment_text(comment.body, post):
                return comment

    def check_comment_text(self, text, post):
        """
        Checking in db, and by is good and found similar text in post comments.
        Similar it is when tokens (only words) have equal length and full intersection
        :param text:
        :param post:
        :return:
        """
        if is_good_text(text):
            c_tokens = set(normalize(text, lambda x: x))
            if (float(len(c_tokens)) / 100) * 20 >= len(re_crying_chars.findall(text)):
                for p_comment in self.get_all_comments(post):
                    p_text = p_comment.body
                    if is_good_text(p_text):
                        p_tokens = set(normalize(p_text, lambda x: x))
                        if len(c_tokens) == len(p_tokens) and len(p_tokens.intersection(c_tokens)) == len(p_tokens):
                            log.info("found similar text [%s] in post %s" % (c_tokens, post.fullname))
                            return False
                self.clear_cache(post)
                return True


if __name__ == '__main__':
    # queue = ProductionQueue()
    # db = HumanStorage()
    # cs = CommentSearcher(db)
    # time.sleep(5)
    # queue.need_comment("videos")
    CommentFounderStateStorage(clear=True)
    cs = CommentSearcher(start_worked=False)
    for el in cs.find_comment("videos"):
        print el
