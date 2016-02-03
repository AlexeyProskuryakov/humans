from collections import defaultdict
import time
from datetime import datetime

import praw

from wsgi.rr_people import DEFAULT_USER_AGENT

MAX_COUNT = 10000

def to_show(el):
    full_name = el.fullname
    result = el.__dict__
    result['fullname'] = full_name

    result["created_utc"] = el.created_utc
    result["subreddit"] = el.subreddit.display_name
    result["ups"] = el.ups
    return result


def to_save(post):
    return {"video_id": post.get("video_id"),
            "video_url": post.get("url") or post.get("video_url"),
            "title": post.get("title"),
            "ups": post.get("ups"),
            "reddit_url": post.get("permalink") or post.get("reddit_url"),
            "subreddit": post.get("subreddit"),
            "fullname": post.get("fullname"),
            "reposts_count": post.get("reposts_count"),
            "created_dt": datetime.fromtimestamp(post.get("created_utc")),
            "created_utc": post.get("created_utc"),
            "comments_count": post.get("num_comments")
            }


def get_interested_posts(sbrdt):
    result = []
    cur = int(time.time())
    before = int(time.time()) - (3600 * 24 * 7 * 2)
    reddit = praw.Reddit(user_agent=DEFAULT_USER_AGENT)
    for post in reddit.search("timestamp:%s..%s"%(before, cur), limit=MAX_COUNT, count=MAX_COUNT, subreddit=sbrdt, syntax="cloudsearch"):
        post_info = to_save(to_show(post))
        result.append(post_info)
    return result



def _get_coefficients(posts_clusters, n):
    result = {}
    for dt, posts in posts_clusters.iteritems():
        result[dt] = float(sum(map(lambda post: post.get("ups") + post.get("comments_count"), posts))) / len(posts)
    return result


def evaluate_statistics(sbrdt_name):
    """
    Evaluating statistics for input subreddit

    :param sbrdt_name:
    :return: 2 dicts of weights and days and hours at day.
    """
    posts = get_interested_posts(sbrdt_name)

    days = defaultdict(list)
    hours = defaultdict(list)
    for post in posts:
        days[post.get("created_dt").weekday()].append(post)
        hours[post.get("created_dt").hour].append(post)

    n = len(posts)
    print "eval statistic for %s posts"%n
    return _get_coefficients(days, n), _get_coefficients(hours, n)


if __name__ == '__main__':
    days, hours = evaluate_statistics(sbrdt_name="cringe")
    print "\n".join(["%s : %s" % (k, v) for k, v in days.iteritems()])

    h_keys = hours.keys()
    h_keys.sort()

    print "\n".join(["%s : %s" % (k, hours[k]) for k in h_keys])
