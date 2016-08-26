from wsgi.db import HumanStorage
from wsgi.rr_people import RedditHandler
from wsgi.rr_people.commenting.connection import CommentHandler


def test_comments_fullname():
    ch = CommentHandler()
    main = HumanStorage()
    rh = RedditHandler()
    for sub in main.get_all_humans_subs():
        comment_posts_fullnames = ch.get_all_comments_ids(sub)
        print "comments for sub: ", sub, "\n", "\n".join(comment_posts_fullnames)
        for fullname in comment_posts_fullnames:
            try:
                result = rh.reddit.get_submission(submission_id=fullname[3:])
                print result
            except Exception as e:
                print e

if __name__ == '__main__':
    test_comments_fullname()
