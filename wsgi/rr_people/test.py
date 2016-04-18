from wsgi.rr_people import A_POST
from wsgi.rr_people.consumer import FakeConsumer
from wsgi.rr_people.he import Kapellmeister
from wsgi.rr_people.posting.posts import PostsStorage, PostSource
from wsgi.rr_people.queue import ProductionQueue

if __name__ == '__main__':
    kplmtr = Kapellmeister("Shlak2k16", FakeConsumer)
    kplmtr.start()

    pq = ProductionQueue(name="test")
    post_storage = PostsStorage(name="test")

    post = PostSource()
    post.url_hash = "test"
    post.title = "test from Shlak"
    post.for_sub = "test"
    post.url = "http://www.example.com"

    pq.put_force_action("Shlak2k16", dict({"action": A_POST}, **post.to_dict()))
    post_storage.add_generated_post("test", post)


    post.title = post.title + " 2"
    post.url = "http://www.example_2.com"

    pq.put_force_action("Shlak2k16", dict({"action": A_POST}, **post.to_dict()))
    post_storage.add_generated_post("test", post)