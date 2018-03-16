#-*- coding:utf-8 -*-
import time,uuid

from orm import Model,StringField,BooleanField,FloatField,TextField,IntegerField

#自动生成ID
def next_id():
	return '%015d%s000' %(int(time.time()*1000),uuid.uuid4().hex)

class User(Model):
	__table__='users'

	#这里指明数据在数据库中的类型，在数据库中创建时候按照这个类型去创建，插入删除修改数据库的时候才不会出错
	id = StringField(primarykey=True,default = next_id,ddl='varchar(50)')
	email = StringField(ddl='varchar(50)')
	passwd = StringField(ddl='varchar(50)')
	admin = BooleanField()
	name = StringField(ddl='varchar(50)')
	image = StringField(ddl="varchar(500)")
	created_at = FloatField(default=time.time)

class Blog(Model):
	__table__='blogs'

	id = StringField(primarykey=True,default=next_id,ddl='varchar(50)')
	user_id = StringField(ddl='varchar(50)')
	user_name=StringField(ddl='varchar(50)')
	user_image=StringField(ddl='varchar(500)')
	name = StringField(ddl='varchar(50)')
	summary=StringField(ddl='varchar(200)')
	content = TextField()
	created_at = FloatField(default = time.time)


class Comment(Model):
	__table__='comments'

	id  = StringField(primarykey=True,default=next_id,ddl='varchar(50)')
	blog_id = StringField(ddl='varchar(50)')
	user_id = StringField(ddl='varchar(50)')
	user_name=StringField(ddl='varchar(50)')
	user_image=StringField(ddl='varchar(500)')
	content=TextField()
	created_at=FloatField(default=time.time)
