import hashlib
import logging
import time
from datetime import datetime

import pymongo
from pymongo import MongoClient

from wsgi.properties import mongo_uri, db_name
from wsgi.rr_people import info_words_hash

__author__ = 'alesha'

log = logging.getLogger("DB")

WORDS_HASH = "words_hash"


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
            self.human_posts.create_index([("time", pymongo.ASCENDING)])

            self.human_posts.create_index([(WORDS_HASH, pymongo.ASCENDING)])
            self.human_posts.create_index([("by", pymongo.ASCENDING)])

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

    def get_human_live_state(self, name):
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

    def set_post_commented(self, post_fullname, by, text, words_hash):
        found = self.human_posts.find_one({"fullname": post_fullname, "commented": {"$exists": False}})
        if not found:
            to_add = {"fullname": post_fullname, "commented": True, "time": time.time(), WORDS_HASH:words_hash, "text":text, "by":by}
            self.human_posts.insert_one(to_add)
        else:
            to_set = {"commented": True, WORDS_HASH:words_hash, "text":text, "by":by, "time": time.time()}
            self.human_posts.update_one({"fullname": post_fullname}, {"$set": to_set})

    def can_comment_post(self, who, post_fullname=None, hash=None):
        q = {"by": who, "commented": True}
        if post_fullname:
            q["fullname"] = post_fullname
        if hash:
            q['info'] = {WORDS_HASH: hash}
        if not hash and not post_fullname:
            return False
        found = self.human_posts.find_one(q)
        return found is None

    def set_post_found_comment_text(self, post_fullname, word_hash, text=None):
        found = self.human_posts.find_one(
                {"fullname": post_fullname, "$or": [{WORDS_HASH: word_hash}, {WORDS_HASH: {"$exist": False}}]})
        if found and found.get("commented"):
            return
        elif found:
            return self.human_posts.update_one(found, {"$set": {"found_text": True, WORDS_HASH: word_hash}})
        else:
            return self.human_posts.insert_one(
                    {"fullname": post_fullname, "found_text": True, WORDS_HASH: word_hash, "text": text})

    def get_posts_found_comment_text(self):
        return list(self.human_posts.find({"found_text": True, "commented": {"$exists": False}}))

    def is_post_used(self, post_fullname):
        found = self.human_posts.find_one({"fullname": post_fullname})
        return found

    def is_post_commented(self, post_fullname):
        found = self.human_posts.find_one({"fullname": post_fullname})
        if found:
            return found.get("commented")
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
    from rr_people import normalize_comment

    db = HumanStorage()
    db.human_posts.delete_many({})
    h1 = hash(normalize_comment(".,./one 1 two 2 three 3"))
    h11 = hash(normalize_comment("one two three"))

    h2 = hash(normalize_comment("one 12two,. three 112four"))
    h21 = hash(normalize_comment("one two three four"))

    db.set_post_commented("1", info={WORDS_HASH: h1})
    print db.is_post_commented("1")
    print db.is_posts_have_words_hash(h11)
    db.set_post_low_copies("1")
    cb = "one, two , three, four, five,s555ix"
    cb2 = "one, two , three, four, five,s555ix, seven"
    cb3 = "one, two , three, four, five,s555ix, eight"
    db.set_post_found_comment_text("2", hash(normalize_comment(cb)))
    db.set_post_found_comment_text("2", hash(normalize_comment(cb)))
    db.set_post_found_comment_text("3", hash(normalize_comment(cb)))
    db.set_post_found_comment_text("4", hash(normalize_comment(cb)))
    db.set_post_found_comment_text("5", hash(normalize_comment(cb2)))
    db.set_post_found_comment_text("5", hash(normalize_comment(cb3)))

    print db.get_posts_found_comment_text()
    print db.get_posts_commented()
    db.set_post_commented("1", info=dict(info_words_hash(cb), **{"by": "u1", "text": cb}))
    print db.get_posts_found_comment_text()
    print db.get_posts_commented()
    db.human_posts.delete_many({})
