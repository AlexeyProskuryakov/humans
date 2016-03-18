from wsgi.rr_people import RedditHandler
from wsgi.rr_people.posting.generator import Generator

YOUTUBE = "youtube"

class YouTubePostGenerator(RedditHandler, Generator):
    def __init__(self):
        super(YouTubePostGenerator, self).__init__(name=YOUTUBE)

    def generate_data(self, subreddit, key_words):
        pass

