# coding=utf-8
import logging
import time

from wsgi.db import DBHandler
from wsgi.properties import comment_redis_address, comment_redis_password, comment_redis_port
from wsgi.properties import comments_mongo_uri, comments_db_name
from wsgi.rr_people.queue import RedisHandler

log = logging.getLogger("comments")

CS_COMMENTED = "commented"
CS_READY_FOR_COMMENT = "ready_for_comment"


class CommentsStorage(DBHandler):
    def __init__(self, name="?"):
        super(CommentsStorage, self).__init__(name=name, uri=comments_mongo_uri, db_name=comments_db_name)
        collections_names = self.db.collection_names(include_system_collections=False)
        if "comments" not in collections_names:
            self.comments = self.db.create_collection(
                "comments",
                # capped=True,
                # size=1024 * 1024 * 256,
            )
            self.comments.drop_indexes()

            self.comments.create_index([("fullname", 1)])
            self.comments.create_index([("state", 1)], sparse=True)
            self.comments.create_index([("sub", 1)], sparse=True)
        else:
            self.comments = self.db.get_collection("comments")

    def _clear(self):
        self.db.drop_collection("comments")

    def set_commented(self, comment_id, by):
        self.comments.update_one({"_id": comment_id},
                                 {"$set": {"state": CS_COMMENTED,
                                           "by": by,
                                           "time": time.time()},
                                  "$unset": {"lock": 1}})

    def get_comment_info(self, post_fullname):
        found = self.comments.find_one(
            {"fullname": post_fullname,
             "state": CS_READY_FOR_COMMENT,
             "_lock": {"$exists": False}})
        if found:
            self.comments.update_one(found, {"$set": {"lock": 1}})
            return found

    def set_comment_info_ready(self, post_fullname, sub, comment_text, permalink):
        self.comments.insert_one(
            {"fullname": post_fullname,
             "state": CS_READY_FOR_COMMENT,
             "sub": sub,
             "text": comment_text,
             "post_url": permalink}
        )

    def get_posts_ready_for_comment(self, sub=None):
        q = {"state": CS_READY_FOR_COMMENT, "sub": sub}
        return list(self.comments.find(q))

    def get_posts_commented(self, sub):
        q = {"state": CS_COMMENTED, "sub": sub}
        return list(self.comments.find(q).sort({"time": -1}))

    def get_posts(self, posts_fullnames):
        for el in self.comments.find({"fullname": {"$in": posts_fullnames}},
                                     projection={"text": True, "fullname": True, "post_url": True}):
            yield el


NEED_COMMENT = "need_comment"
QUEUE_CF = lambda x: "cf_queue_%s" % x


class CommentRedisQueue(RedisHandler):
    """
    Recommendations from reader:

    post_ids = comment_queue.get_all_comments_post_ids(sub)
    posts = map(lambda x: {"url": x.get("post_url"), "fullname": x.get("fullname"), "text": x.get("text")},
                comment_storage.get_posts(post_ids))


    """

    def __init__(self, name="?", clear=False, host=None, port=None, pwd=None, db=None):
        super(CommentRedisQueue, self).__init__("comment queue %s" % name, clear,
                                                comment_redis_address,
                                                comment_redis_port,
                                                comment_redis_password,
                                                0)

    def need_comment(self, sbrdt):
        self.redis.publish(NEED_COMMENT, sbrdt)

    def pop_comment(self, sbrdt):
        result = self.redis.lpop(QUEUE_CF(sbrdt))
        log.debug("redis: get by %s\nthis: %s" % (sbrdt, result))
        return result

    def get_all_comments_post_ids(self, sbrdt):
        result = self.redis.lrange(QUEUE_CF(sbrdt), 0, -1)
        return list(result)


class CommentHandler(CommentsStorage, CommentRedisQueue):
    def __init__(self, name="?"):
        CommentsStorage.__init__(self, "comment handler %s" % name).__init__()
        CommentRedisQueue.__init__(self, "handler")

    def get_comment(self, sub):
        post_fn = self.pop_comment(sub)
        if post_fn:
            comment_info = self.get_comment_info(post_fn)
            if comment_info:
                return comment_info
        self.need_comment(sub)
