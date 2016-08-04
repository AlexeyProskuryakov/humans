from wsgi.db import HumanStorage


def get_action_speed(action_name):
    """
    :param action_name:
    :return: human_name : count actions per hour
    """
    human_storage = HumanStorage()
    result = human_storage.human_log.aggregate([
        {"$match": {"action": action_name}},
        {"$group": {"_id": "$human_name",
                    "from": {"$min": "$time"},
                    "to": {"$max": "$time"},
                    "count": {"$sum": 1}}}])
    return dict(map(lambda y: (y["_id"], 3600/((float(y["to"]) - float(y["from"])) / float(y["count"]))), result))


if __name__ == '__main__':
    print get_action_speed("vote")
