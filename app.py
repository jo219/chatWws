# FLASK_APP=fscli.py FLASK_DEBUG=1 python -m flask run 
# # --host=0.0.0.0
# export FLASK_ENV=development

from flask import (
	Flask, url_for, redirect,
	render_template, request, session,
	jsonify
)

from flask_pymongo import PyMongo
import os, sys, json, uuid

from tornado.wsgi import WSGIContainer
from tornado.web import Application, FallbackHandler
from tornado.websocket import WebSocketHandler
from tornado.ioloop import IOLoop

app = Flask(__name__)
app.secret_key = 'secretkey12345'

app.config['MONGO_URI'] = 'mongodb://jo219:test1234@ds145083.mlab.com:45083/scli?retryWrites=false'
mongo = PyMongo(app)
ids = mongo.db.ids
chatrooms = mongo.db.chatrooms
unread_flags = mongo.db.unread_flags
clients = {}

# mq_creds = pika.PlainCredentials(username="guest", password="guest")
# mq_params = pika.ConnectionParameters(host="0.0.0.0", credentials=mq_creds, virtual_host="/")
# mq_conn = pika.BlockingConnection(mq_params)
# mq_chan = mq_conn.channel()
# mq_exchange    = "amq.topic"
# # mq_chan.basic_publish(exchange=mq_exchange, routing_key=mq_routing_key, body=text)

class WebSocket(WebSocketHandler):
	def __init__(self, application, request, **kwargs):
		super(WebSocket, self).__init__(application, request, **kwargs)
		self.client_username = ''
		# self.client_id = str(uuid.uuid4())

	def open(self, cliUsername):
		clients[cliUsername] = self
		self.client_username = cliUsername
		print("Socket opened for " + cliUsername)

	def on_message(self, message):
		print("Received message: " + message)

	def on_close(self):
		# clients.pop(self.client_username, None)
		print("Socket closed for " + self.client_username)


@app.route('/')
def index():
	return render_template('hscli.html')

@app.route('/signup', methods=['POST', 'GET'])
def signup():
	if request.method == 'POST':
		user_exist = ids.find_one({'username':request.form['username']})
		if user_exist: # collision with existing username
			return "{fail} Username already used"
		
		if ids.estimated_document_count() > 0:
			id_counts = ids.find().sort([('count', -1)]).limit(1)
			for c in id_counts:
				id_count = c['count'] + 1
		else:
			id_count = 0

		new_id = {'username':request.form['username'], 'gender':request.form['gender'], 'count':id_count}

		usernames = ids.find({}, {'username':1, '_id':0})
		cur_send = json.dumps({'tag':'{sonein}', 'username': new_id['username'], 'gender':request.form['gender']})
		for user in usernames:
			chatrooms.insert_one({'c0':request.form['username'], 'c1':user['username'], 'rooms':[]})
			try:
				clients[user['username']].write_message(cur_send)
				# mq_chan.basic_publish(exchange=mq_exchange, routing_key=user['username'], body=cur_send)
			except Exception as e:
				print("==== Safe error [someone in] ====")
				print(e)
		unread_flags.insert_one({'username':request.form['username'], 'flags':{}})

		ids.insert_one(new_id)

		session['username'] = request.form['username']
		session['gender'] = request.form['gender']
		return "Success, wait 5 sec to reload"
	return render_template('hscli.html')

@app.route('/signout', methods=['POST', 'GET'])
def signout():
	if request.method == 'POST':
		# session.pop('username', None); session.pop('gender', None); return "{fail}"  # for bypassing
		session.pop('username', None)
		session.pop('gender', None)

		user_exist = ids.find_one({'username':request.form['username']})
		if not user_exist:
			return "{fail}"

		chatrooms.delete_many({'$or': [{'c0':request.form['username']}, {'c1':request.form['username']}]})
		unread_flags.delete_one({'username':request.form['username']})
		ids.delete_one({'username':request.form['username']}) # tambah query rapihin count kalo niat

		usernames = ids.find({}, {'username':1, '_id':0})
		cur_send = json.dumps({'tag':'{soneout}', 'username': request.form['username']})
		for user in usernames:
			if user!=request.form['username']:
				try:
					clients[user['username']].write_message(cur_send)
					# mq_chan.basic_publish(exchange=mq_exchange, routing_key=user['username'], body=cur_send)
				except Exception as e:
					print("==== Safe error [someone in] ====")
					print(e)

		return "Success, wait 5 sec to reload"
	return render_template('hscli.html')

@app.route('/clientlistsRefresh', methods=['POST', 'GET'])
def clientlistsRefresh():
	if request.method == 'POST':
		user_exist = ids.find_one({'username':request.form['username']})
		if not user_exist:
			return "{fail}"
		ids_toSend = list(ids.find({'username':{'$not' : {'$eq' : request.form['username']}}}, {'_id':0}))
		unread_flags_toSend = unread_flags.find_one({'username':request.form['username']}, {'_id':0})['flags']
		return jsonify(cur_ids=ids_toSend, cur_ufs=unread_flags_toSend)
	return render_template('hscli.html')

@app.route('/openChatroom', methods=['POST', 'GET'])
def openChatroom():
	if request.method == 'POST':
		ids_fr = ids.find_one({'username':request.form['fr']})
		ids_to = ids.find_one({'username':request.form['to']})
		c0, c1 = giveHigherIdCount(ids_fr, ids_to)
		chatroom = chatrooms.find_one({'$and': [{'c0':c0['username']}, {'c1':c1['username']}]})['rooms']

		# tell 'to' he/she has read message from 'fr', 'to' == self
		flag = unread_flags.find_one({'username':request.form['to']})['flags']
		if request.form['fr'] in flag:
			del flag[request.form['fr']]
			unread_flags.update_one({'username':request.form['to']}, {'$set': {'flags':flag}})

		return jsonify(chatroom=chatroom, uf=flag)
	return render_template('hscli.html')

@app.route('/sendMessage', methods=['POST', 'GET']) # here socket used to notify ids_to
def sendMessage():
	if request.method == 'POST':
		ids_fr = ids.find_one({'username':request.form['fr']})
		ids_to = ids.find_one({'username':request.form['to']})
		c0, c1 = giveHigherIdCount(ids_fr, ids_to)
		chatroom = chatrooms.find_one({'$and': [{'c0':c0['username']}, {'c1':c1['username']}]})['rooms']
		chatroom += [ids_fr['username'] + ": " + request.form['msg']]
		chatrooms.update_one({'$and': [{'c0':c0['username']}, {'c1':c1['username']}]}, {'$set': {'rooms':chatroom}})

		# tell 'to' he/she has unread message from 'fr'
		flag = unread_flags.find_one({'username':request.form['to']})['flags']
		if not request.form['fr'] in flag:
			flag.update({request.form['fr']: 1})
			unread_flags.update_one({'username':request.form['to']}, {'$set': {'flags':flag}})

		try:
			cur_send = json.dumps({'tag':'{notify}', 'fr':request.form['fr']})
			clients[request.form['to']].write_message(cur_send)
			# mq_chan.basic_publish(exchange=mq_exchange, routing_key=request.form['to'], body=cur_send)
		except Exception as e:
			print("==== Safe error [notify] ====")
			print(e)

		return jsonify(chatroom=chatroom, uf=flag)
	return render_template('hscli.html')

def giveHigherIdCount(a0, a1):
	if a0['count'] > a1['count']:
		return (a0, a1)
	return (a1, a0)

# if __name__ == "__main__":
# 	app.run("0.0.0.0", port=5000, debug=True)

if __name__ == "__main__":
	container = WSGIContainer(app)
	server = Application([
		(r'/websocket/([^/]+)', WebSocket),
		(r'.*', FallbackHandler, dict(fallback=container))
	])
	port = int(os.getenv('PORT', 5000))
	server.listen(port, address='0.0.0.0')
	IOLoop.instance().start()


   

# hostname = urlparse.urlparse("%s://%s" % (self.request.protocol, self.request.host)).hostname
# ip_address = socket.gethostbyname(hostname)