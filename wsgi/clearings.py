from wsgi.rr_people.posting.balancer import BatchStorage
from wsgi.rr_people.posting.posts import PostsStorage
from wsgi.rr_people.posting.queue import PostRedisQueue


def clear_posts():
    ps = PostsStorage()
    ps.posts.delete_many({})

    bs = BatchStorage()
    bs.batches.delete_many({})

    PostRedisQueue(clear=True)


if __name__ == '__main__':
    clear_posts()
