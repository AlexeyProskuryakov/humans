# coding=utf-8
import logging
import random
import time
import traceback
from Queue import Empty
from multiprocessing.process import Process
from multiprocessing.synchronize import Lock
from threading import Thread

import praw
import requests
import requests.auth
from praw.objects import MoreComments

from wsgi import properties
from wsgi.db import HumanStorage
from wsgi.rr_people import USER_AGENTS, \
    A_CONSUME, A_VOTE, A_COMMENT, A_POST, A_SUBSCRIBE, A_FRIEND, \
    S_UNKNOWN, S_SLEEP, S_WORK, S_BAN, Man, re_url, S_SUSPEND, Singleton, info_words_hash, normalize_comment
from wsgi.rr_people.reader import CommentSearcher, CommentQueue

log = logging.getLogger("he")


def net_tryings(fn):
    def wrapped(*args, **kwargs):
        count = 0
        while 1:
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as e:
                log.exception(e)
                log.warning("can not load data for [%s]\n args: %s, kwargs: %s \n because %s" % (fn, args, kwargs, e))
                if count >= properties.tryings_count:
                    raise e
                time.sleep(properties.step_time_after_trying)
                count += 1

    return wrapped


@net_tryings
def check_any_login(login):
    res = requests.get(
            "http://www.reddit.com/user/%s/about.json" % login,
            headers={"origin": "http://www.reddit.com",
                     "User-Agent": random.choice(USER_AGENTS)})
    if res.status_code != 200:
        return False
    if res.json().get("error", None):
        return False
    return True


def _get_random_near(slice, index, max):
    slice_indices = map(lambda x: x[0], enumerate(slice))
    r_count = random.randint(max / 2, max)
    l_count = random.randint(max / 2, max)

    temp_r = set()
    for _ in slice_indices[index:]:
        r_id = random.randint(index + 1, slice_indices[-1])
        temp_r.add(r_id)
        if len(temp_r) >= r_count:
            break
    res_r = [slice[i] for i in temp_r]

    temp_l = set()
    for _ in slice_indices[:index]:
        l_id = random.randint(0, index - 1)
        temp_l.add(l_id)
        if len(temp_l) >= l_count:
            break
    res_l = [slice[i] for i in temp_l]
    return res_l, res_r


class HumanConfiguration(object):
    def __init__(self, data=None):
        """
        Configuration of rr_people live
        :return:
        """
        if not data:
            self.subscribe = 95
            self.author_friend = 95
            self.comments = 75
            self.comment_vote = 85
            self.comment_friend = 95
            self.comment_url = 85
            self.post_vote = 65

            self.comment_mwt = 5
            self.max_wait_time = 30

            self.max_posts_near_commented = 50

        elif isinstance(data, dict):
            for k, v in data.iteritems():
                self.__dict__[k] = int(v)

    def set(self, conf_name, conf_val):
        if conf_name in self.__dict__:
            self.__dict__[conf_name] = conf_val

    @property
    def data(self):
        return self.__dict__


class Consumer(Man):
    def __init__(self, db, login):
        """
        :param subreddits: subbreddits which this rr_people will comment
        :param login_credentials:  dict object with this attributes: client_id, client_secret, redirect_url, access_token, refresh_token, login and password of user and user_agent 
         user agent can not present it will use some default user agent
        :return:
        """
        super(Consumer, self).__init__()
        self.lock = Lock()

        self.db = db

        state = db.get_human_config(login)
        login_credentials = db.get_human_access_credentials(login)
        if not login_credentials:
            raise Exception("Can not have login credentials at %s", login)
        self.subscribed_subreddits = set(state.get("ss", [])) or set()
        self.friends = set(state.get("frds", [])) or set()

        self.init_engine(login_credentials)
        self.init_work_cycle()

        self.used = set()
        live_config = state.get("live_config")
        if not live_config:
            self.configuration = HumanConfiguration()
            self.db.set_human_live_configuration(login, self.configuration)
        else:
            self.configuration = HumanConfiguration(live_config)

        log.info("Write human [%s] inited with credentials \n%s"
                 "\nConfiguration: \n%s"
                 "\nFriends: %s"
                 "\nSubscribed breddits:%s" % (login,
                                               "\n".join(["%s:\t%s" % (k, v) for k, v in
                                                          login_credentials.get("info", {}).iteritems()]),
                                               "\n".join(["%s:\t%s" % (k, v) for k, v in
                                                          self.configuration.data.iteritems()]),
                                               self.friends,
                                               self.subscribed_subreddits
                                               ))

    def init_engine(self, login_credentials):

        self.user_agent = login_credentials.get("user_agent", random.choice(USER_AGENTS))
        self.user_name = login_credentials["user"]

        r = praw.Reddit(self.user_agent)

        r.set_oauth_app_info(login_credentials['client_id'], login_credentials['client_secret'],
                             login_credentials['redirect_uri'])
        r.set_access_credentials(**login_credentials.get("info"))
        r.login(login_credentials["user"], login_credentials["pwd"], disable_warning=True)

        self.access_information = login_credentials.get("info")
        self.login_credentials = {"user": self.user_name, "pwd": login_credentials["pwd"]}
        self.reddit = r
        self.refresh_token()

    def refresh_token(self):
        self.access_information = self.reddit.refresh_access_information(self.access_information['refresh_token'])
        self.db.update_human_access_credentials_info(self.user_name, self.access_information)
        self.reddit.login(self.login_credentials["user"], self.login_credentials["pwd"], disable_warning=True)

    def incr_counter(self, name):
        self.counters[name] += 1

    @property
    def action_function_params(self):
        return self.__action_function_params

    @action_function_params.setter
    def action_function_params(self, val):
        self.__action_function_params = val
        self.counters = {A_CONSUME: 0, A_VOTE: 0, A_COMMENT: 0, A_POST: 0}

    def init_work_cycle(self):
        consuming = random.randint(properties.min_consuming, properties.max_consuming)
        production = 100 - consuming

        prod_voting = random.randint(properties.min_voting, properties.max_voting)
        prod_commenting = 100 - prod_voting

        production_voting = (prod_voting * production) / 100
        production_commenting = (prod_commenting * production) / 100

        self.action_function_params = {A_CONSUME: consuming,
                                       A_VOTE: production_voting,
                                       A_COMMENT: production_commenting}
        log.info("MY [%s] WORK CYCLE: %s" % (self.user_name, self.action_function_params))
        return self.action_function_params

    def can_do(self, action):
        """
        Action
        :param action: can be: [vote, comment, consume]
        :return:  true or false
        """
        summ = sum(self.counters.values())
        action_count = self.counters[action]
        granted_perc = self.action_function_params.get(action)
        current_perc = int((float(action_count) / (summ if summ else 100)) * 100)

        return current_perc <= granted_perc

    def must_do(self, action):
        # result = reduce(lambda r, a: r and not self.can_do(a),
        #                 [a for a in self.action_function_params.keys() if a != action],
        #                 True)
        result = True
        for another_action in self.action_function_params.keys():
            if another_action == action:
                continue
            result = result and not self.can_do(another_action)
        return result

    def _is_want_to(self, coefficient):
        return coefficient >= 0 and random.randint(0, properties.want_coefficient_max) >= coefficient

    def register_step(self, step_type, info=None):
        if step_type in self.counters:
            self.incr_counter(step_type)

        self.db.save_log_human_row(self.user_name, step_type, info or {})
        self.persist_state()
        log.info("step by [%s] |%s|: %s", self.user_name, step_type, info)

        if info and info.get("fullname"):
            self.used.add(info.get("fullname"))

    @property
    def state(self):
        return {"ss": list(self.subscribed_subreddits),
                "frds": list(self.friends)}

    def persist_state(self):
        self.db.update_human_internal_state(self.user_name, state=self.state)

    def do_see_post(self, post):
        """
        1) go to his url with yours useragent, wait random
        2) random check comments and random check more comments
        3) random go to link in comments
        #todo refactor action want to normal function
        :param post:
        :return:
        """
        try:
            res = requests.get(post.url, headers={"User-Agent": self.user_agent})
            self.register_step(A_CONSUME,
                               info={"url": post.url, "permalink": post.permalink, "fullname": post.fullname})
        except Exception as e:
            log.warning("Can not see post %s url %s \n EXCEPT [%s] \n %s" % (
                post.fullname, post.url, e, traceback.format_exc()))

        wt = self.wait(self.configuration.max_wait_time)

        if self._is_want_to(self.configuration.post_vote) and self.can_do("vote"):
            post_vote_count = random.choice([1, -1])
            try:
                post.vote(post_vote_count)
            except Exception as e:
                log.error(e)
            self.register_step(A_VOTE, info={"fullname": post.fullname, "vote": post_vote_count})
            self.wait(self.configuration.max_wait_time / 2)

        if self._is_want_to(self.configuration.comments) and wt > self.configuration.comment_mwt:  # go to post comments
            for comment in post.comments:
                if self._is_want_to(self.configuration.comment_vote) and self.can_do("vote"):  # voting comment
                    vote_count = random.choice([1, -1])
                    try:
                        comment.vote(vote_count)
                    except Exception as e:
                        log.error(e)
                    self.register_step(A_VOTE, info={"fullname": comment.fullname, "vote": vote_count})
                    self.wait(self.configuration.max_wait_time / 10)
                    if self._is_want_to(
                            self.configuration.comment_friend) and vote_count > 0 and comment.author.name not in self.friends:  # friend comment author
                        c_author = comment.author
                        if c_author.name not in self.friends:
                            try:
                                c_author.friend()
                            except Exception as e:
                                log.error(e)
                            self.friends.add(c_author.name)
                            self.register_step(A_FRIEND, info={"friend": c_author.name, "from": "comment"})
                            log.info("%s was add friend from comment %s because want coefficient is: %s",
                                     (self.user_name, comment.fullname, self.configuration.comment_friend))
                            self.wait(self.configuration.max_wait_time / 10)

                if self._is_want_to(self.configuration.comment_url):  # go to url in comment
                    if isinstance(comment, MoreComments):
                        comments = self.retrieve_comments(comment.comments(), comment.fullname, [])
                        if comments:
                            comment = random.choice(comments)
                        else:
                            continue
                    urls = re_url.findall(comment.body)
                    for url in urls:
                        try:
                            res = requests.get(url, headers={"User-Agent": self.user_agent})
                            log.info("%s was consume comment url: %s" % (self.user_name, res.url))
                        except Exception as e:
                            pass
                    if urls:
                        self.register_step(A_CONSUME, info={"urls": urls})

            self.wait(self.configuration.max_wait_time / 5)

        if self._is_want_to(
                self.configuration.subscribe) and post.subreddit.display_name not in self.subscribed_subreddits:  # subscribe sbrdt
            try:
                self.reddit.subscribe(post.subreddit.display_name)
            except Exception as e:
                log.error(e)
            self.subscribed_subreddits.add(post.subreddit.display_name)
            self.register_step(A_SUBSCRIBE, info={"sub": post.subreddit.display_name})
            self.wait(self.configuration.max_wait_time / 5)

        if self._is_want_to(
                self.configuration.author_friend) and post.author.name not in self.friends:  # friend post author
            try:
                post.author.friend()
            except Exception as e:
                log.error(e)
                log.error(self.reddit)

            self.friends.add(post.author.name)
            self.register_step(A_FRIEND, info={"fullname": post.author.name, "from": "post"})
            log.info("%s was add friend from post %s because want coefficient is: %s" % (
                self.user_name, post.fullname, self.configuration.author_friend))
            self.wait(self.configuration.max_wait_time / 5)

    def set_configuration(self, configuration):
        self.configuration = configuration
        log.info("For %s configuration is setted: %s" % (self.user_name, configuration.data))

    def wait(self, max_wait_time):
        if max_wait_time > 1:
            wt = random.randint(1, max_wait_time)
            time.sleep(wt)
            return wt
        return max_wait_time

    def do_comment_post(self, post_fullname, subreddit_name, comment_text):
        log.info("[%s] will do comment post [%s] (%s) by this text:\n%s" % (
            self.user_name, post_fullname, subreddit_name, comment_text))

        near_posts = self.get_hot_and_new(subreddit_name)
        for i, _post in enumerate(near_posts):
            if _post.fullname == post_fullname:
                see_left, see_right = _get_random_near(near_posts, i, self.configuration.max_posts_near_commented)
                try:
                    for p_ind in see_left:
                        self.do_see_post(p_ind)
                except Exception as e:
                    log.error(e)

                try:
                    for comment in filter(lambda comment: isinstance(comment, MoreComments), _post.comments):
                        comment.comments()
                        if random.randint(0, 10) > 6:
                            break
                except Exception as e:
                    log.error(e)

                try:
                    if self.db.can_comment_post(self.user_name, post_fullname=_post.fullname) and \
                            self.db.can_comment_post(self.user_name, hash=hash(normalize_comment(comment_text))):
                        response = _post.add_comment(comment_text)
                        self.db.set_post_commented(_post.fullname, by=self.user_name,
                                                   info=dict(info_words_hash(comment_text), **{"text": comment_text}))
                        self.register_step(A_COMMENT,
                                           info={"fullname": post_fullname, "text": comment_text,
                                                 "sub": subreddit_name})
                        log.info("[%s] Was comment post [%s] by: [%s] with response: %s" % (
                            self.user_name, _post.fullname, comment_text, response))
                except Exception as e:
                    log.error(e)

                try:
                    for p_ind in see_right:
                        self.do_see_post(p_ind)
                except Exception as e:
                    log.error(e)

        try:
            if self._is_want_to(
                    self.configuration.subscribe) and subreddit_name not in self.subscribed_subreddits:
                self.reddit.subscribe(subreddit_name)
                self.register_step(A_SUBSCRIBE, info={"sub": subreddit_name})
        except Exception as e:
            log.error(e)

    def live_random(self, max_iters=2000, max_actions=100, posts_limit=500, **kwargs):
        sub_posts = {}
        counter = 0
        subs = self.db.get_human_subs(self.user_name)
        if not subs:
            log.error("For %s not any subs at config :(", self.user_name)
            return

        for x in xrange(max_iters):
            random_sub = random.choice(subs)
            if random_sub not in sub_posts:
                sbrdt = self.reddit.get_subreddit(random_sub)
                hot_posts = list(sbrdt.get_hot(limit=posts_limit))
                sub_posts[random_sub] = hot_posts
            else:
                hot_posts = sub_posts[random_sub]

            post = random.choice(hot_posts)
            if post.fullname not in self.used and self._is_want_to(7):
                self.do_see_post(post)
                counter += 1
            if random.randint(0, max_actions) < counter:
                break


class Kapellmeister(Process):
    def __init__(self, name, db, read_human):
        super(Kapellmeister, self).__init__()
        self.db = db
        self.human_name = name
        self.name = name

        self.w_human = Consumer(db, login=name)
        self.r_human = read_human
        self.state = S_UNKNOWN

        self.lock = Lock()
        self.comment_queue = CommentQueue()
        log.info("human kapellmeister inited.")

    def set_config(self, data):
        with self.lock:
            human_config = HumanConfiguration(data)
            self.w_human.set_configuration(human_config)

    def human_check(self):
        ok = check_any_login(self.human_name)
        if not ok:
            self.db.set_human_live_state(self.human_name, S_BAN, self.pid)
        return ok

    def set_state(self, new_state):
        state = self.db.get_human_live_state(self.human_name)
        if state == S_SUSPEND:
            return False
        else:
            self.db.set_human_live_state(self.human_name, new_state, self.pid)
            return True

    def run(self):
        while 1:
            try:
                if not self.human_check():
                    return

                if not self.set_state(S_WORK):
                    return

                for sub in self.db.get_human_subs(self.human_name):
                    self.r_human.start_retrieve_comments(sub)
                    try:
                        to_comment_info = self.comment_queue.get(sub)
                        if to_comment_info:
                            post, text = to_comment_info
                            self.w_human.do_comment_post(post, sub, text)
                    except Empty as e:
                        log.info(
                                "%s can not comment at %s because they no found at this moment" % (
                                self.human_name, sub))

                    except Exception as e:
                        log.info("%s can not comment at %s" % (self.human_name, sub))
                        log.exception(e)

                    if not self.set_state(S_WORK):
                        return

                    self.w_human.live_random(posts_limit=150)

                sleep_time = random.randint(1, self.r_human.configuration.max_wait_time * 100)
                log.info("human [%s] will sleep %s seconds" % (self.human_name, sleep_time))

                if not self.set_state(S_SLEEP):
                    return

                time.sleep(sleep_time)
                self.w_human.refresh_token()
            except Exception as e:
                log.exception(e)


class HumanOrchestra():
    __metaclass__ = Singleton

    def __init__(self):
        self.__humans = {}
        self.read_human = CommentSearcher(HumanStorage())
        self.lock = Lock()
        self.db = HumanStorage()
        Thread(target=self.start_humans, name="Orchestra Human Starter").start()

    def start_humans(self):
        log.info("Will auto start humans")
        for human in self.db.get_humans_available():
            self.add_human(human.get("user"))

    @property
    def humans(self):
        with self.lock:
            return self.__humans

    def add_human(self, human_name):
        with self.lock:
            try:
                human = Kapellmeister(human_name, HumanStorage(), self.read_human)
                self.__humans[human_name] = human
                human.start()
            except Exception as e:
                log.info("Error at starting human %s", human_name, )
                log.exception(e)

    def toggle_human_config(self, human_name):
        with self.lock:
            if human_name in self.__humans:
                def f():
                    db = HumanStorage()
                    human_config = db.get_human_live_configuration(human_name)
                    self.__humans[human_name].set_config(human_config)

                Process(name="config updater", target=f).start()


if __name__ == '__main__':
    l, r = _get_random_near(["a", "b", "c", "d", "e", "f", "g", "h", "i"], 5, 4)
    print l
    print r
