from wsgi.rr_people.he import Kapellmeister
from wsgi.rr_people.human import FakeHuman
from wsgi.rr_people.posting.posts import PostSource


def test_kapelmeister():
    kp = Kapellmeister("test", human_class=FakeHuman)



if __name__ == '__main__':

    from wsgi.rr_people.posting.posts_managing import PostHandler

    post_handler = PostHandler(name="test")

    post_handler.queue.redis.flushall()
    post_handler.posts_storage.posts.delete_many({})

    for i in range(120):
        if i / 10 > 10:
            post_handler.add_new_post("test",
                                      PostSource("test_url%s" % i,
                                                 "test title %s" % i,
                                                 "some sub",
                                                 url_hash="uh%s" % i),
                                      "another sub", None)
        else:
            post_handler.add_new_post("test",
                                      PostSource("test_url%s" % i,
                                                 "test title %s" % i,
                                                 "some sub",
                                                 url_hash="uh%s" % i),
                                      "another sub", "test channel %s" % (i / 10))

    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important1"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important2"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important3"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important4"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important5"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important6"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important7"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important8"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important9"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important10"), "another sub", None,
                              important=True)
    post_handler.add_new_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important11"), "another sub", None,
                              important=True)
    for i in range(120):
        print post_handler.get_post("test")
