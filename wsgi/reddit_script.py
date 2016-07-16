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
    for post_ in get_posts():
        url = post_.get("url")
        sub = post_.get("for_sub")
        title = post_.get("title")
        result = create_post(url, title, sub, h)
        print result