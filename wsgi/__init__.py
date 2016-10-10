from datetime import datetime
import json
import logging
import os
import sys

from wsgi.properties import module_path, test_mode

log = logging.getLogger("wsgi")
CONFIG_FILE_NAME_ENV = "config_file"


def tst_to_dt(value):
    dt_format = "%H:%M:%S"
    dt = datetime.fromtimestamp(value)
    if (datetime.now() - dt).days > 1:
        dt_format += " %d.%m.%Y"
    return dt.strftime(dt_format)


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class ConfigManager(object):
    __metaclass__ = Singleton

    def __init__(self):
        config_file = os.environ.get(CONFIG_FILE_NAME_ENV, None)
        if not config_file:
            config_file = "%s/config.json" % module_path()
        if test_mode:
            config_file = "%s/config_test.json" % module_path()
        try:
            f = open(config_file, )
        except Exception as e:
            log.exception(e)
            log.error("Can not read config file %s" % config_file)
            sys.exit(-1)

        self.config_data = json.load(f)
        log.info("LOAD CONFIG DATA FROM %s:\n%s" % (
            config_file,
            "\n".join(["%s: %s" % (k, v) for k, v in self.config_data.iteritems()]))
                 )

    def get(self, name, type=str):
        if name in self.config_data:
            return type(self.config_data.get(name))
