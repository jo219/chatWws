# send

import pika, sys
connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

# channel.queue_declare(queue='hello', durable=True)
# channel.exchange_declare(exchange='logs', exchange_type='fanout') # 3
# channel.exchange_declare(exchange='direct_logs', exchange_type='direct') # 4
channel.exchange_declare(exchange='topic_logs', exchange_type='topic') # 5


# message = ' '.join(sys.argv[1:]) or "Hello World!"        # 3
# severity = sys.argv[1] if len(sys.argv) > 1 else 'info'   # 4
severity = sys.argv[1] if len(sys.argv) > 2 else 'anonymous.info' # severity being routing_key
message = ' '.join(sys.argv[2:]) or 'Hello World!'          

# channel.basic_publish(exchange='', routing_key='hello', body=message, 
#                       properties=pika.BasicProperties(
#                         delivery_mode = 2, # make message persistent
#                       )) # 'Hello World!')
# channel.basic_publish(exchange='logs', routing_key='', body=message) # 3
channel.basic_publish(exchange='direct_logs', routing_key=severity, body=message)

# print(" [x] Sent " + message) # 3
print(" [x] Sent %r:%r" % (severity, message))
connection.close()


# recv

import pika, sys
connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

# channel.queue_declare(queue='hello', durable=True)
# channel.exchange_declare(exchange='logs', exchange_type='fanout') # 3
# channel.exchange_declare(exchange='direct_logs', exchange_type='direct') # 4
channel.exchange_declare(exchange='topic_logs', exchange_type='topic') # 5

result = channel.queue_declare(queue='', exclusive=True)
queue_name = result.method.queue

# channel.queue_bind(exchange='logs', queue=queue_name) # 3
severities = sys.argv[1:] # "*" any 1 word "#" 0-~ word(s)
if not severities:
    sys.stderr.write("Usage: %s [info] [warning] [error]\n" % sys.argv[0])
    sys.exit(1)
for severity in severities:
    channel.queue_bind(exchange='direct_logs', queue=queue_name, routing_key=severity)

def callback(ch, method, properties, body):
    # print(" [x] Received %r" % body) # 3
    print(" [x] %r:%r" % (method.routing_key, body))
#     time.sleep(body.count(b'.'))
#     print(" [x] Done")
#     ch.basic_ack(delivery_tag = method.delivery_tag)
# channel.basic_qos(prefetch_count=1) # wait to finish callback before send new task

# channel.basic_consume(queue='hello', on_message_callback=callback) # , auto_ack=True)
channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
print(' [*] Waiting for messages. To exit press CTRL+C')
channel.start_consuming()