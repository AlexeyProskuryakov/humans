import random
import string
from multiprocessing import Process, Lock
import requests
import time

from flask import logging

from wsgi.db import DBHandler

log = logging.getLogger("wake_up")


class WakeUpStorage(DBHandler):
    def __init__(self, name="?"):
        super(WakeUpStorage, self).__init__(name=name)
        collections = self.db.collection_names(include_system_collections=False)
        if "wake_up" not in collections:
            self.urls = self.db.create_collection("wake_up")
            self.urls.create_index("url_hash", unique=True)
        else:
            self.urls = self.db.get_collection("wake_up")

    def get_urls(self):
        return map(lambda x: x.get("url"), self.urls.find({}, projection={'_id': False, "url_hash": False}))

    def add_url(self, url):
        hash_url = hash(url)
        found = self.urls.find_one({"url_hash": hash_url})
        if not found:
            log.info("add new url [%s]" % url)
            self.urls.insert_one({"url_hash": hash_url, "url": url})


class WakeUp(Process):
    def __init__(self):
        super(WakeUp, self).__init__()
        self.store = WakeUpStorage("wake_up")
        self.mutex = Lock()

    def run(self):
        while 1:
            time.sleep(3600)
            try:
                for url in self.store.get_urls():
                    salt = ''.join(random.choice(string.lowercase) for _ in range(20))
                    addr = "%s/wake_up/%s" % (url, salt)

                    result = requests.post(addr)
                    if result.status_code != 200:
                        time.sleep(1)
                        log.info("send: [%s][%s] not work will trying next times..." % (addr,result.status_code))
                        continue
                    else:
                        log.info("send: [%s] OK" % addr)
                    time.sleep(10)

            except Exception as e:
                log.error(e)
