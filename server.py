# gnh1201/php-httpproxy
# Go Namyheon <gnh1201@gmail.com>
# Created at: 2022-10-06
# Updated at: 2022-10-24

import argparse
import socket
import sys
import os
from _thread import *
import base64
import json
import ssl
import time
from subprocess import Popen, PIPE
from datetime import datetime
from platform import python_version

import requests
from decouple import config

try:
    listening_port = config('PORT', cast=int)
    server_url = config('SERVER_URL')
except KeyboardInterrupt:
    print("\n[*] User has requested an interrupt")
    print("[*] Application Exiting.....")
    sys.exit()

parser = argparse.ArgumentParser()

parser.add_argument('--max_conn', help="Maximum allowed connections", default=5, type=int)
parser.add_argument('--buffer_size', help="Number of samples to be used", default=8192, type=int)

args = parser.parse_args()
max_connection = args.max_conn
buffer_size = args.buffer_size

cakey = config('CA_KEY')
cacert = config('CA_CERT')
certkey = config('CERT_KEY')
certdir = config('CERT_DIR')

def start():    #Main Program
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', listening_port))
        sock.listen(max_connection)
        print("[*] Server started successfully [ %d ]" %(listening_port))
    except Exception:
        print("[*] Unable to Initialize Socket")
        print(Exception)
        sys.exit(2)

    while True:
        try:
            conn, addr = sock.accept() #Accept connection from client browser
            data = conn.recv(buffer_size) #Recieve client data
            start_new_thread(conn_string, (conn, data, addr)) #Starting a thread
        except KeyboardInterrupt:
            sock.close()
            print("\n[*] Graceful Shutdown")
            sys.exit(1)

def conn_string(conn, data, addr):
    first_line = data.split(b'\n')[0]

    method, url = first_line.split()[0:2]

    http_pos = url.find(b'://') #Finding the position of ://
    scheme = b'http'  # check http/https or other protocol
    if http_pos == -1:
        temp = url
    else:
        temp = url[(http_pos+3):]
        scheme = url[0:http_pos]

    port_pos = temp.find(b':')

    webserver_pos = temp.find(b'/')
    if webserver_pos == -1:
        webserver_pos = len(temp)
    webserver = ""
    port = -1
    if port_pos == -1 or webserver_pos < port_pos:
        port = 80
        webserver = temp[:webserver_pos]
    else:
        port = int((temp[(port_pos+1):])[:webserver_pos-port_pos-1])
        webserver = temp[:port_pos]
        if port == 443:
            scheme = b'https'

    proxy_server(webserver, port, scheme, method, url, conn, addr, data)

def proxy_connect(webserver, conn):
    hostname = webserver.decode('utf-8')
    certpath = "%s/%s.crt" % (certdir.rstrip('/'), hostname)

    conn.send(b'HTTP/1.1 200 Connection Established\r\n')

    try:
        if not os.path.isfile(certpath):
            epoch = "%d" % (time.time() * 1000)
            p1 = Popen(["openssl", "req", "-new", "-key", certkey, "-subj", "/CN=%s" % hostname], stdout=PIPE)
            p2 = Popen(["openssl", "x509", "-req", "-days", "3650", "-CA", cacert, "-CAkey", cakey, "-set_serial", epoch, "-out", certpath], stdin=p1.stdout, stderr=PIPE)
            p2.communicate()
    except Exception as e:
        print("[*] Skipped generating the key. %s" % (str(e)))

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certpath, certkey)

    # what the heck? why hang?
    conn = context.wrap_socket(conn, server_side=True)

    return conn

def proxy_server(webserver, port, scheme, method, url, conn, addr, data):
    try:
        print("[*] Started Request. %s" % (str(addr[0])))

        if scheme in [b'https', b'tls', b'ssl'] and method == b'CONNECT':
            conn = proxy_connect(webserver, conn)

        proxy_data = {
            'headers': {
                "User-Agent": "php-httpproxy/0.1.3-dev (Client; Python " + python_version() + ")",
            },
            'data': {
                "data": base64.b64encode(data).decode("utf-8"),
                "client": str(addr[0]),
                "server": webserver.decode("utf-8"),
                "port": str(port),
                "scheme": scheme.decode("utf-8"),
                "url": url.decode("utf-8"),
                "length": str(len(data)),
                "chunksize": str(buffer_size),
                "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            }
        }
        print (proxy_data)
        
        raw_data = json.dumps(proxy_data['data'])

        print("[*] Sending %s bytes..." % (str(len(raw_data))))

        i = 0
        relay = requests.post(server_url, headers=proxy_data['headers'], data=raw_data, stream=True)
        for chunk in relay.iter_content(chunk_size=buffer_size):
            conn.send(chunk)
            i = i + 1

        print("[*] Received %s chucks. (%s bytes/chuck)" % (str(i), str(buffer_size)))
        print("[*] Request Done. %s" % (str(addr[0])))

        conn.close()
    except Exception as e:
        print("[*] f: proxy_server: %s" % (str(e)))
        conn.close()

if __name__== "__main__":
    start()
