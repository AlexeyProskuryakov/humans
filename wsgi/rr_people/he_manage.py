from multiprocessing import Queue
import logging
import os
from threading import Thread, RLock

from wsgi.db import HumanStorage
from wsgi.properties import test_mode
from wsgi.rr_people import Singleton, S_SUSPEND, S_WORK
from wsgi.rr_people.he import Kapellmeister, HE_ASPECT
from wsgi.rr_people.states.entity_states import StatesHandler
from wsgi.rr_people.states.processes import ProcessDirector

log = logging.getLogger("orchestra")

HUMAN_ORCHESTRA_ASPECT = "orchestra"


class HumanOrchestra():
    __metaclass__ = Singleton

    def __init__(self):
        self.__humans = {}
        self.db = HumanStorage(name="human orchestra")
        self.states = StatesHandler(name="human orchestra", hs=self.db)
        self.process_director = ProcessDirector(name="human orchestra")

        self.childs_results = Queue()
        self._kappelmeisters = {}
        self.mu = RLock()

        if not self.process_director.is_aspect_worked(HUMAN_ORCHESTRA_ASPECT):
            log.info("Will auto start humans because i am first:)")
            self._auto_start_humans()
            self.process_director.start_aspect(HUMAN_ORCHESTRA_ASPECT, os.getpid())
        else:
            log.info("Another orchestra work.")

        Thread(target=self.kappelmeister_destruct).start()
        log.info("Human Orchestra inited")

    @property
    def kappelmeisters(self):
        self.mu.acquire()
        result = self._kappelmeisters
        self.mu.release()
        return result

    def kappelmeister_destruct(self):
        log.info("will destruct zombies...")
        while 1:
            try:
                to_join = self.childs_results.get()
            except Exception as e:
                log.info("Queue is broken")
                return

            log.info("received that %s want to stop..." % to_join)
            if to_join in self.kappelmeisters:
                self.kappelmeisters[to_join].join()
                log.info("was end %s", to_join)

    def _auto_start_humans(self):
        log.info("Will auto start humans")
        for human_name, state in self.states.get_all_humans_states().iteritems():
            if state != S_SUSPEND:
                self.start_human(human_name)

    def suspend_human(self, human_name):
        self.states.set_human_state(human_name, S_SUSPEND)

    def start_human(self, human_name):
        if self.process_director.is_aspect_worked(HE_ASPECT(human_name)):
            log.warn("Trying start [%s] but he is work now" % HE_ASPECT(human_name))
            return

        self.states.set_human_state(human_name, S_WORK)
        if test_mode:
            from wsgi.tests.test_human import FakeHuman, FakeRedditHandler
            kplm = Kapellmeister(human_name, self.childs_results,
                                 human_class=FakeHuman,
                                 reddit=FakeRedditHandler,
                                 reddit_class=FakeRedditHandler)
        else:
            kplm = Kapellmeister(human_name, self.childs_results)
        kplm.start()

        self.mu.acquire()
        self._kappelmeisters[kplm.pid] = kplm
        self.mu.release()

    def get_human_state(self, human_name):
        human_state = self.states.get_human_state(human_name)
        process_state = self.process_director.get_state(HE_ASPECT(human_name))
        return {"human_state": human_state, "process_state": process_state}

    def delete_human(self, human_name):
        self.states.delete_human_state(human_name)
