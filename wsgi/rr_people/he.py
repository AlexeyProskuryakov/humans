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
from wsgi.rr_people.consumer import Consumer, HumanConfiguration, FakeConsumer
from wsgi.rr_people.posting.posts import PostsStorage, PS_POSTED
from wsgi.rr_people.queue import ProductionQueue
from wsgi.rr_people.states import StatesHandler

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


class Kapellmeister(Process):
    def __init__(self, name, human_class=Consumer):
        super(Kapellmeister, self).__init__()
        self.main_storage = HumanStorage(name="main storage for [%s]" % name)
        self.human_name = name
        self.ae = ActionGenerator(group_name=name)
        self.human = human_class(login=name)
        self.states_handler = StatesHandler(name="kplmtr of [%s]" % name)
        self.queue = ProductionQueue(name="klmtr of [%s]" % name)
        self.lock = Lock()
        log.info("Human kapellmeister inited.")

    def set_config(self, data):
        with self.lock:
            human_config = HumanConfiguration(data)
            self.human.set_configuration(human_config)

    def human_check(self):
        ok = check_any_login(self.human_name)
        if not ok:
            self.states_handler.set_human_state(self.human_name, S_BAN)
        return ok

    def set_state(self, new_state):
        state = self.states_handler.get_human_state(self.human_name)
        if state == S_SUSPEND:
            log.info("%s is suspended will stop" % self.human_name)
            return False
        else:
            self.states_handler.set_human_state(self.human_name, new_state)
            return True

    def get_force_action(self):
        action = self.queue.pop_force_action(self.human_name)
        return action

    def _do_force_action(self, action_config):
        completed = False
        action = action_config.get("action")
        if action == A_POST:
            if self.human.can_do(A_POST):
                sub = action_config.get("sub")
                url_hash = action_config.get("url_hash")
                self.set_state(WORK_STATE("force post at %s" % (sub)))
                self.human.do_post(url_hash)
                completed = True
        return completed

    def _do_action(self, action, subs, step, _start):
        if action == A_COMMENT:
            if self.human.can_do(A_COMMENT):
                sub_name = random.choice(subs)
                comment = self.queue.pop_comment_hash(sub_name)
                if comment:
                    pfn, ct = comment
                    log.info("will comment [%s] [%s]" % (pfn, ct))
                    self.set_state(WORK_STATE("comment"))
                    self.human.do_comment_post(pfn, sub_name, ct)
                else:
                    log.info("will send need comment for sub [%s]" % sub_name)
                    self.set_state(WORK_STATE("need comment"))
                    self.queue.need_comment(sub_name)

            else:
                log.info("will live random can not comment")
                self.human.do_live_random(max_actions=random.randint(10, 20))

        elif action == A_POST:
            if self.human.can_do(A_POST):
                sub_name = random.choice(subs)
                url_hash = self.queue.pop_post(sub_name)
                if url_hash:
                    self.set_state(WORK_STATE("posting"))
                    self.human.do_post(url_hash)
                else:
                    self.set_state(WORK_STATE("[%s] no posts at [%s] in queue :( " % (self.human_name, sub_name)))
                    log.error("[%s] no posts at [%s] in queue :( " % (self.human_name, sub_name))
        else:
            self.set_state(WORK_STATE("live random"))
            self.human.do_live_random(max_actions=random.randint(10, 20))

        _diff = int(time.time() - _start)
        step += _diff
        if step > WEEK:
            step = step - WEEK

        log.info("[%s] step is end. Action was: [%s], time spent: %s, next step: %s" % (
            self.human_name, action, _diff, step))

        return step

    def run(self):
        log.info("start kappellmeister for [%s]" % self.human_name)
        t_start = time_hash(datetime.utcnow())
        step = t_start
        last_token_refresh_time = t_start
        subs = self.main_storage.get_human_subs(self.human_name)
        prev_force_action = None
        while 1:
            _start = time.time()

            if not self.set_state(S_WORK):
                return

            if step - last_token_refresh_time > HOUR - 100:
                if not self.human_check():
                    log.info("%s is not checked..." % self.human_name)
                    return
                log.info("will refresh token")
                self.human.refresh_token()
                last_token_refresh_time = step

            action = self.ae.get_action(step)
            if action != A_SLEEP:
                force_action = prev_force_action or self.get_force_action()
                completed = False
                if force_action:
                    log.info("[%s] have force action %s" % (self.human_name, force_action))
                    if self._do_force_action(force_action):
                        log.info("[%s] complete force action" % self.human_name)
                        prev_force_action = None
                        completed = True
                    else:
                        log.info("[%s] not complete force action" % self.human_name)
                        prev_force_action = force_action

                if not force_action or not completed:
                    step = self._do_action(action, subs, step, _start)
            else:
                if not self.set_state(S_SLEEP):
                    return
                time.sleep(MINUTE)


class HumanOrchestra():
    __metaclass__ = Singleton

    def __init__(self):
        self.__humans = {}
        self.lock = Lock()
        self.db = HumanStorage(name="human orchestra")
        self.states = StatesHandler(name="human orchestra")
        Thread(target=self.start_humans, name="Orchestra Human Starter").start()

    def start_humans(self):
        log.info("Will auto start humans")
        for human_name, state in self.states.get_all_humans_states().iteritems():
            if state != S_STOP:
                self.add_human(human_name)

    @property
    def humans(self):
        with self.lock:
            return self.__humans

    def add_human(self, human_name):
        with self.lock:
            human_kapellmeister = self.__humans.get(human_name)
            if not human_kapellmeister or not human_kapellmeister.is_alive():
                try:
                    kplmtr = Kapellmeister(human_name)
                    self.__humans[human_name] = kplmtr
                    kplmtr.start()
                except Exception as e:
                    log.info("Error at starting human %s", human_name, )
                    log.exception(e)

    def toggle_human_config(self, human_name):
        with self.lock:
            if human_name in self.__humans:
                def f():
                    db = HumanStorage(name="toggle human config")
                    human_config = db.get_human_live_configuration(human_name)
                    self.__humans[human_name].set_config(human_config)
                    del db

                Process(name="config updater", target=f).start()
