import logging
import random
import string
from multiprocessing import Process

import requests
import time

from wsgi.wake_up import S_BAD, S_OK
from wsgi.wake_up.storage import WakeUpStorage

log = logging.getLogger("wake_up_process")

class WakeUp(Process):
    def __init__(self):
        super(WakeUp, self).__init__()
        self.store = WakeUpStorage("wake_up")

    def check_url(self, url):
        salt = ''.join(random.choice(string.lowercase) for _ in range(20))
        addr = "%s/wake_up/%s" % (url, salt)
        result = requests.post(addr)
        return result.status_code

    def imply_url_code(self, url, code):
        if code != 200:
            log.info("send: [%s] BAD: [%s]" % (url, code))
            self.store.set_url_state(url, S_BAD)
        else:
            log.info("send: [%s] OK" % url)
            self.store.set_url_state(url, S_OK)

    def check(self):
        log.info("Will check services...")
        for url in self.store.get_urls():
            code = self.check_url(url)
            self.imply_url_code(url, code)

        urls_with_bad_state = self.store.get_urls_with_state(S_BAD)
        if urls_with_bad_state:
            time.sleep(5)
            log.info("will check bad services")
            for url in urls_with_bad_state:
                code = self.check_url(url)
                self.imply_url_code(url, code)

    def run(self):
        while 1:
            time.sleep(10)
            try:
                self.check()
            except Exception as e:
                log.error(e)

            time.sleep(3600)

