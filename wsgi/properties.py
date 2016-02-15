# coding=utf-8
import logging
import os
import sys

__author__ = 'alesha'

# import urllib3.contrib.pyopenssl
# urllib3.contrib.pyopenssl.inject_into_urllib3()

def module_path():
    if hasattr(sys, "frozen"):
        return os.path.dirname(
                sys.executable
        )
    return os.path.dirname(__file__)


log_file_f = lambda x: os.path.join(module_path(), (x if x else "") + 'result.log')
log_file = os.path.join(module_path(), 'result.log')
cacert_file = os.path.join(module_path(), 'cacert.pem')

logger = logging.getLogger()

logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s[%(levelname)s]%(name)s|%(processName)s(%(process)d): %(message)s')
formatter_process = logging.Formatter('%(asctime)s[%(levelname)s]%(name)s|%(processName)s: %(message)s')
formatter_human = logging.Formatter('%(asctime)s[%(levelname)s]%(name)s|%(processName)s: %(message)s')

sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)

fh = logging.FileHandler(log_file)
fh.setFormatter(formatter)
logger.addHandler(fh)

fh.setFormatter(formatter_process)

fh_human = logging.FileHandler(log_file_f("he_"))
fh_human.setFormatter(formatter_human)
logging.getLogger("he").addHandler(fh_human)

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

SRC_SEARCH = "search"
SRC_OBSERV = "observation"

mongo_uri = "mongodb://3030:sederfes100500@ds055525.mongolab.com:55525/reddit_people"
db_name = "reddit_people"

ae_mongo_uri = "mongodb://localhost:27017"
ae_db_name = "ae"

c_queue_mongo_uri = mongo_uri
c_queue_db_name = db_name

c_queue_redis_addres = "pub-redis-11997.us-east-1-3.7.ec2.redislabs.com"
c_queue_redis_port = 11997

DEFAULT_LIMIT = 100
DEFAULT_SLEEP_TIME_AFTER_READ_SUBREDDIT = 60 * 60 * 4

min_copy_count = 2
min_comment_create_time_difference = 3600 * 24 * 10

shift_copy_comments_part = 5  # общее количество комментариев / это число  = сколько будет пропускаться
min_donor_comment_ups = 5
max_donor_comment_ups = 100000
min_donor_num_comments = 50

max_consuming = 90
min_consuming = 70

min_voting = 65
max_voting = 95

step_time_after_trying = 60
tryings_count = 10

time_step_less_iteration_power = 0.85

want_coefficient_max = 100

test_mode = os.environ.get("RR_TEST", "false").strip().lower() in ("true","1","yes")
print "TEST? ", test_mode

logger.info(
    "Reddit People MANAGEMENT SYSTEM STARTED... \nEnv:%s" % "\n".join(["%s:\t%s" % (k, v) for k, v in os.environ.iteritems()]))
