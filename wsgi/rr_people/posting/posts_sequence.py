# coding=utf-8
from copy import copy
from datetime import datetime
import random
import time
from sys import maxint

from Crypto.Random import random as crypto_random
from flask import logging

from wsgi.db import DBHandler, HumanStorage
from wsgi.properties import WEEK, AVG_ACTION_TIME
from wsgi.rr_people.ae import AuthorsStorage, time_hash, delta_info

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
DEFAULT_MIN_POSTS_COUNT = 75
DEFAULT_POSTS_SEQUEMCE_CACHED_TTL = 5 * AVG_ACTION_TIME


class PostsSequence(object):
    def __init__(self, data, store):
        self.human = data.get('human')
        self.right = data.get('right')
        self.left = data.get('left')

        self.passed = data.get("passed")
        self.skipped = data.get("skipped")

        self.__store = store

    def to_dict(self):
        dict = self.__dict__
        for k in dict.keys():
            if str(k).startswith("__"):
                del dict[k]
        return dict

    def get_near_time(self, time):
        result = {}
        for i, n_el in enumerate(self.right):
            result[abs(n_el - time)] = i
        near = min(result.keys())
        position = result[near]
        return self.right[position], position, near

    def pass_element(self, position):
        new_length = len(self.right)
        self.passed += 1
        if position > 0:
            self.skipped += position - 1
            for i in range(new_length):
                if i <= position:
                    self.left.append(self.right.pop(0))
                else:
                    break
            self.__store.update_sequence(self)
        else:
            post = self.right.pop(0)
            self.left.append(post)
            self.__store.pass_post(self.human, post)


class PostsSequenceStore(DBHandler):
    coll_name = "posts_sequence"

    def __init__(self, name="?"):
        super(PostsSequenceStore, self).__init__(name=name)
        if self.coll_name not in self.collection_names:
            self.posts_sequence = self.db.create_collection(self.coll_name)
            self.posts_sequence.create_index("human", unique=True)
        else:
            self.posts_sequence = self.db.get_collection(self.coll_name)

    def create_posts_sequence_data(self, human, sequence_metadata, sequence_data):
        return self.posts_sequence.update_one({"human": human},
                                       {"$set": {"metadata": sequence_metadata,
                                                 "right": sequence_data,
                                                 "left": [],
                                                 "passed": 0,
                                                 "skipped": 0
                                                 }},
                                       upsert=True)

    def get_posts_sequence(self, human):
        result = self.posts_sequence.find_one({"human": human})
        if result:
            return PostsSequence(result, store=self)

    def pass_post(self, human, post_time):
        result = self.posts_sequence.update_one({"human": human}, {"$push": {"left", post_time}, "$pop": {"right": -1}})
        return result

    def update_sequence(self, sequence):
        self.posts_sequence.update_one({"human": sequence.human},
                                       {"$set": sequence.to_dict()})


class PostsSequenceHandler(object):
    name = "post sequence handler"

    def __init__(self, human, ps_store=None, ae_store=None, hs=None):
        self.human = human
        self.ps_store = ps_store or PostsSequenceStore(self.name)
        self.ae_store = ae_store or AuthorsStorage(self.name)
        self.hs = hs or HumanStorage(self.name)

        self._sequence_cache = None
        self._sequence_cache_time = None

    def evaluate_posts_time_sequence(self, min_posts, max_posts=None, iterations_count=10):
        '''
        1) getting time slices when human not sleep in ae .
        2) generate sequence data
        3) for each slice:
            3.1) we have time of active (dtA) and avg action time = ~2-3-4min (tAct) and count of posts in this slice (cp)
            3.2) create array of 0 count = dtA/tAct - cp and add array of 1 with count = cp
            3.3) shuffle result array.
            3.4) on shuffled result array create list of timings posts
        4) setting head of result is max similar of now

        :param min_posts ~minimum posts at week
        :param max_posts ~maximum posts at week
        :param iterations_count count of iterations for evaluate sequence data
        :return:
        '''
        time_sequence = self.ae_store.get_time_sequence(self.human)
        if not time_sequence:
            raise Exception("Not time sequence for %s" % self.human)

        sequence_meta_data = generate_sequence_days_metadata(min_posts, n_max=max_posts,
                                                             iterations_count=iterations_count,
                                                             count=len(time_sequence))
        log.info("\n%s:: %s : %s" % (self.human, sum(sequence_meta_data), sequence_meta_data))
        sequence_data = []
        for i, slice in enumerate(time_sequence):
            start, stop = tuple(slice)
            if start > stop:
                td = (WEEK - start) + stop
            else:
                td = stop - start

            action_counts_per_slice = (td / AVG_ACTION_TIME) - sequence_meta_data[i]
            actions_sequence = [0] * action_counts_per_slice + [1] * sequence_meta_data[i]

            crypto_random.shuffle(actions_sequence)
            random.shuffle(actions_sequence)
            crypto_random.shuffle(actions_sequence)
            random.shuffle(actions_sequence)
            crypto_random.shuffle(actions_sequence)

            print actions_sequence

            for i, action_flag in enumerate(actions_sequence):
                if action_flag:
                    time = start + (i * AVG_ACTION_TIME)
                    if time > WEEK: time -= WEEK
                    sequence_data.append(time)

        sequence_data = self._sort_from_current_time(sequence_data)
        min, max, avg = self._evaluate_info_counts(sequence_data)
        log.info("\n%s %s: \n%s\n----------\nmin: %s \nmax: %s \navg: %s" % (
            self.human,
            time_hash(datetime.utcnow()), "\n".join([str(t) for t in sequence_data]),
            delta_info(min),
            delta_info(max),
            delta_info(avg),
        ))
        return sequence_data, sequence_meta_data

    def _sort_from_current_time(self, post_time_sequence):
        i_time = time_hash(datetime.utcnow())
        prev_pt = None
        position = None
        for i, pt in enumerate(post_time_sequence):
            if prev_pt == None:
                prev_pt = pt

            if i_time < pt and i_time > prev_pt:
                position = i
                break
        result_post_time_sequence = post_time_sequence[position:] + post_time_sequence[:position]
        return result_post_time_sequence

    def _evaluate_info_counts(self, post_time_sequence):
        min_diff = maxint
        max_diff = 0

        diff_acc = []
        prev_pt = None
        for pt in post_time_sequence:
            if prev_pt == None:
                prev_pt = pt
                continue
            if prev_pt > pt:
                pt += WEEK
            diff = abs(prev_pt - pt)
            if diff < min_diff:
                min_diff = diff
            if diff > max_diff:
                max_diff = diff
            diff_acc.append(diff)

            prev_pt = pt

        avg_diff = sum(diff_acc) / len(diff_acc)
        return min_diff, max_diff, avg_diff

    def _get_sequence(self):
        if not self._sequence_cache or time.time() - self._sequence_cache_time > DEFAULT_POSTS_SEQUEMCE_CACHED_TTL:
            sequence = self.ps_store.get_posts_sequence(self.human)
            if not sequence:
                sequence_config = self.hs.get_human_posts_sequence_config(self.human) or \
                                  {"min_post": DEFAULT_MIN_POSTS_COUNT}
                data, metadata = self.evaluate_posts_time_sequence(**sequence_config)
                self.ps_store.create_posts_sequence_data(self.human, metadata, data)
                sequence = self.ps_store.get_posts_sequence(self.human)

            self._sequence_cache = sequence
            self._sequence_cache_time = time.time()

        return self._sequence_cache

    def accept_post(self, date_hash=None):
        date_hash = date_hash or time_hash(datetime.utcnow())
        sequence = self._get_sequence()
        time, position, remained = sequence.get_near_time(date_hash)
        if position > 0:
            return position
        else:
            steps_remained = remained / AVG_ACTION_TIME
            if steps_remained < 2:
                return position
        return False

    def pass_post(self, position):
        sequence = self._get_sequence()
        sequence.pass_element(position)


def generate_sequence_days_metadata(n_min, n_max=None, iterations_count=10, count=DAYS_IN_WEEK):
    result = [0] * count
    _n_max = n_max or n_min
    creator = (n_min + _n_max) / (2. * DAYS_IN_WEEK)
    adder = 0
    prev_adder = 0
    for passage in range(iterations_count):
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
    psh = PostsSequenceHandler("Shlak2k15")
    psh.evaluate_posts_time_sequence(70)
