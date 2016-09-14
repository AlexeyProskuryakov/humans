# coding=utf-8
import calendar
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from uuid import uuid4
import time

import praw
from flask import Flask, logging, request, render_template, session, url_for, g, flash
from flask.json import jsonify
from flask_debugtoolbar import DebugToolbarExtension
from flask_login import LoginManager, login_user, login_required, logout_user
from werkzeug.utils import redirect

from wsgi.db import HumanStorage
from wsgi.properties import want_coefficient_max, WEEK, AE_GROUPS, AE_DEFAULT_GROUP, POLITICS
from wsgi.rr_people import A_POST
from wsgi.rr_people.ae import AuthorsStorage, time_hash, hash_info
from wsgi.rr_people.commenting.connection import CommentHandler
from wsgi.rr_people.he_manage import HumanOrchestra
from wsgi.rr_people.human import HumanConfiguration
from wsgi.rr_people.posting.posts import PostsStorage
from wsgi.rr_people.posting.posts_important import ImportantYoutubePostSupplier
from wsgi.rr_people.posting.posts_sequence import PostsSequenceStore, PostsSequenceHandler
from wsgi.rr_people.states.processes import ProcessDirector
from wsgi.wake_up import WakeUp

__author__ = '4ikist'

import sys

reload(sys)
sys.setdefaultencoding('utf-8')

log = logging.getLogger("web")
cur_dir = os.path.dirname(__file__)
app = Flask("Humans", template_folder=cur_dir + "/templates", static_folder=cur_dir + "/static")

app.secret_key = 'foo bar baz'
app.config['SESSION_TYPE'] = 'filesystem'


def tst_to_dt(value):
    return datetime.fromtimestamp(value).strftime("%H:%M %d.%m.%Y")


def array_to_string(array):
    return " ".join([str(el) for el in array])


app.jinja_env.filters["tst_to_dt"] = tst_to_dt
app.jinja_env.globals.update(array_to_string=array_to_string)

if os.environ.get("test", False):
    log.info("will run at test mode")
    app.config["SECRET_KEY"] = "foo bar baz"
    app.debug = True
    app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
    toolbar = DebugToolbarExtension(app)

url = "http://rr-alexeyp.rhcloud.com"
wu = WakeUp()
wu.store.add_url(url)
wu.daemon = True
wu.start()


@app.route("/wake_up/<salt>", methods=["POST"])
def wake_up(salt):
    return jsonify(**{"result": salt})


@app.route("/wake_up", methods=["GET", "POST"])
def wake_up_manage():
    if request.method == "POST":
        urls = request.form.get("urls")
        urls = urls.split("\n")
        for url in urls:
            url = url.strip()
            if url:
                wu.store.add_url(url)

    urls = wu.store.get_urls()
    return render_template("wake_up.html", **{"urls": urls})


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

db = HumanStorage(name="hs server")


class User(object):
    def __init__(self, name, pwd):
        self.id = str(uuid4().get_hex())
        self.auth = False
        self.active = False
        self.anonymous = False
        self.name = name
        self.pwd = pwd

    def is_authenticated(self):
        return self.auth

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id


class UsersHandler(object):
    def __init__(self):
        self.users = {}
        self.auth_users = {}

    def get_guest(self):
        user = User("Guest", "")
        user.anonymous = True
        self.users[user.id] = user
        return user

    def get_by_id(self, id):
        found = self.users.get(id)
        if not found:
            found = db.users.find_one({"user_id": id})
            if found:
                user = User(found.get('name'), found.get("pwd"))
                user.id = found.get("user_id")
                self.users[user.id] = user
                found = user
        return found

    def auth_user(self, name, pwd):
        authed = db.check_user(name, pwd)
        if authed:
            user = self.get_by_id(authed)
            if not user:
                user = User(name, pwd)
                user.id = authed
            user.auth = True
            user.active = True
            self.users[user.id] = user
            return user

    def logout(self, user):
        user.auth = False
        user.active = False
        self.users[user.id] = user

    def add_user(self, user):
        self.users[user.id] = user
        db.add_user(user.name, user.pwd, user.id)


usersHandler = UsersHandler()
log.info("users handler was initted")
usersHandler.add_user(User("3030", "89231950908zozo"))


@app.before_request
def load_user():
    if session.get("user_id"):
        user = usersHandler.get_by_id(session.get("user_id"))
    else:
        # user = None
        user = usersHandler.get_guest()
    g.user = user


@login_manager.user_loader
def load_user(userid):
    return usersHandler.get_by_id(userid)


@login_manager.unauthorized_handler
def unauthorized_callback():
    return redirect(url_for('login'))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login = request.form.get("name")
        password = request.form.get("password")
        remember_me = request.form.get("remember") == u"on"
        user = usersHandler.auth_user(login, password)
        if user:
            try:
                login_user(user, remember=remember_me)
                return redirect(url_for("main"))
            except Exception as e:
                log.exception(e)

    return render_template("login.html")


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route("/")
@login_required
def main():
    if request.method == "POST":
        _url = request.form.get("url")
        wu.what = _url

    user = g.user
    return render_template("main.html", **{"username": user.name})


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
    stat = db.get_human_statistics(name)

    human_cfg = db.get_human_config(name)

    human_state = human_orchestra.get_human_state(name)
    politic = db.get_human_post_politic(name)

    errors = db.get_errors(name)

    return render_template("human_info.html", **{"human_name": name,
                                                 "human_stat": stat,
                                                 "human_log": human_log,
                                                 "human_live_state": human_state,
                                                 "subs": human_cfg.get("subs", []),
                                                 "config": human_cfg.get("live_config") or HumanConfiguration().data,
                                                 "ss": human_cfg.get("ss", []),
                                                 "friends": human_cfg.get("frds", []),
                                                 "want_coefficient": want_coefficient_max,
                                                 "channel_id": human_cfg.get("channel_id"),

                                                 "politic": politic,
                                                 "politics": POLITICS,
                                                 "posts_sequence_config": human_cfg.get("posts_sequence_config", {}),
                                                 "ae_group": human_cfg.get("ae_group", AE_DEFAULT_GROUP),
                                                 "ae_groups": AE_GROUPS,

                                                 "errors": errors,
                                                 })


@app.route("/humans/<name>/state", methods=["post"])
@login_required
def human_state(name):
    return jsonify(**{"state": human_orchestra.get_human_state(name), "human": name})


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


try:
    ips = ImportantYoutubePostSupplier()
except Exception as e:
    pass


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


@app.route("/humans/<name>/channel_id", methods=["POST"])
@login_required
def update_channel_id(name):
    data = json.loads(request.data)
    channel_id = data.get("channel_id")
    db.set_human_channel_id(name, channel_id)
    if channel_id:
        result, err = ips.load_new_posts_for_human(name, channel_id)
        if not err:
            return jsonify(**{"ok": True, "loaded": result})
        return jsonify(**{"ok": False, "error": err})

    return jsonify(**{"ok": True, "loaded": 0})


sequence_storage = PostsSequenceStore("server")
ae_storage = AuthorsStorage("as server")


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
    if posts_sequence:
        real_posted = map(lambda x: [get_point_x(time_hash(datetime.fromtimestamp(x.get("time")))), p_y - 0.25, 1, 1],
                          db.get_last_actions(name, A_POST))
        candidates = map(lambda x: [get_point_x(x), p_y, 1, 1], [int(x) for x in posts_sequence.middle])
        posts = map(lambda x: [get_point_x(x), p_y, 1, 1], [int(x) for x in posts_sequence.right])
        passed_posts = map(lambda x: [get_point_x(x), p_y, 1, 1], [int(x) for x in posts_sequence.left])

        return jsonify(**{
            "current": [get_point_x(time_hash(datetime.fromtimestamp(time.time()))), 0.75, 1, 1],
            "work": work_result,
            "posts": posts,
            "posts_passed": passed_posts,
            "real": real_posted,
            "candidates": candidates,
            'metadata': "By days: %s; All: %s; Time prev: %s; Generate time: %s" % (
                posts_sequence.metadata,
                sum(posts_sequence.metadata),
                hash_info(posts_sequence.prev_time),
                tst_to_dt(float(posts_sequence.generate_time or time.time())),
            )})
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
process_director = ProcessDirector("server")
post_storage = PostsStorage(name="server")


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
    print os.path.dirname(__file__)
    app.run(port=65010)
