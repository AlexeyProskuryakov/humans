# coding=utf-8
import logging
import time
from threading import Thread
from multiprocessing import RLock

from bson.objectid import ObjectId

from wsgi.db import DBHandler
from wsgi.properties import comment_redis_address, comment_redis_password, comment_redis_port, TIME_TO_COMMENT_SPOILED
from wsgi.properties import comments_mongo_uri, comments_db_name
from wsgi.rr_people.queue import RedisHandler

log = logging.getLogger("comments")

CS_COMMENTED = "commented"
CS_READY_FOR_COMMENT = "ready_for_comment"
CS_ERROR = "error"

_comments = "comments"


class CommentsStorage(DBHandler):
    def __init__(self, name="?", clear=False):
        super(CommentsStorage, self).__init__(name=name, uri=comments_mongo_uri, db_name=comments_db_name)
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

        self.remover_stop = False
        self.remover = Thread(target=self._remove_old)
        self.remover.start()

        self.mutex = RLock()

    def __del__(self):
        self.remover_stop = True

    def _remove_old(self):
        while 1:
            if self.remover_stop: break
            time.sleep(3600)
            result = self.comments.delete_many({"time": {"$lte": time.time() - TIME_TO_COMMENT_SPOILED}})
            if result.deleted_count != 0:
                log.info("old comments removed %s, ok? %s" % (result.deleted_count, result.acknowledged))

    def _clear(self):
        try:
            result = self.db.drop_collection(_comments)
            log.info("clearing result: %s", result)
        except Exception as e:
            log.exception(e)

    def end_comment_post(self, comment_oid, by, error_info=None):
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
        found = self.comments.find_one({"_id":ObjectId(comment_oid)})
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
        for el in self.comments.find({"_id": {"$in": comment_ids}},
                                     projection=_projection):
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

    def pop_comment_id(self, sbrdt):
        result = self.redis.lpop(QUEUE_CF(sbrdt))
        log.debug("redis: get by %s\nthis: %s" % (sbrdt, result))
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
        CommentRedisQueue.__init__(self, "handler")
