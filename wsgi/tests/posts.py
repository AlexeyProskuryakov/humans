import random

from wsgi.db import HumanStorage
from wsgi.rr_people.posting.posts import PostsStorage, PostsBalancer, PS_POSTED, PostSource, PS_READY
from wsgi.rr_people.posting.posts_sequence import PostsSequenceHandler

human = "Shlak2k16"
sub = "test_sub"
sub1 = sub + "_1"


def create_posts(ps):
    for i in range(100):
        important = True if random.randint(0, 3) < 1 else False
        _sub = random.choice([sub, sub1])
        ps.add_generated_post(
            PostSource("test url %s" % i, "title: huaitle %s" % i, for_sub="funny", important=important),
            sub=_sub,
            important=important,
            human=human
        )


def test_noise_and_important():
    ps = PostsStorage("test")
    hs = HumanStorage()
    pb = PostsBalancer(human, ps)
    hs.set_human_subs(human, [sub, sub1])
    for i in range(100):
        post = pb.start_post()
        if not post:
            create_posts(ps)
        else:
            pb.end_post(post, PS_POSTED)



    ps.posts.delete_many({"human": human})


def test_posts_sequence():
    psh = PostsSequenceHandler(human)
    psh.is_post_time()

if __name__ == '__main__':
    test_noise_and_important()