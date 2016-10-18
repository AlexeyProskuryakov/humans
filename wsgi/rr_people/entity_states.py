# coding=utf-8
import logging
import re

import redis

from wsgi import ConfigManager
from wsgi.db import HumanStorage
from wsgi.properties import redis_max_connections
from wsgi.rr_people import S_STOP

STATE_CF = lambda x: "cf_state_%s" % x
STATE_PG = lambda x: "pg_state_%s" % x

HUMAN_STATES = "hs_hashset"
HUMAN_STATE = lambda x: "h_state_%s" % x

log = logging.getLogger("states")

digits_re = re.compile("\d+")

class StatesHandler(object):
    def __init__(self, name="?", clear=False, max_connections=redis_max_connections, hs=None):
        cm = ConfigManager()
        self.redis = redis.StrictRedis(host=cm.get('states_redis_address'),
                                       port=cm.get('states_redis_port'),
                                       password=cm.get('states_redis_password'),
                                       db=0,
                                       max_connections=max_connections
                                       )

        if clear:
            self.redis.flushdb()

        self.db = hs or HumanStorage("states handler %s" % name)
        self._last_states = []
        log.info("States handler inited for [%s]" % name)

    def _set_last_state(self, state):
        if digits_re.findall(state):
            _state = digits_re.sub("", state)
        else:
            _state = state

        if len(self._last_states) == 3:
            self._last_states.pop(0)
        self._last_states.append(_state)

    def set_human_state(self, human_name, state):
        old_state = self.get_human_state(human_name)
        self._set_last_state(state)
        if self._last_states[0] != self._last_states[-1] or len(self._last_states) < 3:
            self.db.set_human_state_log(human_name, old_state, state)

        pipe = self.redis.pipeline()
        pipe.hset(HUMAN_STATES, human_name, state)
        pipe.set(HUMAN_STATE(human_name), state)
        pipe.execute()

    def get_human_state(self, human_name):
        state = self.redis.get(HUMAN_STATE(human_name))
        if not state:
            return S_STOP
        return state

    def get_all_humans_states(self):
        result = self.redis.hgetall(HUMAN_STATES)
        for k, v in result.iteritems():
            result[k] = self.get_human_state(k)
        return result

    def delete_human_state(self, human_name):
        pipe = self.redis.pipeline()
        pipe.hdel(HUMAN_STATES, human_name)
        pipe.delete([HUMAN_STATE(human_name)])
        pipe.execute()
