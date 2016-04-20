import logging
import random
from multiprocessing.process import Process

import time

from wsgi.db import HumanStorage
from wsgi.rr_people import A_POST
from wsgi.rr_people.posting.posts import PostsStorage, PostSource
from wsgi.rr_people.queue import CommentQueue, PostQueue

from wsgi.properties import YOUTUBE_DEVELOPER_KEY, YOUTUBE_API_VERSION, YOUTUBE_API_SERVICE_NAME, \
    force_post_manager_sleep_iteration_time

from apiclient.discovery import build
from apiclient.errors import HttpError

log = logging.getLogger("force_action_handler")

class PostBalancer():
    def __init__(self, pq=None):
        self.queue = pq or PostQueue("post_balancer")

    def add_post(self, post_source, sub, channel_id=None):
        pass

class PostHandler(object):
    def __init__(self, pq=None, ps=None):
        self.queue = pq or PostQueue("fah")
        self.posts_storage = ps or PostsStorage("fah")
        self.balancer = PostBalancer(pq=self.queue)

    def add_force_post(self, human_name, sub, post_source):
        if isinstance(post_source, PostSource):
            self.posts_storage.add_generated_post(post_source, sub)
            self.queue.put_force_action(human_name, {"action": A_POST, "sub": sub, "url_hash": post_source.url_hash})
        else:
            raise Exception("post_source is not post source!")

    def add_new_post(self, sub, post_source, channel_id=None):
        if isinstance(post_source, PostSource):
            self.posts_storage.add_generated_post(post_source, sub)
            self.balancer.add_post(post_source, sub, channel_id)
        else:
            raise Exception("post_source is not post source!")

    def add_ready_post(self, sub, post):
        pass

class MainPostManager(Process):
    def __init__(self, pq=None, ps=None, ms=None):
        super(MainPostManager, self).__init__()
        self.queue = pq or PostQueue("fpm")
        self.posts_storage = ps or PostsStorage("fpm")
        self.main_storage = ms or HumanStorage("fpm")
        self.action_handler = PostHandler(self.queue, self.posts_storage)
        self.posts_supplier = YoutubePostSupplier(self.posts_storage)

    def run(self):
        while 1:
            for human_data in self.main_storage.get_humans_info(
                    projection={"user": True, "subs": True, "channel_id": True}):
                channel = human_data.get("channel_id")
                if channel:
                    new_posts = self.posts_supplier.get_channel_videos(channel)
                    log.info("For [%s] found [%s] new forced posts:\n%s" % (
                    human_data.get("user"), len(new_posts), '\n'.join([str(post) for post in new_posts])))
                    for post in new_posts:
                        sub = random.choice(human_data.get("subs"))
                        self.action_handler.add_new_post(sub, post)
            time.sleep(force_post_manager_sleep_iteration_time)


YOUTUBE_URL = lambda x: "https://www.youtube.com/watch?v=%s" % x


class YoutubePostSupplier(object):
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

    def get_channel_videos(self, channel_id):
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


if __name__ == '__main__':
    yps = YoutubePostSupplier()
    videos = yps.get_channel_videos("UC1J8hBTK7oKIfgCMvN7Fwag")
    print videos
