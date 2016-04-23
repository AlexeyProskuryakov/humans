from wsgi.rr_people import A_POST
from wsgi.rr_people.consumer import FakeConsumer
from wsgi.rr_people.he import Kapellmeister
from wsgi.rr_people.posting.posts import PostsStorage, PostSource
from wsgi.rr_people.queue import CommentQueue

if __name__ == '__main__':

    from wsgi.rr_people.posting.posts_managing import PostHandler

    post_handler = PostHandler(name="test")

    for i in range(120):
        post_handler.add_new_post("test", PostSource("test_url%s"%i, "test title %s"%i, "some sub"), "another sub", "test channel %s"%(i/10))

    for i in range(120):
        print post_handler.get_post("test")

