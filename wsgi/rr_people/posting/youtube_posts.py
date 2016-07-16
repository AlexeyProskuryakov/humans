import logging
import re

from apiclient.discovery import build
from apiclient.errors import HttpError

from wsgi.properties import YOUTUBE_DEVELOPER_KEY, YOUTUBE_API_VERSION, YOUTUBE_API_SERVICE_NAME
from wsgi.rr_people.posting.posts import PostsStorage, PostSource

log = logging.getLogger("youtube")

YOUTUBE_URL = lambda x: "https://www.youtube.com/watch?v=%s" % x

y_url_re = re.compile("((y2u|youtu)\.be\/|youtube\.com\/watch\?v\=)(?P<id>[a-zA-Z0-9-]+)")


class YoutubeChannelsHandler(object):
    def __init__(self, ps=None):
        self.youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                             developerKey=YOUTUBE_DEVELOPER_KEY)
        self.posts_storage = ps or PostsStorage(name="youtube posts supplier")

    def _get_sub_on_tags(self, tags):
        for tag in tags:
            if "sub:" in tag:
                return tag.replace("sub:", "").strip()

    def _form_posts_on_videos_info(self, items):
        result = []
        for video_info in items:
            id = video_info.get("id")
            if id:
                title = video_info.get("snippet", {}).get("title") or video_info.get("snippet", {}).get("description")
                sub = self._get_sub_on_tags(video_info.get("snippet", {}).get("tags", []))
                if not sub:
                    log.warn("Video [%s] (%s) without sub; Skip this video :(" % (id, title))
                    continue
                url = YOUTUBE_URL(id)
                ps = PostSource(url=url, title=title, for_sub=sub)
                result.append(ps)
                log.info("Generate important post: %s", ps)
            else:
                log.warn("video: \n%s\nis have not id :( " % video_info)
        return result

    def _get_new_videos_ids(self, video_ids):
        result = []
        for v_id in video_ids:
            if self.posts_storage.get_post_state(str(hash(YOUTUBE_URL(v_id)))):
                continue
            result.append(v_id)
        return result

    def get_new_channel_videos(self, channel_id):
        items = []
        q = {"channelId": channel_id,
             "part": "snippet",
             "maxResults": 50,
             "order": "date"}
        while 1:
            search_result = self.youtube.search().list(**q).execute()
            video_ids = filter(lambda x: x,
                               map(lambda x: x.get("id", {}).get("videoId"),
                                   search_result.get('items', [])))
            new_videos_ids = self._get_new_videos_ids(video_ids)
            log.info("found %s posts in channel: %s; not saved: %s" % (len(video_ids), channel_id, len(new_videos_ids)))

            if new_videos_ids:
                videos_data = self.youtube.videos().list(
                    **{"id": ",".join(new_videos_ids), "part": "snippet"}).execute()
                prep_videos = self._form_posts_on_videos_info(videos_data.get("items", []))
                items.extend(prep_videos)
            else:
                break

            if not search_result.get("nextPageToken"):
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
    # print yps.get_video_id("https://www.youtube.com/watch?v=cQL3JIYg9Io&feature=youtu.be")
    # channel_id = yps.get_channel_id("https://www.youtube.com/watch?v=cQL3JIYg9Io&feature=youtu.be")

    videos = yps.get_new_channel_videos("UCEMga_5kPDRwFXaJM1NQryA")  # 3030 channel
    # videos = yps.get_new_channel_videos("UCNBfdM4qeFvyFag-34wnCeQ") #alesha channel
    # videos = yps.get_new_channel_videos("UCqojywe2RqVPgALVyV0LrWg")
    channel_id = yps.get_channel_id("https://www.youtube.com/watch?v=LuXBjs7eN4o")
    print channel_id
