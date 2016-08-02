from wsgi.rr_people.human import Human
from wsgi.rr_people.posting.posts import PostsStorage


def get_posts():
    ps = PostsStorage()
    return list(ps.posts.find({}))


def create_post(url, title, sub, by):
    sub_ = by.reddit.get_subreddit(sub)
    result = sub_.submit(save=True, title=title, url=url)
    return result


if __name__ == '__main__':
    h = Human("Shlak2k15")
    result = h.reddit.get_submission(submission_id="t3_4rdu5r"[3:])
    print result
