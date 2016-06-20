from wsgi.rr_people.commenting.connection import CommentsStorage

if __name__ == '__main__':
    CommentsStorage("test")._clear()

    cs = CommentsStorage("test")
    cs.set_comment_info_ready("pfn1", "test_sub", "some text 1", "http://example1.com")
    cs.set_comment_info_ready("pfn1", "test_sub", "some text 2", "http://example2.com")
    cs.set_comment_info_ready("pfn1", "test_sub", "some text 3", "http://example3.com")
    cs.set_comment_info_ready("pfn2", "test_sub_2", "some text 2.1", "http://example21.com")
    cs.set_comment_info_ready("pfn2", "test_sub_2", "some text 2.2", "http://example22.com")
    cs.set_comment_info_ready("pfn2", "test_sub_2", "some text 2.3", "http://example23.com")

    ci = cs.get_comment_info("pfn1")
    ci2 = cs.get_comment_info("pfn1")
    ci3 = cs.get_comment_info("pfn1")

    print ci, ci2, ci3
    assert ci != ci2 != ci3 != None

    cs.set_commented(ci['_id'], "test1")
    cs.set_commented(ci2['_id'], "test1")
    cs.set_commented(ci3['_id'], "test1")

    commented = cs.get_posts_commented("test_sub")
    print "commented:", "\n".join([str(el) for el in commented])
