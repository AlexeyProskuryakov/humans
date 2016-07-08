import logging
import time

from wsgi.rr_people.posting.posts import PostsStorage, PS_READY, PS_AT_QUEUE, PS_POSTED

log = logging.getLogger("migration")


def migration_add_time_to_posts():
    ps = PostsStorage("migration")

    ps.posts.create_index("url_hash", unique=True)
    ps.posts.create_index("sub")
    ps.posts.create_index("state")
    ps.posts.create_index("time")

    for post in ps.posts.find({"time": {"$exists": False}, "state": {"$in": [PS_READY, PS_AT_QUEUE, PS_POSTED]}}):
        ps.posts.update_one(post, {"$set": {"time": time.time()}})
        log.info("Post: %s migrate" % post)


if __name__ == '__main__':
    migration_add_time_to_posts()
