import logging
import random
import time
import traceback
from collections import defaultdict

import praw
import requests
from praw import Reddit
from praw.objects import MoreComments, Submission
from requests.exceptions import ConnectionError

from wsgi import properties
from wsgi.db import HumanStorage
from wsgi.properties import WEEK
from wsgi.rr_people import RedditHandler, USER_AGENTS, A_CONSUME, A_VOTE, A_COMMENT, A_POST, A_SUBSCRIBE, A_FRIEND, \
    re_url, cmp_by_created_utc
from wsgi.rr_people.commenting.connection import CommentHandler, CS_COMMENTED
from wsgi.rr_people.posting.posts import PS_POSTED, PS_ERROR, PS_NO_POSTS, PostsStorage, PostSource, PostsBalancer

log = logging.getLogger("consumer")

LIVE_RANDOM_SUB_DATA_REFRESH_TIME = 3600 * 2


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


def _wait_time_to_write(text):
    time_to_write = int(len(text) / random.randint(2, 4))
    log.info("will posting and write post on %s seconds" % time_to_write)
    time.sleep(time_to_write)


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

    def __repr__(self):
        return "\n".join(["%s: %s" % (k, v) for k, v in self.data.iteritems()])


class Human(RedditHandler):
    def __init__(self, login, db=None, reddit=None, reddit_class=Reddit):
        super(Human, self).__init__(reddit=reddit)
        self.reddit_class = reddit_class
        self.login = login
        self.db = db or HumanStorage(name="consumer %s" % login)
        login_credentials = self.db.get_human_access_credentials(login)
        if not login_credentials:
            raise Exception("Can not have login credentials at %s", login)

        self.comments_handler = CommentHandler(name="consumer %s" % login)
        self.posts = PostsBalancer(self.login)

        human_configuration = self.db.get_human_config(login)
        self._load_configuration(human_configuration)
        self.subscribed_subreddits = set(human_configuration.get("ss", [])) or set()
        self.friends = set(human_configuration.get("frds", [])) or set()
        self.last_friend_add = human_configuration.get("last_friend_add") or time.time() - WEEK

        self.reload_counters()

        self.init_engine(login_credentials)
        log.info("MY [%s] WORK CYCLE: %s" % (self.name, self.counters_thresholds))

        # todo this cache must be persisted at mongo or another
        self._used = set()
        self.cache_last_loads = {}
        self.cache_sub_posts = {}
        self._last_post_ids = defaultdict(int)

        log.info("Human [%s] inited with credentials \n%s"
                 "\nConfiguration: \n%s"
                 "\nFriends: %s"
                 "\nSubscribed breddits:%s" % (login,
                                               "\t\n".join(["%s:\t%s" % (k, v) for k, v in
                                                            login_credentials.get("info", {}).iteritems()]),
                                               "\t\n".join(["%s:\t%s" % (k, v) for k, v in
                                                            self.configuration.data.iteritems()]),
                                               self.friends,
                                               self.subscribed_subreddits
                                               ))

    def _load_configuration(self, loaded=None):
        human_configuration = loaded or self.db.get_human_config(self.login, projection={"live_config": True})
        live_config = human_configuration.get("live_config")
        if not live_config:
            self.configuration = HumanConfiguration()
            self.db.set_human_live_configuration(self.login, self.configuration)
        else:
            self.configuration = HumanConfiguration(live_config)

    def init_engine(self, login_credentials):
        self.user_agent = login_credentials.get("user_agent", random.choice(USER_AGENTS))
        self.name = login_credentials["user"]

        r = self.reddit_class(self.user_agent)

        r.set_oauth_app_info(login_credentials['client_id'], login_credentials['client_secret'],
                             login_credentials['redirect_uri'])
        r.set_access_credentials(**login_credentials.get("info"))
        r.login(login_credentials["user"], login_credentials["pwd"], disable_warning=True)

        self.access_information = login_credentials.get("info")
        self.login_credentials = {"user": self.name, "pwd": login_credentials["pwd"]}
        self.reddit = r

        self.refresh_token()

    def refresh_token(self):
        self.access_information = self.reddit.refresh_access_information(self.access_information['refresh_token'])
        self.db.update_human_access_credentials_info(self.name, self.access_information)
        self.reddit.login(self.login_credentials["user"], self.login_credentials["pwd"], disable_warning=True)

    def reload_counters(self):
        self.counters_thresholds = self.calculate_counters()
        self.db.update_human_internal_state(self.login, state=self.state)

    def incr_counter(self, name):
        self.counters[name] += 1

    def decr_counter(self, name, by=1):
        self.counters[name] -= by

    @property
    def counters_thresholds(self):
        return self._counters_thresholds

    @counters_thresholds.setter
    def counters_thresholds(self, val):
        self._counters_thresholds = val
        self.counters = {A_CONSUME: 0, A_VOTE: 0, A_COMMENT: 0, A_POST: 0}

    def calculate_counters(self):
        cth = self.db.get_human_counters_thresholds_min_max(self.login) or properties.default_counters_thresholds
        consuming = random.randint(cth.get(A_CONSUME).get('min'), cth.get(A_CONSUME).get('max'))
        production_piece = 100. - consuming

        prod_voting = random.randint(cth.get(A_VOTE).get('min'), cth.get(A_VOTE).get('max'))
        voting = (prod_voting * production_piece) / 100.
        comment_post_piece = production_piece - voting

        prod_commenting = random.randint(cth.get(A_COMMENT).get('min'), cth.get(A_COMMENT).get('max'))
        commenting = (prod_commenting * comment_post_piece) / 100.
        posting = comment_post_piece - commenting

        thresholds = {A_CONSUME: consuming,
                      A_VOTE: voting,
                      A_COMMENT: commenting,
                      A_POST: posting
                      }

        return thresholds

    def can_do(self, action):
        """
        Action
        :param action: can be: [vote, comment, consume, post]
        :return:  true or false
        """
        summ = sum(self.counters.values())
        action_count = self.counters[action]
        granted_perc = self.counters_thresholds.get(action)
        current_perc = (float(action_count) / (summ if summ else 100)) * 100

        return current_perc <= granted_perc

    def must_do(self, action):
        result = True
        for another_action in self.counters_thresholds.keys():
            if another_action == action:
                continue
            result = result and not self.can_do(another_action)
        return result

    def _is_want_to(self, coefficient):
        return coefficient >= 0 and random.randint(0, properties.want_coefficient_max) >= coefficient

    def register_step(self, step_type, info=None):
        if step_type in self.counters:
            self.incr_counter(step_type)

        if step_type == A_FRIEND:
            self.last_friend_add = time.time()

        if step_type != A_CONSUME:
            self.db.save_log_human_row(self.name, step_type, info or {})
        else:
            self.db.add_to_statistic(self.name, A_CONSUME, 1)

        self.db.update_human_internal_state(self.name, state=self.state)
        log.info("step by [%s] |%s|: %s", self.name, step_type, info)

        if info and info.get("fullname"):
            self._used.add(info.get("fullname"))

    def get_actions_percent(self, counters):
        summ = sum(counters.values())
        result = {}
        for action, count in counters.items():
            current_perc = (float(count) / (summ if summ else 100)) * 100
            result[action] = current_perc
        return result

    @property
    def state(self):
        return {"ss": list(self.subscribed_subreddits),
                "frds": list(self.friends),
                "last_friend_add": self.last_friend_add,
                "counters": {
                    "counters": self.counters,
                    "percents": self.get_actions_percent(self.counters),
                    "threshold": self.counters_thresholds,
                }
                }

    def can_friendship_create(self, friend_name):
        return friend_name not in self.friends and time.time() - self.last_friend_add > random.randint(WEEK / 5, WEEK)

    def get_comment_in_more(self, comment):
        if isinstance(comment, MoreComments):
            try:
                time.sleep(1)
                comments = comment.comments()
                comment_ = random.choice(comments)
                return comment_
            except Exception as e:
                log.error("Can not get comments in more comment %s" % e)
                return

        return comment

    def get_comments_in_post(self, post):
        try:
            time.sleep(1)
            comments = post.comments
            return comments
        except Exception as e:
            log.error("Can not get comments in post %s" % e)
            return

    def do_see_post(self, post):
        """
        1) go to his url with yours useragent, wait random
        2) random check comments and random check more comments
        3) random go to link in comments
        #todo friend five in week
        :param post:
        :return:
        """
        self._load_configuration()
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
                self.register_step(A_VOTE, info={"fullname": post.fullname, "vote": post_vote_count})
            except Exception as e:
                log.exception(e)

            self.wait(self.configuration.max_wait_time / 2)

        if self._is_want_to(self.configuration.comments) and wt > self.configuration.comment_mwt:  # go to post comments
            comments = self.get_comments_in_post(post)
            if not comments: return

            for comment in comments:
                if self._is_want_to(self.configuration.comment_vote) and self.can_do("vote"):  # voting comment
                    comment = self.get_comment_in_more(comment)
                    if not comment: return
                    vote_count = random.choice([1, -1])
                    try:
                        comment.vote(vote_count)
                        self.register_step(A_VOTE, info={"fullname": comment.fullname, "vote": vote_count})
                        self.wait(self.configuration.max_wait_time / 10)
                    except Exception as e:
                        log.exception(e)

                    if self._is_want_to(self.configuration.comment_friend) and \
                                    vote_count > 0 and \
                            self.can_friendship_create(comment.author.name):  # friend comment author
                        try:
                            c_author = comment.author
                            c_author.friend()
                            self.friends.add(c_author.name)
                            self.register_step(A_FRIEND, info={"friend": c_author.name, "from": "comment"})
                            log.info("%s was add friend from comment %s because want coefficient is: %s",
                                     (self.name, comment.fullname, self.configuration.comment_friend))
                            self.wait(self.configuration.max_wait_time / 10)
                        except Exception as e:
                            log.exception(e)

                if self._is_want_to(self.configuration.comment_url):  # go to url in comment
                    if isinstance(comment, MoreComments):
                        continue

                    urls = re_url.findall(comment.body)
                    if urls:
                        url = random.choice(urls)
                        try:
                            res = requests.get(url, headers={"User-Agent": self.user_agent})
                            self.register_step(A_CONSUME, info={"url": url})
                        except Exception as e:
                            pass

            self.wait(self.configuration.max_wait_time / 5)

        if self._is_want_to(self.configuration.subscribe) and \
                        post.subreddit.display_name not in self.subscribed_subreddits:  # subscribe sbrdt
            try:
                self.reddit.subscribe(post.subreddit.display_name)
                self.subscribed_subreddits.add(post.subreddit.display_name)
                self.register_step(A_SUBSCRIBE, info={"sub": post.subreddit.display_name})
                self.wait(self.configuration.max_wait_time / 5)
            except Exception as e:
                log.exception(e)

        if self._is_want_to(self.configuration.author_friend) and \
                self.can_friendship_create(post.author.name):  # friend post author
            try:
                post.author.friend()
                self.friends.add(post.author.name)
                self.register_step(A_FRIEND, info={"fullname": post.author.name, "from": "post"})
                log.info("%s was add friend from post %s because want coefficient is: %s" % (
                    self.name, post.fullname, self.configuration.author_friend))
                self.wait(self.configuration.max_wait_time / 5)
            except Exception as e:
                log.exception(e)

    def wait(self, max_wait_time):
        if max_wait_time > 1:
            wt = random.randint(1, max_wait_time)
            time.sleep(wt)
            return wt
        return max_wait_time

    def do_comment_post(self, sub=None):
        if not sub:
            human_subs = self.db.get_subs_of_human(self.login)
            _sub = self.comments_handler.get_sub_with_comments(human_subs) or random.choice(human_subs)
        else:
            _sub = sub
        log.info("[%s] will commenting in %s" % (self.login, _sub))

        comment_id = self.comments_handler.pop_comment_id(_sub)
        log.info("[%s] comment id: %s" % (self.login, comment_id))
        if not comment_id:
            log.info("[%s] need comment for %s" % (self.login, _sub))
            self.comments_handler.need_comment(_sub)
        else:
            log.info("[%s] comment: %s" % (self.login, comment_id))
            result = self._humanised_comment_post(_sub, comment_id)
            log.info("[%s] comment result: %s" % (self.login, result))
            return result

    def _humanised_comment_post(self, sub, comment_id):
        post_fullname = self.comments_handler.get_comment_post_fullname(comment_id)
        hot_and_new = self.load_hot_and_new(sub, sort=cmp_by_created_utc)
        # check if post fullname is too old
        all_posts_fns = set(map(lambda x: x.fullname, hot_and_new))
        if post_fullname not in all_posts_fns:
            log.info("post [%s] for comment is too old and not present at hot or new" % post_fullname)
            try:
                post = self.reddit.get_submission(submission_id=post_fullname[3:],
                                                  # because submission id must be without prefix
                                                  comment_limit=None)
                if post:
                    comment_result = self._comment_post(post, comment_id, sub)
                    if comment_result:
                        return A_COMMENT
                    return PS_ERROR

            except Exception as e:
                log.warning("can not getting submission [%s %s], because: %s" % (comment_id, post_fullname, e.message))
                log.exception(e)
                return PS_ERROR
        else:
            log.info("post [%s] for comment is present at hot and new and will posting")
            self._load_configuration()
            for i, _post in enumerate(hot_and_new):
                if _post.fullname == post_fullname:
                    see_left, see_right = _get_random_near(hot_and_new, i, self.configuration.max_posts_near_commented)
                    self._see_near_posts(see_left)
                    self._see_comments(_post)
                    comment_result = self._comment_post(_post, comment_id, sub)
                    if comment_result:
                        self._see_near_posts(see_right)
                        return A_COMMENT
                    return PS_ERROR

    def _see_comments(self, post):
        comments = self.get_comments_in_post(post)
        if not comments: return
        for comment in comments:
            comment = self.get_comment_in_more(comment)
            if not comment: return
            if random.randint(0, 10) > 6:
                return

    def _comment_post(self, _post, comment_oid, sub):
        comment = self.comments_handler.start_comment_post(comment_oid)
        text = comment.get("text")
        _wait_time_to_write(text)
        try:
            result = _post.add_comment(text)
            self.comments_handler.end_comment_post(comment_oid, self.name)
            self.register_step(A_COMMENT, {"fullname": _post.fullname, "sub": sub})
            return result
        except Exception as e:
            log.exception(e)
            self.comments_handler.end_comment_post(comment_oid, self.name, e)

    def _see_near_posts(self, posts):
        try:
            for p_ind in posts:
                self.do_see_post(p_ind)
        except Exception as e:
            log.error(e)

    def do_live_random(self, max_actions=100, posts_limit=500):

        def get_hot_or_new(sbrdt):
            funcs = [lambda: sbrdt.get_hot(limit=posts_limit), lambda: sbrdt.get_new(limit=posts_limit)]
            f = random.choice(funcs)
            try:
                result = list(f())
                return result
            except Exception as e:
                log.error("Cannot get hot or new for %s because %s" % (sbrdt, e))
                return []

        counter = 0
        subs = self.db.get_subs_of_human(self.name)
        if not subs:
            log.error("For %s not any subs at config :(", self.name)
            return

        random_sub = random.choice(subs)
        if random_sub not in self.cache_sub_posts or \
                                time.time() - self.cache_last_loads.get(random_sub,
                                                                        time.time()) > LIVE_RANDOM_SUB_DATA_REFRESH_TIME:
            log.info("%s will load posts for live random in %s" % (self.name, random_sub))
            sbrdt = self.get_subreddit(random_sub)
            posts = get_hot_or_new(sbrdt)
            self.cache_sub_posts[random_sub] = posts
            self.cache_last_loads[random_sub] = time.time()
        else:
            log.info("%s will use cached posts in %s" % (self.name, random_sub))
            posts = self.cache_sub_posts[random_sub]

        w_k = random.randint(properties.want_coefficient_max / 2, properties.want_coefficient_max)

        start_from = self._last_post_ids.get(random_sub, 0)
        for i, post in enumerate(posts, start=start_from):
            if post.fullname not in self._used and self._is_want_to(w_k):
                self.do_see_post(post)
                counter += 1
            if random.randint(int(max_actions / 1.5), max_actions) < counter:
                self._last_post_ids[random_sub] = i
                return

    def do_post(self):
        post_data = self.posts.start_post()
        if not post_data:
            log.warn("no posts for me [%s] :(" % self.name)
            raise Exception("For %s is %s" % (self.name, PS_NO_POSTS))

        post = PostSource.from_dict(post_data)
        while 1:
            try:
                subreddit = self.get_subreddit(post.for_sub)
                _wait_time_to_write(post.title)
                result = subreddit.submit(save=True, title=post.title, url=post.url)
                log.info("%s was post at [%s]; title: [%s]; url: [%s]" % (
                    "!!!important!!!" if post.important else "noise",
                    post.for_sub,
                    post.title,
                    post.url))
            except praw.errors.RateLimitExceeded as e:
                log.warning("rate_limit and will wait %s" % e.sleep_time)
                time.sleep(e.sleep_time + random.randint(5, 10))
                continue
            except Exception as e:
                log.error("exception at posting %s" % (post))
                log.exception(e)
                self.posts.end_post(post_data, PS_ERROR)
                self.db.store_error(self.name, "Exception at post: %s" % e, post_data)
                return PS_ERROR

            if not isinstance(result, Submission):
                self.posts.end_post(post_data, PS_ERROR)
                log.info("NOT OK :( result: %s" % (result))
                self.db.store_error(self.name, "Submit error: %s" % result, post_data)
                return PS_ERROR

            self.register_step(A_POST,
                               {"fullname": result.fullname, "sub": post.for_sub, 'title': post.title,
                                'url': post.url})
            self.posts.end_post(post_data, PS_POSTED)
            log.info("OK! result: %s" % (result))
            return PS_POSTED
