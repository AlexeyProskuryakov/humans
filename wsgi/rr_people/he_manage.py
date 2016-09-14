import logging
from multiprocessing import Process

from wsgi.db import HumanStorage
from wsgi.properties import test_mode
from wsgi.rr_people import Singleton, S_SUSPEND, S_WORK
from wsgi.rr_people.he import Kapellmeister
from wsgi.rr_people.states.entity_states import StatesHandler
from wsgi.rr_people.states.processes import ProcessDirector

log = logging.getLogger("orchestra")


class HumanOrchestra():
    __metaclass__ = Singleton

    def __init__(self):
        self.__humans = {}
        self.db = HumanStorage(name="human orchestra")
        self.states = StatesHandler(name="human orchestra")
        self.process_director = ProcessDirector(name="human orchestra")

        Process(target=self._auto_start_humans, name="Orchestra Human Starter").start()

    def _auto_start_humans(self):
        log.info("Will auto start humans")
        for human_name, state in self.states.get_all_humans_states().iteritems():
            if state != S_SUSPEND:
                self.start_human(human_name)

    def suspend_human(self, human_name):
        self.states.set_human_state(human_name, S_SUSPEND)

    def start_human(self, human_name):
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

    def get_human_state(self, human_name):
        human_state = self.states.get_human_state(human_name)
        process_state = self.process_director.get_state(HE_ASPECT(human_name))
        return {"human_state": human_state, "process_state": process_state}

    def delete_human(self, human_name):
        self.states.delete_human_state(human_name)
