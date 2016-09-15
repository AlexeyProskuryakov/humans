# encoding:utf-8
import logging
from functools import reduce

import vk_api

from wsgi.vkontakter.gephi import GephiStreamer

from wsgi.vkontakter.vk_tools import VkTools, VkRequestsPool

DEFAULT_SCOPE = "friend,videos"


def get_human():
    return {"login": "+79046090659", "password": "sederfes100500@)"}


def captcha_handler(captcha):
    """
        При возникновении капчи вызывается эта функция и ей передается объект
        капчи. Через метод get_url можно получить ссылку на изображение.
        Через метод try_again можно попытаться отправить запрос с кодом капчи
    """

    key = input("Enter Captcha {0}: ".format(captcha.get_url())).strip()

    # Пробуем снова отправить запрос с капчей
    return captcha.try_again(key)


log = logging.getLogger("VK")


def get_session(human):
    vk_session = vk_api.VkApi(**dict(human, **{"captcha_handler": captcha_handler}))
    try:
        vk_session.authorization()
        return vk_session
    except vk_api.AuthorizationError as error_msg:
        log.exception(error_msg)
        return


def get_api(human):
    return get_session(human).get_api()


def get_all_by_word(words, depth=2):
    """
        VkTools.get_all позволяет получить все итемы, например со стены или
        получить все диалоги, или сообщения. При использовании get_all
        сокращается количество запросов к API за счет метода execute в 25 раз.
        Например за раз со стены можно получить 100 * 25 = 2500, где
        100 - максимальное количество постов, которое можно получить за один
        запрос.
    """
    vk_session = get_session(get_human())
    gephi = GephiStreamer()

    users = VkTools(vk_session).get_all('users.search', 1000, {'q': " ".join(words), "sort": 0, "fields": ["counters,counters.videos"]})
    videos = VkTools(vk_session).get_all("video.search", 10000, {"q": " ".join(words), "sort": 2, "adult": 1})
    video_users_ids = list(map(lambda x: x.get("owner_id"), videos.get("items")))
    users_ids = list(map(lambda x: x.get("id"), users["items"]))
    users_ids.extend(video_users_ids)

    log.info("words: %s \nnUsers count:%s \nVideos count:%s\n" % (words, users['count'], videos["count"]))
    _depth = 0
    while _depth <= depth:
        user_videos = VkTools(vk_session).get_all("users.get", 1000, {"user_ids":",".join([str(x) for x in users_ids[:900]]), "fields":["counters"]})

        # with VkRequestsPool(vk_session) as pool:
        #     videos = pool.method_one_param("users.get", key="owner_id", values=users_ids)
        # for user in users_ids:
        #     if user in videos:
        #         node = {"user_id": user, "count_videos": videos.get(user, {}).get("count")}
        #         gephi.add_node(node, id_key="user_id", )
        with VkRequestsPool(vk_session) as pool:
            friends = pool.method_one_param(
                'friends.get', key='user_id', values=users_ids)
        print(friends)


        for from_node, nodes in friends.items():
            for node in nodes:
                gephi.add_relation(from_node_id=from_node, to_node_id=node, relation_type="friend")

        new_users = reduce(lambda x, y: x.extend(y), map(lambda x: x.get("items"), friends.values()), [])

        users_ids = new_users

        _depth += 1


if __name__ == '__main__':
    get_all_by_word(["cuckold", "sissy"])
