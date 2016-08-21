# coding=utf-8
import functools
import hashlib
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import CollectionInvalid

from wsgi.properties import mongo_uri, db_name, DEFAULT_POLITIC, AE_DEFAULT_GROUP

__author__ = 'alesha'

log = logging.getLogger("DB")


class Cache(object):
    DEFAULT_TTL = 60

    def __init__(self):
        self.mutex = threading.Lock()
        self.cache_data = {}
        self.cache_timings = {}
        self.pathes = defaultdict(list)

        self.ttl = {}

    @staticmethod
    def key(data, path=None):
        return "%s$$%s" % (path or "", data)

    def get(self, key, path=None):
        _key = Cache.key(key, path)
        if _key in self.cache_timings:
            t = time.time()
            ttl = self.ttl.get(_key, self.DEFAULT_TTL)
            if t - self.cache_timings[_key] < ttl:
                return self.cache_data.get(_key)
            else:
                self.remove_key(_key)

    def remove_key(self, _key):
        with self.mutex:
            del self.cache_data[_key]
            del self.cache_timings[_key]
            if _key in self.ttl:
                del self.ttl[_key]

    def remove_path(self, path):
        for key in self.pathes[path]:
            _key = Cache.key(key, path)
            self.remove_key(_key=_key)

    def set(self, key, value, path=None, ttl=None):
        _key = Cache.key(key, path)
        with self.mutex:
            self.cache_data[_key] = value
            self.cache_timings[_key] = time.time()
            self.pathes[path].append(key)
            if ttl:
                self.ttl[_key] = ttl


cache = Cache()

cache_path = lambda x: str(x).replace("set", "").replace("get", "").replace("_", "").strip()


def cache_refresh(f):
    def wrapped(*args, **kwargs):
        cache.remove_path(cache_path(f.__name__))
        return f(*args, **kwargs)

    return wrapped


def cached(ttl=None):
    def cached_dec(f):
        def wrapped(*args):
            k = "".join([str(a) for a in args])
            print k
            path = cache_path(f.__name__)
            result = cache.get(k, path=path)
            if not result:
                f_result = f(*args)
                if f_result:
                    cache.set(k, f_result, path=path, ttl=ttl)
                    result = f_result
            return result

        return wrapped

    return cached_dec


class DBHandler(object):
    def __init__(self, name="?", uri=mongo_uri, db_name=db_name):
        log.info("start db handler for [%s] %s" % (name, uri))
        self.client = MongoClient(host=uri, maxPoolSize=10, connect=False)
        self.db = self.client[db_name]
        self.collection_names = self.db.collection_names(include_system_collections=False)


class HumanStorage(DBHandler):
    def __init__(self, name="?"):
        super(HumanStorage, self).__init__(name=name)
        db = self.db
        collections = self.db.collection_names(include_system_collections=False)
        try:
            self.users = db.create_collection("users")
            self.users.create_index([("name", 1)], unique=True)
            self.users.create_index([("user_id", 1)], unique=True)
        except CollectionInvalid as e:
            self.users = db.get_collection("users")

        if "human_log" not in collections:
            self.human_log = db.create_collection(
                "human_log",
                capped=True,
                size=1024 * 1024 * 50,
            )
            self.human_log.create_index([("human_name", 1)])
            self.human_log.create_index([("time", 1)])
            self.human_log.create_index([("action", 1)])

        else:
            self.human_log = db.get_collection("human_log")

        if "human_statistic" not in collections:
            self.human_statistic = db.create_collection("human_statistic")
            self.human_statistic.create_index([("human_name", 1)])
        else:
            self.human_statistic = db.get_collection("human_statistic")

        try:
            self.human_config = db.create_collection("human_config")
            self.human_config.create_index([("user", 1)], unique=True)
        except CollectionInvalid as e:
            self.human_config = db.get_collection("human_config")

        collection_names = self.db.collection_names(include_system_collections=False)
        if "global_config" not in collection_names:
            self.global_config = db.create_collection("global_config")
            self.global_config.create_index([("name", 1)], unique=True)
        else:
            self.global_config = db.get_collection("global_config")

        if "human_errors" not in collections:
            self.human_errors = db.create_collection("human_errors")
            self.human_errors.create_index([("human_name", 1)])
        else:
            self.human_errors = db.get_collection("human_errors")

    def store_error(self, name, error):
        self.human_errors.insert_one({"human_name": name, "error": error})

    def get_errors(self, name):
        return list(self.human_errors.find({"human_name": name}))

    def clear_errors(self, name):
        self.human_errors.delete_many({"human_name": name})

    def get_global_config(self, name):
        return self.global_config.find_one({"name": name}, projection={"_id": False})

    def set_global_config(self, name, data):
        if isinstance(data, dict):
            doc = dict({"name": name}, **data)
        else:
            doc = {"name": name, "data": data}

        found = self.global_config.find_one({"name": name})
        if found:
            return self.global_config.update_one({"name": name}, {"$set": doc})

        return self.global_config.insert_one(doc)

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

    def get_humans_info(self, q=None, projection=None):
        found = self.human_config.find(q or {}, projection=projection or {"_id": False})
        result = list(found)
        return result

    @cache_refresh
    def set_human_subs(self, name, subreddits):
        self.human_config.update_one({"user": name}, {"$set": {"subs": subreddits}}, upsert=True)

    @cached(ttl=120)
    def get_human_subs(self, name):
        found = self.human_config.find_one({"user": name}, projection={"subs": True})
        if found:
            human_subs = found.get("subs", [])
            return human_subs

    @cache_refresh
    def set_ae_group(self, name, group_name):
        self.human_config.update_one({"user": name}, {"$set": {"ae_group": group_name}})

    @cached()
    def get_ae_group(self, name):
        found = self.human_config.find_one({"user": name}, projection={"ae_group": 1})
        if found:
            return found["ae_group"]
        else:
            return AE_DEFAULT_GROUP

    def set_human_posts_sequence_config(self, name, min_posts, max_posts=None, iterations_count=None):
        to_set = {"min_posts": min_posts}
        if max_posts: to_set["max_posts"] = max_posts
        if iterations_count: to_set["iterations_count"] = iterations_count

        self.human_config.update_one({"user": name}, {"$set": {"posts_sequence_config": to_set}}, upsert=True)

    def get_human_posts_sequence_config(self, name):
        found = self.human_config.find_one({"user": name}, projection={"posts_sequence_config": 1})
        if found:
            return found.get("posts_sequence_config")

    @cache_refresh
    def set_human_post_politic(self, name, politic):
        self.human_config.update_one({"user": name}, {"$set": {"posting_politic": politic}})

    @cached(ttl=3600)
    def get_human_post_politic(self, name):
        found = self.human_config.find_one({"user": name}, projection={"posting_politic"})
        if found:
            return found.get("posting_politic")
        else:
            return DEFAULT_POLITIC

    def get_all_humans_subs(self):
        cfg = self.human_config.find({}, projection={"subs": True})
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
        found = self.human_config.find_one({"user": name}, projection={"ss": True, "frds": True})
        if found:
            return {"ss": set(found.get("ss", [])),  # subscribed subreddits
                    "frds": set(found.get("frds", [])),  # friends
                    }

    def set_human_live_configuration(self, name, configuration):
        self.human_config.update_one({'user': name}, {"$set": {"live_config": configuration.data}})

    def get_human_live_configuration(self, name):
        found = self.human_config.find_one({"user": name}, projection={"live_config": True})
        if found:
            live_config = found.get("live_config")
            return live_config

    @cached(ttl=120)
    def get_human_config(self, name, projection=None):
        proj = projection or {"_id": False}
        return self.human_config.find_one({"user": name}, projection=proj)

    def set_human_channel_id(self, name, channel_id):
        self.human_config.update_one({"user": name}, {"$set": {"channel_id": channel_id}})

    #################HUMAN LOG
    def save_log_human_row(self, human_name, action_name, info):
        self.human_log.insert_one(
            {"human_name": human_name,
             "action": action_name,
             "time": time.time(),
             "info": info})
        self.add_to_statistic(human_name, action_name)

    def add_to_statistic(self, human_name, action_name, inc=1):
        self.human_statistic.update_one({"human_name": human_name}, {"$inc": {action_name: inc}}, upsert=True)

    def get_log_of_human(self, human_name, limit=None):
        res = self.human_log.find({"human_name": human_name}).sort("time", -1)
        if limit:
            res = res.limit(limit)
        return list(res)

    def get_log_of_human_statistics(self, human_name):
        return self.human_statistic.find_one({"human_name": human_name}, projection={"_id": False, "human_name": False})

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
    hs = HumanStorage()
    hs.save_log_human_row("Shlak2k15", "test", {"info": "test"})
