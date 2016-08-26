from wsgi.rr_people.commenting.connection import CommentHandler


def test_consume_comment():
    '''
    Use it function with test connection in read

def create_test_comment(sub="ts", text="test_text", fn="test_fn", link="http://test_link"):
    cs = CommentsStorage("test")

    text_hash = hash(sub + text + fn)
    cs.comments.delete_one({"fullname": fn, "text_hash": text_hash})
    result = cs.set_comment_info_ready(fn, text_hash, sub, text, link)

    assert result.inserted_id
    comment_id = str(result.inserted_id)

    found = cs.comments.find_one({"_id": ObjectId(comment_id)})
    assert found.get("_id") == result.inserted_id
    return comment_id, sub


if __name__ == '__main__':
    queue = CommentQueue("test")

    cid, sub = create_test_comment()
    queue.put_comment(sub, cid)

    cid, sub = create_test_comment(sub="tst")
    queue.put_comment(sub, cid)

    cid, sub = create_test_comment(text="foo_bar_baz")
    queue.put_comment(sub, cid)

    cid, sub = create_test_comment(fn="fuckingfullname")
    queue.put_comment(sub, cid)

    cid, sub = create_test_comment(link="huipizdadjugurda")
    queue.put_comment(sub, cid)

    '''
    ch = CommentHandler("test")

    cid = ch.pop_comment_id("ts")
    comment = ch.get_comment_info(cid)
    assert comment
    assert comment.get("text") == "test_text"
    assert comment.get("fullname") == "test_fn"
    assert comment.get("post_url") == "http://test_link"
    assert comment.get("sub") == "ts"

    cid = ch.pop_comment_id("ts")
    comment = ch.get_comment_info(cid)
    assert comment
    assert comment.get("text") == "foo_bar_baz"
    assert comment.get("fullname") == "test_fn"
    assert comment.get("post_url") == "http://test_link"
    assert comment.get("sub") == "ts"

    cid = ch.pop_comment_id("ts")
    comment = ch.get_comment_info(cid)
    assert comment
    assert comment.get("text") == "test_text"
    assert comment.get("fullname") == "fuckingfullname"
    assert comment.get("post_url") == "http://test_link"
    assert comment.get("sub") == "ts"

    cid = ch.pop_comment_id("ts")
    comment = ch.get_comment_info(cid)
    assert comment
    assert comment.get("text") == "test_text"
    assert comment.get("fullname") == "test_fn"
    assert comment.get("post_url") == "huipizdadjugurda"
    assert comment.get("sub") == "ts"

    cid = ch.pop_comment_id("tst")
    comment = ch.get_comment_info(cid)
    assert comment
    assert comment.get("text") == "test_text"
    assert comment.get("fullname") == "test_fn"
    assert comment.get("post_url") == "http://test_link"
    assert comment.get("sub") == "tst"

    print "OK"

if __name__ == '__main__':
    test_consume_comment()