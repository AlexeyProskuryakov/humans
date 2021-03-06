# coding=utf-8
import calendar
import json
import os
import random
import string
from collections import defaultdict
from datetime import datetime, timedelta
import time

import praw
import requests
from flask import Flask, logging, request, render_template, url_for, g, flash
from flask import session
from flask.json import jsonify
from flask_login import LoginManager, login_required

from werkzeug.utils import redirect

from wsgi import tst_to_dt, array_to_string
from wsgi.db import HumanStorage
from wsgi.properties import want_coefficient_max, WEEK, AE_GROUPS, AE_DEFAULT_GROUP, POLITICS, \
    default_counters_thresholds, test_mode
from wsgi.rr_people import A_POST, S_RELOAD_COUNTERS, A_CONSUME, A_VOTE, A_COMMENT, S_FORCE_POST_IMPORTANT
from wsgi.rr_people.ae import AuthorsStorage, time_hash, hash_info, hash_length_info
from wsgi.rr_people.commenting.connection import CommentHandler
from wsgi.rr_people.he_manage import HumanOrchestra
from wsgi.rr_people.human import HumanConfiguration
from wsgi.rr_people.posting.posts import PostsStorage, CNT_NOISE, EVERY
from wsgi.rr_people.posting.posts_sequence import PostsSequenceStore, PostsSequenceHandler
from wake_up.views import wake_up_app
from rr_lib.users.views import users_app, usersHandler

__author__ = '4ikist'

import sys

reload(sys)
sys.setdefaultencoding('utf-8')

log = logging.getLogger("web")

cur_dir = os.path.dirname(__file__)
app = Flask("Humans", template_folder=cur_dir + "/templates", static_folder=cur_dir + "/static")

app.secret_key = 'foo bar baz'
app.config['SESSION_TYPE'] = 'filesystem'

app.register_blueprint(wake_up_app, url_prefix="/wake_up")
app.register_blueprint(users_app, url_prefix="/u")

app.jinja_env.filters["tst_to_dt"] = tst_to_dt
app.jinja_env.globals.update(array_to_string=array_to_string)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@app.before_request
def load_user():
    if session.get("user_id"):
        user = usersHandler.get_by_id(session.get("user_id"))
    else:
        user = usersHandler.get_guest()
    g.user = user


@login_manager.user_loader
def load_user(userid):
    return usersHandler.get_by_id(userid)


@login_manager.unauthorized_handler
def unauthorized_callback():
    return redirect(url_for('users_api.login'))


@app.route("/time-now")
def time_now():
    return tst_to_dt(time.time())


@app.route("/")
@login_required
def main():
    user = g.user
    return render_template("main.html", **{"username": user.name})


db = HumanStorage(name="hs server")

REDIRECT_URI = "http://rr-alexeyp.rhcloud.com/authorize_callback"
C_ID = None
C_SECRET = None


@app.route("/humans/add_credential", methods=["GET", "POST"])
@login_required
def human_auth_start():
    global C_ID
    global C_SECRET
    global REDIRECT_URI

    if request.method == "GET":
        return render_template("human_add_credentials.html", **{"url": False})
    if request.method == "POST":
        C_ID = request.form.get("client_id")
        C_SECRET = request.form.get("client_secret")
        user = request.form.get("user")
        pwd = request.form.get("pwd")
        redirect_uri = request.form.get("redirect_uri")
        if redirect_uri:
            REDIRECT_URI = redirect_uri

        db.prepare_human_access_credentials(C_ID, C_SECRET, REDIRECT_URI, user, pwd)

        r = praw.Reddit("Hui")
        r.set_oauth_app_info(C_ID, C_SECRET, REDIRECT_URI)
        url = r.get_authorize_url("KEY",
                                  'creddits,modcontributors,modconfig,subscribe,wikiread,wikiedit,vote,mysubreddits,submit,modlog,modposts,modflair,save,modothers,read,privatemessages,report,identity,livemanage,account,modtraffic,edit,modwiki,modself,history,flair',
                                  refreshable=True)
        return render_template("human_add_credentials.html", **{"url": url})


@app.route("/authorize_callback")
@login_required
def human_auth_end():
    state = request.args.get('state', '')
    code = request.args.get('code', '')

    r = praw.Reddit("Hui")
    r.set_oauth_app_info(C_ID, C_SECRET, REDIRECT_URI)
    info = r.get_access_information(code)
    user = r.get_me()
    r.set_access_credentials(**info)
    db.update_human_access_credentials_info(user.name, info)
    return render_template("authorize_callback.html", **{"user": user.name, "state": state, "info": info, "code": code})


human_orchestra = HumanOrchestra()


@app.route("/humans", methods=["POST", "GET"])
@login_required
def humans():
    if request.method == "POST":
        subreddits_raw = request.form.get("human_subs")
        subreddits = subreddits_raw.strip().split()

        human_name = request.form.get("for-human-name")
        human_name = human_name.strip()
        log.info("Add subreddits: \n%s\n to human with name: %s" % ('\n'.join([el for el in subreddits]), human_name))

        db.set_human_subs(human_name, list(set(subreddits)))
        # human_orchestra.start_human(human_name)

        return redirect(url_for('humans_info', name=human_name))

    humans_info = db.get_humans_info()
    for human in humans_info:
        human['state'] = human_orchestra.get_human_state(human['user'])

    return render_template("humans_management.html",
                           **{"humans": humans_info})


@app.route("/humans/<name>", methods=["POST", "GET"])
@login_required
def humans_info(name):
    if request.method == "POST":
        if request.form.get("stop"):
            human_orchestra.suspend_human(name)
            return redirect(url_for('humans_info', name=name))

        if request.form.get("start"):
            human_orchestra.start_human(name)
            return redirect(url_for('humans_info', name=name))

        if request.form.get("delete"):
            pwd = request.form.get("pwd")
            if db.check_user(g.user.name, pwd):
                human_orchestra.delete_human(name)
                db.remove_human_data(name)
                return redirect(url_for("humans"))
            else:
                flash(u"Идите нахуй! Пароль не верен.")
        if request.form.get("config"):
            config = HumanConfiguration(request.form)
            db.set_human_live_configuration(name, config)

    human_log = db.get_log_of_human(name, 100)
    human_state_log = db.get_human_state_log(name)
    stat = db.get_human_statistics(name)

    human_cfg = db.get_human_config(name)

    human_state = human_orchestra.get_human_state(name)
    politic = db.get_human_post_politic(name)

    errors = db.get_errors(name)

    return render_template("human_info.html", **{"human_name": name,
                                                 "human_stat": stat,
                                                 "human_log": human_log,
                                                 "human_state_log": human_state_log,
                                                 "human_live_state": human_state,
                                                 "subs": human_cfg.get("subs", []),
                                                 "config": human_cfg.get("live_config") or HumanConfiguration().data,
                                                 "ss": human_cfg.get("ss", []),
                                                 "friends": human_cfg.get("frds", []),
                                                 "counters": human_cfg.get("counters").get("counters"),
                                                 "counters_percents": human_cfg.get("counters").get("percents"),
                                                 "counters_threshold": human_cfg.get("counters").get("threshold", {}),
                                                 "counters_threshold_min_max": human_cfg.get("counters_thresholds"),
                                                 "want_coefficient": want_coefficient_max,
                                                 "channel_id": human_cfg.get("channel_id"),

                                                 "politic": politic,
                                                 "politics": POLITICS,
                                                 "posts_sequence_config": human_cfg.get("posts_sequence_config", {}),
                                                 "ae_group": human_cfg.get("ae_group", AE_DEFAULT_GROUP),
                                                 "ae_groups": AE_GROUPS,

                                                 "errors": errors,

                                                 })


@app.route("/humans/<name>/state", methods=["POST"])
@login_required
def human_state(name):
    return jsonify(**{"state": human_orchestra.get_human_state(name), "human": name})


@app.route("/humans/<name>/post_important", methods=["POST"])
@login_required
def human_post_important(name):
    human_orchestra.states.set_human_state(name, S_FORCE_POST_IMPORTANT)
    return jsonify(**{"ok": True})


@app.route("/humans/<name>/config", methods=["GET"])
@login_required
def human_config(name):
    if request.method == "GET":
        config_data = db.get_human_config(name)
        if config_data:
            config_data = dict(config_data)
            return jsonify(**{"ok": True, "data": config_data})

    return jsonify(**{"ok": False})


@app.route("/humans/<name>/politic", methods=["POST"])
@login_required
def human_politic(name):
    politic_name = request.form.get("politic")
    db.set_human_post_politic(name, politic_name)
    return redirect(url_for('humans_info', name=name))


@app.route("/humans/<name>/counters/recreate", methods=["POST"])
@login_required
def human_refresh_counters(name):
    human_orchestra.states.set_human_state(name, S_RELOAD_COUNTERS)
    counters = db.get_human_counters(name) or {}
    return jsonify(**dict({"ok": True}, **counters))


@app.route("/humans/<name>/counters/set_thresholds", methods=["POST"])
@login_required
def human_set_threshold_counters(name):
    data = json.loads(request.data)
    counters_thresh = {
        A_CONSUME: {"max": int(data.get(A_CONSUME, {}).get("max", default_counters_thresholds[A_CONSUME]["max"])),
                    "min": int(data.get(A_CONSUME, {}).get("min", default_counters_thresholds[A_CONSUME]["min"]))},
        A_VOTE: {"max": int(data.get(A_VOTE, {}).get("max", default_counters_thresholds[A_VOTE]["max"])),
                 "min": int(data.get(A_VOTE, {}).get("min", default_counters_thresholds[A_VOTE]["min"]))},
        A_COMMENT: {"max": int(data.get(A_COMMENT, {}).get("max", default_counters_thresholds[A_COMMENT]["max"])),
                    "min": int(data.get(A_COMMENT, {}).get("min", default_counters_thresholds[A_COMMENT]["min"]))}
    }
    db.set_human_counters_thresholds_min_max(name, counters_thresh)
    human_orchestra.states.set_human_state(name, S_RELOAD_COUNTERS)
    counters = db.get_human_counters(name) or {}
    return jsonify(**dict({"ok": True}, **counters))


@app.route("/humans/<name>/counters", methods=["POST"])
@login_required
def human_get_counters(name):
    counters = db.get_human_counters(name) or {}
    return jsonify(**dict({"ok": True}, **counters))


@app.route("/humans/<name>/clear_errors", methods=["POST"])
@login_required
def human_clear_errors(name):
    db.clear_errors(name)
    return jsonify(**{"ok": True})


@app.route("/humans/<name>/clear_statistic", methods=["POST"])
@login_required
def human_clear_statistic(name):
    result = db.clear_human_statistic(name)
    if result.modified_count == 1:
        return jsonify(**{"ok": True})
    return jsonify(**{"ok": False})


@app.route("/humans/<name>/clear_log", methods=["POST"])
@login_required
def human_clear_log(name):
    db.clear_errors(name)
    return jsonify(**{"ok": True})


generators_url = "http://generators-shlak0bl0k.rhcloud.com/load_important" if not test_mode else "http://localhost:65010/load_important"


@app.route("/humans/<name>/channel_id", methods=["POST"])
@login_required
def update_channel_id(name):
    data = json.loads(request.data)
    channel_id = data.get("channel_id")
    db.set_human_channel_id(name, channel_id)
    if channel_id:
        key = ''.join(random.choice(string.lowercase) for _ in range(20))
        result = requests.post(generators_url, data=json.dumps({
            "name": name,
            "channel_id": channel_id,
            "key": key}))
        if result.status_code != 200:
            return jsonify(**{"ok": False, "error": result.content})

        result = json.loads(result.content)
        if result.get("key") == key:
            return jsonify(**result)
    return jsonify(**{"ok": True, "loaded": 0})


sequence_storage = PostsSequenceStore("server")
ae_storage = AuthorsStorage("as server")
post_storage = PostsStorage(name="server")


@app.route("/sequences/info/<name>", methods=["GET"])
@login_required
def sequences(name):
    def get_point_x(x):
        now = datetime.now()
        dt = now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second) + timedelta(
            seconds=x)
        return calendar.timegm(dt.timetuple()) * 1000

    w_y = 0.5
    p_y = 1
    ae_group = db.get_ae_group(name)
    work_sequence = ae_storage.get_time_sequence(ae_group)
    work_result = []
    for w_t in work_sequence:
        start = int(w_t[0])
        stop = int(w_t[1])
        if start > stop:
            work_result.append([get_point_x(start), w_y, 1, (WEEK - start) * 1000])
            work_result.append([get_point_x(0), w_y, 1, (stop) * 1000])
        else:
            work_result.append([get_point_x(start), w_y, 1, (stop - start) * 1000])

    posts_sequence = sequence_storage.get_posts_sequence(name)
    counters = post_storage.get_posting_counters(name)
    noise = int(counters.get(CNT_NOISE, 0))
    counters["next_important"] = EVERY - noise
    next_times = posts_sequence.get_time_for_nearest(time_hash(datetime.now()), EVERY - noise)
    if next_times:
        n_noise, n_important = next_times
        next_times = {"noise": hash_length_info(n_noise),
                      "important": hash_length_info(n_important)}

    if posts_sequence:
        real_posted = map(lambda x: [get_point_x(time_hash(datetime.fromtimestamp(x.get("time")))), p_y - 0.25, 1, 1],
                          db.get_last_actions(name, A_POST))
        posts = map(lambda x: [get_point_x(x), p_y, 1, 1], [int(x) for x in posts_sequence.right])
        passed_posts = map(lambda x: [get_point_x(x), p_y, 1, 1], [int(x) for x in posts_sequence.left])

        return jsonify(**{
            "current": [get_point_x(time_hash(datetime.fromtimestamp(time.time()))), 0.75, 1, 1],
            "work": work_result,
            "posts": posts,
            "posts_passed": passed_posts,
            "real": real_posted,
            'metadata': "By days: %s; All: %s; Time prev: %s; Generate time: %s" % (
                posts_sequence.metadata,
                sum(posts_sequence.metadata),
                hash_info(posts_sequence.prev_time),
                tst_to_dt(float(posts_sequence.generate_time or time.time())),
            ),
            "next_times": next_times,
            "counters": counters,
        })
    else:
        return jsonify(**{"work": work_result})


@app.route("/sequences/manage/<name>", methods=["POST"])
@login_required
def sequences_manage(name):
    ae_group = request.form.get("ae-group")
    min_c = int(request.form.get('min-seq-count'))
    max_c = int(request.form.get('max-seq-count'))

    db.set_ae_group(name, ae_group)
    db.set_human_posts_sequence_config(name, min_c, max_c)
    posts_handler = PostsSequenceHandler(name, ae_store=ae_storage, hs=db, ae_group=ae_group, ps_store=sequence_storage)
    posts_handler.evaluate_new()

    return redirect(url_for('humans_info', name=name))


@app.route("/global_configuration/<name>", methods=["GET", "POST"])
@login_required
def configuration(name):
    if request.method == "GET":
        result = db.get_global_config(name)
        if result:
            return jsonify(**{"ok": True, "result": result})
        return jsonify(**{"ok": False, "error": "no config with name %s" % name})
    elif request.method == "POST":
        try:
            data = json.loads(request.data)
            result = db.set_global_config(name, data)
            return jsonify(**{"ok": True, "result": result})
        except Exception as e:
            log.warning(e.message)
            return jsonify(**{"ok": False, "error": e})


# posts & comments
comment_handler = CommentHandler("server")


@app.route("/queue/comments/<name>", methods=["GET"])
@login_required
def queue_of_comments(name):
    subs = db.get_subs_of_human(name)
    comments = defaultdict(list)
    for sub in subs:
        comments_ids = comment_handler.get_all_comments_ids(sub)
        comments[sub] = list(comment_handler.get_comments_by_ids(comments_ids, projection={"_id": False}))
        log.info("find %s comments for sub %s" % (len(comments[sub]), sub))
    return render_template("comments_queue.html", **{"human_name": name, "comments": comments, "subs": subs})


if __name__ == '__main__':
    port = 65010
    while 1:
        try:
            print "starts at %s..." % port
            app.run(port=port)
        except Exception as e:
            port += 1
            print "fuck i try to: %s" % port
