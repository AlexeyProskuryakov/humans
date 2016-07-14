from wsgi.rr_people.posting.balancer import BatchStorage, PostBalancer
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


def remove_head_noise_from_queue_to_balanser(for_human):
    ps = PostsStorage()
    q = PostRedisQueue()
    pb = PostBalancer()

    for qp in q.show_all_posts_hashes(for_human):
        post, p_data = ps.get_post(qp)
        if p_data.get("important") == False:
            poped_id = q.pop_post(for_human)
            if poped_id == qp:
                pb.add_post(qp, p_data.get("channel_id"), human_name=for_human, sub=post.for_sub or p_data.get("sub"))
            else:
                print "FUCK!"
        else:
            break

if __name__ == '__main__':
    # clear_posts()
    #clear_important_posts()
    remove_head_noise_from_queue_to_balanser("Shlak2k16")
