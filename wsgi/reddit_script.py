from wsgi.rr_people import RedditHandler
from wsgi.rr_people.human import Human


def post(url, title, sub, by="Shlak2k15"):
    human = Human(by)
    sub_ = human.reddit.get_subreddit(sub)
    result = sub_.submit(save=True, title=title, url=url)
    return result

if __name__ == '__main__':
    result = post("https://vimeo.com/173941652","Norwich shows its solidarity","vidoes")
    print result