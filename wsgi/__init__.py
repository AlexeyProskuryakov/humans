from datetime import datetime
import logging

from wsgi.properties import module_path, test_mode

log = logging.getLogger("wsgi")

def array_to_string(array):
    return " ".join([str(el) for el in array])


def tst_to_dt(value):
    dt_format = "%H:%M:%S"
    dt = datetime.fromtimestamp(value)
    if (datetime.now() - dt).days > 1:
        dt_format += " %d.%m.%Y"
    return dt.strftime(dt_format)

