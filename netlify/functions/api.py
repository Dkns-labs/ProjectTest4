import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app
import serverless_wsgi


def handler(event, context):
    return serverless_wsgi.handle_request(app, event, context)
