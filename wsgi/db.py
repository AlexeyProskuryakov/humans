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
        log.info("start db handler for [%s] %s" % (name,uri))
        self.client = MongoClient(host=uri)
        self.db = self.client[db_name]


class HumanStorage(DBHandler):
    def __init__(self, delete_posts=False, expire_low_copies_posts=TIME_TO_WAIT_NEW_COPIES, name="?"):
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
            self.human_log.create_index([("time", 1)], expireAfterSeconds=3600*24)
            self.human_log.create_index([("action", 1)])

        self.human_config = db.get_collection("human_config")
        if not self.human_config:
            self.human_config = db.create_collection("human_config")
            self.human_config.create_index([("user", 1)], unique=True)

        self.human_posts = db.get_collection("commented_posts")
        if not self.human_posts or delete_posts:
            db.drop_collection("human_posts")

            self.human_posts = db.create_collection(
                    "human_posts",
                    capped=True,
                    size=1024 * 1024 * 256,
            )
            self.human_posts.drop_indexes()

            self.human_posts.create_index([("fullname", 1)], unique=True)
            self.human_posts.create_index([("commented", 1)], sparse=True)
            self.human_posts.create_index([("ready_for_comment", 1)], sparse=True)
            self.human_posts.create_index([("ready_for_post", 1)], sparse=True)

            self.human_log.create_index("low_copies", expireAfterSeconds=expire_low_copies_posts, sparse=True)

            self.human_posts.create_index([("text_hash", 1)], sparse=True)

        self.humans_states = db.get_collection("human_states")
        if not self.humans_states:
            self.humans_states = db.create_collection("human_states")
            self.human_posts.create_index([("name", 1)])
            self.human_posts.create_index([("state", 1)])

    def update_human_access_credentials_info(self, user, info):
        if isinstance(info.pop_comment("scope"), set):
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

    ############STATES################
    def get_humans_available(self):
        worked = self.humans_states.find({"state": {"$in": ["work", "sleep"]}})
        return worked

    def set_human_state(self, name, state):
        if state == "ban":
            self.humans_states.update_one({"name": name}, {"$inc": {"ban_count": 1}, "$set": {'state': state}},
                                          upsert=True)
        else:
            self.humans_states.update_one({"name": name}, {"$set": {'state': state}}, upsert=True)

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
    def set_post_commented(self, post_fullname, by, hash):
        found = self.human_posts.find_one({"fullname": post_fullname, "commented": {"$exists": False}})
        if not found:
            to_add = {"fullname": post_fullname, "commented": True, "time": time.time(), "text_hash": hash, "by": by}
            self.human_posts.insert_one(to_add)
        else:
            to_set = {"commented": True, "text_hash": hash, "by": by, "time": time.time(), "low_copies": datetime.utcnow()}
            self.human_posts.update_one({"fullname": post_fullname}, {"$set": to_set})

    def can_comment_post(self, who, post_fullname, hash):
        q = {"by": who, "commented": True, "$or": [{"fullname": post_fullname}, {"text_hash": hash}]}
        found = self.human_posts.find_one(q)
        return found is None

    def set_post_ready_for_comment(self, post_fullname):
        found = self.human_posts.find_one({"fullname": post_fullname})
        if found and found.get("commented"):
            return
        elif found:
            return self.human_posts.update_one(found,
                                               {"$set": {"ready_for_comment": True}, "$unset": {"low_copies": datetime.utcnow()}})
        else:
            return self.human_posts.insert_one({"fullname": post_fullname, "ready_for_comment": True})

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
            if (datetime.utcnow() - found.get("low_copies", datetime.utcnow())).total_seconds() > TIME_TO_WAIT_NEW_COPIES:
                self.human_posts.remove(found)
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
            self.human_posts.insert_one({"fullname": post_fullname, "low_copies": datetime.utcnow(), "time": time.time()})
        else:
            self.human_posts.update_one({"fullname": post_fullname},
                                        {'$set': {"low_copies": datetime.utcnow(), "time": time.time()}})

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
