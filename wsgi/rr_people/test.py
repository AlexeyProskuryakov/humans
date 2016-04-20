from wsgi.rr_people import A_POST
from wsgi.rr_people.consumer import FakeConsumer
from wsgi.rr_people.he import Kapellmeister
from wsgi.rr_people.posting.posts import PostsStorage, PostSource
from wsgi.rr_people.queue import CommentQueue

if __name__ == '__main__':
    name = "Shlak2k16"
    kplmtr = Kapellmeister(name, FakeConsumer)
    kplmtr.start()

    pq = CommentQueue(name="test")
    post_storage = PostsStorage(name="test")

    post = PostSource()
    post.url_hash = "test"
    post.title = "test from Shlak"
    post.for_sub = "test"
    post.url = "http://www.example.com"
