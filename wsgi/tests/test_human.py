import logging
import random

import praw
import time

from wsgi import properties
from wsgi.db import HumanStorage
from wsgi.properties import AVG_ACTION_TIME
from wsgi.properties import WEEK
from wsgi.rr_people import A_COMMENT, A_POST, A_SLEEP, A_CONSUME, A_VOTE
from wsgi.rr_people.he import Kapellmeister
from wsgi.rr_people.human import Human

log = logging.getLogger("HUMAN TEST")


class FakeRedditHandler(praw.Reddit):
    def __init__(self, *args, **kwargs):
        super(FakeRedditHandler, self).__init__(*args, **kwargs)

    def has_oauth_app_info(self):
        return True

    def refresh_access_information(self, refresh_token):
        log.info("refresh access token %s" % refresh_token)
        return {"scope": []}

    def get_submission(self, url=None, submission_id=None, comment_limit=0,
                       comment_sort=None, params=None):
        log.info("getting submission %s %s %s %s %s" % (url, submission_id, comment_limit, comment_sort, params))
        return None

    def login(self, username=None, password=None, **kwargs):
        log.info("login %s %s %s" % (username, password, kwargs))

    def subscribe(self, subreddit, unsubscribe=False):
        log.info("subscribe %s %s" % subreddit, unsubscribe)

    def set_oauth_app_info(self, client_id, client_secret, redirect_uri):
        log.info("set oauth app info %s %s %s" % (client_id, client_secret, redirect_uri))

    def set_access_credentials(self, scope, access_token, refresh_token=None,
                               update_user=True):
        log.info("set access credentials %s %s %s %s" % (scope, access_token, refresh_token, update_user))


class FakeHuman(Human):
    def __init__(self, login, *args, **kwargs):
        super(FakeHuman, self).__init__(login, reddit_class=FakeRedditHandler, reddit=FakeRedditHandler)

    def refresh_token(self):
        log.info("REFRESH TOKEN")
        self.counters_thresholds = self.calculate_counters()

    def do_post(self):
        post = self.posts.start_post()
        count = random.randint(0, AVG_ACTION_TIME / 10)
        log.info("DO POSTING...(%s)" % count)
        time.sleep(count)
        self.register_step(A_POST)
        self.posts.end_post(post, "TEST")
        return A_POST

    def do_comment_post(self, sub=None):
        count = random.randint(0, AVG_ACTION_TIME / 10)
        log.info("DO COMMENT...(%s)" % count)
        time.sleep(count)
        self.register_step(A_COMMENT)
        return A_COMMENT

    def _humanised_comment_post(self, sub, comment_id):
        log.info("humanised comment post")
        pass

    def do_see_post(self, post):
        count = random.randint(0, AVG_ACTION_TIME / 10)
        log.info("DO SEEE POST...(%s)" % count)
        time.sleep(count)


    def do_live_random(self, max_actions=100, posts_limit=500):
        if self.can_do(A_VOTE):
            self.register_step(A_VOTE)
        else:
            self.register_step(A_CONSUME)

        count = random.randint(0, AVG_ACTION_TIME / 10)
        log.info("DO LIVE RANDOM...(%s)" % count)
        time.sleep(count)

    def load_hot_and_new(self, subreddit_name, sort=None, limit=properties.DEFAULT_LIMIT):
        return []

    def __repr__(self):
        return "".join(["%s:\t%s\n" % (k, v) for k, v in self.counters.iteritems()])


def test_kapelmeister():
    user = "Shlak2k16"
    db = HumanStorage()
    db.update_human_access_credentials_info(user, {"scope": ["read"], "access_token": "foo", "refresh_token": "bar"})

    kplm = Kapellmeister(user, None, human_class=FakeHuman, reddit=FakeRedditHandler, reddit_class=FakeRedditHandler)
    kplm.psh.evaluate_new()

    sleep = 0
    for step in xrange(0, WEEK, AVG_ACTION_TIME):
        action, force = kplm.decide(step)
        print action, force
        if action == A_SLEEP:
            log.info("SLEEP")
            sleep += 1
        else:
            result = kplm.do_action(action, force)
            print result

    print kplm.human, "sleep:", sleep


if __name__ == '__main__':
    test_kapelmeister()
