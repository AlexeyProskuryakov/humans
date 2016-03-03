# coding=utf-8
import hashlib
import logging
import time
from datetime import datetime

import pymongo
from pymongo import MongoClient

from wsgi.properties import mongo_uri, db_name, TIME_TO_WAIT_NEW_COPIES

__author__ = 'alesha'

log = logging.getLogger("DB")


class DBHandler(object):
    def __init__(self):
        log.info("start db handler %s" % mongo_uri)
        self.client = MongoClient(host=mongo_uri)
        self.db = self.client[db_name]


class StatisticsCache(object):
    def __init__(self):
        self.last_update = time.time()
        self.data = {}


class HumanStorage(DBHandler):
    def __init__(self):
        super(HumanStorage, self).__init__()
        db = self.db
        self.users = db.get_collection("users")
        if not self.users:
            self.users = db.create_collection()
            self.users.create_index([("name", pymongo.ASCENDING)], unique=True)
            self.users.create_index([("user_id", pymongo.ASCENDING)], unique=True)

        self.cache = {}
        self.statistics = db.get_collection("statistics")
        if not self.statistics:
            self.statistics = db.create_collection(
                    'statistics',
                    capped=True,
                    size=1024 * 1024 * 2,  # required
            )
            self.statistics.create_index([("time", pymongo.ASCENDING)])
            self.statistics.create_index([("type", pymongo.ASCENDING)])

        self.human_log = db.get_collection("human_log")
        if not self.human_log:
            self.human_log = db.create_collection(
                    "human_log",
                    capped=True,
                    size=1024 * 1024 * 256,
            )

            self.human_log.create_index([("human_name", pymongo.ASCENDING)])
            self.human_log.create_index([("time", pymongo.ASCENDING)])
            self.human_log.create_index([("action", pymongo.ASCENDING)])

        self.human_config = db.get_collection("human_config")
        if not self.human_config:
            self.human_config = db.create_collection("human_config")
            self.human_config.create_index([("user", pymongo.ASCENDING)], unique=True)

        self.human_posts = db.get_collection("human_posts")
        if not self.human_posts:
            self.human_posts = db.create_collection(
                    "human_posts",
                    capped=True,
                    size=1024 * 1024 * 256,
            )

            self.human_posts.create_index([("fullname", pymongo.ASCENDING)], unique=True)
            self.human_posts.create_index([("low_copies", pymongo.ASCENDING), ("commented", pymongo.ASCENDING),
                                           ("found_text", pymongo.ASCENDING)])

            self.human_posts.create_index([("time", pymongo.ASCENDING)])
            self.human_posts.create_index([("text_hash", pymongo.ASCENDING)])
            self.human_posts.create_index([("by", pymongo.ASCENDING)])

        self.humans_states = db.get_collection("human_states")
        if not self.humans_states:
            self.humans_states = db.create_collection("human_states")
            self.human_posts.create_index([("name", pymongo.ASCENDING)])
            self.human_posts.create_index([("state", pymongo.ASCENDING)])

    def update_human_access_credentials_info(self, user, info):
        if isinstance(info.get("scope"), set):
            info['scope'] = list(info['scope'])
        self.human_config.update_one({"user": user}, {"$set": {"info": info, "time": time.time()}})

    def prepare_human_access_credentials(self, client_id, client_secret, redirect_uri, user, pwd):
        found = self.human_config.find_one({"user": user})
        if not found:
            self.human_config.insert_one(
                    {"client_id": client_id,
                     "client_secret": client_secret,
                     "redirect_uri": redirect_uri,
                     "user": user,
                     "pwd": pwd
                     })
        else:
            self.human_config.update_one({"user": user}, {"$set": {"client_id": client_id,
                                                                   "client_secret": client_secret,
                                                                   "redirect_uri": redirect_uri,
                                                                   "pwd": pwd}})

    def get_human_access_credentials(self, user):
        result = self.human_config.find_one({"user": user})
        if result.get("info", {}).get("scope"):
            result['info']['scope'] = set(result['info']['scope'])
            return dict(result)
        return None

    def set_human_channel_id(self, name, channel_id):
        self.human_config.update_one({"user": name}, {"$set": {"channel_id": channel_id}})

    def get_humans_info(self):
        found = self.human_config.find({})
        result = list(found)
        return result

    def set_human_subs(self, name, subreddits):
        self.human_config.update_one({"user": name}, {"$set": {"subs": subreddits}})

    def get_human_subs(self, name):
        found = self.human_config.find_one({"user": name})
        if found:
            return found.get("subs", [])
        return []

    def update_human_internal_state(self, name, state):
        update = {}
        if state.get("ss"):
            update["ss"] = {"$each": state['ss']}
        if state.get("frds"):
            update["frds"] = {"$each": state['frds']}
        if update:
            update = {"$addToSet": update}
            result = self.human_config.update_one({"user": name}, update)

    def get_human_internal_state(self, name):
        found = self.human_config.find_one({"user": name})
        if found:
            return {"ss": set(found.get("ss", [])),  # subscribed subreddits
                    "frds": set(found.get("friends", [])),  # friends
                    }

    def set_human_live_configuration(self, name, configuration):
        self.human_config.update_one({'user': name}, {"$set": {"live_config": configuration.data}})

    def get_human_live_configuration(self, name):
        found = self.human_config.find_one({"user": name})
        if found:
            live_config = found.get("live_config")
            return live_config

    def get_human_config(self, name):
        return self.human_config.find_one({"user": name})

    ############STATES################
    def get_humans_available(self):
        worked = self.humans_states.find({"state": {"$in": ["work", "sleep"]}})
        return worked

    def set_human_state(self, name, state, last_action):
        if state == "ban":
            self.humans_states.update_one({"name": name}, {"$inc": {"ban_count": 1}, "$set": {'state': state, "last_action":last_action}},
                                          upsert=True)
        else:
            self.humans_states.update_one({"name": name}, {"$set": {'state': state, "last_action":last_action}}, upsert=True)

    def get_human_state(self, name):
        found = self.humans_states.find_one({"name": name})
        if found:
            state = found.get("state")
            if state == "ban" and found.get("ban_count") <= 3:
                return "work"
            return state
        return None

    def get_humans_with_state(self, state):
        return self.humans_states.find({"state": state})

    ######POSTS###########################
    def set_post_commented(self, post_fullname, by, text, text_hash):
        found = self.human_posts.find_one({"fullname": post_fullname, "commented": {"$exists": False}})
        if not found:
            to_add = {"fullname": post_fullname, "commented": True, "time": time.time(), "text_hash": text_hash,
                      "commented_text": text, "by": by}
            self.human_posts.insert_one(to_add)
        else:
            to_set = {"commented": True, "text_hash": text_hash, "commented_text": text, "by": by, "time": time.time(), "low_copies":False}
            self.human_posts.update_one({"fullname": post_fullname}, {"$set": to_set})

    def can_comment_post(self, who, post_fullname, hash):
        q = {"by": who, "commented": True, "$or": [{"fullname": post_fullname}, {"text_hash": hash}]}
        found = self.human_posts.find_one(q)
        return found is None

    def set_post_ready_for_comment(self, post_fullname, text_hash):
        found = self.human_posts.find_one(
                {"fullname": post_fullname, "$or": [{"text_hash": text_hash}, {"text_hash": {"$exists": False}}]})
        if found and found.get("commented"):
            return
        elif found:
            return self.human_posts.update_one(found,
                                               {"$set": {"ready_for_comment": True, "text_hash": text_hash, "low_copies":False}})
        else:
            return self.human_posts.insert_one(
                    {"fullname": post_fullname, "ready_for_comment": True, "text_hash": text_hash})

    def get_posts_ready_for_comment(self):
        return list(self.human_posts.find({"ready_for_comment": True, "commented": {"$exists": False}}))

    def get_post(self, post_fullname):
        found = self.human_posts.find_one({"fullname": post_fullname})
        return found

    def is_can_see_post(self, fullname):
        """
        Можем посмотреть пост только если у него было мало копий давно.
        Или же поста нет в бд.
        :param fullname:
        :return:
        """
        found = self.human_posts.find_one({"fullname": fullname})
        if found:
            if found.get("low_copies") and time.time() - found.get("time") > TIME_TO_WAIT_NEW_COPIES:
                return True
            return False
        return True

    def is_post_commented(self, post_fullname):
        found = self.human_posts.find_one({"fullname": post_fullname})
        if found:
            return found.get("commented") or False
        return False

    def get_posts_commented(self, by=None):
        q = {"commented": True}
        if by:
            q["by"] = by
        return list(self.human_posts.find(q))

    def set_post_low_copies(self, post_fullname):
        found = self.human_posts.find_one({"fullname": post_fullname})
        if not found:
            self.human_posts.insert_one({"fullname": post_fullname, "low_copies": True, "time": time.time()})
        else:
            self.human_posts.update_one({"fullname": post_fullname},
                                        {'$set': {"low_copies": True, "time": time.time()}})

    #################HUMAN LOG
    def save_log_human_row(self, human_name, action_name, info):
        self.human_log.insert_one(
                {"human_name": human_name,
                 "action": action_name,
                 "time": datetime.utcnow(),
                 "info": info})

    def get_log_of_human(self, human_name, limit=None):
        res = self.human_log.find({"human_name": human_name}).sort("time", pymongo.DESCENDING)
        if limit:
            res = res.limit(limit)
        return list(res)

    def get_log_of_human_statistics(self, human_name):
        pipeline = [
            {"$match": {"human_name": human_name}},
            {"$group": {"_id": "$action", "count": {"$sum": 1}}},
        ]
        return list(self.human_log.aggregate(pipeline))

        #######################USERS

    def add_user(self, name, pwd, uid):
        log.info("add user %s %s %s" % (name, pwd, uid))
        if not self.users.find_one({"$or": [{"user_id": uid}, {"name": name}]}):
            m = hashlib.md5()
            m.update(pwd)
            crupt = m.hexdigest()
            self.users.insert_one({"name": name, "pwd": crupt, "user_id": uid})

    def change_user(self, name, old_p, new_p):
        if self.check_user(name, old_p):
            m = hashlib.md5()
            m.update(new_p)
            crupt = m.hexdigest()
            self.users.insert_one({"name": name, "pwd": crupt})

    def check_user(self, name, pwd):
        found = self.users.find_one({"name": name})
        if found:
            m = hashlib.md5()
            m.update(pwd)
            crupt = m.hexdigest()
            if crupt == found.get("pwd"):
                return found.get("user_id")


#
if __name__ == '__main__':
    from rr_people import normalize

    db = HumanStorage()
    db.human_posts.delete_many({})
    t1 = ".,./one 1 two 2 three 3"
    h1 = hash(normalize(t1))

    t11 = "one two three"
    h11 = hash(normalize(t11))

    t2 = "one 12two,. three 112four"
    h2 = hash(normalize(t2))

    t21 = "one two three four"
    h21 = hash(normalize(t21))

    db.set_post_low_copies("p1")
    p1 = db.get_post("p1")
    print "low copies:", p1
    print "can see", db.is_can_see_post("p1")

    db.set_post_ready_for_comment("p2", h1)
    print "not commented?: ", db.is_post_commented("p2")
    print "ready for comment: ", db.get_post("p2")
    print "can see", db.is_can_see_post("p2")

    db.set_post_commented("p3", "u1", t2, h2)
    print "commented?: ", db.is_post_commented("p3")
    print "commented:", db.get_post("p3")
    print "can not comment u1 p3 h2", db.can_comment_post("u1", "p3", h2)
    print "can comment u2?", db.can_comment_post("u2", "p3", h2)
    print "can comment u1 p3 h21?", db.can_comment_post("u1", "p3", h21)
    print "can comment u1? p4", db.can_comment_post("u1", "p4", h2)
    print "can see", db.is_can_see_post("p3")

    print "can see", db.is_can_see_post("p4")