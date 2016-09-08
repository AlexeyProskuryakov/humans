# coding=utf-8
import logging
import random
import time
import traceback
from datetime import datetime
from multiprocessing.process import Process
from multiprocessing.synchronize import Lock
from threading import Thread

import requests
import requests.auth
from praw import Reddit
from sqlalchemy.sql.functions import current_time

from wsgi import properties
from wsgi.db import HumanStorage
from wsgi.properties import WEEK, HOUR, MINUTE, POLITIC_WORK_HARD, AVG_ACTION_TIME, MIN_TIMES_BETWEEN
from wsgi.rr_people import USER_AGENTS, \
    A_COMMENT, A_POST, A_SLEEP, \
    S_WORK, S_BAN, S_SLEEP, S_SUSPEND, \
    Singleton, A_CONSUME, A_PRODUCE
from wsgi.rr_people.ae import ActionGenerator, time_hash, hash_info, now_hash
from wsgi.rr_people.human import Human
from wsgi.rr_people.posting.posts_sequence import PostsSequenceHandler
from wsgi.rr_people.states.entity_states import StatesHandler
from wsgi.rr_people.states.processes import ProcessDirector
from os import sys

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
                time.sleep(properties.st_between_net_request)
                count += 1

    return wrapped


@net_tryings
def check_to_ban(login):
    statuses = set()
    errors = set()
    for i in range(3):
        res = requests.get(
            "http://www.reddit.com/user/%s/about.json" % login,
            headers={"origin": "http://www.reddit.com",
                     "User-Agent": random.choice(USER_AGENTS)})
        json = res.json()
        if json:
            if res.status_code == 200:
                return True

            errors.add(json.get("error"))

        time.sleep(random.randint(1, 5))
        statuses.add(res.status_code)
    if 200 not in statuses:
        return False
    if None not in errors:
        return False
    return True


WORK_STATE = lambda x: "%s: %s" % (S_WORK, x)

HE_ASPECT = lambda x: "he_%s" % x


class Kapellmeister(Process):
    def __init__(self, name, human_class=Human, reddit=None, reddit_class=None):
        super(Kapellmeister, self).__init__()
        self.db = HumanStorage(name="main storage for [%s]" % name)
        self.human_name = name
        self.name = "KPLM [%s]" % (self.human_name)
        self.ae = ActionGenerator(human_name=self.human_name, human_storage=self.db)
        self.psh = PostsSequenceHandler(human=self.human_name, hs=self.db, ae_store=self.ae._storage)
        self.human = human_class(login=name, db=self.db, reddit=reddit, reddit_class=reddit_class or Reddit)

        self.states_handler = StatesHandler(name="kplmtr of [%s]" % name)
        self.process_director = ProcessDirector(name="kplmtr of [%s] " % name)

        self.lock = Lock()
        log.info("Human [%s] kapellmeister inited." % name)

    def _human_check(self):
        ok = check_to_ban(self.human_name)
        if not ok:
            self.states_handler.set_human_state(self.human_name, S_BAN)
        return ok

    def _set_state(self, new_state):
        state = self.states_handler.get_human_state(self.human_name)
        if state == S_SUSPEND:
            log.info("%s is suspended, will stop" % self.human_name)
            return False
        else:
            self.states_handler.set_human_state(self.human_name, new_state)
            return True

    def _get_previous_post_time(self, action):
        cur = self.db.human_log.find({"human_name": self.human_name, "action": action},
                                     projection={"time": 1}).sort("time", -1)
        try:
            result = cur.next()
            return result.get("time")
        except Exception:
            return 0

    def wait_after_last(self, what, randomise=False):
        time_to_post = time.time() - self._get_previous_post_time(what)
        after = MIN_TIMES_BETWEEN.get(what) - time_to_post
        if randomise:
            after += random.randint(0, int(after / 2))

        if after < 0:
            self._set_state(WORK_STATE(what))
        else:
            self._set_state(WORK_STATE("%s after %s" % (what, after)))
            time.sleep(after)

    def do_action(self, action, force=False):
        produce = False
        if action == A_COMMENT and self.human.can_do(A_COMMENT):
            self.wait_after_last(A_COMMENT, randomise=True)

            comment_result = self.human.do_comment_post()
            if comment_result == A_COMMENT:
                produce = True

        elif action == A_POST and (self.human.can_do(A_POST) or force):
            self.wait_after_last(A_POST)

            post_result = self.human.do_post()
            if post_result == A_POST:
                self.psh.accept_post()
                produce = True

        if not produce:
            if self.human.can_do(A_CONSUME):
                self._set_state(WORK_STATE("live random"))
                self.human.do_live_random(max_actions=random.randint(5, 20), posts_limit=random.randint(25, 50))
                action_result = A_CONSUME
            else:
                self._set_state(WORK_STATE("sleeping because can not consume"))
                self.human.decr_counter(A_CONSUME)
                self.human.decr_counter(A_POST, 2)
                self.human.decr_counter(A_COMMENT, 2)
                self.human.load_hot_and_new(random.choice(self.human.db.get_subs_of_human(self.human_name)),
                                            limit=random.randint(500, 1000))
                time.sleep((random.randint(1, 2) * MINUTE) / random.randint(1, 8))
                action_result = A_SLEEP
        else:
            action_result = A_PRODUCE

        return action_result

    def check_token_refresh(self, step):
        if step - self.last_token_refresh_time > HOUR - 100:
            log.info("will refresh token for [%s]" % self.human_name)
            self.human.refresh_token()
            self.last_token_refresh_time = step

    def run(self):
        if not self.process_director.can_start_aspect(HE_ASPECT(self.human_name), self.pid).get("started"):
            log.warning("another kappelmeister for [%s] worked..." % self.human_name)
            return

        log.info("start kappellmeister for [%s]" % self.human_name)
        self.last_token_refresh_time = time_hash(datetime.now())

        while 1:
            try:
                step = now_hash()
                if not self._set_state(S_WORK):
                    return
                self.check_token_refresh(step)

                action, force = self.decide(step)
                log.info("[%s] decide: %s" % (self.human_name, action))

                if action != A_SLEEP:
                    action_result = self.do_action(action, force)
                else:
                    self._set_state(S_SLEEP)
                    action_result = A_SLEEP
                    time.sleep(MINUTE)

                log.info("[%s] step is end. Action: [%s] => %s; time spent: %s;" % (
                    self.human_name,
                    action,
                    action_result,
                    step - now_hash(),
                ))

            except Exception as e:
                log.error("ERROR AT HE! ")
                _, _, tb = sys.exc_info()
                log.exception(e)
                self.db.store_error(self.human_name, e, " ".join(traceback.format_tb(tb)))
                time.sleep(10)

    def decide(self, step):
        politic = self.db.get_human_post_politic(self.human_name)
        action = self.ae.get_action(step)
        force = False
        if politic == POLITIC_WORK_HARD and action != A_SLEEP:
            log.info("Maybe post %s,  %s" % (hash_info(step), hash_info(now_hash())))
            if self.psh.is_post_time(step):
                action = A_POST
                force = True
            elif action == A_POST:
                action = A_CONSUME

        return action, force


class HumanOrchestra():
    __metaclass__ = Singleton

    def __init__(self):
        self.__humans = {}
        self.db = HumanStorage(name="human orchestra")
        self.states = StatesHandler(name="human orchestra")
        self.process_director = ProcessDirector(name="human orchestra")

        Thread(target=self._auto_start_humans, name="Orchestra Human Starter").start()

    def _auto_start_humans(self):
        log.info("Will auto start humans")
        for human_name, state in self.states.get_all_humans_states().iteritems():
            if state != S_SUSPEND:
                self.start_human(human_name)

    def suspend_human(self, human_name):
        self.states.set_human_state(human_name, S_SUSPEND, ex=None)

    def start_human(self, human_name):
        self.states.set_human_state(human_name, S_WORK)
        kplmtr = Kapellmeister(human_name)
        kplmtr.start()

    def get_human_state(self, human_name):
        human_state = self.states.get_human_state(human_name)
        process_state = self.process_director.get_state(HE_ASPECT(human_name))
        return {"human_state": human_state, "process_state": process_state}

    def delete_human(self, human_name):
        self.states.delete_human_state(human_name)
