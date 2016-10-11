import logging

from wsgi import tst_to_dt, Singleton
from wsgi.db import HumanStorage
from wsgi.properties import test_mode
from wsgi.rr_people import S_SUSPEND, S_WORK
from wsgi.rr_people.he import Kapellmeister, HE_ASPECT
from wsgi.rr_people.entity_states import StatesHandler
from states.processes import ProcessDirector

log = logging.getLogger("orchestra")

HUMAN_ORCHESTRA_ASPECT = "orchestra"


class HumanOrchestra():
    __metaclass__ = Singleton

    def __init__(self):
        self.__humans = {}
        self.db = HumanStorage(name="human orchestra")
        self.states = StatesHandler(name="human orchestra", hs=self.db)
        self.process_director = ProcessDirector(name="human orchestra")

        log.info("Will auto start humans")
        self._auto_start_humans()

        log.info("Human Orchestra inited")

    def _auto_start_humans(self):
        for human_name, state in self.states.get_all_humans_states().iteritems():
            if state != S_SUSPEND:
                self.start_human(human_name)

    def suspend_human(self, human_name):
        self.states.set_human_state(human_name, S_SUSPEND)

    def start_human(self, human_name):
        is_work = self.process_director.is_aspect_work(HE_ASPECT(human_name))
        if is_work:
            log.info("Can not start human %s, because already started." % human_name)
            return

        self.states.set_human_state(human_name, S_WORK)
        if test_mode:
            from wsgi.tests.test_human import FakeHuman, FakeRedditHandler
            kplm = Kapellmeister(human_name,
                                 human_class=FakeHuman,
                                 reddit=FakeRedditHandler,
                                 reddit_class=FakeRedditHandler)
        else:
            kplm = Kapellmeister(human_name)
        kplm.start()

        log.info("ORCHESTRA START kappelmeister %s" % kplm.pid)

    def get_human_state(self, human_name):
        human_state = self.states.get_human_state(human_name)
        process_state = self.process_director.is_aspect_work(HE_ASPECT(human_name))
        return {"human_state": human_state,
                "process_state": tst_to_dt(float(process_state)) if process_state else False}

    def delete_human(self, human_name):
        self.states.delete_human_state(human_name)
