#-*- coding:utf-8 -*-

#这是一个建立在aiomysql基础上的orm框架，作为映射mysql数据库中表到python的class中的作用
import logging;logging.basicConfig(level=logging.INFO)
import asyncio,aiomysql

#打印输入的sql语句函数，可以给用户检查自己的sql语句的语法
def log(sql,args=()):
	logging.info('SQL: %s' %sql)

def create_args_string(num):
	L = []
	for i in range(num):
		L.append('?')
	return ','.join(L)

async def create_pool(loop,**kw):
	logging.info('create database connection pool...')
	#声明一个全局变量__pool，这个变量用于存放所有用户的连接conn
	global __pool
	#连接数据库需要各种信息，这些信息用户通过**kw传递，在读取的时候要考虑到用户如果没有传递相应的参数则需要给其设置default value
	#create_pool()函数返回的是一个Pool类的实例（instance
	__pool = await aiomysql.create_pool(loop = loop,
		    #host和port都有默认值，可以不用用户传递
		    host=kw.get('host','127.0.0.1'),
		    port = kw.get('port',3306),
		    #用户名和密码则需要用户给出
		    user=kw['user'],
		    password=kw['password'],
		    db=kw['db'],
		    #用户需要指定连接数据库的字符，默认情况下采用utf8
		    charset=kw.get('charset','utf8'),
		    autocommit=kw.get('autocommit',True),
		    maxsize=kw.get('maxsize',10),
		    minsize=kw.get('minsize',1)
		)

#连接数据库之后，把增上查改分别写成函数，而其他操作直接调用即可，代码重用之后的归纳
async def select(sql,args=None,size=None):
	#打印传递过来的参数
	log(sql,args)
	global __pool
	with await __pool as conn:
		#DictCursor是返回结果是Dict的Cursor
		cur = await conn.cursor(aiomysql.DictCursor)
		#python的字符标准中占位符用的是'%',而sql用的是'?'，所以执行的时候要将其替换掉
		await cur.execute(sql.replace('?','%s'),args or None)
		if size:
			rs = await cur.fetchmany(size)
		else:
			rs = await cur.fetchall()
		await cur.close()
		#这里的rs是dict类型的
		logging.info('rows returned: %s' %len(rs))
		return rs

#delete,update,insert属于类似的操作，它们只对数据库数据产生影响，并不需要将数据返回
async def execute(sql,args):
	log(sql,args)
	global __pool
	with await __pool as conn:
		#因为并不需要具体数据，所以不需要dictcursor,但是操作可能会引起错误，毕竟是写操作，所以要考虑异常处理
		try:
			cur = await conn.cursor()
			await cur.execute(sql.replace('?','%s'),args or None)
			#curcor.rowcount就是用来返回受影响的行数
			r =  cur.rowcount
			await cur.close()
		except BaseException as e:
			raise
		logging.info('rows affected: %s' %str(r))
		return r


#当一个class和一张table对应的时候，table中每一列数据的属性，是否是主键，数据类型等也要在class中体现，所以建立数据类型对应类
class Field():

	def __init__(self,name,column_type,primarykey,default):
		self.name = name
		self.column_type= column_type
		self.primarykey=primarykey
		self.default = default

	def __str__(self):
		return '<%s, %s, %s>' %(self.__class__.__name__,self.column_type,self.name)

#python的string对应的是varchar
class StringField(Field):

	def __init__(self,name=None,primarykey=False,default=None,ddl='varchar(100)'):
		super().__init__(name,ddl,primarykey,default)

class BooleanField(Field):
	def __init__(self,name=None,default=False,ddl='boolean',primarykey=False):
		super().__init__(name,ddl,primarykey,default)

class IntegerField(Field):

	def __init__(self,name=None,default=0,ddl='bigint',primarykey=False):
		super().__init__(name,ddl,primarykey,default)

class FloatField(Field):

	def __init__(self,name=None,primarykey=False,default=0.0,ddl='real'):
		super().__init__(name,ddl,primarykey,default)

class TextField(Field):

	def __init__(self,name = None,default =None,primarykey = False,ddl = 'text'):
		super().__init__(name,ddl,primarykey,default)


'''
User这个类只是一个和table的映射关系，而实际上存储数据是通过父类Model(继承自Dict)实现，具有根据自身实际情况增删查改的功能则是由metaclass完成
所以这里的metaclass就完成了一个API的功能，Model只是一个接口，根据进入的内容的不同返回的新类也不同
class User(Model):
	__tablename__='user'

	id = StringField(primarykey = True)
	name = StringField()

'''		

#元类
class ModelMetaclass(type):

	def __new__(cls,name,bases,attrs):
		if name == 'Model':
			#Model是所有类的父类，不需要实例化，也不需要根据输入有所变动（有点像java里的抽象类
			return type.__new__(cls,name,bases,attrs)
		#创建类的时候要得到table的名称，不同的类对应的table不一样，同时新的类（生产出来的）里也需要有tablename
		tablename = attrs['__tablename__']
		logging.info('found mode: %s (table: %s' %(name,tablename))
		#新的类还有传递过来的各种参数，主键等信息是存储在User的属性类里的，现在要把他们转换出来
		mappings = dict()
		fields = []
		primarykey = None
		for k,v in attrs.items():
			#table映射类里除了__tablename__意外，其他都是Field的子类
			if isinstance(v,Field):
				logging.info('found mapping: %s ==> %s' % (k,v))
				mappings[k] = v
				#判断这个属性是否是主键，主键信息存在Field类的属性里，此时v是一个实例
				if v.primarykey:
					if primarykey:
						#说明有两个属性都有主键信息，不符合数据库规范
						raise RuntimeError('Duplicate primary key for field: %s'%k)
					primarykey = k
				else:
					#fields里面存储的非主键信息
					fields.append(k)
		if not primarykey:
			#说明这张table没有主键
			raise RuntimeError('Primary key not found!')
		for k in mappings.keys():
			#将原来的attrs里面用户新建的属性弹出，添加新的属性，从而保留系统的属性
			attrs.pop(k)
		#把非主键信息规范化，以便SQL语句
		escaped_fields=list(map(lambda f:'`%s`' %f,fields))
		#添加新的属性
		attrs['__mappings__'] = mappings
		attrs['__table__'] = tablename
		attrs['__primary_key__'] = primarykey
		attrs['__fields__'] = fields
		#构造默认的Select,Insert,Update,Delete语句,要把primarykey单独写出来是因为fields里面只有非主键属性
		attrs['__select__']='select `%s`, %s from `%s`' %(primarykey,', '.join(escaped_fields),tablename)
		attrs['__insert__'] = 'insert into `%s` (%s,`%s`) values (%s)' %(tablename,','.join(escaped_fields),primarykey,create_args_string(len(escaped_fields)+1))
		attrs['__update__'] = 'update `%s` set %s where `%s`=?' %(tablename,','.join(map(lambda f:'`%s` = ?' %(mappings.get(f).name or f),fields)),primarykey)
		attrs['__delete__'] ='delete from `%s` where `%s` =?' %(tablename,primarykey)
		#用新的属性生成类
		return type.__new__(cls,name,bases,attrs)

#继承自dict，是所有table映射class的父类，通过元类ModelMetaclass根据输入不同创建新的类
class Model(dict,metaclass=ModelMetaclass):

	#因为不知道这个类是具体的哪一个类，所以参数选择**这种
	def __init__(self,**kw):
		super().__init__(self,**kw)

	def __getattr__(self,key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Model' object has no attribute '%s'" %key)

	def __setattr__(self,key,value):
		self[key] = value

	def getValue(self,key):
		#这里用的是内建函数
		return getattr(self,key,None)

	def getValueOrDefault(self,key):
		value = getattr(self,key,None)
		if value is None:
			field = self.__mappings__[key]
			if field.default is not None:
				value = field.default() if callable(field.default) else field.default
				logging.info('using default value for %s: %s' %(key,str(value)))
		return value

	#这些table类要具有增删查改的功能，其中查询是整张表才需要的，所以是类功能，而增改都是一条数据自己需要的功能,所以是实例功能
	@classmethod
	async def findAll(cls,where = None,args = None,**kw):
		#findAll语句要考虑是否有find语句
		sql = [cls.__select__]
		if where:
			sql.append('where')
			sql.append(where)
		if args is None:
			args = []
		#select 语句还有orderby
		orderby = kw.get('oederBy',None)
		if orderby is not None:
			sql.append('Order By')
			sql.append(oederby)
		limit = kw.get('limit',None)
		if limit is not None:
			sql.append('limit')
			if isinstance(limit,int):
				sql.append('?')
				sql.append(limit)
			if isinstance(limit,tuple) and len(limit) == 2:
				sql.append('?','?')
				sql.append(limit)
			else:
				raise ValueError('Invalid limit value: %s' %str(limit))
		rs = await select(' '.join(sql),args)
		return [cls(**r) for r in rs]

	@classmethod
	async def findName(cls,selectField,where = None,args = None):
		'''select data by where '''
		sql = ['select %s from `%s`' %(selectField,cls.__table__)]
		if where:
			sql.append('where')
			sql.append(where)
		rs = await select(' '.join(sql),args,1)
		if rs == 0:
			return None
		else:
			return rs[0]

	async def save(self):
		#因为save的时候是先存非主键参数，而最后才是主键，而到__insert__语句的时候是按照list的顺序来的
		args = list(map(self.getValueOrDefault,self.__fields__))
		args.append(self.getValueOrDefault(self.__primary_key__))
		rows = await execute(self.__insert__,args)
		if rows!= 1:
			logging.info('failed to inser into table: %s' %(self.__table__))

	async def delete(self):
		primarykey = self.getValueOrDefault(self.__primary_key__)
		r = await execute(self.__delete__,primarykey)
		if r != 1:
			logging.info('failed to delete into table: %s wiht %s'%(self.__table__,self.__primary_key__))
#test
class User(Model):
	__tablename__ = 'user'

	id = StringField(primarykey=True)
	name = StringField()

if __name__=='__main__':
	user = User(id='6',name='mariah')
	loop = asyncio.get_event_loop()
	loop.run_until_complete(create_pool(user='sa',password='5h6je63q',db='blogs',loop=loop))
	#loop.run_until_complete(select(user.__insert__,args))
	#print(loop.run_until_complete(user.save()))
	print(loop.run_until_complete(User.findName('name')))
	#print(r)	

