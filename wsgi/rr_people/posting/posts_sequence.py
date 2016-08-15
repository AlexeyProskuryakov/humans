# coding=utf-8
import random
from datetime import datetime

import math

from flask import logging

from wsgi.db import DBHandler
from Crypto.Random import random as crypto_random
from wsgi.properties import DAY, WEEK, AVG_ACTION_TIME, COUNT_SHUFFLE_ITERATIONS
from wsgi.rr_people.ae import AuthorsStorage, time_hash
from wsgi.rr_people.posting.posts import PostsStorage

__doc__ = """
Нужно отправлять посты таким образом:
1) От N штук в неделю до N'
2) Чтобы каждый пост был разбавлен шумовыми. Вопрос про количество шумовых между? Мне кажется, это тоже должен быть
рандом, только не менее чего-то и не более чего-то.
3) Каждый день должен быть рандом. Но в сумее - недельный рандом. Нужно выводить это как-то.
4*) На праздниках, либо в определенные дни должны быть затишья.
5*) Должны быть затишья и наоборот подъемы глобальные. То есть, предусмотреть что чувак будет
ходить в продолжительный отпуск.
"""

log = logging.getLogger("POST_SEQUENCE")

DAYS_IN_WEEK = 7


class PostsSequence(object):
    def __init__(self, sequence, data=None, storage=None):
        data = data or {}
        self.sequence = sequence
        self.started = data.get("started", time_hash(datetime.utcnow()))
        self.cur_day = data.get("cur_day", 0)
        self.cur_day_posts_passed = data.get("cur_day_posts_passed", 0)

        self._human = data.get("human")
        self._storage = storage

    def to_dict(self):
        return dict(filter(lambda x: not str(x[0]).startswith("_"), self.__dict__.iteritems()))

    def get_today_posts_count(self):
        return self.sequence[self.cur_day]

    def set_post_passed(self):
        self.cur_day_posts_passed += 1
        self._storage.posts_sequence.update({"human": self._human}, {"$inc": {"cur_day_post_passed": 1}})


class PostsSequenceStore(DBHandler):
    coll_name = "posts_sequence"

    def __init__(self, name="?"):
        super(PostsSequenceStore, self).__init__(name=name)
        if self.coll_name not in self.collection_names:
            self.posts_sequence = self.db.create_collection(self.coll_name)
            self.posts_sequence.create_index("human", unique=True)
        else:
            self.posts_sequence = self.db.get_collection(self.coll_name)

    def set_posts_sequence_data(self, human, sequence):
        self.posts_sequence.update_one({"human": human},
                                       {"$set": sequence},
                                       upsert=True)

    def get_posts_sequence(self, human):
        result = self.posts_sequence.find_one({"human": human})
        if result:
            return PostsSequence(sequence=result.get("sequence"), data=result, storage=self)


class PostSequenceHandler(object):
    name = "post sequence handler"

    def __init__(self, human, ps_store=None, ae_store=None):
        self.human = human
        self.ps_store = ps_store or PostsSequenceStore(self.name)
        self.ae_store = ae_store or AuthorsStorage(self.name)

    def evaluate_posts_times(self, n_min, n_max=None, pass_count=10):
        '''
        1) getting time slices when human not sleep in ae .
        2) generate sequence data
        3) for each slice:
            3.1) we have time of active (dtA) and avg action time = ~2-3-4min (tAct) and count of posts in this slice (cp)
            3.2) create array of 0 count = dtA/tAct - cp and add array of 1 with count = cp
            3.3) shuffle result array.
            3.4) on shuffled result array create list of timings posts
        4) persist

        :param n_min ~minimum posts at week
        :param n_max ~maximum posts at week
        :param pass_count count of iterations for evaluate sequence data
        :return:
        '''
        time_sequence = self.ae_store.get_time_sequence(self.human)
        sequence_data = generate_sequence_data(n_min, n_max=n_max, pass_count=pass_count, count=len(time_sequence))
        log.info("\n%s:: %s : %s" % (self.human, sum(sequence_data), sequence_data))
        sequence_result = []
        for i, slice in enumerate(time_sequence):
            start, stop = tuple(slice)
            if start > stop:
                td = (WEEK - start) + stop
            else:
                td = stop - start

            action_counts_per_slice = (td / AVG_ACTION_TIME) - sequence_data[i]
            actions_sequence = [0] * action_counts_per_slice + [1] * sequence_data[i]
            crypto_random.shuffle(actions_sequence)
            for i, action_flag in enumerate(actions_sequence):
                if action_flag:
                    time = start + (i * AVG_ACTION_TIME)
                    if time > WEEK: time -= WEEK
                    sequence_result.append(time)

        log.info("\n%s: \n%s" % (self.human, "\n".join([str(t) for t in sequence_result])))
        self.posts_time_sequence = sequence_result


def generate_sequence_data(n_min, n_max=None, pass_count=10, count=DAYS_IN_WEEK):
    result = [0] * count
    _n_max = n_max or n_min
    creator = (n_min + _n_max) / (2. * DAYS_IN_WEEK)
    adder = 0
    prev_adder = 0
    for passage in range(pass_count):
        for day_number in range(DAYS_IN_WEEK):
            if result[day_number] == 0:
                day_count = random.randint(
                    int(-(creator / 4)),
                    int(creator + creator / 2)
                )
            else:
                day_count = result[day_number]

            if adder != 0:
                day_count += int(random.random() * adder)

            if day_count < 0:
                day_count = 0

            result[day_number] = day_count

        week_count = sum(result)
        if week_count <= _n_max and week_count >= n_min:
            break
        elif week_count > _n_max:
            adder = float(_n_max - week_count) / DAYS_IN_WEEK
        elif week_count < n_min:
            adder = float((n_min - week_count) * 3) / DAYS_IN_WEEK

        if adder == prev_adder:
            break
        else:
            prev_adder = adder

    return result


if __name__ == '__main__':
    # res = generate_sequence_data(70, pass_count=50)
    # print sum(res), res
    psh = PostSequenceHandler("Shlak2k15")
    psh.evaluate_posts_times(70)
