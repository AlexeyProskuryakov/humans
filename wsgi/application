#!/usr/bin/python
import os

from server import app as application

virtenv = os.path.join(os.environ.get('OPENSHIFT_PYTHON_DIR', '.'), 'virtenv')
virtualenv = os.path.join(virtenv, 'bin/activate_this.py')
try:
    execfile(virtualenv, dict(__file__=virtualenv))
except IOError:
    pass

if __name__ == '__main__':

    from wsgiref.simple_server import make_server

    httpd = make_server('localhost', 8051, application)

    httpd.serve_forever()
