#-*- coding:utf-8 -*-

#coroweb是web框架，类似于flask那种，需要完成从URL到函数之间的连接，编写了框架之后，用户就只需要编写URL处理函数
import asyncio,functools,inspect,logging,os
from urllib import parse
from aiohttp import web
from apis import APIError


#编写get post装饰器，这样handler就不需要从request中获取get和post信息
def get(path):
	'''
	define decorator @get('/path')
	'''

	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args,**kw):
			return func(*args,**kw)
		wrapper.__method__ = 'GET'
		wrapper.__path__ = path
		return wrapper
	return decorator

def post(path):
	'''
	define decorator @post('/path')
	'''

	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args,**kw):
			return func(*args,**kw)
		wrapper.__method__= 'POST'
		wrapper.__path__ = 'path'
		return wrapper
	return decorator

'''
POSTIONAL_ONLY:位置参数
KEYWORD_ONLY:命名关键词参数
VAR_POSITIONAL:可选参数，*args
VAR_KEYWORD:关键词参数，**args
POSTIONAL_OR_KEYWORD:位置或者关键字参数
'''
#因为URL处理函数fn中会有参数，所以需要将这些参数分类取出来
#获取位置参数，位置参数的默认值为空
def get_required_kw_args(fn):
	args = []
	#inspect.signature(fn)可以获取fn函数中的所有参数信息
	params = inspect.signature(fn).parameters
	for name,param in params.items():
		if param.kind == inspect.Parameter.POSITIONAL_ONLY and param.default == inspect.Parameter.empty:
			args.append(name)
		return tuple(args)

#获取fn中所有关键字参数
def get_named_kw_args(fn):
	args = []
	params = inspect.signature(fn).parameters
	for name,param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY:
			args.append(name)
	return tuple(args)

#判断fn中是否有关键字参数
def has_named_kw_args(fn):
	params = inspect.signature(fn).parameters
	for name,param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY:
			return True

#判断fn中是否关键词参数**args
def has_var_kw_args(fn):
	params = inspect.signature(fn).parameters
	for name,param in params.items():
		if param.kind == inspect.Parameter.VAR_KEYWORD:
			return True

#判断fn中是否有’request'参数，request不能为位置参数，在python 里面位置参数必须放在参数顺位第一位
def has_request_arg(fn):
	params = inspect.signature(fn).parameters
	found = False
	for name,param in params.items():
		if name == 'request':
			found = True
			continue
		if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
			raise ValueError('request parameter must be the last named parameter in function: %s%s' %(fn.__name__,str(sig)))
	return found


class RequestHandler(object):

	def __init__(self,app,fn):
		self._app = app
		self._func = fn
		#分类获取fn中的参数
		self._has_request_arg = has_request_arg(fn)
		self._has_var_kw_args = has_var_kw_args(fn)
		self._has_named_kw_args = has_named_kw_args(fn)
		self._named_kw_args = get_named_kw_args(fn)
		self._required_kw_args = get_required_kw_args(fn)

	#定义了__call__函数，类就可以像是调用函数那样去调用
	async def __call__(self,request):
		kw = None
		if self._has_named_kw_args or self._has_var_kw_args or self._has_request_arg:
			#判断是否具有关键字关键词参数,如果有的话，要分post和get情况对其进行处理
			if request.method == 'POST':
				#在POST情况下，app接受客户端传递过来的数据，对其数据类型进行判断
				if not request.content_type:
					return web.HTTPBadRequest('Missing Conetnt-Type')
				ct = request.conetnt_typt.lower()
				#判断客户端传递过来的数据类型
				if ct.startswith('application/json'):
					params = await request.json()
					if not isinstance(params,dict):
						#json数据是字典类型的
						return web.HTTPBadRequest('JSON body must be obejct.')
					kw = params
				elif ct.startswith('application/x-www-form-urlencode') or ct.startswith('multipart/form-data'):
					params = await request.post()
					kw = dict(**params)
				else:
					return web.HTTPBadRequest('Unsupported Conent-Type: %s' %request.content_type)
			if request.method =='GET':
				qs = request.query_string
				if qs:
					kw = dict()
					for k,v in parse.parse_qs(qs,True).items():
						kw[k] = v[0]
		if kw is None:
			#说明fn并没有接收到除了request意外的其他从客户端传递来的参数
			kw = dict(**request.match_info)
		else:
			if not self._has_var_kw_args and self._named_kw_args:
				#remove all unnamed kw,此时没有关键词参数
				copy = dict()
				for name in self._named_kw_args:
					if name in kw:
						copy[name] = kw[name]
				kw = copy
			for k,v in request.match_info.items():
				if k in kw:
					logging.warning('Duplicate arg name in named arg and kw args: %s' %k)
				kw[k] = v
		if self._has_request_arg:
			kw['request'] = request
		#check required kw:
		if self._required_kw_args:
			for name in self._required_kw_args:
				if not name in kw:
					return web.HTTPBadRequest('Missing argument:' %name)
		logging.info('call with args: %s' %str(kw))
		try:
			#参数处理完之后，用处理好的参数作为fn的参数进行调用
		    r = await self._func(**kw)
		    return r
		except APIError as e:
		    return dict(error = e.error,data = e.data,message = e.message)

#URL处理函数就是服务器的Resource,需要将这些Resource进行Dispatcher,因此要将它们同意进行注册
def add_static(app):
	#注册静态资源，这些资源里有前端的js,css文件等
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'static')
	app.router.add_static('/static/',path)
	logging.info('add static %s => %s' %('/static/',path))

def add_route(app,fn):
	method = getattr(fn,'__method__',None)
	path = getattr(fn,'__path__',None)
	if path is None or method is None:
		raise ValueError('@get or @post not defined in %s' %str(fn))
	if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
		fn = asyncio.coroutine(fn)
	logging.info('add route %s %s => %s(%s)' %(method,path,fn.__name__,','.join(inspect.signature(fn).parameters.keys())))
	#将经过ReuqestHandler包裹之后的fn进行注册，实际调用的时候是实例调用，就会将客户端的request参数传递给fn的实例类，实例通过()操作符即可调用call
	app.router.add_route(method,path,RequestHandler(app,fn))

def add_routes(app,module_name):
	#str.rfind(str)返回字符串在原始字符串中最后一次出现的位置，如果没有匹配则返回-1
	n = module_name.rfind('.')
	if n == (-1):
		mod = __import__(module_name,globals(),locals())
	else:
		name = module_name[n+1:]
		mod = getattr(__import__(module_name[:n],globals(),locals(),[name]),name)
	for attr in dir(mod):
		#URL处理函数是用户自建的
		if attr.startswith('_'):
			continue
		fn = getattr(mod,attr)
		#URL处理函数是函数不是其他属性
		if callable(fn):
			method = getattr(fn,'__method__',None)
			path = getattr(fn,'__path__',None)
			if method and path:
				add_route(app,fn)




