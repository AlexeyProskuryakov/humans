import logging

import praw

from wsgi.rr_people.human import Human

log = logging.getLogger("HUMAN TEST")


class FakeRedditHandler(praw.Reddit):
    def __init__(self, *args, **kwargs):
        super(FakeRedditHandler, self).__init__(*args, **kwargs)

    def refresh_access_information(self, **kwargs):
        log.info("refresh access token %s" % kwargs)

    def get_submission(self, url=None, submission_id=None, comment_limit=0,
                       comment_sort=None, params=None):
        log.info("getting submission %s %s %s %s %s" % (url, submission_id, comment_limit, comment_sort, params))
        return None

    def login(self, username=None, password=None, **kwargs):
        log.info("login %s %s %s" % (username, password, kwargs))

    def subscribe(self, subreddit, unsubscribe=False):
        log.info("subscribe %s %s" % subreddit, unsubscribe)


class FakeHuman(Human):
    def __init__(self, login, *args, **kwargs):
        super(FakeHuman, self).__init__(login)

    def refresh_token(self):
        log.info("REFRESH TOKEN")

    def do_post(self):
        log.info("DO POSTING...")

    def do_comment_post(self):
        return super(FakeHuman, self).do_comment_post()

    def _humanised_comment_post(self, sub, post_fullname):
        log.info("humanised comment post")
        pass

    def do_see_post(self, post):
        log.info("DO SEE POST %s" % post)

    def do_live_random(self, max_actions=100, posts_limit=500):
        log.info("DO LIVE RANDOM %s %s" % (max_actions, posts_limit))



def test_kapelmeister():
