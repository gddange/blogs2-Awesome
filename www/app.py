#-*- coding:utf-8 -*-

#这是服务器的首页，即为生成服务web.app的地方

import logging;logging.basicConfig(level=logging.INFO)
import asyncio
from aiohttp import web

def index(request):
	#return web.Response(body='<h1>Awesome</h1>' ,headers={'content-type':'text/html'}),这里是按照http格式传递数据的，content-type等信息是放在headers里的
	return web.Response(body='<h1>Awesome</h1>',content_type='text/html')

async def init(loop):
	app = web.Application(loop = loop)
	#将resource进行dispatcher
	app.router.add_route('GET','/',index)
	#开始服务
	srv = await loop.create_server(app.make_handler(),'127.0.0.1',8000)
	logging.info('Server started at 127.0.0.1 on 8000...')
	return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()