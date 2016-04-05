# coding=utf-8
import logging
import random
import time
from datetime import datetime
from multiprocessing import Process

import praw
from praw.objects import MoreComments

from wsgi.db import HumanStorage, DBHandler
from wsgi.properties import DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA, min_donor_num_comments, \
    min_comment_create_time_difference, min_copy_count, \
    shift_copy_comments_part, min_donor_comment_ups, max_donor_comment_ups, \
    comments_mongo_uri, comments_db_name, expire_low_copies_posts, TIME_TO_WAIT_NEW_COPIES
from wsgi.rr_people import RedditHandler, cmp_by_created_utc
from wsgi.rr_people import re_url, normalize, S_WORK, S_SLEEP, re_crying_chars
from wsgi.rr_people.queue import ProductionQueue

log = logging.getLogger("reader")


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


class CommentsStorage(DBHandler):
    def __init__(self, name="?"):
        super(CommentsStorage, self).__init__(name=name, uri=comments_mongo_uri, db_name=comments_db_name)
        self.comments = self.db.get_collection("comments")
        if not self.comments:
            self.comments = self.db.create_collection(
                    "comments",
                    capped=True,
                    size=1024 * 1024 * 256,
            )
            self.comments.drop_indexes()

            self.comments.create_index([("fullname", 1)], unique=True)
            self.comments.create_index([("commented", 1)], sparse=True)
            self.comments.create_index([("ready_for_comment", 1)], sparse=True)
            self.comments.create_index([("ready_for_post", 1)], sparse=True)

            self.comments.create_index("low_copies", expireAfterSeconds=expire_low_copies_posts, sparse=True)
            self.comments.create_index([("text_hash", 1)], sparse=True)

    def set_post_commented(self, post_fullname, by, hash):
        found = self.comments.find_one({"fullname": post_fullname, "commented": {"$exists": False}})
        if not found:
            to_add = {"fullname": post_fullname, "commented": True, "time": time.time(), "text_hash": hash, "by": by}
            self.comments.insert_one(to_add)
        else:
            to_set = {"commented": True, "text_hash": hash, "by": by, "time": time.time(),
                      "low_copies": datetime.utcnow()}
            self.comments.update_one({"fullname": post_fullname}, {"$set": to_set})

    def can_comment_post(self, who, post_fullname, hash):
        q = {"by": who, "commented": True, "$or": [{"fullname": post_fullname}, {"text_hash": hash}]}
        found = self.comments.find_one(q)
        return found is None

    def set_post_ready_for_comment(self, post_fullname):
        found = self.comments.find_one({"fullname": post_fullname})
        if found and found.get("commented"):
            return
        elif found:
            return self.comments.update_one(found,
                                            {"$set": {"ready_for_comment": True},
                                             "$unset": {"low_copies": datetime.utcnow()}})
        else:
            return self.comments.insert_one({"fullname": post_fullname, "ready_for_comment": True})

    def get_posts_ready_for_comment(self):
        return list(self.comments.find({"ready_for_comment": True, "commented": {"$exists": False}}))

    def get_post(self, post_fullname):
        found = self.comments.find_one({"fullname": post_fullname})
        return found

    def is_can_see_post(self, fullname):
        """
        Можем посмотреть пост только если у него было мало копий давно.
        Или же поста нет в бд.
        :param fullname:
        :return:
        """
        found = self.comments.find_one({"fullname": fullname})
        if found:
            if (datetime.utcnow() - found.get("low_copies",
                                              datetime.utcnow())).total_seconds() > TIME_TO_WAIT_NEW_COPIES:
                self.comments.remove(found)
                return True
            return False
        return True

    def is_post_commented(self, post_fullname):
        found = self.comments.find_one({"fullname": post_fullname})
        if found:
            return found.get("commented") or False
        return False

    def get_posts_commented(self, by=None):
        q = {"commented": True}
        if by:
            q["by"] = by
        return list(self.comments.find(q))

    def set_post_low_copies(self, post_fullname):
        found = self.comments.find_one({"fullname": post_fullname})
        if not found:
            self.comments.insert_one(
                    {"fullname": post_fullname, "low_copies": datetime.utcnow(), "time": time.time()})
        else:
            self.comments.update_one({"fullname": post_fullname},
                                     {'$set': {"low_copies": datetime.utcnow(), "time": time.time()}})


class CommentSearcher(RedditHandler):
    def __init__(self, user_agent=None, add_authors=False):
        """
        :param user_agent: for reddit non auth and non oauth client
        :param lcp: low copies posts if persisted
        :param cp:  commented posts if persisted
        :return:
        """
        super(CommentSearcher, self).__init__(user_agent)
        self.db = CommentsStorage(name="comment searcher")
        self.comment_queue = ProductionQueue(name="comment searcher")
        self.subs = {}

        self.add_authors = add_authors
        if self.add_authors:
            from wsgi.rr_people.ae import ActionGeneratorDataFormer
            self.agdf = ActionGeneratorDataFormer()

        self.start_supply_comments()
        log.info("Read human inited!")

    def comment_retrieve_iteration(self, sub, sleep=True):
        self.comment_queue.set_comment_founder_state(sub, S_WORK)
        start = time.time()
        log.info("Will start find comments for [%s]" % (sub))
        for pfn, ct in self.find_comment(sub):
            self.comment_queue.put_comment(sub, pfn, ct)
        end = time.time()
        sleep_time = random.randint(DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA / 5,
                                    DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA)
        self.comment_queue.set_comment_founder_state(sub, S_SLEEP, ex=sleep_time + 1)
        if sleep:
            log.info(
                    "Was get all comments which found for [%s] at %s seconds... Will trying next after %s" % (
                        sub, end - start, sleep_time))
            time.sleep(sleep_time)

    def start_find_comments(self, sub):
        if sub in self.subs and self.subs[sub].is_alive():
            return

        def f():
            while 1:
                self.comment_retrieve_iteration(sub)

        ps = Process(name="[%s] comment founder" % sub, target=f)
        ps.start()
        self.subs[sub] = ps

    def start_supply_comments(self):
        log.info("start supplying comments")

        def f():
            for message in self.comment_queue.get_who_needs_comments():
                nc_sub = message.get("data")
                log.info("receive need comments for sub [%s]" % nc_sub)
                founder_state = self.comment_queue.get_comment_founder_state(nc_sub)
                if not founder_state or founder_state is S_SLEEP:
                    log.info("will forced start found comments for [%s]" % (nc_sub))
                    self.comment_retrieve_iteration(nc_sub, sleep=False)

        process = Process(name="comment supplier", target=f)
        process.daemon = True
        process.start()

    def find_comment(self, at_subreddit,
                     add_authors=False):  # todo вынести загрузку всех постов в отдельную хуйню чтоб не делать это много раз
        subreddit = at_subreddit
        all_posts = self.get_hot_and_new(subreddit, sort=cmp_by_created_utc)
        self.comment_queue.set_comment_founder_state(subreddit, "%s found %s" % (S_WORK, len(all_posts)),
                                                     ex=len(all_posts) * 2)
        for post in all_posts:
            if self.db.is_can_see_post(post.fullname):
                try:
                    copies = self.get_post_copies(post)
                    copies = filter(
                            lambda copy: _so_long(copy.created_utc, min_comment_create_time_difference) and \
                                         copy.num_comments > min_donor_num_comments,
                            copies)
                    if len(copies) >= min_copy_count:
                        copies.sort(cmp=cmp_by_created_utc)
                        comment = None
                        for copy in copies:
                            if copy.subreddit != post.subreddit and copy.fullname != post.fullname:
                                comment = self._retrieve_interested_comment(copy, post)
                                if comment:
                                    log.info("Find comment: [%s] in post: [%s] at subreddit: [%s]" % (
                                        comment, post.fullname, subreddit))
                                    break

                        if comment and self.db.set_post_ready_for_comment(post.fullname):
                            yield post.fullname, comment.body
                    else:
                        self.db.set_post_low_copies(post.fullname)
                except Exception as e:
                    log.exception(e)

            if add_authors or self.add_authors:
                self.agdf.add_author_data(post.author.name)

    def get_post_copies(self, post):
        search_request = "url:\'%s\'" % post.url
        copies = list(self.reddit.search(search_request))
        return list(copies)

    def _retrieve_interested_comment(self, copy, post):
        # prepare comments from donor to selection
        comments = self.retrieve_comments(copy.comments, copy.fullname)
        after = len(comments) / shift_copy_comments_part
        for i in range(after, len(comments)):
            comment = comments[i]
            if comment.ups >= min_donor_comment_ups and \
                            comment.ups <= max_donor_comment_ups and \
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


if __name__ == '__main__':
    queue = ProductionQueue()
    db = HumanStorage()
    cs = CommentSearcher(db)
    time.sleep(5)
    queue.need_comment("videos")
