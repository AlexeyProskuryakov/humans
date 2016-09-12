# coding:utf-8
import logging
from multiprocessing.synchronize import Lock
import os
import signal

import redis

from wsgi.properties import process_director_redis_address, process_director_redis_port, process_director_redis_password
from wsgi.rr_people import Singleton
from wsgi.rr_people.states import get_worked_pids
from wsgi.rr_people.states.signals import STOP_SIGNAL

log = logging.getLogger("process_director")

PREFIX = lambda x: "PD_%s" % x
PREFIX_QUERY = "PD_*"
PREFIX_GET_DATA = lambda x: x.replace("PD_", "") if isinstance(x, (str, unicode)) and x.count("PD_") == 1 else x


class ProcessDirector(Singleton):
    def __init__(self, what, name="?", clear=False, max_connections=2):
        super(ProcessDirector, self).__init__(what)
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
            log.info("will stop another processes of %s" % aspect)
            result = self.redis.setnx(PREFIX(aspect), pid)
            if not result:
                stored_pid = int(self.redis.get(PREFIX(aspect)))
                if stored_pid in get_worked_pids():
                    result = os.kill(stored_pid, STOP_SIGNAL)
                    log.info("stop result is: %s", result)

            self._store_aspect_pid(aspect, pid)



    def get_state(self, aspect, worked_pids=None):
        pid_raw = self.redis.get(PREFIX(aspect))
        result = {"aspect": aspect,}
        wp = worked_pids or get_worked_pids()
        if pid_raw:
            pid = int(pid_raw)
            result = dict(result, **{"pid": pid, "work": pid in wp})
        else:
            result["work"] = False
        return result
