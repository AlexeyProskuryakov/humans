from wsgi.rr_people.commenting.connection import CommentsStorage

if __name__ == '__main__':
    cs = CommentsStorage("test", clear=True)
    cs.set_comment_info_ready("pfn1", "test_sub", "some text 1", "http://example1.com")
    cs.set_comment_info_ready("pfn1", "test_sub", "some text 2", "http://example2.com")
    cs.set_comment_info_ready("pfn1", "test_sub", "some text 3", "http://example3.com")
    cs.set_comment_info_ready("pfn2", "test_sub_2", "some text 2.1", "http://example21.com")
    cs.set_comment_info_ready("pfn2", "test_sub_2", "some text 2.2", "http://example22.com")
    cs.set_comment_info_ready("pfn2", "test_sub_2", "some text 2.3", "http://example23.com")

    ci = cs.get_comment_info("pfn1")
    ci2 = cs.get_comment_info("pfn1")
    ci3 = cs.get_comment_info("pfn1")

    print "comment info:"
    print ci, '\n', ci2, '\n', ci3
    assert ci != ci2 != ci3 != None

    cs.set_commented(ci['_id'], "test2")

    ready = cs.get_posts_ready_for_comment("test_sub")
    assert len(ready) == 2
    commented = cs.get_posts_commented("test_sub")
    assert len(commented) == 1

    cs.set_commented(ci2['_id'], "test2")

    ready = cs.get_posts_ready_for_comment("test_sub")
    assert len(ready) == 1
    commented = cs.get_posts_commented("test_sub")
    assert len(commented) == 2

    cs.set_commented(ci3['_id'], "test3")

    ready = cs.get_posts_ready_for_comment("test_sub")
    assert len(ready) == 0
    commented = cs.get_posts_commented("test_sub")
    assert len(commented) == 3

    print "commented:\n", "\n".join([str(el) for el in commented])
