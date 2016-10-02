from datetime import datetime

multithread = False
multiprocess = False


def tst_to_dt(value):
    dt_format = "%H:%M:%S"
    dt = datetime.fromtimestamp(value)
    if (datetime.now() - dt).days > 1:
        dt_format += " %d.%m.%Y"
    return dt.strftime(dt_format)
