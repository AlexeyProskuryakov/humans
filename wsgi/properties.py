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

mongo_uri = "mongodb://3030:sederfes100500@ds055525.mongolab.com:55525/reddit_people"
db_name = "reddit_people"

# ae_mongo_uri = "mongodb://localhost:27017"
# ae_db_name = "ae"

ae_mongo_uri = "mongodb://aliper:sederfes100500@ds025449.mlab.com:25449/ae"
ae_db_name = "ae"

comments_mongo_uri = "mongodb://milena:sederfes100500@ds015760.mlab.com:15760/humans_comments"
comments_db_name = "humans_comments"
expire_low_copies_posts = 3600 * 24 * 7

comment_redis_address = "pub-redis-11997.us-east-1-3.7.ec2.redislabs.com"
comment_redis_port = 11997
comment_redis_password = "sederfes100500"

states_redis_address = "pub-redis-17140.us-east-1.1.azure.garantiadata.com"
states_redis_port = 17140
states_redis_password = "sederfes100500"

posts_redis_address = "pub-redis-11691.us-east-1-4.2.ec2.garantiadata.com"
posts_redis_port = 11691
posts_redis_password = "sederfes100500"

redis_max_connections = 2

SEC = 1
MINUTE = 60
HOUR = MINUTE * 60
DAY = HOUR * 24
WEEK = DAY * 7
WEEK_DAYS = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU"}

TIME_TO_WAIT_NEW_COPIES = 3600 * 24
TIME_TO_RELOAD_SUB_POSTS = 3600 * 2  # at live random in consumer

AE_MIN_COMMENT_KARMA = 10000
AE_MIN_LINK_KARMA = 10000
AE_MIN_SLEEP_TIME = 6 * HOUR
AE_MAX_SLEEP_TIME = 12 * HOUR
AE_AUTHOR_MIN_ACTIONS = 1000

AE_ADD_AUTHORS = True

DEFAULT_LIMIT = 500
# DEFAULT_LIMIT = 20
DEFAULT_SLEEP_TIME_AFTER_GENERATE_DATA = 60 * 60 * 4

min_copy_count = 3
min_comment_create_time_difference = 3600 * 24 * 10

shift_copy_comments_part = 5  # общее количество комментариев / это число  = сколько будет пропускаться
min_donor_comment_ups = 5
max_donor_comment_ups = 100000
min_donor_num_comments = 50

max_consuming = 80
min_consuming = 60

min_voting = 65
max_voting = 85

step_time_after_trying = 60
tryings_count = 10

time_step_less_iteration_power = 0.85

want_coefficient_max = 100

# imgur properties
ImgrClientID = 'd7e9f9350ebe5a8'
ImgrClientSecret = '945c124e48fd9ca208788c70028d7e8d8c7dc7c1'

# youtube props
YOUTUBE_DEVELOPER_KEY = "AIzaSyCYF4GPkVpdYjZ5RpDaSMcbpRpfkavnUzc"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

force_post_manager_sleep_iteration_time = 3600  # время через которое он будет сканировать ютуб

test_mode = os.environ.get("RR_TEST", "false").strip().lower() in ("true", "1", "yes")
print "TEST? ", test_mode

logger.info(
    "Reddit People MANAGEMENT SYSTEM STARTED... \nEnv:%s" % "\n".join(["%s:\t%s" % (k, v) for k, v in os.environ.iteritems()]))

WORKED_PIDS_QUERY = "python"