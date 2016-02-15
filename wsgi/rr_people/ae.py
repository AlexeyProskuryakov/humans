from datetime import datetime

import pymongo
from pymongo.mongo_client import MongoClient

from wsgi.db import DBHandler
from wsgi.properties import ae_mongo_uri, ae_db_name
from wsgi.rr_people import S_SLEEP, A_SLEEP, A_CONSUME, A_COMMENT, A_VOTE


class AuthorsStorage(DBHandler):
    def __init__(self):
        super(AuthorsStorage, self).__init__()
        self.client = MongoClient(ae_mongo_uri)
        self.db = self.client[ae_db_name]

        self.authors = self.db.get_collection("authors")
        if not self.authors:
            self.authors = self.db.create_collection(
                    "ae_authors",
            )

            self.authors.create_index([("author", pymongo.ASCENDING)])
            self.authors.create_index([("action_type", pymongo.ASCENDING)])

            self.authors.create_index([("current_time", pymongo.ASCENDING)])
            self.authors.create_index([("next_time", pymongo.ASCENDING)])
            self.authors.create_index([("prev_time", pymongo.ASCENDING)])
            self.authors.create_index([("wd", pymongo.ASCENDING)])


class ActivityEngine(object):
    def __init__(self, authors=None):
        self.authors = authors or []
        self._storage = AuthorsStorage()

    def set_authors(self, authors):
        self.authors = authors

    def save_action(self, time, author, action_type, previous_time=None, next_time=None):
        q = {"author": author, "time": time, "action_type": action_type}
        if previous_time:
            if isinstance(previous_time, datetime):
                previous_time = self.time_hash(previous_time)
            q["prev_time"] = previous_time
        if next_time:
            if isinstance(next_time, datetime):
                next_time = self.time_hash(next_time)
            q["next_time"] = next_time

        found = self._storage.authors.find_one(q)
        if found:
            self._storage.authors.update_one(q, {"$inc": {"count": 1}})
        else:
            q["count"] = 1
            self._storage.authors.insert_one(q)

    def time_hash(self, time):
        if not isinstance(time, datetime):
            return ""
        else:
            h = time.hour
            m = time.minute
            s = time.second
            d = time.day
            print h, m, s
            return d * 3600 * 24 + h * 3600 + m * 60 + s

    def get_actions(self, current_step_time=None, next_time_step=None):
        """
         If all actions will save <time|author|action_type|next_time|prev_time|count|week day>
         we get from now to next_step_time
         and aggregate match(authors in self.authors)
        :return: action from [A_* see in __init__.py]
        """
        pipe = [
            {"$match": {"author": {"$in": self.authors},
                        "$or": [
                            {"prev_time": {"$lt": self.time_hash(current_step_time or datetime.utcnow())}},
                            {"current_time":{"$gt":self.time_hash(current_step_time), "$lt":self.time_hash(next_time_step) if next_time_step else self.time_hash(current_step_time) + 60*15}}
                        ]
                        }},
            {"$group": {"_id": "$action_type", "count": {"$sum": "$count"}, "authors": {"$addToSet": "$author"}},
             }
        ]
        result = self._storage.authors.aggregate(pipe)
        return result


if __name__ == '__main__':
    authors = ["auth_a", "auth_b", "auth_c", "auth_d"]
    ae = ActivityEngine(authors)
    day = 1 * 3600 * 24
    hour = day / 24
    etalon = datetime.utcnow().replace(year=1, month=1, day=0, hour=0, minute=0, second=0)
    from random import randint, choice

    for i in xrange(day):
        step = randint(1, 40)
        time = ae.time_hash(etalon.replace(second=i))
        if i > step:
            time_prev = ae.time_hash(etalon.replace(second=i - step))
        else:
            time_prev = time
        time_next = ae.time_hash(etalon.replace(second=i + step))

        if time == 0:
            for au in authors:
                ae.save_action(time, au, A_SLEEP)

        au_min = 0
        au_max = 0
        cnt_min = 0
        cnt_max = 0

        if time > 8 * hour:
            au_min = 0
            au_max = 1
            cnt_min = 0
            cnt_max = 2

        if time > 11 * hour:
            au_min = 1
            au_max = 2
            cnt_min = 1
            cnt_max = 3

        if time > 15 * hour and time < 22 * hour:
            au_min = 2
            au_max = 4
            cnt_min = 1
            cnt_max = 10

        if time > 22 * hour:
            for au in authors:
                ae.save_action(time, au, A_SLEEP)
            break

        for au in range(randint(au_min, au_max)):
            for cnt in range(randint(cnt_min, cnt_max)):
                for i in range(cnt):
                    ae.save_action(time, choice(authors), choice([A_CONSUME, A_COMMENT, A_VOTE]), time_prev, time_next)

    print ae.get_actions()
