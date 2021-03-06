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
from wsgi.rr_people.ae import AuthorsStorage, time_hash, hash_info
from wsgi.rr_people.posting.posts import EVERY

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
    def __init__(self, data):
        self.human = data.get('human')

        self.right = data.get('right')
        self.left = data.get('left', [])

        self.prev_time = data.get('prev_time')
        self.generate_time = data.get("generate_time")

        self.metadata = data.get("metadata")

    def to_dict(self):
        result = {}
        for k, v in self.__dict__.iteritems():
            if not str(k).startswith("_"):
                result[k] = v
        return result

    def is_have_elements_between_prev_time_and(self, cur_time):
        if len(self.find_posts_between(cur_time)) > 0:
            self.prev_time = cur_time
            return True

    def find_posts_between(self, cur_time):
        # will check if was end of week in previous finding
        if self.prev_time > cur_time and (self.prev_time - cur_time) > WEEK / 2:
            self.prev_time = 0

        start, stop = None, None
        for i, post_time in enumerate(self.right):
            if post_time <= cur_time and post_time >= self.prev_time:
                if not start:
                    start = i
                else:
                    stop = i

        if start is None:
            log.info("Not found posts in [%s .. %s]" % (hash_info(self.prev_time), hash_info(cur_time)))
            return []

        if stop is None:
            stop = start + 1

        found = self.right[start:stop]
        log.info("Found %s posts in [%s .. %s]" % (len(found), hash_info(self.prev_time), hash_info(cur_time)))
        self.left.extend(found)
        self.right = self.right[:(start - 1) if start > 0 else start] + self.right[stop:]
        return found

    def is_end(self):
        return len(self.right) <= 1

    def get_time_for_nearest(self, date_hash, current_step):
        counter = current_step
        next_nearest = None
        for post_time in self.right:
            if post_time >= date_hash:
                next_time_important = post_time
                if next_nearest is None:
                    next_nearest = next_time_important
                counter += 1
                if counter == EVERY:
                    return next_nearest - date_hash, next_time_important - date_hash


class PostsSequenceStore(DBHandler):
    coll_name = "posts_sequence"

    def __init__(self, name="?"):
        super(PostsSequenceStore, self).__init__(name=name)
        if self.coll_name not in self.collection_names:
            self.posts_sequence = self.db.create_collection(self.coll_name)
            self.posts_sequence.create_index("human", unique=True)
        else:
            self.posts_sequence = self.db.get_collection(self.coll_name)

    def add_posts_sequence_initial_state(self, human, sequence_metadata, sequence_data):
        return self.posts_sequence.update_one({"human": human},
                                              {"$set": {"metadata": sequence_metadata,
                                                        "right": sequence_data,
                                                        "generate_time": time.time(),
                                                        "middle": [],
                                                        "left": [],
                                                        "prev_time": time_hash(datetime.now())
                                                        }},
                                              upsert=True)

    def get_posts_sequence(self, human):
        result = self.posts_sequence.find_one({"human": human})
        if result:
            return PostsSequence(result)

    def update_post_sequence(self, sequence):
        self.posts_sequence.update_one({"human": sequence.human}, {"$set": sequence.to_dict()})


class PostsSequenceHandler(object):
    name = "post sequence handler"

    def __init__(self, human, ps_store=None, ae_store=None, hs=None, ae_group=None):
        self.human = human
        self.ps_store = ps_store or PostsSequenceStore(self.name)
        self.ae_store = ae_store or AuthorsStorage(self.name)
        self.hs = hs or HumanStorage(self.name)
        self.ae_group = ae_group or self.hs.get_ae_group(self.human)

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
            time_hash(datetime.now()), "\n".join([str(t) for t in sequence_data]),
            hash_info(min),
            hash_info(max),
            hash_info(avg),
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
        self.ps_store.add_posts_sequence_initial_state(self.human, metadata, data)
        return self.ps_store.get_posts_sequence(self.human)

    def _get_sequence(self):
        sequence = self.ps_store.get_posts_sequence(self.human)
        if not sequence or sequence.is_end():
            sequence = self.evaluate_new()
        return sequence

    def get_remained(self, x):
        return x - WEEK if x > WEEK else x

    def is_post_time(self, date_hash=None):
        date_hash = date_hash if date_hash is not None else time_hash(datetime.now())
        sequence = self._get_sequence()
        if sequence.is_have_elements_between_prev_time_and(date_hash):
            self.ps_store.update_post_sequence(sequence)
            return True


if __name__ == '__main__':
    p_store = PostsSequenceStore()
    seq = p_store.get_posts_sequence("Shlak2k16")
    print "\n".join(hash_info(el) for el in seq.right)
