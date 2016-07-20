from collections import Counter

from wsgi.rr_people.posting.queue import PostRedisQueue


def check_difference_between_humans():
    qp = PostRedisQueue()
    p16 = qp.show_all_posts_hashes("Shlak2k16")
    p15 = qp.show_all_posts_hashes("Shlak2k15")
    inter = set(p16).intersection(set(p15))
    print inter
    print len(inter), len(p16), len(p15)


def check_duplicates_in_queue():
    qp = PostRedisQueue()
    p16 = qp.show_all_posts_hashes("Shlak2k16")
    # p15 = qp.show_all_posts_hashes("Shlak2k15")
    c16 = Counter(p16)
    print c16.most_common(len(p16))


if __name__ == '__main__':
    # check_difference_between_humans()
    check_duplicates_in_queue()