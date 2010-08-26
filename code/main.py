# coding: UTF-8

import settings

from flask import Flask
app = Flask(__name__)
app.config.from_object('settings')

from flask import g
from flask import redirect
from flask import url_for
from flask import session
from flask import request
from flask import render_template
from flask import abort
from flask import flash
from flask import get_flashed_messages
from flask import json

from models import User

from deck.util import generate_key
from google.appengine.api.labs import taskqueue
from functools import wraps

from werkzeug.contrib.cache import GAEMemcachedCache
cache = GAEMemcachedCache()

def login_required(f):
    """
    redirects to the landing page if the user has no session
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('landing'))
        return f(*args, **kwargs)
    return decorated_function

def cache_page(timeout=5 * 60, key='view/%s'):
    """
    caches a full page in memcache, takes a timeout in seconds
    which specifies how long the cache should be valid.
    also allows a formatstring to be used as memcache key prefix.

    source:
    http://flask.pocoo.org/docs/patterns/viewdecorators/#caching-decorator
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            cache_key = key % request.path
            rv = cache.get(cache_key)
            if rv is not None:
                return rv
            rv = f(*args, **kwargs)
            cache.set(cache_key, rv, timeout=timeout)
            return rv
        return decorated_function
    return decorator

@app.before_request
def before_request():
    """
    adds facebook configuration data to g.
    if the session includes a user_key it will also try to fetch
    the user's object from memcache (or the datastore).
    if this succeeds, the user object is also added to g.
    """
    g.facebook_application_id = app.config['FACEBOOK_APPLICATION_ID']

    if 'user_key' in session:
        user = cache.get(session['user_key'])

        if user is None:
            # if the user is not available in memcache we fetch
            # it from the datastore
            user = User.get_by_key_name(session['user_key'])

            if user:
                # add the user object to memcache so we
                # don't need to hit the datastore next time
                cache.set(session['user_key'], user)

        g.user = user
    else:
        g.user = None

@app.route('/')
def landing():
    """
    renders the landing page template which includes example usage of
    jquery in combination with the facebook-connect js api
    """
    return render_template('landing.html')

@app.route('/session/', methods=['PUT'])
def session_from_facebook():
    """
    uses the facebook session cookie to create a site specific session.

    it will also fetch profile information from facebook and add
    the user to the datastore if it does not exist yet
    """
    import facebook
    # get facebook user id and token from facebook cookie
    fb_user = facebook.get_user_from_cookie(request.cookies,
                                            app.config['FACEBOOK_APPLICATION_ID'],
                                            app.config['FACEBOOK_APPLICATION_SECRET'])

    if fb_user:
        # check whether the user is already in the datastoreg
        user = User.all().filter('facebook_id =', str(fb_user['uid'])).get()

        if user is None:
            # if not we fetch his profile information via the facebook graph api
            graph = facebook.GraphAPI(fb_user["access_token"])
            profile = graph.get_object("me")

            # now we can put the user in the datastore
            user = User(key_name=generate_key(),
                        facebook_id=str(profile['id']),
                        facebook_token=request.values.get('access_token'),
                        email=profile['email'],
                        name=profile['name'])
            user.save()

        # last but not least we add the user's key to the session cookie
        session['user_key'] = user.key().name()
    return "ok"
