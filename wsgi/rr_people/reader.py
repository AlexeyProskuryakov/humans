# coding=utf-8
import logging
import random
import time
from datetime import datetime
from multiprocessing import Process

import praw
import redis
from praw.objects import MoreComments
from redis.client import Pipeline

from wsgi import properties
from wsgi.db import HumanStorage
from wsgi.properties import c_queue_redis_addres, c_queue_redis_port
from wsgi.rr_people import re_url, normalize, S_WORK, S_SLEEP, S_STOP, re_crying_chars
from wsgi.rr_people import Man

log = logging.getLogger("reader")

CQ_SEP = "$:$"


def get_post_and_comment_text(key):
    if isinstance(key, (str, unicode)) and CQ_SEP in key:
        splitted = key.split(CQ_SEP)
        if len(splitted) == 2:
            return tuple(splitted)
    return None


set_post_and_comment_text = lambda pfn, ct: "%s%s%s" % (pfn, CQ_SEP, ct)


def _so_long(created, min_time):
    return (datetime.utcnow() - datetime.fromtimestamp(created)).total_seconds() > min_time


def is_good_text(text):
    return len(re_url.findall(text)) == 0 and \
           len(text) > 15 and \
           len(text) < 120 and \
           "Edit" not in text


__doc__ = """
    По сути марковская цепь: где узлы есть временные точки, а связи - события произошедшие между этими точками, имеющие вес равный
    у скольких авторов эти события произошли. Ввсегда есть событие - ниего не делать.
    Определяет что делать чуваку в текущий момент: потреблять, комментировать, постить, ничего не делать.
    Для создания требуется мена авторов, по которым будет строиться модель.


    Строится в два этапа.
    Первый, выделение авторов поведение которых будет номиналом:
    1) При извлечении комментариев, выделяем авторов коментариев и авторов постов.
    Наполняем информацию об авторах таким образом: <час>;<день недели>:<автор>:<тип действия><количество>.
    2) В этой таблице делаем аггрегацию: автор:количество действий. Выбираем средне постящих или много постящих.
    3) В этой же таблице делаем аггрегацию по <час>, <день недели> и находим последовательности бездействия авторов (цепочки отсутствия).
    Это будет список [<час>, <день недели>] которые идут подряд и в которых нету какой-либо активности выбранных на 2 этапе авторов.
    Берем те списки которые длины от 2 до 8 часов.
    Метрикой класстеризации будет пересечение этих списков. Класстеризуем с использованием метрикии и получаем класстеры из авторов,
    сидящих примерно в одно и то же время.

    Второй этап получение инфорации об этих авторах.
    1) Строим модель на основе комментариев данных реддитом по авторам извлеченным на первом этапе. GET /user/username/comments
    То есть сохраняем каждый комментрарий так: <минута: час: день недели> : автор : количество. И делаем аггрегацию:
    <минута: час: день недели> : количество комментариев: количество авторов сделавших комментарий.
    Также можно и с воутами сделать.
    2) Модель отвечает что делать в определенную минуту часа дня недели. Высчитывая веса сколько авторов сделали комментарии а сколько
      в этот промежуток времени отсутсвовали.
      Отсутствие считаем тогда когда время попадает в цепочку отсутствия.
    3) В модель можно добавлять или удалять авторов.

    """


class CommentSearcher(Man):
    def __init__(self, db, user_agent=None):
        """
        :param user_agent: for reddit non auth and non oauth client
        :param lcp: low copies posts if persisted
        :param cp:  commented posts if persisted
        :return:
        """
        super(CommentSearcher, self).__init__(user_agent)
        self.db = db
        self.comment_queue = CommentQueue()
        self.subs = {}
        log.info("Read human inited!")

    def start_retrieve_comments(self, sub):
        if sub in self.subs and self.subs[sub].is_alive():
            return

        def f():
            while 1:
                self.comment_queue.set_reader_state(sub, S_WORK)
                start = time.time()
                log.info("Will start find comments for [%s]" % (sub))
                for el in self.find_comment(sub):
                    self.comment_queue.put(sub, el)
                end = time.time()
                sleep_time = random.randint(properties.DEFAULT_SLEEP_TIME_AFTER_READ_SUBREDDIT / 5,
                                            properties.DEFAULT_SLEEP_TIME_AFTER_READ_SUBREDDIT)
                log.info(
                        "Was get all comments which found for [%s] at %s seconds... Will trying next after %s" % (
                            sub, end - start, sleep_time))
                self.comment_queue.set_reader_state(sub, S_SLEEP, ex=sleep_time + 1)
                time.sleep(sleep_time)

        ps = Process(name="[%s] comment founder" % sub, target=f)
        ps.start()
        self.subs[sub] = ps

    def find_comment(self, at_subreddit, serialise=set_post_and_comment_text):
        def cmp_by_created_utc(x, y):
            result = x.created_utc - y.created_utc
            if result > 0.5:
                return 1
            elif result < 0.5:
                return -1
            else:
                return 0

        subreddit = at_subreddit
        all_posts = self.get_hot_and_new(subreddit, sort=cmp_by_created_utc)
        self.comment_queue.set_reader_state(subreddit, "%s found %s" % (S_WORK, len(all_posts)), ex=len(all_posts) * 2)
        for post in all_posts:
            if self.db.is_can_see_post(post.fullname):
                try:
                    copies = self._get_post_copies(post)
                    copies = filter(
                            lambda copy: _so_long(copy.created_utc, properties.min_comment_create_time_difference) and \
                                         copy.num_comments > properties.min_donor_num_comments,
                            copies)
                    if len(copies) >= properties.min_copy_count:
                        copies.sort(cmp=cmp_by_created_utc)
                        comment = None
                        for copy in copies:
                            if copy.subreddit != post.subreddit and copy.fullname != post.fullname:
                                comment = self._retrieve_interested_comment(copy, post)
                                if comment:
                                    log.info("Find comment: [%s] in post: [%s] at subreddit: [%s]" % (
                                        comment, post.fullname, subreddit))
                                    break

                        if comment and self.db.set_post_ready_for_comment(post.fullname,
                                                                          hash(normalize(comment.body))):
                            yield serialise(post.fullname, comment.body)
                    else:
                        self.db.set_post_low_copies(post.fullname)
                except Exception as e:
                    log.exception(e)

                post.author

    def _get_post_copies(self, post):
        search_request = "url:\'%s\'" % post.url
        copies = list(self.reddit.search(search_request))
        return list(copies)

    def _retrieve_interested_comment(self, copy, post):
        # prepare comments from donor to selection
        comments = self.retrieve_comments(copy.comments, copy.fullname)
        after = len(comments) / properties.shift_copy_comments_part
        for i in range(after, len(comments)):
            comment = comments[i]
            if comment.ups >= properties.min_donor_comment_ups and \
                            comment.ups <= properties.max_donor_comment_ups and \
                            post.author != comment.author and \
                    self.check_comment_text(comment.body, post):
                return comment

    def _get_all_post_comments(self, post, filter_func=lambda x: x):
        result = self.retrieve_comments(post.comments, post.fullname)
        result = set(map(lambda x: x.body, result))
        return result

    def check_comment_text(self, text, post):
        """
        Checking in db, and by is good and found similar text in post comments.
        Similar it is when tokens (only words) have equal length and full intersection
        :param text:
        :param post:
        :return:
        """
        if is_good_text(text):
            normalized_text = normalize(text)
            tokens = set(normalized_text.split())
            if (float(len(tokens)) / 100) * 20 >= len(re_crying_chars.findall(text)):
                for comment in praw.helpers.flatten_tree(post.comments):
                    if isinstance(comment, MoreComments):
                        continue
                    c_text = comment.body
                    if is_good_text(c_text):
                        pc_tokens = set(normalize(c_text).split())
                        if len(tokens) == len(pc_tokens) and len(pc_tokens.intersection(tokens)) == len(pc_tokens):
                            log.info("found similar text [%s] in post %s" % (tokens, post.fullname))
                            return False
                return True


Q_SUB_QUEUE = lambda x: "%s_cq" % x
Q_SUBS_STATES_H = "sbrdt_states"


class CommentQueue():
    def __init__(self, clear=False):
        self.redis = redis.StrictRedis(host=c_queue_redis_addres, port=c_queue_redis_port, db=0,
                                       password="sederfes100500")

        log.info("Comment Queue inited!\n Entry subs is:")
        for sub in self.redis.hgetall(Q_SUBS_STATES_H):
            log.info("%s: \n%s\n" % (sub, "\n".join(["%s\t%s" % (k, v) for k, v in self.show_all(sub).iteritems()])))

    def put(self, sbrdt, key):
        log.debug("redis: push to %s \nthis:%s" % (sbrdt, key))
        self.redis.rpush(Q_SUB_QUEUE(sbrdt), key)

    def get(self, sbrdt):
        """
        :param sbrdt: subreddit name in which post will comment
        :return: post full name (which will comment), comment text
        """
        result = self.redis.lpop(Q_SUB_QUEUE(sbrdt))
        log.debug("redis: get by %s\nthis: %s" % (sbrdt, result))
        return get_post_and_comment_text(result)

    def show_all(self, sbrdt):
        result = self.redis.lrange(Q_SUB_QUEUE(sbrdt), 0, -1)
        return dict(map(lambda x: get_post_and_comment_text(x), result))

    def set_reader_state(self, sbrdt, state, ex=None):
        pipe = self.redis.pipeline()
        pipe.hset(Q_SUBS_STATES_H, sbrdt, state)
        pipe.set(sbrdt, state, ex=ex or 3600)
        pipe.execute()

    def get_reader_state(self, sbrdt):
        return self.redis.get(sbrdt)

    def get_sbrdts_states(self):
        result = self.redis.hgetall("sbrdt_states")
        for k, v in result.iteritems():
            ks = self.get_reader_state(k)
            if v is None or ks is None:
                result[k] = S_STOP
        return result


if __name__ == '__main__':
    queue = CommentQueue()
    db = HumanStorage()
    cs = CommentSearcher(db)
    for res in cs.find_comment("videos"):
        print res
