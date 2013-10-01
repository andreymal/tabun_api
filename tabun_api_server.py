#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import json
import time
import socket
import struct
import threading
import traceback
import tabun_api as api

server = None
user = api.User()
user_lock = threading.RLock()

query_times = {}
query_ips = {}
query_times_lock = threading.RLock()
query_tic = 0

try:
    import gevent
    import gevent.monkey
    thread_mode = False
except ImportError:
    log("Note: gevent not found")
    thread_mode = True
else:
    gevent.monkey.patch_all()

def log(*args):
    print time.strftime("[%H:%M:%S]"),
    for x in args:
        print x,
    print

def method2group(method):
    if method in ('get_post', 'get_posts', 'get_comments', 'get_post_and_comments'):
        return 'get_post_group'
    if method in ('post', 'comment'):
        return 'send_group'
    return method

def check_query_time(ip, method):
    global query_tic
    if not isinstance(method, (str, unicode)): return True
    
    method = method2group(method)
    
    with query_times_lock:
        # clear cache
        query_tic += 1
        if query_tic >= 100:
            query_tic = 0
            tm = time.time()
            for key, value in list(query_times.items()):
                for vmethod, vvalue in list(value.items()):
                    if tm - vvalue > 120:
                        value.pop(vmethod)
                if not value:
                    query_times.pop(key)
        #
        
        data = query_times.get(ip)
        if data is None:
            return False
        diff = time.time() - data.get(method, 0.0)
        if method == 'get_post_group' and diff < 3:
            return False
        if method == 'send_group' and diff < 10:
            return False
        if diff < 1:
            return False
        return True

def update_query_time(ip, method):
    if not isinstance(method, (str, unicode)): return True
    method = method2group(method)
    with query_times_lock:
        data = query_times.get(ip)
        if data is None: return
        data[method] = time.time()

def exec_api(query):
    method = query.get("method")
    phpsessid = query.get("phpsessid")
    if not method:
        return {"error": 400, "data": "Empty Method"}
    
    if method == "get_posts":
        url = str(query.get("url", "/index/newall/"))
        if url[0] != '/':
            return {"error": 400, "data": "Invalid URL"}
        with user_lock:
            user.phpsessid = phpsessid
            posts = user.get_posts(url)
        posts = map(post2json, posts)
        return {"result": posts}
    
    elif method == "get_post":
        try: post_id = int(query.get("post_id"))
        except: return {"error": 400, "data": "Invalid post_id"}
        blog = query.get("blog")
        
        with user_lock:
            user.phpsessid = phpsessid
            post = user.get_post(post_id, str(blog) if blog else None)
            return {"result": post2json(post) if post else None}
    
    elif method == "get_comments":
        url = None
        try:
            post_id = int(query.get("post_id"))
        except:
            pass
        else:
            blog = str(query.get("blog", ""))
            if blog:
                url = "/blog/" + blog + "/" + str(post_id) + ".html"
            else:
                url = "/blog/" + str(post_id) + ".html"
        
        if not url:
            url = str(query.get("url", "/comments/"))
        if url[0] != '/':
            return {"error": 400, "data": "Invalid URL"}
        with user_lock:
            user.phpsessid = phpsessid
            comments = user.get_comments(url)
        comments = map(comment2json, comments)
        return {"result": comments}
    
    elif method == "methods":
        return {'result':[
                {'name': 'get_posts', 'params': ['url']},
                {'name': 'get_post', 'params': ['post_id', 'blog']},
                {'name': 'get_comments', 'params': ['url', 'post_id', 'blog']},
            ]}
    
    else:
        return {"error": 405, "data": "Unknown Method"}

def post2json(post):
    post_dict = {
        'time': time.mktime(post.time),
        'blog': post.blog,
        'post_id': post.post_id,
        'author': post.author,
        'title': post.title.encode("utf-8"),
        'body': api.node2string(post.body) if not isinstance(post.body, str) else post.body,
        'tags': map(lambda x:x.encode("utf-8"), post.tags),
        'short': post.short,
        'private': post.private
    }
    return post_dict

def comment2json(comment, with_title=False):
    if isinstance(comment, (int, long)):
        return {
            'time': 0,
            'blog': "",
            'post_id': 0,
            'comment_id': 0,
            'parent_id': 0,
            'author': "",
            'body': u"",
            'del': 1
        }
    comment_dict = {
        'time': time.mktime(comment.time),
        'blog': comment.blog,
        'post_id': comment.post_id,
        'comment_id': comment.comment_id,
        'parent_id': comment.parent_id,
        'author': comment.author,
        'body': api.node2string(comment.body) if not isinstance(comment.body, str) else comment.body,
        'del': 0
    }
    if with_title:
        comment_dict['post_title'] = comment.post_title
    return comment_dict

def parse(conn, addr):
    try:
        ip = addr[0]
        log(ip, "connected")
        
        hello = read_packet(conn)
        if not hello: return
        if hello != "hello":
            if ip.find("127.") == 0:
                ip = hello
                log(addr[0], "=>", ip)
            else:
                send_packet(conn, "Invalid hello")
                return
        
        with query_times_lock:
            if not query_ips.get(ip):
                query_times[ip] = {}
                query_ips[ip] = 0
            query_ips[ip] += 1
        send_packet(conn, "hello")
        
        jd = json.JSONDecoder(encoding="utf-8")
        je = json.JSONEncoder(encoding="utf-8", ensure_ascii=False)
        je_fancy = json.JSONEncoder(encoding="utf-8", ensure_ascii=False, sort_keys=True, indent=2)
        while 1:
            query = read_packet(conn)
            if not query or query[0] != "{": break
            try:
                query = jd.decode(query)
            except ValueError:
                return
            try:
                if not check_query_time(ip, query.get("method")):
                    result = {"error":429, "data":"Too fast"}
                else:
                    update_query_time(ip, query.get("method"))
                    try:
                        result = exec_api(query)
                    finally:
                        update_query_time(ip, query.get("method"))
                log(ip, "query:", query.get("method"))
            except api.TabunError as error:
                result = {"error": error.code, "data": str(error)}
            except:
                traceback.print_exc()
                result = {"error": 500, "data": "Internal Server Error"}
                log("query:", str(query)[:2000])
            
            if query.get("fancy"):
                result = je_fancy.encode(result)
            else:
                result = je.encode(result)
            send_packet(conn, result)
            
    finally:
        log(ip, "disconnected")
        try: conn.close()
        except: pass

def read_packet(conn):
    l = ''
    while len(l) < 4:
        tmp = conn.recv(4 - len(l))
        if not tmp: return ''
        l += tmp
    l = struct.unpack('<I', l)[0]
    
    data = ''
    while len(data) < l:
        tmp = conn.recv(l - len(data))
        if not tmp: return ''
        data += tmp
    if conn.recv(1) != '\n': return ''
    return data

def send_packet(conn, data):
    if isinstance(data, unicode):
        data = data.encode("utf-8")
    elif not isinstance(data, str):
        raise ValueError("data is not str")
    
    if len(data) == 0: return
    conn.sendall(struct.pack('<I', len(data)) + data + '\n')

def start_parsing(conn, addr):
    global thread_mode
    conn.settimeout(120)
    if not thread_mode:
        gevent.spawn(parse, conn, addr)
    else:
        threading.Thread(None, parse, None, (conn, addr)).start()

def start_server(host, port, listen=10):
    global server
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(listen)
     
    log("Server started")
    while 1:
        start_parsing(*server.accept())
        
if __name__ == "__main__":
    try: start_server('', 19000)
    except KeyboardInterrupt: print
