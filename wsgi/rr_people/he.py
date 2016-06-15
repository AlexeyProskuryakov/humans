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
    Singleton, S_STOP
from wsgi.rr_people.ae import ActionGenerator, time_hash
from wsgi.rr_people.human import Human, HumanConfiguration
from wsgi.rr_people.queue import CommentRedisQueue
from wsgi.rr_people.states.entity_states import StatesHandler
from wsgi.rr_people.states.persisted_queue import RedisQueue
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


class Kapellmeister(Process):
    def __init__(self, name, human_class=Human):
        super(Kapellmeister, self).__init__()
        self.main_storage = HumanStorage(name="main storage for [%s]" % name)
        self.human_name = name
        self.ae = ActionGenerator(group_name=name)
        self.human = human_class(login=name)
        self.states_handler = StatesHandler(name="kplmtr of [%s]" % name)
        self.comment_queue = CommentRedisQueue(name="klmtr of [%s]" % name)

        self.process_director = ProcessDirector(name="kplmtr of [%s] " % name)

        self.lock = Lock()
        log.info("Human kapellmeister inited.")

    def _human_check(self):
        ok = check_to_ban(self.human_name)
        if not ok:
            self.states_handler.set_human_state(self.human_name, S_BAN)
        return ok

    def _set_state(self, new_state):
        state = self.states_handler.get_human_state(self.human_name)
        if state == S_SUSPEND:
            log.info("%s is suspended will stop" % self.human_name)
            return False
        else:
            self.states_handler.set_human_state(self.human_name, new_state)
            return True

    def _do_action(self, action, subs, step, _start):
        if action == A_COMMENT and self.human.can_do(A_COMMENT):
            sub_name = random.choice(subs)
            comment = self.comment_queue.pop_comment_hash(sub_name)
            if comment:
                pfn, ct = comment
                log.info("will comment [%s] [%s]" % (pfn, ct))
                self._set_state(WORK_STATE("comment"))
                self.human.do_comment_post(pfn, sub_name, ct)
            else:
                log.info("will send need comment for sub [%s]" % sub_name)
                self._set_state(WORK_STATE("need comment"))
                self.comment_queue.need_comment(sub_name)

        elif action == A_POST and self.human.can_do(A_POST):
            self._set_state(WORK_STATE("posting"))
            self.human.do_post()

        else:
            self._set_state(WORK_STATE("live random"))
            self.human.do_live_random(max_actions=random.randint(10, 20), posts_limit=random.randint(50, 100))

        _diff = int(time.time() - _start)
        step += _diff
        if step > WEEK:
            step = step - WEEK

        log.info("[%s] step is end. Action was: [%s], time spent: %s, next step: %s" % (
            self.human_name, action, _diff, step))

        return step

    def run(self):
        if not self.process_director.can_start_aspect(HE_ASPECT(self.human_name), self.pid).get("started"):
            log.info("another kappelmeister for [%s] worked..." % self.human_name)
            return

        log.info("start kappellmeister for [%s]" % self.human_name)
        t_start = time_hash(datetime.utcnow())
        step = t_start
        last_token_refresh_time = t_start
        subs = self.main_storage.get_human_subs(self.human_name)

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
            if action != A_SLEEP:
                step = self._do_action(action, subs, step, _start)
            else:
                if not self._set_state(S_SLEEP):
                    return
                time.sleep(MINUTE)


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
        self.states.set_human_state(human_name, S_SUSPEND)

    def start_human(self, human_name):
        self.states.set_human_state(human_name, S_WORK)
        kplmtr = Kapellmeister(human_name)
        kplmtr.start()

    def get_human_state(self, human_name):
        human_state = self.states.get_human_state(human_name)
        process_state = self.process_director.get_state(HE_ASPECT(human_name))
        return {"human_state": human_state, "process_state": process_state}
