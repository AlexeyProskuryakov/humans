import logging
import random

from imgurpython import ImgurClient

from wsgi import properties
from wsgi.rr_people import RedditHandler, normalize
from wsgi.rr_people.posting.generator import Generator
from wsgi.rr_people.posting.posts import PostSource

log = logging.getLogger("imgur")

MAX_PAGES = 5
IMGUR = "imgur"
MIN_UPS = 10

def _get_post_id(url):
    return url


class ImgurPostsProvider(RedditHandler, Generator):
    def __init__(self):
        super(ImgurPostsProvider, self).__init__(IMGUR)
        self.client = ImgurClient(properties.ImgrClientID, properties.ImgrClientSecret)
        self.toggled = set()

    def get_copies(self, url):
        search_request = "url:\'%s\'" % _get_post_id(url)
        return list(self.reddit.search(search_request))

    def check(self, image):
        if not image.title or hash(normalize(image.title)) in self.toggled or \
                        image.height < 500 or image.width < 500:
            return False

        copies = self.get_copies(image.id)
        if len(copies) == 0:
            return True

    def process_title(self, title):
        #todo fix by re
        if isinstance(title,str):
            title.replace("my", "")
            title.replace("My", "")
            title.replace("MY", "")
            title.replace("me", "")
            title.replace("Me", "")
            title.replace("ME", "")

        return title

    def generate_data(self, subreddit, key_words):
        try:#todo fix rate limit
            #todo add posts statuses
            for page in xrange(MAX_PAGES):
                q = "tag:%s OR title:%s OR album:%s" % (subreddit, subreddit, subreddit)
                log.info("retrieve for %s at page %s" % (subreddit, page))

                for entity in self.client.gallery_search(q=q, sort='time', page=page, window='week'):
                    if entity.is_album:
                        if entity.ups - entity.downs > 0 and entity.ups > MIN_UPS:
                            images = [random.choice(self.client.get_album_images(entity.id))]
                        else:
                            images=[]
                    else:
                        images = [entity]

                    for image in images:
                        if self.check(image):
                            self.toggled.add(hash(normalize(image.title)))
                            yield PostSource(image.link, self.process_title(image.title))
        except Exception as e:
            log.exception(e)
            return

if __name__ == '__main__':
    imgrpp = ImgurPostsProvider()
    for url, title in imgrpp.generate_data('cringe', []):
        print url, title
