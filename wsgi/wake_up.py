import random
import string
from multiprocessing import Process, Lock
import requests
import time

from flask import logging

from wsgi.db import DBHandler

log = logging.getLogger("wake_up")

S_BAD = "BAD"
S_OK = "OK"


class WakeUpStorage(DBHandler):
    def __init__(self, name="?"):
        super(WakeUpStorage, self).__init__(name=name)

        if "wake_up" not in self.collection_names:
            self.urls = self.db.create_collection("wake_up")
            self.urls.create_index("url_hash", unique=True)
            self.urls.create_index("state")
        else:
            self.urls = self.db.get_collection("wake_up")

    def get_urls_info(self):
        return self.urls.find({})

    def get_urls(self):
        return map(lambda x: x.get("url"), self.urls.find({}, projection={'url': True}))

    def add_url(self, url):
        hash_url = hash(url)
        found = self.urls.find_one({"url_hash": hash_url})
        if not found:
            log.info("add new url [%s]" % url)
            self.urls.insert_one({"url_hash": hash_url, "url": url})

    def delete_urls(self, urls):
        hashes = map(lambda x:hash(x), urls)
        result = self.urls.delete_many({"url_hash":{"$in":hashes}})
        return result.deleted_count

    def set_url_state(self, url, state):
        self.urls.update_one({"url": url}, {"$set": {"state": state}})

    def get_urls_with_state(self, state):
        return map(lambda x: x.get("url"), self.urls.find({"state": state}, projection={'url': True}))


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


if __name__ == '__main__':
    w = WakeUp()
    w.start()
