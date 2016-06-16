import logging
from subprocess import check_output

from wsgi.properties import WORKED_PIDS_QUERY


class StateObject(object):
    def __init__(self, global_state, mutex_state=None, history=None):
        self.global_state = global_state
        self.mutex_state = mutex_state
        self.history = history or []


class AspectState(object):
    def __init__(self, aspect, state, pid):
        self.aspect = aspect
        self.state = state
        self.pid = pid

    def to_dict(self):
        return self.__dict__

    @staticmethod
    def from_dict(dict):
        if "aspect" in dict and "state" in dict:
            return AspectState(**dict)
        raise Exception("can not create aspect state from this dict %s", dict)

    def __repr__(self):
        return "%s [%s] {%s}" % (self.aspect, self.state, self.pid)


class HeartBeatTask(object):
    def __init__(self, action, aspect, state, pid):
        self.action = action
        self._pid = pid
        self._state = AspectState(aspect, state, pid)

    @property
    def state(self):
        return self._state

    @property
    def pid(self):
        return self._pid

    @property
    def aspect(self):
        return self._state.aspect

    def to_dict(self):
        return dict(self._state.to_dict(), **{"action": self.action})

    @staticmethod
    def from_dict(dict):
        if "aspect" in dict and "state" in dict and "action" in dict:
            return HeartBeatTask(**dict)
        raise Exception("can not create hart beat task from dict %s", dict)

    def __repr__(self):
        return "HBTASK %s: aspect: %s, pid: %s, state: %s" % (self.action, self.aspect, self.pid, self.state)


log = logging.getLogger("states")


def get_worked_pids():
    def check_contains(l, s):
        for el in l:
            if s in el:
                return True

    def get_all_pids():
        result = check_output(["ps", "aux"]).split('\n')
        for el in result:
            process_info = el.split()
            if len(process_info) > 10 and check_contains(process_info, WORKED_PIDS_QUERY):
                yield int(process_info[1])

    worked_pids = set(list(get_all_pids()))
    # log.info("worked pids: \n%s"%worked_pids)
    return worked_pids
