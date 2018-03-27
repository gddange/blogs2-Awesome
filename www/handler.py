#-*- coding:utf-8 -*-

from models import User,Blog,Comment,next_id
import markdown2
from aiohttp import web
from coroweb import get,post
import time,re,hashlib,json,logging,base64,asyncio
from apis import APIError,APIValueError,APIPermissionError,Page
from config import configs


COOKIE_NAME = 'awesession'
_COOKIE_KEY=configs.session.secret

def check_admin(request):
	user = request.__user__
	if user is None or not user.admin:
		raise APIPermissionError()

def text2html(text):
	lines = map(lambda s:'<p>%s</p>' %s.replace('&','&amp;').replace('<','&lt').replace('>','&gt'),filter(lambda s: s.strip() != '',text.split('\n')))
	return ''.join(lines)

#返回博文管理最下面的那个索引
def get_page_index(page_str):
	p = 1
	try:
		p = int(page_str)
	except ValueError as e:
		pass
	if p < 1:
		p = 1
	return p

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
async def index(*,page='1',request):
	#从数据库里取出博客
	page_index = get_page_index(page)
	num = await Blog.findNumber('count(id)')
	page = Page(num)
	if num == 0:
		blogs = []
	else:
		blogs = await Blog.findAll(orderBy='created_at',limit=(page.offset,page.limit))
	return{
	    '__template__':'blogs.html',
	    'page':page,
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

#根据博客ID从数据库中查询该博客的评论
@get('/blog/{id}')
async def get_blog(id,request):
	blog = await Blog.find(id)
	comments = await Comment.findAll('blog_id=%s',[id],orderBy="created_at")
	for c in comments:
		c.html_content = text2html(c.content)
	blog.html_content = markdown2.markdown(blog.content)
	return {
	    '__template__':'blog.html',
	    'blog':blog,
	    'comments':comments,
	    'user':request.__user__
	}

#博客分页管理函数
@get('/manage/blogs')
def manage_blogs(*,page='1',request):
	return {
	    '__template__':'manage_blogs.html',
	    'page_index':get_page_index(page),
	    'user':request.__user__
	}

#对已有的博客进行编辑并保存
@get('/manage/blogs/edit')
def manage_edit_blog_by_id(id,request):
	print('the id of this blog is %s'%id)
	return {
	    '__template__':'manage_blog_edit.html',
	    'id':id,
	    'action':'/api/blogs/%s' %id,
	    'user':request.__user__
	}

#创建博客
@get('/manage/blogs/create')
def manage_create_blog(request):
	return {
	    '__template__':'manage_blog_edit.html',
	    'id':'',
	    'action':'/api/blogs',
	    'user':request.__user__
	}

#转到分页管理评论页面
@get('/manage/comments')
def manage_comments(*,page='1',request):
	return{
	    '__template__':'manage_comments.html',
	    'page_index':get_page_index(page),
	    'user':request.__user__
	}

#转到分页管理用户页面
@get('/manage/users')
def manage_users(*,page='1',request):
	return{
	    '__template__':'manage_users.html',
	    'page_index':get_page_index(page),
	    'user':request.__user__
	}

#创建blog，当点击保存之后将blog存到数据库中
@post('/api/blogs')
async def api_create_blog(request,*,name,summary,content):
	#检查是否是管理员，只有管理员才可以创建博客
	check_admin(request)
	if not name or not name.strip():
		raise APIValueError('name','name cannot be empty.')
	if not summary or not summary.strip():
		raise APIValueError('summary','summary cannot be empty.')
	if not content or not content.strip():
		raise APIValueError('content','content cannot be empty.')
	#因为在orm里面，save就包括了update，所以此处不用判断博文是否已经存在
	blog = Blog(user_id = request.__user__.id,user_name=request.__user__.name,user_image=request.__user__.image,name=name.strip(),summary=summary.strip(),content=content.strip())
	await blog.save()
	return blog

#更新保存博客
@post('/api/blogs/{id}')
async def api_update_blog(id,request,*,name,summary,content):
	check_admin(request)
	blog = await Blog.findAll('id=%s',[id])
	if not name or not name.strip():
		raise APIValueError('name','name cannot be empty.')
	if not summary or not summary.strip():
		raise APIValueError('summary','summary cannot be empty.')
	if not content or not content.strip():
		raise APIValueError('conetnt','content cannot be empty.')
	blog[0].name = name
	blog[0].summary = summary
	blog[0].content = content
	await blog[0].update()
	return blog[0]

#根据id删除博客
@post('/api/blogs/{id}/delete')
async def api_delete_blog(id,request):
	check_admin(request)
	blogs = await Blog.findAll('id=%s',[id])
	if len(blogs) ==0:
		return None
	blog = blogs[0]
	await blog.delete()
	return dict(id=id)

#创建保存评论
@post('/api/blogs/{blog_id}/comments')
async def create_blog_comments(blog_id,request,*,content):
	#所有人都可以评论，因此不需要检查用户的类型
	if not blog_id or not blog_id.strip():
		raise APIValueError('blog.id','blog.id cannot be empty.')
	if not content or not content.strip():
		raise APIValueError('content','content cannot be empty.')
	comment = Comment(blog_id = blog_id,user_id = request.__user__.id,user_name = request.__user__.name,user_image=request.__user__.image,content=content)
	await comment.save()
	return comment

#根据博客ID返回博客
@get('/api/blogs/{id}')
async def api_get_blog(*,id):
	blog = await Blog.find(id)
	return blog

#取出数据填充分页管理博客界面
@get('/api/blogs')
async def api_blogs(*,page = '1'):
	page_index = get_page_index(page)
	#博客总数
	num = await Blog.findNumber('count(id)')
	p = Page(num,page_index)
	if num == 0:
		return dict(page = p,blogs = ())
	blogs = await Blog.findAll(orderBy='created_at',limit=(p.offset,p.limit))
	return dict(page = p,blogs = blogs)

#取出数据填充分页管理用户界面
@get('/api/comments')
async def api_comments(*,page='1'):
	page_index = get_page_index(page)
	num = await Comment.findNumber('count(id)')
	p = Page(num,page_index)
	if num == 0:
		return dict(page=p,comments=())
	comments = await Comment.findAll(orderBy='blog_id',limit=(p.offset,p.limit))
	return dict(page=p,comments=comments)

#删除评论页面
@post('/api/comments/{comment_id}/delete')
async def delete_comments(comment_id,request):
	check_admin(request)
	comments = await Comment.findAll('id=%s',[comment_id])
	if len(comments) == 0:
		return None
	comment = comments[0]
	await comment.delete()
	return dict(id=comment_id)

#取出数据填充分页管理用户界面
@get('/api/users')
async def api_users(*,page='1'):
	page_index = get_page_index(page)
	num = await User.findNumber('count(id)')
	p = Page(num,page_index)
	if num == 0:
		return dict(page=p,users = ())
	users = await User.findAll(orderBy='created_at',limit=(p.offset,p.limit))
	return dict(page=p,users=users)
