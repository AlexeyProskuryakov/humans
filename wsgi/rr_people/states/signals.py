# -*- coding: utf-8 -*-
import logging
import signal
import time
import os

from multiprocessing import Process

log = logging.getLogger("SIGNALS")

STOP_SIGNAL = signal.SIGHUP


class _signalHandler(object):
    """ Класс обрабатывающий системные сигналы """

    def __init__(self, target):
        """target - экземпляр класса"""
        self.target = target

    def handle_signal(self, signum, frame):
        self.target.receive_signal(signum, frame)


class SignalReceiver(object):
    def __init__(self, name="NONAME signal receiver"):
        sh = _signalHandler(self)
        signal.signal(signal.SIGHUP, sh.handle_signal)
        self.can_work = True
        self.name = name

    def receive_signal(self, signum, frame):
        log.info("%s have signal to stop" % self.name)
        self.can_work = False


class some_process(Process, SignalReceiver):
    def __init__(self, name="main"):
        super(some_process, self).__init__()
        SignalReceiver.__init__(self)
        self.name = name

    def run(self):
        print("will work %s" % self.pid)
        while self.can_work:
            time.sleep(1)
            print("work... %s" % self.pid)

        print("end %s" % self.pid)


if __name__ == '__main__':
    print os.getpid()
    mp1 = some_process()

    mp1.start()

    time.sleep(3)

    os.kill(mp1.pid, STOP_SIGNAL)

    mp1.join()
