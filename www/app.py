#-*- coding:utf-8 -*-

#这是服务器的首页，即为生成服务web.app的地方

import logging;logging.basicConfig(level=logging.INFO)
import asyncio,os
import orm,handler
from jinja2 import Environment,FileSystemLoader
from aiohttp import web
from coroweb import get,add_routes,add_static

#初始化jinja2模板
def init_jinja2(app,**kw):
	logging.info('init jinja2...')
	options = dict(
		    autoescape = kw.get('autoescape',True),
		    block_start_string = kw.get('block_start_string','{%'),
		    block_end_string = kw.get('block_end_string','%}'),
		    variable_start_string = kw.get('variable_start_string','{{'),
		    variable_end_string = kw.get('variable_end_string','}}'),
		    auto_reload = kw.get('auto_reload',True)
		)
	path = kw.get('path',None)
	if path is None:
		path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates')
	logging.info('set jinja2 template path: %s' %str(path))
	env = Environment(loader=FileSystemLoader(path),**options)
	filters = kw.get('filters',None)
	if filters is not None:
		for name, f in filters.items():
			env.filters[name] = f
	#给app增添'__templating__'属性，值为jinja2的env，可以通过调用env.get_template来获取模板
	app['__templating__'] = env

#middlewares拦截器
async def logger_factory(app,handler):
	async def logger(request):
		logging.info('Request: %s %s' %(request.method,request.path))
		return (await handler(request))
	return logger

#这里解析的是request里的数据
async def data_factory(app,handler):
	async def parse_data(request):
		if request.method == 'POST':
			if request.content_type.startswith('application/json'):
				request.__data__ = await request.json()
				logging.info('request json: %s' %str(request.__data__))
			elif request.content_type.startswith('application/x-www-form-urlencoded'):
				request.__data__ = await request.post()
				logging.info('request form: %s ' %str(request.__data__))
		return (await handler(request))
	return parse_data

#对handler的返回结果进行处理，使其符合aiohttp的response格式
async def response_factory(app,handler):
	async def response(request):
		logging.info('Response handler...')
		r = await handler(request)
		if isinstance(r,web.StreamResponse):
			#StreamResponse是aiohttp的标准返回对象，不需要处理
			return r
		if isinstance(r,bytes):
			resp = web.Response(body = r)
			resp.content_type = 'application/octer-stream'
			return resp
		if isinstance(r,str):
			if r.startswith('redirect:'):
				return web.HTTPFound(r[9:])
			resp = web.Response(body = r.encode('utf-8'))
			resp.content_type='text/html;charset=utf-8'
			return resp
		if isinstance(r,dict):
			#在handler里用'__template__'属性来作为键指向返回对象（html模板
			template = r.get('__template__')
			if template is None:
				resp = web.Response(body = json.dumps(r,ensure_ascii = False,default = lambda o:o.__dict__).encode('utf-8'))
				resp.content_type = 'application/json;charset=utf-8'
				return resp
			else:
				resp = web.Response(body = app['__templating__']).get_template(template).render(**r).encode('utf-8')
				resp.content_type = 'text/html;charset=utf-8'
				return resp
		if isinstance(r,int) and r >= 100 and r<600:
			return web.Response(r)
		if isinstance(r,tuple) and len(r) == 2:
			t,m = r
			if isinstance(t,int) and t>=100 and t<600:
				return web.Response(t,str(m))
		#default
		resp = web.Response(body = str(r).encode('utf-8'))
		resp.conent_type= 'text/plain;charset=utf-8'
		return resp
	return response

async def datetime_filter(t):
	delta = int(time.time() - t)
	if delta <60:
		return u'1分钟前'
	if delta <3600:
		return u'%s分钟前' %(delta //60)
	if delta <86400:
		return u'%s小时前' %(delta//3600)
	if delta <604800:
		return u'%s天前' %(delta//86400)
	dt = datetime.formtimestamp(t)
	return u'%s年%s月%s日' %(dt.year,dt.month,dt.day)

async def init(loop):
	await orm.create_pool(loop = loop,user = 'sa',password='******',db='blogs')
	app = web.Application(loop = loop,middlewares=[logger_factory,response_factory])
	init_jinja2(app,filters=dict(datetime = datetime_filter))
	add_routes(app,'handler')
	add_static(app)
	srv = await loop.create_server(app.make_handler(),'127.0.0.1',9000)
	logging.info('server started at http://127.0.0.1:9000...')
	return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
