# coding=utf-8
import logging
from datetime import datetime
from multiprocessing import Process
from multiprocessing.queues import Queue

import time

import re

from wsgi import properties
from wsgi.rr_people import re_url
from wsgi.rr_people.he import Man

log = logging.getLogger("reader")

def _so_long(created, min_time):
    return (datetime.utcnow() - datetime.fromtimestamp(created)).total_seconds() > min_time


check_comment_text = lambda text: not re_url.match(text) and len(text) > 15 and len(text) < 120 and "Edit" not in text

__doc__= """
    По сути марковская цепь: где узлы есть временные точки, а связи - события произошедшие между этими точками, имеющие вес
    у скольких авторов эти события произошли. Ввсегда есть событие - ниего не делать.
    Определяет что делать чуваку в текущий момент: потреблять, комментировать, ничего не делать.
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


class ActionModel():
    """
    """

class AuthorHandler():
    def __init__(self, db):
        self.db = db



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
        self.queues = {}
        log.info("Read human inited!")

    def start_retrieve_comments(self, sub):
        if sub in self.queues:
            return self.queues[sub]

        self.queues[sub] = Queue()

        def f():
            while 1:
                start = time.time()
                log.info("Will start find comments for [%s]" % (sub))
                for el in self.find_comment(sub):
                    self.queues[sub].put(el)
                end = time.time()
                log.info(
                        "Was get all comments which found for [%s] at %s seconds... Will trying next." % (
                            sub, end - start))
                time.sleep(properties.DEFAULT_SLEEP_TIME_AFTER_READ_SUBREDDIT)

        Process(name="[%s] comment founder" % sub, target=f).start()
        return self.queues[sub]

    def find_comment(self, at_subreddit):
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
        for post in all_posts:
            # log.info("Find comments in %s"%post.fullname)
            if self.db.is_post_used(post.fullname):
                # log.info("But post %s have low copies or commented yet"%post.fullname)
                continue
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
                        # log.info("Validating copy %s for post %s"%(copy.fullname, post.fullname))
                        if copy.subreddit != post.subreddit and copy.fullname != post.fullname:
                            comment = self._retrieve_interested_comment(copy)
                            if comment and post.author != comment.author:
                                log.info("Find comment: [%s] in post: [%s] at subreddit: [%s]" % (
                                    comment, post.fullname, subreddit))
                                break
                                # else:
                                # log.info("But not valid comment found or authors are equals")
                                # else:
                                # log.info("But subreddits or fulnames are equals")
                    if comment:
                        yield {"post": post.fullname, "comment": comment.body}
                    else:
                        log.info("Can not find any valid comments for [%s]" % (post.fullname))
                else:
                    # log.info("But have low copies")
                    self.db.set_post_low_copies(post.fullname)
            except Exception as e:
                log.error(e)

    def _get_post_copies(self, post):
        search_request = "url:\'%s\'" % post.url
        copies = list(self.reddit.search(search_request))
        return list(copies)

    def _retrieve_interested_comment(self, copy):
        # prepare comments from donor to selection
        comments = self.retrieve_comments(copy.comments, copy.fullname)
        after = len(comments) / properties.shift_copy_comments_part
        for i in range(after, len(comments)):
            comment = comments[i]
            if comment.ups >= properties.min_donor_comment_ups and \
                            comment.ups <= properties.max_donor_comment_ups and \
                    check_comment_text(comment.body):
                return comment

    def _get_all_post_comments(self, post, filter_func=lambda x: x):
        result = self.retrieve_comments(post.comments, post.fullname)
        result = set(map(lambda x: x.body, result))
        return result