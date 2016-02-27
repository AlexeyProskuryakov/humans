import logging
import random
from collections import defaultdict, Counter
from datetime import datetime
from random import choice

import praw
import pymongo
from pymongo.mongo_client import MongoClient

from wsgi.db import DBHandler
from wsgi.properties import ae_mongo_uri, ae_db_name
from wsgi.rr_people import USER_AGENTS, A_SLEEP, A_CONSUME, A_COMMENT, DAY, HOUR, MINUTE, SEC

log = logging.getLogger("ae")


class AEPrepearer(object):
    def __init__(self, auth_storage):
        self.auth_storage = auth_storage


class AuthorsStorage(DBHandler):
    def __init__(self):
        super(AuthorsStorage, self).__init__()
        self.client = MongoClient(ae_mongo_uri)
        self.db = self.client[ae_db_name]

        self.authors = self.db.get_collection("ae_authors")
        if not self.authors:
            self.authors = self.db.create_collection(
                    "ae_authors",
            )

            self.authors.create_index([("author", pymongo.ASCENDING)])
            self.authors.create_index([("action_type", pymongo.ASCENDING)])
            self.authors.create_index([("time", pymongo.ASCENDING)])
            self.authors.create_index([("end_time", pymongo.ASCENDING)])

        self.author_groups = self.db.get_collection("ae_author_groups")

        if not self.author_groups:
            self.author_groups = self.db.create_collection("ae_author_groups")

    def get_interested_authors(self, min_count_actions=1500):
        result = self.authors.aggregate([
            {"$group": {"_id": "$author", "count": {"$sum": "$count"}}},
            {"$match": {"count": {"$gte": min_count_actions}}}])
        return filter(lambda x: x is not None, map(lambda x: x.get("_id"), result))

    def get_authors_groups(self, min_difference=2 * HOUR, difference_step=2 * HOUR, step_count=10, min_nights=5,
                           by=A_SLEEP):
        authors = defaultdict(list)
        groups = []

        for author in self.get_interested_authors():
            author_steps = []
            for step in self.authors.find(
                    {"end_time": {"$exists": True}, "action_type": by, "author": author}).sort("time"):
                author_steps.append(dict(step))
            if len(author_steps) >= min_nights:
                authors[author] = author_steps[:]
                groups.append({author})

        log.info("Preparing authors for groups: %s" % authors.keys())

        def create_new_groups(nearest_groups, groups):
            auth_1 = set(groups[nearest_groups[0]])
            auth_2 = set(groups[nearest_groups[1]])
            new_group = auth_1.union(auth_2)
            result = [new_group]
            for g_id, group in enumerate(groups):
                if g_id not in nearest_groups:
                    result.append(group)
            return result

        result = []
        step = 0

        while len(groups) > 4 or len(groups) == 0:
            log.info("adding to group. Group len is:%s" % len(groups))
            max_nearest_weight = 0
            nearest_groups = (None, None)

            for i, authors_group in enumerate(groups):
                for j, authors_a_group in enumerate(groups):
                    if i == j: continue
                    nearest = 0
                    for author in authors_group:
                        for a_author in authors_a_group:
                            nearest += self.get_authors_nearest(authors[author], authors[a_author])

                    nearest = nearest / (len(authors_group) * len(authors_a_group))
                    if max_nearest_weight < nearest:
                        max_nearest_weight = nearest
                        nearest_groups = (i, j)

            groups = create_new_groups(nearest_groups, groups)
            result.append(groups[:])
            log.info("filtered groups count: %s" % len(groups))

            step += 1

            if step > step_count:
                break

        return result, authors

    def get_authors_nearest(self, author1_steps, author2_steps):
        """
        :param author1_steps:
        :param author2_steps:
        :return: more is than authors more equals
        """
        result = 0
        s = lambda x: x['time']
        e = lambda x: x["end_time"]

        if len(author1_steps) != len(author2_steps):
            return 0
        for one in author1_steps:
            for two in author2_steps:
                if e(one) < s(two) or e(two) < s(one):
                    result -= 1
                    continue

                k = abs(e(one) - e(two)) + abs(s(one) - s(two))
                if k > (e(one) - s(one)) or k > (e(two) - s(two)):
                    continue

                result += max(e(one), e(two)) - min(s(one), s(two)) - k

        return result

    def get_best_group(self, groups, authors):
        best_group = None
        max_group_nearest = 0
        for group in groups:
            if len(group) < 2: continue
            group_nearest = 0
            for author in group:
                for a_author in group:
                    if author == a_author: continue
                    group_nearest += self.get_authors_nearest(authors[author], authors[a_author])
            if group_nearest > max_group_nearest:
                max_group_nearest = group_nearest
                best_group = group

        return best_group


WEEK_DAYS = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU"}


class ActivityEngine(object):
    class ActionStack():
        def __init__(self, size):
            self.data = []
            self.size = size

        def push(self, action):
            self.data.append(action)
            if len(self.data) > self.size:
                del self.data[0]

        def get_prevailing_action(self):
            if self.data:
                cnt = Counter(self.data)
                return cnt.most_common()[0]

    def __init__(self, authors=None, size=5):
        self.authors = authors or []
        self._storage = AuthorsStorage()
        self._r = praw.Reddit(user_agent=choice(USER_AGENTS))
        self._action_stack = ActivityEngine.ActionStack(size)

    def set_authors(self, authors, group_name=None):
        name = group_name or datetime.now().strftime("%A%B")
        self.authors = list(authors)
        if not self._storage.authors.find_one(group_name):
            self._storage.author_groups.insert_one({"name": name, "authors": self.authors})

    def set_authors_by_group_name(self, group_name):
        result = self._storage.author_groups.find_one({"name": group_name})
        if result:
            self.authors = result.get("authors")
            return self.authors
        return None

    def save_action(self, author, action_type, time, end_time=None):
        q = {"author": author, "action_type": action_type}
        if isinstance(time, datetime):
            q["time"] = self.time_hash(time)
        elif isinstance(time, int):
            q["time"] = time

        if end_time:
            q["end_time"] = end_time

        found = self._storage.authors.find_one(q)
        if found:
            self._storage.authors.update_one(q, {"$inc": {"count": 1}})
        else:
            q["count"] = 1
            self._storage.authors.insert_one(q)

    def hash_string(self, time_hash):
        if not isinstance(time_hash, int):
            return None
        else:
            d, r = divmod(time_hash, DAY)
            h, r = divmod(r, HOUR)
            m, r = divmod(r, MINUTE)
            s = r
            return "%s %s:%s:%s" % (WEEK_DAYS[d], h, m, s)

    def time_hash(self, time):
        if not isinstance(time, datetime):
            return ""
        else:
            h = time.hour
            m = time.minute
            s = time.second
            d = time.weekday()
            return d * DAY + h * HOUR + m * MINUTE + s * SEC

    def weighted_choice_king(self, action_weights):
        total = 0
        winner = 0
        for i, w in action_weights.iteritems():
            total += w
            if random.random() * total < w:
                winner = i
        return winner

    def get_action(self, for_time, step=60):
        pipe = [
            {"$match": {"author": {"$in": self.authors},
                        "$or": [{"time": {"$gte": for_time, "$lte": for_time + step}},
                                {"end_time": {"$gte": for_time + step}, "time": {"$lte": for_time}}
                                ]}
             },
            {"$group": {"_id": "$action_type", "count": {"$sum": "$count"}, "authors": {"$addToSet": "$author"}}}
        ]
        result = self._storage.authors.aggregate(pipe)
        action_weights = {}
        for r in result:
            action_weights[r.get("_id")] = r.get("count")
        getted_action = self.weighted_choice_king(action_weights)
        self._action_stack.push(getted_action)
        if self._action_stack.get_prevailing_action() == A_SLEEP: return A_SLEEP
        return getted_action

    def fill_consume_and_sleep(self, authors_min_actions_count=1500):
        for author in self._storage.get_interested_authors(authors_min_actions_count):
            start_time, end_time = 0, 0
            actions = self._storage.authors.find({"author": author}).sort("time", 1)
            for i, action in enumerate(actions):
                if i == 0:
                    start_time = action.get("time")
                    continue

                end_time = action.get("time")
                delta = (end_time - start_time)
                if delta > 6 * HOUR and delta < 24 * HOUR:
                    self.save_action(author, A_SLEEP, start_time, end_time)
                else:
                    self.save_action(author, A_CONSUME, start_time - 60 * 5, end_time + 60 * 5)
                start_time = end_time

            log.info("Was update consume and sleep steps for %s" % author)

    def _get_comments_of(self, author):
        r_author = self._r.get_redditor(author)
        try:
            cb = list(r_author.get_comments(sort="new", limit=1000))
            return cb
        except Exception as e:
            log.exception(e)
        return []

    def fill_ae(self, author_list):
        # todo add for submission (post) action
        count = 0
        for author in author_list:
            log.info("will retrieve comments from %s" % author)
            comments = self._get_comments_of(author)
            for comment in comments:
                self.save_action(author, "comment", datetime.fromtimestamp(comment.created_utc))
                count += 1
        log.info("fill by %s actions" % count)

    def clear(self):
        self._storage.authors.delete_many({})


# def visualise_steps(groups, authors_steps):
#     import matplotlib.pyplot as plt
#
#     counter = 1
#     clrs = ["b", "g", "r", "c", "m", "y", "k"]
#     for i, group in enumerate(groups):
#         c = random.choice(clrs)
#         fstp = None
#         for author in group:
#             counter += 1
#             for step in authors_steps[author]:
#                 if not fstp:
#                     fstp = step
#                 plt.plot([step.get("time"), step.get("end_time")], [counter, counter], "k-", lw=1, label=author,
#                          color=c)
#
#         plt.text(fstp["time"], counter, "%s" % i)
#
#     plt.axis([0, WEEK, 0, len(authors_steps) + 5])
#     plt.xlabel("time")
#     plt.ylabel("authors")
#     plt.show()


# def visualise_group_life(group, ae, step=HOUR):
#     ae.set_authors(group)
#     sleep = []
#     consume = []
#     comment = []
#     for t in range(0, WEEK, step):
#         result = ae.get_action(t)
#         for action in result:
#             if action["_id"] == A_SLEEP:
#                 sleep.append((action.get("count"), t))
#             if action["_id"] == A_CONSUME:
#                 consume.append((action.get("count"), t))
#             if action["_id"] == A_COMMENT:
#                 comment.append((action.get("count"), t))
#
#     get_y = lambda arr: map(lambda x: x[0], arr)
#     get_x = lambda arr: map(lambda x: x[1], arr)
#
#     import matplotlib.pyplot as plt
#
#     plt.plot(get_x(sleep), get_y(sleep), "o", color="r")
#     plt.plot(get_x(consume), get_y(consume), "o", color="g")
#     plt.plot(get_x(comment), get_y(comment), "o", color="b")
#     plt.axis([0, WEEK, 0, 20])
#     plt.xlabel("time")
#     plt.ylabel("actions")
#     plt.show()


if __name__ == '__main__':
    ae = ActivityEngine()
    a_s = AuthorsStorage()
    groups_result, authors = a_s.get_authors_groups()
    group = a_s.get_best_group(groups_result[-1], authors)
    ae.set_authors(group, "Shlak2k15")
    ae.set_authors(group, "Shlak2k16")
    ae.set_authors_by_group_name("Shlak2k15")

    import matplotlib.pyplot as plt
    from wsgi.rr_people import WEEK
    from wsgi.rr_people.he import Consumer

    count = defaultdict(int)
    for t in range(0, WEEK, HOUR / 2):
        result = ae.get_action(t, HOUR / 2)
        if result == A_SLEEP:
            plt.plot([t], [2], "o", color="r")
            count[A_SLEEP] += 1
        if result == A_CONSUME:
            plt.plot([t], [4], "o", color="g")
            count[A_CONSUME] += 1
        if result == A_COMMENT:
            plt.plot([t], [6], "o", color="b")
            count[A_COMMENT] += 1

    print count

    plt.axis([0, WEEK, 0, 8])
    plt.xlabel("time")
    plt.ylabel("actions")
    plt.show()

    # for author in a_s.get_interested_authors(min_count_actions=0):
    #     result = a_s.authors.aggregate([{"$match":{"author":author, "action_type":A_COMMENT}}, {"$group":{"_id":"$action_type", "count":{"$sum":"$count"}}}])
    #     print author,"\t", ";\t".join(["%s: %s"%(el.get("_id"), el.get("count")) for el in  result])

# # visualise_steps([group], authors)
# visualise_group_life(group, ae, HOUR/12)
