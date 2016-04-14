# coding=utf-8
import hashlib
import logging
import time
from datetime import datetime

from pymongo import MongoClient

from wsgi.properties import mongo_uri, db_name, TIME_TO_WAIT_NEW_COPIES

__author__ = 'alesha'

log = logging.getLogger("DB")


class DBHandler(object):
    def __init__(self, name="?", uri=mongo_uri, db_name=db_name):
        log.info("start db handler for [%s] %s" % (name, uri))
        self.client = MongoClient(host=uri)
        self.db = self.client[db_name]


class HumanStorage(DBHandler):
    def __init__(self, name="?"):
        super(HumanStorage, self).__init__(name=name)
        db = self.db
        self.users = db.get_collection("users")
        if not self.users:
            self.users = db.create_collection()
            self.users.create_index([("name", 1)], unique=True)
            self.users.create_index([("user_id", 1)], unique=True)

        self.human_log = db.get_collection("human_log")
        if not self.human_log:
            self.human_log = db.create_collection(
                    "human_log",
                    capped=True,
                    size=1024 * 1024 * 50,
            )
            self.human_log.create_index([("human_name", 1)])
            self.human_log.create_index([("time", 1)], expireAfterSeconds=3600 * 24)
            self.human_log.create_index([("action", 1)])

        self.human_config = db.get_collection("human_config")
        if not self.human_config:
            self.human_config = db.create_collection("human_config")
            self.human_config.create_index([("user", 1)], unique=True)


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

    def get_all_humans_subs(self):
        cfg = self.human_config.find({})
        subs = []
        for el in cfg:
            subs.extend(el.get("subs", []))
        return list(set(subs))

    def remove_sub_for_humans(self, sub_name):
        result = self.human_config.update_many({"subs": sub_name}, {"$pull": {"subs": sub_name}})
        return result

    def update_human_internal_state(self, name, state):
        update = {}
        if state.get("ss"):
            update["ss"] = {"$each": state['ss']}
        if state.get("frds"):
            update["frds"] = {"$each": state['frds']}
        if update:
            update = {"$addToSet": update}
            result = self.human_config.update_one({"user": name}, update)
            return result

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


    #################HUMAN LOG
    def save_log_human_row(self, human_name, action_name, info):
        self.human_log.insert_one(
                {"human_name": human_name,
                 "action": action_name,
                 "time": datetime.utcnow(),
                 "info": info})

    def get_log_of_human(self, human_name, limit=None):
        res = self.human_log.find({"human_name": human_name}).sort("time", -1)
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
    hs = HumanStorage(delete_posts=False, expire_low_copies_posts=5)
    # hs.set_post_low_copies("foo")
    # time.sleep(5)
    while 1:
        print hs.is_can_see_post("foo")
        time.sleep(5)
