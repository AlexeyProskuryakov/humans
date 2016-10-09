import logging

from pymongo import MongoClient

log = logging.getLogger("wake_up_storage")

mongo_uri = "mongodb://3030:sederfes100500@ds055525.mongolab.com:55525/reddit_people"
db_name = "reddit_people"

class WakeUpStorage():
    def __init__(self, name="?"):
        self.client = MongoClient(host=mongo_uri, maxPoolSize=10, connect=False)
        self.db = self.client[db_name]
        self.collection_names = self.db.collection_names(include_system_collections=False)

        if "wake_up" not in self.collection_names:
            self.urls = self.db.create_collection("wake_up")
            self.urls.create_index("url_hash", unique=True)
            self.urls.create_index("state")
        else:
            self.urls = self.db.get_collection("wake_up")

        log.info("Init wake up storage [%s]"%name)

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
