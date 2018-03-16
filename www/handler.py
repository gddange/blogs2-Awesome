#-*- coding:utf-8 -*-

from aiohttp import web
from coroweb import get,post

@get('/')
def index(request):
	return web.Response(body="<h1>Awesome!It's successful!</h1>",content_type='text/html')