# coding=utf-8
import logging
import os
import sys

__author__ = 'alesha'


def module_path():
    if hasattr(sys, "frozen"):
        return os.path.dirname(
            sys.executable
        )
    return os.path.dirname(__file__)


cacert_file = os.path.join(module_path(), 'cacert.pem')

logger = logging.getLogger()

logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s[%(levelname)s]%(name)s|%(processName)s(%(process)d): %(message)s')
formatter_process = logging.Formatter('%(asctime)s[%(levelname)s]%(name)s|%(processName)s: %(message)s')
formatter_human = logging.Formatter('%(asctime)s[%(levelname)s]%(name)s|%(processName)s: %(message)s')

sh = logging.StreamHandler()
sh.setFormatter(formatter)
logger.addHandler(sh)

fh = logging.FileHandler(os.path.join(module_path(), "humans.log"), mode="w")
fh.setFormatter(formatter)
logger.addHandler(fh)

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

logger.info("MODULE PATH: %s" % module_path())

TIME_TO_COMMENT_SPOILED = 3600 * 24 * 30 * 6

redis_max_connections = 2

SEC = 1
MINUTE = 60
HOUR = MINUTE * 60
DAY = HOUR * 24
WEEK = DAY * 7
WEEK_DAYS = {0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU"}

AE_MIN_COMMENT_KARMA = 10000
AE_MIN_LINK_KARMA = 10000
AE_MIN_SLEEP_TIME = 6 * HOUR
AE_MAX_SLEEP_TIME = 12 * HOUR
AE_AUTHOR_MIN_ACTIONS = 1000

AE_GROUPS = ["eniki", "beniki"]
AE_DEFAULT_GROUP = "eniki"

# for posts sequence evaluate
AVG_ACTION_TIME = 3 * MINUTE
COUNT_SHUFFLE_ITERATIONS = 5
DEFAULT_MIN_POSTS_COUNT = 75
DEFAULT_POSTS_SEQUENCE_CACHED_TTL = 5 * AVG_ACTION_TIME

MIN_STEP_TIME = 60
MIN_TIMES_BETWEEN = {"post": 9 * 60, "comment": 3 * 60}

POLITIC_FREE_LIFE = "free_life"
POLITIC_WORK_HARD = "work_hard"
DEFAULT_POLITIC = POLITIC_FREE_LIFE
POLITICS = [POLITIC_WORK_HARD, POLITIC_FREE_LIFE]

DEFAULT_LIMIT = 500
# DEFAULT_LIMIT = 20

default_counters_thresholds = {"consume": {"min": 80, "max": 90},
                               "vote": {"min": 80, "max": 85},
                               "comment": {"min": 70, "max": 80}
                               }

sleep_between_net_request_if_error = 60
tryings_count = 10

want_coefficient_max = 100

WORKED_PIDS_QUERY = "python"

YOUTUBE_API_VERSION = "v3"
YOUTUBE_TAG_SUB = "sub:"
YOUTUBE_TAG_TITLE = "pt:"

force_post_manager_sleep_iteration_time = 5 * MINUTE  # время через которое он будет сканировать ютуб

test_mode = os.environ.get("RR_TEST", "false").strip().lower() in ("true", "1", "yes")
print "TEST? ", test_mode

logger.info(
    "Reddit People MANAGEMENT SYSTEM STARTED... \nEnv:%s" % "\n".join(
        ["%s:\t%s" % (k, v) for k, v in os.environ.iteritems()]))
