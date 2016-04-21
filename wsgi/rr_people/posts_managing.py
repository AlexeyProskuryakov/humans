import logging
import random
from multiprocessing.process import Process

import time

import re

from wsgi.db import HumanStorage, DBHandler

from wsgi.rr_people.posting.posts import PostsStorage, PostSource
from wsgi.rr_people.queue import PostQueue

from wsgi.properties import YOUTUBE_DEVELOPER_KEY, YOUTUBE_API_VERSION, YOUTUBE_API_SERVICE_NAME, \
    force_post_manager_sleep_iteration_time

from apiclient.discovery import build
from apiclient.errors import HttpError

log = logging.getLogger("force_action_handler")


class BacthStorage(DBHandler):
    def __init__(self, name="?", ):
        super(BacthStorage, self).__init__("bulk storage %s" % name)
        self.bulks = self.db.get_collection("humans_posts_bulks")
        if not self.bulks:
            self.bulks = self.db.create_collection("humans_posts_bulks")
            self.bulks.create_index("human_name")
            self.bulks.create_index("count")

    def get_human_post_batch(self, human_name):
        for bulk in self.bulks.find({"human_name":human_name}).sort("count", -1):
            yield PostBatch(self, bulk)


class PostBatch():
    def __init__(self, store, data):
        if isinstance(store, BacthStorage):
            self.store = store
        else:
            raise Exception("store is not bulk store")

        self.channels = set(data.get("channels"))
        self.human_name = data.get("human_name")
        self.bulk_id = data.get("_id")
        self._elements_count = data.get("count")

    @property
    def elements_count(self):
        return self._elements_count

    def contains_channel(self, channel_id):
        if not channel_id: return False
        return channel_id in self.channels

    def add(self, url_hash, channel_id, to_start=False):
        self.channels.add(channel_id)
        modify = {"$addToSet": {"channels": channel_id}, "$inc": {"count": 1}}
        if not to_start:
            modify["$push"] = {"url_hashes": url_hash}
        else:
            modify["$push"] = {"url_hashes": {"$each": [url_hash], "$position": 0}}
        self.store.bulks.update_one({"_id": self.bulk_id}, modify)
        self._elements_count += 1

    def __del__(self):
        print "delete bulk %s"%self.bulk_id
        self.store.bulks.delete_one({"_id":self.bulk_id})


class PostBalancer():
    def __init__(self, pq, ps):
        self.queue = pq

    def add_post(self, url_hash, channel_id, important=False, human_name=None, sub=None):
        pass


class PostHandler(object):
    def __init__(self, name="?", pq=None, ps=None):
        self.queue = pq or PostQueue("ph %s" % name)
        self.posts_storage = ps or PostsStorage("ph %s" % name)
        self.youtube = YoutubeChannelsHandler(self.posts_storage)
        self.balancer = PostBalancer(pq=self.queue)

    def add_new_post(self, human_name, post_source, sub, channel_id):
        if isinstance(post_source, PostSource):
            self.posts_storage.add_generated_post(post_source, sub)
            self.balancer.add_post(post_source.url_hash, channel_id, important=True, human_name=human_name)
        else:
            raise Exception("post_source is not post source!")

    def add_ready_post(self, sub, post_source):
        if isinstance(post_source, PostSource):
            channel_id = self.youtube.get_channel_id(post_source.url)
            self.balancer.add_post(post_source.url_hash, channel_id, sub=sub)
        else:
            raise Exception("post_source is not post source!")

    def get_post(self, human_name):
        pass

    def set_post_state(self, url_hash, new_state):
        self.posts_storage.set_post_state(url_hash, new_state)


class YoutubePostSupplier(Process):
    """
    Process which get humans config and retrieve channel_id, after retrieve new posts from it and
    """

    def __init__(self, pq=None, ps=None, ms=None):
        super(YoutubePostSupplier, self).__init__()
        self.queue = pq or PostQueue("fpm")
        self.posts_storage = ps or PostsStorage("fpm")
        self.main_storage = ms or HumanStorage("fpm")
        self.post_handler = PostHandler(self.queue, self.posts_storage)
        self.posts_supplier = YoutubeChannelsHandler(self.posts_storage)

    def run(self):
        while 1:
            for human_data in self.main_storage.get_humans_info(
                    projection={"user": True, "subs": True, "channel_id": True}):
                channel = human_data.get("channel_id")
                if channel:
                    new_posts = self.posts_supplier.get_new_channel_videos(channel)
                    log.info("For [%s] found [%s] new posts:\n%s" % (
                        human_data.get("user"), len(new_posts), '\n'.join([str(post) for post in new_posts])))
                    for post in new_posts:
                        subs = human_data.get("subs_to_post") or human_data.get("subs")
                        sub = random.choice(subs)
                        self.post_handler.add_new_post(human_data.get("user"), post, sub, channel)
            time.sleep(force_post_manager_sleep_iteration_time)


YOUTUBE_URL = lambda x: "https://www.youtube.com/watch?v=%s" % x

y_url_re = re.compile("((y2u|youtu)\.be\/|youtube\.com\/watch\?v\=)(?P<id>[a-zA-Z0-9]+)")


class YoutubeChannelsHandler(object):
    def __init__(self, ps=None):
        self.youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                             developerKey=YOUTUBE_DEVELOPER_KEY)
        self.posts_storage = ps or PostsStorage(name="youtube posts supplier")

    def _form_posts_on_videos_info(self, items):
        result = []
        for video_info in items:
            id = video_info.get("id", {}).get("videoId")
            title = video_info.get("snippet", {}).get("title") or video_info.get("snippet", {}).get("description")
            if id:
                url = YOUTUBE_URL(id)
                result.append(PostSource(url=url, title=title))
            else:
                log.warn("video: \n%s\nis have not id :( " % video_info)
        return result

    def _get_new_videos(self, posts):
        result = []
        for post in posts:
            if self.posts_storage.get_post_state(post.url_hash):
                break
            result.append(post)
        return result

    def get_new_channel_videos(self, channel_id):
        items = []
        q = {"channelId": channel_id,
             "part": "snippet",
             "maxResults": 50,
             "order": "date"}
        while 1:
            search_result = self.youtube.search().list(**q).execute()
            prep_videos = self._form_posts_on_videos_info(search_result.get("items"))
            new_videos = self._get_new_videos(prep_videos)
            items.extend(new_videos)
            if len(new_videos) < len(prep_videos):
                break

            total_results = search_result.get("pageInfo").get("totalResults")
            if len(items) == total_results or not search_result.get("nextPageToken"):
                break
            else:
                q['pageToken'] = search_result.get("nextPageToken")

        return items

    def get_video_id(self, post_url):
        found = y_url_re.findall(post_url)
        if found:
            found = found[0]
            return found[-1]

    def get_channel_id(self, post_url):
        video_id = self.get_video_id(post_url)
        if not video_id: return
        video_response = self.youtube.videos().list(
            id=video_id,
            part='snippet'
        ).execute()
        for item in video_response.get('items'):
            snippet = item.get("snippet")
            return snippet.get("channelId")


if __name__ == '__main__':
    yps = YoutubeChannelsHandler()
    # videos = yps.get_channel_videos("UC1J8hBTK7oKIfgCMvN7Fwag")
    print yps.get_channel_id("https://youtu.be/QtxlCsVKkvY?t=1")
