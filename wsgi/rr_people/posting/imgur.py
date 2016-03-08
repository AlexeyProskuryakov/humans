import logging

from imgurpython import ImgurClient

from wsgi import properties
from wsgi.rr_people import RedditHandler, normalize
from wsgi.rr_people.posting import Generator, pp_objects, IMGUR

log = logging.getLogger("imgur")

MAX_PAGES = 5

def _get_post_id(url):
    return url

class ImgurPostsProvider(RedditHandler, Generator):
    def __init__(self):
        super(ImgurPostsProvider, self).__init__("imgur")
        self.client = ImgurClient(properties.ImgrClientID, properties.ImgrClientSecret)
        self.toggled = set()

    def get_copies(self, url):
        search_request = "url:\'%s\'" % _get_post_id(url)
        return list(self.reddit.search(search_request))

    def check(self, image):
        if not image.title or hash(normalize(image.title)) in self.toggled or image.height < 500 or image.width < 500:
            return False

        copies = self.get_copies(image.id)
        if len(copies) == 0:
            return True

    def generate_data(self, subreddit):
        for page in xrange(MAX_PAGES):
            q = "tag:%s OR title:%s OR album:%s OR meme:%s"%(subreddit, subreddit, subreddit, subreddit)
            log.info("retrieve for %s at page %s" % (subreddit, page))

            for entity in self.client.gallery_search(q=q, sort='time', page=page, window='week'):
                if entity.is_album:
                    images = self.client.get_album_images(entity.id)
                else:
                    images = [entity]

                for image in images:
                    if self.check(image):
                        self.toggled.add(hash(normalize(image.title)))
                        yield image.link, image.title


pp_objects[IMGUR] = ImgurPostsProvider

if __name__ == '__main__':
    imgrpp = ImgurPostsProvider()
    for url, title in imgrpp.generate_data('cringe'):
        print url, title
