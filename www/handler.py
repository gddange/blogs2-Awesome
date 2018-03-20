#-*- coding:utf-8 -*-

from models import User,Blog,Comment,next_id
from aiohttp import web
from coroweb import get,post
import time,re,hashlib,json,logging,base64,asyncio
from apis import APIError,APIValueError
from config import configs


COOKIE_NAME = 'awesession'
_COOKIE_KEY=configs.session.secret
#Cookie生成函数，cookie中存储了用户id,cookie过期时间，以及用户id,passwd、cookie_str和max-age计算出来的单向验证字符串sha1
def user2cookie(user,max_age):
	#expires表示cookie过期的时间
	expires = str(int(time.time()+max_age))
	s = '%s-%s-%s-%s' %(user.id,user.passwd,expires,_COOKIE_KEY)
	L =[user.id,expires,hashlib.sha1(s.encode('utf-8')).hexdigest()]
	return '-'.join(L)

#解析cookie函数
async def cookie2user(cookie_str):
	if not cookie_str:
		#没有cookie_str就返回None，那么request.__user__就是None
		raise None
	try:
		L = cookie_str.split('-')
		if len(L) != 3:
			#如果不等于说明是用户伪造的cookie
			return None
		uid,expires,sha1 = L
		if int(expires) <time.time():
			#最大生存时间小于当前时间，说明Cookie已经过期
			return None
		#根据uid从数据库中取出用户的信息，用于判断sha1是不是伪造的,findAll()函数返回的是列表
		user = await User.findAll('id=%s',[uid])
		s = '%s-%s-%s-%s' %(uid,user[0].passwd,expires,_COOKIE_KEY)
		if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
			logging.info('invalid sha1')
			return None
		#为了保密，所以将用户的密码重置
		user[0].passwd='******'
		return user[0]
	except Exception as e:
		logging.exception(e)
		return None

@get('/')
async def index(request):
	summary='He lived alone in his house in Saville Row,whither none penetrated.A single domestic sufficed to save him.He breakfasted and dined at club,at hours mathematically fixed,in the same room,at the table,never taking his meals with other memebers, muck less bringing a guest with him;'
	blogs=[
	    Blog(id='1',name='Test blog', summary=summary,created_at=time.time()-120),
	    Blog(id='2',name='Something new',summary=summary,created_at=time.time()-3600),
	    Blog(id='3',name='Learn Swift',summary=summary,created_at=time.time()-7200)
	]
	return{
	    '__template__':'blogs.html',
	    'blogs':blogs,
	    'user':request.__user__
	}

@get('/register')
def register():
	return{
	    '__template__':'register.html'
	}

@get('/signin')
def signin():
	return{
	    '__template__':'signin.html'
	}

#登出时将cookie生存时间设为0
@get('/signout')
def signout(request):
	referer = request.headers.get('Referer')
	r = web.HTTPFound(referer or '/')
	r.set_cookie(COOKIE_NAME,'-delete-',max_age=0,httponly=True)
	logging.info('user signed out.')
	return r

#^表示匹配字符串开头，如果是[^a]则表示取反，即不取这个字符'[]'表示字符集，'$'表示匹配字符末尾'{m,n}'：匹配前一个字符m至n次
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
#16进制0-9a-f
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

#注册API
@post('/api/users')
async def api_register_user(*,name,email,passwd):
	if not name or not name.strip():
		raise APIValueError('name')
	if not email or not _RE_EMAIL.match(email):
		raise APIValueError('email')
	if not passwd or not _RE_SHA1.match(passwd):
		raise APIValueError('password')
	#验证用户输入的email是否已经注册过，如果注册过就不能再注册了
	users = await User.findAll('email = ?',[email])
	if len(users)>0:
		raise APIError('register:failed','email','email is already in user!')
	uid = next_id()
	#数据库存储的密码是sha1(uid:sha1(password))值
	sha1_passwd = '%s:%s' %(uid,passwd)
	#注册时候需要将用户信息存储进入数据库
	user = User(id = uid,name = name,email = email,passwd = hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),image='http://www.gravatar.com/avatar/%s?d=mm&s=120' %hashlib.md5(email.encode('utf-8')).hexdigest())
	await user.save()
	#make session cookie
	r = web.Response()
	#注册之后就相当于已经登陆了，所以需要设置cookie
	r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
	user.passwd='******'
	r.content_type='application/json'
	r.body=json.dumps(user,ensure_ascii=False).encode('utf-8')
	return r

#登陆时验证函数
@post('/api/authenticate')
async def authenticate(*,email,passwd):
	if not email:
		raise APIValueError('email','Invalid email')
	if not passwd:
		raise APIValueError('passwd','Invalid password')
	#登陆的时候先验证用户名是否已经注册过了
	users = await User.findAll('email= %s',[email])
	if len(users) == 0:
		raise APIValueError('email','Email not exist')
	user = users[0]
	#检查用户输入的密码是否正确
	sha1 = hashlib.sha1()
	sha1.update(user.id.encode('utf-8'))
	sha1.update(b':')
	sha1.update(passwd.encode('utf-8'))
	if user.passwd != sha1.hexdigest():
		raise APIValueError('password','Invalid password.')
	#用户名和密码均输入正确，检查cookie是否已经过期
	r = web.Response()
	r.set_cookie(COOKIE_NAME,user2cookie(user,86400),max_age=86400,httponly=True)
	user.passwd = '******'
	r.content_type='application/json'
	#json.dumps把python数据结构转换为json格式，json.load把json编码的字符串转换为python数据结构
	r.body=json.dumps(user,ensure_ascii = False).encode('utf-8')
	return r