# coding=utf-8
from copy import copy
from datetime import datetime
import random
import time
from sys import maxint

from Crypto.Random import random as crypto_random
from flask import logging

from wsgi.db import DBHandler, HumanStorage
from wsgi.properties import WEEK, AVG_ACTION_TIME, DEFAULT_MIN_POSTS_COUNT, DEFAULT_POSTS_SEQUENCE_CACHED_TTL
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


class PostsSequence(object):
    def __init__(self, data, store):
        self.human = data.get('human')
        self.right = data.get('right')
        self.left = data.get('left', [])
        self.middle = data.get('middle', [])
        self.prev_time = data.get('prev_time', 0)

        self.metadata = data.get("metadata")

        self.__store = store

    def to_dict(self):
        result = {}
        for k, v in self.__dict__.iteritems():
            if not str(k).startswith("_"):
                result[k] = v
        return result

    def can_post(self, cur_time):
        self._accumulate_posts_between(cur_time)
        log.info("Can post %s <-> %s" % (delta_info(self.prev_time), delta_info(cur_time)))
        return len(self.middle) != 0

    def accept_post(self):
        if len(self.middle) != 0:
            post = self.middle.pop(0)
            self.left.append(post)
            self._remove_from_middle(post)
        else:
            log.warning("accept post when middle is empty :(")

    def _remove_from_middle(self, post):
        self.__store.posts_sequence.update_one({"human": self.human}, {"$pop": {"middle": -1}, "$push": {'left', post}})

    def _update_sequence_middle_state(self, right, middle, prev_time):
        self.__store.posts_sequence.update_one({"human": self.human},
                                               {"$set": {"middle": middle,
                                                         "right": right,
                                                         "prev_time": prev_time}})

    def _accumulate_posts_between(self, cur_time):
        start, stop = None, None
        for i, post_time in enumerate(self.right):
            if post_time <= cur_time and post_time >= self.prev_time:
                if not start:
                    start = i
                else:
                    stop = i
        if start is None:
            return
        if not stop:
            stop = start + 1

        self.middle.extend(self.right[start:stop])
        self.right = self.right[:start] + self.right[stop:]
        self.prev_time = cur_time
        self._update_sequence_middle_state(self.right, self.middle, self.prev_time)

    def is_end(self):
        return len(self.right) == 0


class PostsSequenceStore(DBHandler):
    coll_name = "posts_sequence"

    def __init__(self, name="?"):
        super(PostsSequenceStore, self).__init__(name=name)
        if self.coll_name not in self.collection_names:
            self.posts_sequence = self.db.create_collection(self.coll_name)
            self.posts_sequence.create_index("human", unique=True)
        else:
            self.posts_sequence = self.db.get_collection(self.coll_name)

    def set_posts_sequence_data(self, human, sequence_metadata, sequence_data):
        return self.posts_sequence.update_one({"human": human},
                                              {"$set": {"metadata": sequence_metadata,
                                                        "right": sequence_data,
                                                        },
                                               "$unset":{
                                                   "middle":1,
                                                   "left":1,
                                                   "prev_time":1

                                               }},
                                              upsert=True)

    def get_posts_sequence(self, human):
        result = self.posts_sequence.find_one({"human": human})
        if result:
            return PostsSequence(result, store=self)


class PostsSequenceHandler(object):
    name = "post sequence handler"

    def __init__(self, human, ps_store=None, ae_store=None, hs=None, ae_group=None):
        self.human = human
        self.ps_store = ps_store or PostsSequenceStore(self.name)
        self.ae_store = ae_store or AuthorsStorage(self.name)
        self.hs = hs or HumanStorage(self.name)
        self.ae_group = ae_group or self.hs.get_ae_group(self.human)

        self._sequence_cache = None
        self._sequence_cache_time = None

    def __evaluate_posts_time_sequence(self, min_posts, max_posts=None, iterations_count=10, current_datetime=None):
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
        time_sequence = self.ae_store.get_time_sequence(self.ae_group)
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

            for i, action_flag in enumerate(actions_sequence):
                if action_flag:
                    time = start + (i * AVG_ACTION_TIME)
                    if time > WEEK: time -= WEEK
                    sequence_data.append(time)

        sequence_data.sort()

        min, max, avg = self._evaluate_info_counts(sequence_data)
        log.info("\n%s %s: \n%s\n----------\nmin: %s \nmax: %s \navg: %s" % (
            self.human,
            time_hash(datetime.utcnow()), "\n".join([str(t) for t in sequence_data]),
            delta_info(min),
            delta_info(max),
            delta_info(avg),
        ))
        return sequence_data, sequence_meta_data

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

    def evaluate_new(self):
        sequence_config = self.hs.get_human_posts_sequence_config(self.human) or \
                          {"min_posts": DEFAULT_MIN_POSTS_COUNT}

        data, metadata = self.__evaluate_posts_time_sequence(**sequence_config)
        self.ps_store.set_posts_sequence_data(self.human, metadata, data)
        return self.ps_store.get_posts_sequence(self.human)

    def _get_sequence(self):
        sequence = self.ps_store.get_posts_sequence(self.human)
        if not sequence or sequence.is_end():
            sequence = self.evaluate_new()
        return sequence

    def get_remained(self, x):
        return x - WEEK if x > WEEK else x

    def is_post_time(self, date_hash=None):
        date_hash = date_hash if date_hash is not None else time_hash(datetime.utcnow())
        sequence = self._get_sequence()
        return sequence.can_post(date_hash)

    def accept_post(self):
        sequence = self._get_sequence()
        sequence.accept_post()


if __name__ == '__main__':
    # res = generate_sequence_data(70, pass_count=50)
    # print sum(res), res
    import random

    psh = PostsSequenceHandler("Shlak2k15")
    psh.evaluate_new()

    step = 0

    while step <= WEEK:
        print psh.is_post_time(step), \
            step, '\n(', psh._sequence_cache.prev_time, ")\n", psh._sequence_cache.left, '\n', psh._sequence_cache.middle, '\n', psh._sequence_cache.right, '\n--------------\n\n'

        step += random.randint(AVG_ACTION_TIME, AVG_ACTION_TIME * 5)
        print "next step: ", step
