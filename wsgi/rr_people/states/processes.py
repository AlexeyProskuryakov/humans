# coding:utf-8
import logging
from multiprocessing.synchronize import Lock
import os
import signal

import redis

from wsgi.properties import process_director_redis_address, process_director_redis_port, process_director_redis_password
from wsgi.rr_people.states import get_worked_pids
from wsgi.rr_people.states.signals import STOP_SIGNAL

log = logging.getLogger("process_director")

PREFIX = lambda x: "PD_%s" % x
PREFIX_QUERY = "PD_*"
PREFIX_GET_DATA = lambda x: x.replace("PD_", "") if isinstance(x, (str, unicode)) and x.count("PD_") == 1 else x


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

    def _store_aspect_pid(self, aspect, pid):
        p = self.redis.pipeline()
        p.delete(PREFIX(aspect))
        p.set(PREFIX(aspect), pid)
        p.execute()

    def is_aspect_worked(self, aspect):
        aspect_pid = self.redis.get(PREFIX(aspect))
        return int(aspect_pid) in get_worked_pids()

    def can_start_aspect(self, aspect, pid):
        """
        starting or returning False if aspect already started
        :param aspect:
        :param pid:
        :return:
        """
        with self.mutex:
            log.info("will check start aspect %s for %s" % (aspect, pid))
            result = self.redis.setnx(PREFIX(aspect), pid)
            if not result:
                aspect_pid = int(self.redis.get(PREFIX(aspect)))
                log.info("setnx result is None... stored aspect pid is: %s" % aspect_pid)

                if aspect_pid in get_worked_pids():
                    return {"state": "already work", "by": aspect_pid, "started": False}
                else:
                    self._store_aspect_pid(aspect, pid)
                    return {"state": "restarted", "started": True}
            else:
                return {"state": "started", "started": True}

    def start_aspect(self, aspect, pid):
        with self.mutex:
            aspect_pid_raw = self.redis.get(PREFIX(aspect))
            if aspect_pid_raw:
                stored_pid = int(aspect_pid_raw)
                if stored_pid in get_worked_pids():
                    log.info("will kill stored pid: %s", stored_pid)
                    os.kill(stored_pid, STOP_SIGNAL)

            log.info("will store new pid %s [%s]" % (aspect, pid))
            self._store_aspect_pid(aspect, pid)

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
