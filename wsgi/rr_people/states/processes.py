# coding:utf-8
import logging
from multiprocessing.synchronize import Lock

import redis

from wsgi.properties import process_director_redis_address, process_director_redis_port, process_director_redis_password
from wsgi.rr_people.states import get_worked_pids

log = logging.getLogger("process_director")

PREFIX = lambda x: "PD_%s" % x
PREFIX_QUERY = "PD_*"
PREFIX_GET_DATA = lambda x: x.replace("PD_", "") if isinstance(x, (str, unicode)) and x.count("PD_") == 1 else x

PREFIX_PID = lambda aspect, pid: "PD_PID_%s_%s" % (aspect, pid)

state_work = "WORK"
state_end = "END"


class ProcessDirector(object):
    def __init__(self, name="?", clear=False, max_connections=2):
        self.redis = redis.StrictRedis(host=process_director_redis_address,
                                       port=process_director_redis_port,
                                       password=process_director_redis_password,
                                       db=0,
                                       max_connections=max_connections
                                       )
        if clear:
            self.redis.flushdb()

        self.mutex = Lock()
        log.info("Process director [%s] inited." % name)

    def _store_aspect_pid(self, aspect, pid, imply_signals=True):
        p = self.redis.pipeline()
        p.delete(PREFIX(aspect))
        p.set(PREFIX(aspect), pid)
        if imply_signals:
            p.set(PREFIX_PID(aspect, pid), state_work)
        p.execute()

    def can_work(self, aspect, pid):
        if self.redis.get(PREFIX_PID(aspect, pid)) == state_end:
            return False
        else:
            return True

    def kill(self, aspect, pid):
        self.redis.set(PREFIX_PID(aspect, pid), state_end)

    def del_pid(self, aspect, pid):
        self.redis.delete(*[PREFIX_PID(aspect, pid)])

    def is_aspect_worked(self, aspect):
        aspect_pid = self.redis.get(PREFIX(aspect))
        if aspect_pid is not None:
            return int(aspect_pid) in get_worked_pids()
        else:
            return False

    def start_aspect(self, aspect, pid, imply_signals=True):
        with self.mutex:
            aspect_pid_raw = self.redis.get(PREFIX(aspect))
            if aspect_pid_raw:
                stored_pid = int(aspect_pid_raw)
                if stored_pid in get_worked_pids():
                    log.info("will kill stored pid: %s", stored_pid)
                    if imply_signals:
                        self.kill(aspect, stored_pid)

            log.info("will store new pid %s [%s]" % (aspect, pid))
            self._store_aspect_pid(aspect, pid, imply_signals)

    def get_state(self, aspect):
        pid_raw = self.redis.get(PREFIX(aspect))
        result = {"aspect": aspect,}
        wp = get_worked_pids()
        if pid_raw:
            pid = int(pid_raw)
            result = dict(result, **{"pid": pid, "work": pid in wp})
        else:
            result["work"] = False
        return result
