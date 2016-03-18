import logging

from wsgi.rr_people import RedditHandler
from wsgi.rr_people.posting.generator import Generator
from wsgi.db import DBHandler

COPY = "copy"

log = logging.getLogger("copy")

class SubsStore(DBHandler):
    def __init__(self):
        super(SubsStore, self).__init__()
        self.sub_col = self.db.get_collection("sub_relations")
        if not self.sub_col:
            self.sub_col = self.db.create_collection("sub_relations")
            self.sub_col.create_index([("name", 1)], unique=True)

    def add_sub_relations(self, sub_name, related_subs):
        found = self.sub_col.find_one({"name": sub_name})
        if found:
            result = self.sub_col.update_one(found, {"$addToSet": {"related": {"$each": related_subs}}})
        else:
            result = self.sub_col.insert_one({"name": sub_name, "related": related_subs})

        return result

    def get_related_subs(self, sub_name):
        found = self.sub_col.find_one({"name":sub_name})
        return found.get("related", [])


class CopyPostGenerator(RedditHandler, Generator):
    def __init__(self):
        super(CopyPostGenerator, self).__init__()
        self.sub_store = SubsStore()

    def found_copy_in_sub(self):
        pass
    def generate_data(self, subreddit, key_words):
        related_subs = self.sub_store.get_related_subs(subreddit)
        if not related_subs:
            log.warning("for sub [%s] not any related subs :(" % subreddit)
            return
        for sub in related_subs:
            pass