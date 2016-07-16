# coding=utf-8
import logging
import random
import time
from datetime import datetime
from multiprocessing.process import Process
from multiprocessing.synchronize import Lock
from threading import Thread

import requests
import requests.auth

from wsgi import properties
from wsgi.db import HumanStorage
from wsgi.properties import WEEK, HOUR, MINUTE
from wsgi.rr_people import USER_AGENTS, \
    A_COMMENT, A_POST, A_SLEEP, \
    S_WORK, S_BAN, S_SLEEP, S_SUSPEND, \
    Singleton, A_CONSUME, A_PRODUCE
from wsgi.rr_people.ae import ActionGenerator, time_hash, delta_info
from wsgi.rr_people.human import Human
from wsgi.rr_people.states.entity_states import StatesHandler
from wsgi.rr_people.states.processes import ProcessDirector

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

MIN_STEP_TIME = 60
MIN_TIME_BETWEEN_POSTS = 9 * 60


class Kapellmeister(Process):
    def __init__(self, name, human_class=Human):
        super(Kapellmeister, self).__init__()
        self.main_storage = HumanStorage(name="main storage for [%s]" % name)
        self.human_name = name
        self.name = "KPLM [%s]" % (self.human_name)
        self.ae = ActionGenerator(group_name=name)
        self.human = human_class(login=name)

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

    def _get_previous_post_time(self):
        cur = self.main_storage.human_log.find({"human_name": self.human_name, "action": A_POST},
                                               projection={"time": 1}).sort("time", -1)
        result = cur.next()
        return result.get("time")

    def _can_post_at_time(self):
        return (time.time() - self._get_previous_post_time()) > MIN_TIME_BETWEEN_POSTS

    def _do_action(self, action, step, _start):
        produce = False
        if action == A_COMMENT and self.human.can_do(A_COMMENT):
            self._set_state(WORK_STATE("commenting"))
            comment_result = self.human.do_comment_post()
            if comment_result == A_COMMENT:
                produce = True

        elif action == A_POST and self.human.can_do(A_POST) and self._can_post_at_time():
            self._set_state(WORK_STATE("posting"))
            post_result = self.human.do_post()
            if post_result == A_POST: produce = True

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
                self.human.get_hot_and_new(random.choice(self.human.db.get_human_subs(self.human_name)),
                                           limit=random.randint(500, 1000))
                time.sleep((random.randint(1, 2) * MINUTE) / random.randint(1, 6))
                action_result = A_SLEEP
        else:
            action_result = A_PRODUCE

        _diff = int(time.time() - _start)
        step += _diff if _diff > MIN_STEP_TIME else MIN_STEP_TIME * random.randint(1, 10)
        return step, action_result

    def run(self):
        if not self.process_director.can_start_aspect(HE_ASPECT(self.human_name), self.pid).get("started"):
            log.warning("another kappelmeister for [%s] worked..." % self.human_name)
            return

        log.info("start kappellmeister for [%s]" % self.human_name)
        t_start = time_hash(datetime.utcnow())
        step = t_start
        last_token_refresh_time = t_start

        while 1:
            _start = time.time()

            if not self._set_state(S_WORK):
                return

            if step - last_token_refresh_time > HOUR - 100:
                if not self._human_check():
                    log.info("%s is not checked..." % self.human_name)
                    return
                log.info("will refresh token for [%s]" % self.human_name)
                self.human.refresh_token()
                last_token_refresh_time = step

            action = self.ae.get_action(step)
            log.info("[%s] ae get step: %s" % (self.human_name, action))
            _prev_step = step
            if action != A_SLEEP:
                step, action_result = self._do_action(action, step, _start)
            else:
                if not self._set_state(S_SLEEP):
                    return
                step += MINUTE
                action_result = A_SLEEP
                time.sleep(MINUTE)

            if step > WEEK:
                step = step - WEEK
                _prev_step = _prev_step - WEEK

            log.info("[%s] step is end. Action: [%s] -> [%s]; time spent: %s; \nnext step after: %s secs." % (
                self.human_name,
                action, action_result,
                time.time() - _start,
                step - _prev_step))


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
