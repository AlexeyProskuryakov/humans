# coding=utf-8

import os
from uuid import uuid4

import praw
from datetime import datetime
import time
from flask import Flask, logging, request, render_template, session, url_for, g
from flask.json import jsonify
from flask_debugtoolbar import DebugToolbarExtension
from flask_login import LoginManager, login_user, login_required, logout_user
from werkzeug.utils import redirect

from wsgi.properties import want_coefficient_max
from wsgi.rr_people import S_STOP, S_WORK, S_SUSPEND
from wsgi.rr_people.he import HumanConfiguration, HumanOrchestra
from wsgi.db import HumanStorage
from wsgi.rr_people.reader import CommentSearcher, get_post_and_comment_text, SUB_QUEUE
from wsgi.wake_up import WakeUp

__author__ = '4ikist'

log = logging.getLogger("web")
cur_dir = os.path.dirname(__file__)
app = Flask("Humans", template_folder=cur_dir + "/templates", static_folder=cur_dir + "/static")

app.secret_key = 'foo bar baz'
app.config['SESSION_TYPE'] = 'filesystem'


def tst_to_dt(value):
    return datetime.fromtimestamp(value).strftime("%H:%M %d.%m.%Y")


app.jinja_env.filters["tst_to_dt"] = tst_to_dt

if os.environ.get("test", False):
    log.info("will run at test mode")
    app.config["SECRET_KEY"] = "foo bar baz"
    app.debug = True
    app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
    toolbar = DebugToolbarExtension(app)

url = "http://rr-alexeyp.rhcloud.com"
wu = WakeUp(url)
wu.daemon = True
wu.start()


@app.route("/wake_up/<salt>", methods=["POST"])
def wake_up(salt):
    return jsonify(**{"result": salt})


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

db = HumanStorage()


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
    return render_template("main.html", **{"username": user.name, "url": wu.what})


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
    global human_orchestra

    if request.method == "POST":
        subreddits_raw = request.form.get("sbrdts")
        subreddits = subreddits_raw.strip().split()

        human_name = request.form.get("human-name")
        human_name = human_name.strip()
        log.info("Add subreddits: \n%s\n to human with name: %s" % ('\n'.join([el for el in subreddits]), human_name))

        db.set_human_subs(human_name, subreddits)

        human_orchestra.add_human(human_name)

        return redirect(url_for('humans_info', name=human_name))

    humans_info = db.get_humans_info()
    worked_humans = human_orchestra.humans.keys()
    return render_template("humans_management.html",
                           **{"humans": humans_info,
                              "worked_humans": worked_humans})


@app.route("/humans/<name>", methods=["POST", "GET"])
@login_required
def humans_info(name):
    global human_orchestra

    if request.method == "POST":
        if request.form.get("stop"):
            db.set_human_live_state(name, S_SUSPEND, "web")
            return redirect(url_for('humans_info', name=name))

        if request.form.get("start"):
            db.set_human_live_state(name, S_WORK, "web")
            human_orchestra.add_human(name)
            return redirect(url_for('humans_info', name=name))

        config = HumanConfiguration(request.form)
        db.set_human_live_configuration(name, config)
        human_orchestra.toggle_human_config(name)

    human_log = db.get_log_of_human(name, 100)
    stat = db.get_log_of_human_statistics(name)

    human_cfg = db.get_human_config(name)

    return render_template("humans_info.html", **{"human_name": name,
                                                  "human_stat": stat,
                                                  "human_log": human_log,
                                                  "human_live_state": human_cfg.get("live_state"),
                                                  "subs": human_cfg.get("subs", []),
                                                  "config": human_cfg.get("live_config") or HumanConfiguration().data,
                                                  "ss": human_cfg.get("ss", []),
                                                  "friends": human_cfg.get("frds", []),
                                                  "want_coefficient": want_coefficient_max
                                                  })


comment_searcher = CommentSearcher(db)


@app.route("/comment_search/start/<sub>", methods=["POST"])
@login_required
def start_comment_search(sub):
    comment_searcher.start_retrieve_comments(sub)
    while 1:
        state = comment_searcher.comment_queue.get_state(sub)
        if "work" in state:
            return jsonify({"state":state})
        time.sleep(1)




@app.route("/posts")
def posts():
    subs = comment_searcher.comment_queue.get_sbrdts_states()
    qc_s = {}
    for sub in subs.keys():
        queued_comments = comment_searcher.comment_queue.show_all(sub)
        qc_s[sub] = queued_comments

    return render_template("posts_and_comments.html", **{"subs": subs, "qc_s": qc_s})


@app.route("/comment_search/info/<sub>")
def comment_search_info(sub):
    posts = db.get_posts_found_comment_text()
    comments = comment_searcher.comment_queue.show_all(sub)
    if comments:
        for i, post in enumerate(posts):
            post['is_in_queue'] = post.get("fullname") in comments
            if post["is_in_queue"]:
                post['text'] = comments.get(post.get("fullname"), "")
            posts[i] = post

    posts_commented = db.get_posts_commented()
    subs_ = db.human_config.aggregate([{"$group": {"_id": "$subs"}}])
    subs = []
    for sbs in subs_:
        for sb in sbs["_id"]:
            if sub != sb:
                subs.append(sb)
    subs_states = comment_searcher.comment_queue.get_sbrdts_states()
    state = comment_searcher.comment_queue.get_state(sub)

    result = {"posts_found_comment_text": posts,
              "posts_commented": posts_commented,
              "sub": sub,
              "a_subs": subs,
              "subs_states": subs_states,
              "state": state}
    return render_template("comment_search_info.html", **result)


if __name__ == '__main__':
    print os.path.dirname(__file__)
    app.run(port=65010)
