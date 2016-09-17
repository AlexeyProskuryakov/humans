# -*- coding: utf-8 -*-
import logging
import signal

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
        log.info("%s init signal receiver" % self.name)

    def receive_signal(self, signum, frame):
        log.info("%s have signal to stop" % self.name)
        self.can_work = False
