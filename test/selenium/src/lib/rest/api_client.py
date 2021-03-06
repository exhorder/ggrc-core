# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""GGRC REST API client."""
import urlparse

from lib import environment, users
from lib.service.rest import session_pool


def send_get(url):
  """Sends GET request to `url`."""
  url = urlparse.urljoin(environment.app_url, url)
  return _user_session().get(url)


def send_post(url, json_body):
  """Sends POST request to `url` with `json_body`."""
  url = urlparse.urljoin(environment.app_url, url)
  return _user_session().post(url, json=json_body)


def send_put(url, json_body, headers):
  """Sends PUT request to `url` with `json_body`."""
  url = urlparse.urljoin(environment.app_url, url)
  return _user_session().put(url, json=json_body, headers=headers)


def _user_session():
  """Returns a Requests session for the current user."""
  return session_pool.get_session(users.current_user())
