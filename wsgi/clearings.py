from wsgi.rr_people.posting.balancer import BatchStorage
from wsgi.rr_people.posting.posts import PostsStorage
from wsgi.rr_people.posting.queue import PostRedisQueue, QUEUE_PG


def clear_posts():
    ps = PostsStorage()
    ps.posts.delete_many({})

    bs = BatchStorage()
    bs.batches.delete_many({})

    PostRedisQueue(clear=True)


def clear_important_posts():
    ps = PostsStorage()
    bs = BatchStorage()
    q = PostRedisQueue()

    for post in ps.posts.find({"important": True}):
        bs.batches.delete_one({"human_name": post.get("human_name")})
        q.redis.delete(QUEUE_PG(post.get("human_name")))
        ps.posts.delete_one(post)
        print "delete: ", post


if __name__ == '__main__':
    # clear_posts()
    clear_important_posts()
