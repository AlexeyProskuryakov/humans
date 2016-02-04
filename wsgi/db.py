from datetime import datetime
import hashlib
import time
import pymongo
from pymongo import MongoClient
from wsgi.properties import mongo_uri, db_name
import logging

__author__ = 'alesha'

log = logging.getLogger("DB")


class StatisticsCache(object):
    def __init__(self):
        self.last_update = time.time()
        self.data = {}


class DBHandler(object):
    def __init__(self):
        log.info("start db handler %s" % mongo_uri)
        client = MongoClient(host=mongo_uri)
        db = client[db_name]

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
            self.human_posts.create_index([("low_copies", pymongo.ASCENDING), ("commented", pymongo.ASCENDING)])
            self.human_posts.create_index([("time", pymongo.ASCENDING)])

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

    def get_humans_available(self):
        return self.human_config.find({"info": {"$exists": True},
                                       "subs": {"$exists": True},
                                       "live_state": {"$in": ["work", "unknown", "sleep"]}})

    def set_human_live_state(self, name, state, pid):
        self.human_config.update_one({"user": name},
                                     {"$set": {"live_state": state, "live_state_time": time.time(), "live_pid": pid}})

    def get_human_live_state(self, name, pid):
        found = self.human_config.find_one({"user": name})
        if found:
            state_time = found.get("live_state_time")
            if not state_time or (state_time and time.time() - state_time > 3600):
                return "unknown"
            else:
                return found.get("live_state")
        return None

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

    ######POSTS###########################
    def set_post_commented(self, post_fullname, info=None):
        found = self.human_posts.find_one({"fullname": post_fullname})
        if not found:
            to_add = {"fullname": post_fullname, "commented": True}
            if info:
                to_add["info"] = info
            self.human_posts.insert_one(to_add)
        else:
            to_set = {"commented": True}
            if info:
                to_set["info"] = info
            self.human_posts.update_one({"fullname": post_fullname},
                                        {"$set": to_set})

    def is_post_used(self, post_fullname):
        found = self.human_posts.find_one({"fullname": post_fullname})
        if found:
            if found.get("low_copies"):
                _time = found.get("time", 0)
                return time.time() - _time < 3600 * 24
            if found.get("commented"):
                return True

        return False

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


if __name__ == '__main__':
    db = DBHandler()
    db.set_post_low_copies("tplc1")
    db.set_post_commented("tpc1")
    print db.is_post_used("tpc11")
    print db.is_post_used("tpc1")
    print db.is_post_used("tplc1")
    print db.is_post_used("tplc11")
