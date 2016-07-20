from multiprocessing import Process

import signal

import time

from wsgi.rr_people.he import Kapellmeister
from wsgi.rr_people.human import FakeHuman, Human
from wsgi.rr_people.posting.posts import PostSource
from wsgi.rr_people.states.processes import ProcessDirector


def test_balanser():
    from wsgi.rr_people.posting.posts_managing import PostHandler

    post_handler = PostHandler(name="test")

    post_handler.queue.redis.flushall()
    post_handler.storage.posts.delete_many({})

    for i in range(120):
        if i / 10 > 10:
            post_handler.add_important_post("test",
                                            PostSource("test_url%s" % i,
                                                       "test title %s" % i,
                                                       "some sub",
                                                       url_hash="uh%s" % i),
                                            "another sub", None)
        else:
            post_handler.add_important_post("test",
                                            PostSource("test_url%s" % i,
                                                       "test title %s" % i,
                                                       "some sub",
                                                       url_hash="uh%s" % i),
                                            "another sub", "test channel %s" % (i / 10))

    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important1"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important2"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important3"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important4"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important5"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important6"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important7"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important8"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important9"), "another sub", None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important10"), "another sub",
                                    None,
                                    important=True)
    post_handler.add_important_post("test", PostSource("tu", "tt", "ss", url_hash="uh_important11"), "another sub",
                                    None,
                                    important=True)
    for i in range(120):
        print post_handler.get_prepared_post("test")


def test_kapelmeister():
    kp = Kapellmeister("Shlak2k15", human_class=Human)
    kp.human.do_comment_post()


class T(Process):
    def __init__(self):
        super(T, self).__init__()
        signal.signal(signal.SIGUSR2, self.receive)

        self.pd = ProcessDirector()

    def receive(self, signum, stack):
        print "%s receive: %s" % (self.pid, signum)

    def run(self):
        self.pd.must_start_aspect("test", self.pid)
        print "start: ", self.pid
        time.sleep(5)
        print "end: ", self.pid


def test_must_start():
    for i in range(10):
        t = T()
        t.start()
        time.sleep(1)



if __name__ == '__main__':
    # test_kapelmeister()
    test_must_start()