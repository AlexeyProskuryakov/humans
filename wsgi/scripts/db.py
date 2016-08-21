from wsgi.db import HumanStorage
from wsgi.rr_people.ae import AuthorsStorage


def ensure_normal_group_names():
    change = {"Shlak2k16": "eniki", "Shlak2k15": "beniki"}

    ae_storage = AuthorsStorage("scripts")
    hs = HumanStorage("scripts")
    for group_info in ae_storage.get_all_groups():
        cur_name = group_info.get("name")
        ae_storage.author_groups.update_many({"name": cur_name}, {"$set": {"name": change[cur_name]}})
        ae_storage.steps.update_many({"used": cur_name}, {"$set": {"used": change[cur_name]}})
        ae_storage.time_sequence.update_many({"used": cur_name}, {"$set": {"used": change[cur_name]}})
        hs.set_ae_group(cur_name, change[cur_name])
        print "%s ==> %s" % (cur_name, change[cur_name])


if __name__ == '__main__':
    # ae_storage = AuthorsStorage("scripts")
    # print ae_storage.get_all_groups()
    ensure_normal_group_names()
