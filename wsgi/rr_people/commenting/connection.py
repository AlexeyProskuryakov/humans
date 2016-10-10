# coding=utf-8
import logging
import time

from multiprocessing import RLock, Process

from bson.objectid import ObjectId

from wsgi import ConfigManager
from wsgi.db import DBHandler
from wsgi.rr_people.queue import RedisHandler

log = logging.getLogger("comments")

CS_COMMENTED = "commented"
CS_READY_FOR_COMMENT = "ready_for_comment"
CS_ERROR = "error"

_comments = "comments"


class CommentsStorage(DBHandler):
    def __init__(self, name="?", clear=False):
        cm = ConfigManager()
        super(CommentsStorage, self).__init__(name=name, uri=cm.get('comments_mongo_uri'),
                                              db_name=cm.get('comments_db_name'))
        collections_names = self.db.collection_names(include_system_collections=False)
        if _comments not in collections_names or clear:
            self._clear()
            self.comments = self.db.create_collection(
                _comments,
            )
            self.comments.drop_indexes()
            self.comments.create_index([("text_hash", 1)], unique=True)
            self.comments.create_index([("fullname", 1)])
            self.comments.create_index([("state", 1)], sparse=True)
            self.comments.create_index([("sub", 1)], sparse=True)
        else:
            self.comments = self.db.get_collection(_comments)

        self.mutex = RLock()

    def __del__(self):
        self.remover_stop = True

    def _clear(self):
        try:
            result = self.db.drop_collection(_comments)
            log.info("clearing result: %s", result)
        except Exception as e:
            log.exception(e)

    def end_comment_post(self, comment_oid, by, error_info=None):
        with self.mutex:
            to_set = {"by": by,
                      "time": time.time()}
            if error_info:
                to_set['state'] = CS_ERROR
                to_set['error_info'] = str(error_info)
            else:
                to_set['state'] = CS_COMMENTED

            self.comments.update_one({"_id": ObjectId(comment_oid)},
                                     {"$set": to_set,
                                      "$unset": {"_lock": 1}})

    def start_comment_post(self, comment_oid):
        with self.mutex:
            found = self.comments.find_one(
                {"_id": ObjectId(comment_oid),
                 "state": CS_READY_FOR_COMMENT,
                 "_lock": {"$exists": False}})
            if found:
                self.comments.update_one(found, {"$set": {"_lock": 1}})
                return found

    def get_comment_post_fullname(self, comment_oid):
        found = self.comments.find_one({"_id": ObjectId(comment_oid)})
        if found:
            return found.get("fullname")

    def get_comments_ready_for_comment(self, sub=None):
        q = {"state": CS_READY_FOR_COMMENT, "sub": sub}
        return list(self.comments.find(q))

    def get_comments_commented(self, sub):
        q = {"state": CS_COMMENTED, "sub": sub}
        return list(self.comments.find(q).sort([("time", -1)]))

    def get_comments_by_ids(self, comment_ids, projection=None):
        _projection = projection or {"text": True, "fullname": True, "post_url": True}
        for el in self.comments.find({"_id": {"$in": map(lambda x: ObjectId(x), comment_ids)}},
                                     projection=_projection):
            yield el

    def get_comment_state(self, comment_id):
        found = self.comments.find_one({"_id": ObjectId(comment_id)}, projection={"state": 1})
        if found:
            return found.get('state')


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
        cm = ConfigManager()
        super(CommentRedisQueue, self).__init__("comment queue %s" % name, clear,
                                                cm.get('comment_redis_address'),
                                                cm.get('comment_redis_port'),
                                                cm.get('comment_redis_password'),
                                                0)

    def need_comment(self, sbrdt):
        self.redis.publish(NEED_COMMENT, sbrdt)

    def pop_comment_id(self, sbrdt):
        key = QUEUE_CF(sbrdt)
        result = self.redis.lpop(key)
        log.debug("redis: get by %s\nthis: %s" % (key, result))
        return result

    def get_all_comments_ids(self, sbrdt):
        result = self.redis.lrange(QUEUE_CF(sbrdt), 0, -1)
        return list(result)

    def put_comment(self, sbrdt, comment_id):
        log.debug("redis: push to %s %s" % (sbrdt, comment_id))
        self.redis.rpush(QUEUE_CF(sbrdt), comment_id)


class CommentHandler(CommentsStorage, CommentRedisQueue):
    def __init__(self, name="?"):
        CommentsStorage.__init__(self, "comment handler %s" % name).__init__()
        CommentRedisQueue.__init__(self, "comment handler %s" % name)

    def get_sub_with_comments(self, human_subs):
        subs_with_comments = self.comments.aggregate(
            [{"$match": {'state': CS_READY_FOR_COMMENT}},
             {"$group": {"_id": "$sub", "count": {"$sum": 1}, "time": {"$min": "$time"}}},
             {"$match": {"count": {"$ne": 0}}},
             {"$sort": {"time": 1}}
             ])
        for data in subs_with_comments:
            sub = data.get("_id")
            if sub in human_subs:
                return sub

    def pop_comment_id(self, sbrdt):
        while 1:
            comment_id = CommentRedisQueue.pop_comment_id(self, sbrdt)
            if comment_id:
                result = self.get_comment_state(comment_id)
                if result == CS_READY_FOR_COMMENT:
                    return comment_id
                else:
                    log.warn("Comment [%s] in [%s] is not ready. It is: [%s]" % (comment_id, sbrdt, result))
            else:
                return
