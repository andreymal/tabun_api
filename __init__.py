#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import time
from html2xml import HTML2XML, findTag, findTags
from httputil import encode_multipart_formdata
import urllib2
import socket
from json import JSONDecoder
from Cookie import BaseCookie

try:
    import simplexml
except:
    from xmpp import simplexml

http_host = "http://tabun.everypony.ru"
halfclosed = ("borderline", "shipping", "erpg", "gak", "RPG", "roliplay")

headers_example = {
    "connection": "close",
    "user-agent": "Mozilla/5.0 (X11; Linux i686) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1500.52 Safari/537.36",
    
}

class NoRedirect(urllib2.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp

    http_error_301 = http_error_303 = http_error_307 = http_error_302
    
global_opener = urllib2.build_opener()

class TabunError(Exception):
    def __init__(self, msg=None, code=0):
        if not msg: msg = str(code)
        Exception.__init__(self, str(msg))
        self.code = int(code)

class TabunResultError(TabunError): pass

class Post:
    def __init__(self, time, blog, post_id, author, title, body, tags, short=False, private=False, blog_name=None):
        self.time = time
        self.blog = str(blog)
        self.post_id = int(post_id)
        self.author = str(author)
        self.title = unicode(title)
        if not isinstance(body, simplexml.Node): raise ValueError
        self.body = body
        self.tags = tags
        self.short = bool(short)
        self.private = bool(private)
        self.blog_name = unicode(blog_name) if blog_name else None
        
    def __repr__(self):
        return "<post " + self.blog + "/" + str(self.post_id) + ">"
    
    def __str__(self):
        return self.__repr__()

class Comment:
    def __init__(self, time, blog, post_id, comment_id, author, body, parent_id=None, post_title=None):
        self.time = time
        self.blog = str(blog) if blog else None
        self.post_id = int(post_id)
        self.comment_id = int(comment_id)
        self.author = str(author)
        if not isinstance(body, simplexml.Node): raise ValueError
        self.body = body
        if parent_id: self.parent_id = int(parent_id)
        else: self.parent_id = None
        if post_title: self.post_title = unicode(post_title)
        else: self.post_title = None
        
    def __repr__(self):
        return "<comment " + (self.blog + "/" + str(self.post_id) + "/" if self.blog and self.post_id else "") + str(self.comment_id) + ">"

    def __str__(self):
        return self.__repr__()

class Blog:
    def __init__(self, blog_id, blog, name, creator, readers=0, rating=0.0, closed=False):
        self.blog_id = int(blog_id)
        self.blog = str(blog)
        self.name = unicode(name)
        self.creator = str(creator)
        self.readers = int(readers)
        self.rating = int(rating)
        self.closed = bool(closed)

    def __repr__(self):
        return "<blog " + self.blog + ">"

    def __str__(self):
        return self.__repr__()

class StreamItem:
    def __init__(self, blog, blog_title, title, author, comment_id, comments_count):
        self.blog = str(blog)
        self.blog_title = unicode(blog_title)
        self.title = unicode(title)
        self.author = str(author)
        self.comment_id = int(comment_id)
        self.comments_count = int(comments_count)

    def __repr__(self):
        return "<stream_item " + self.blog + "/" + str(self.comment_id) + ">"

    def __str__(self):
        return self.__repr__()

 
class User:
    phpsessid = None
    username = None
    security_ls_key = None
    key = None
    
    def __init__(self, login=None, passwd=None, phpsessid=None, security_ls_key=None, key=None):
        "Допустимые комбинации параметров:"
        "- login + passwd (не реализовано)"
        "- phpsessid [+ key] - без куки key разлогинивает через некоторое время"
        "- login + phpsessid + security_ls_key [+ key] (без запроса к серверу)"
        "- без параметров (анонимус)"
        
        self.jd = JSONDecoder()
        
        # for thread safety
        self.opener = urllib2.build_opener()
        self.noredir = urllib2.build_opener(NoRedirect)
        
        if phpsessid:
            self.phpsessid = str(phpsessid).split(";", 1)[0]
        if key:
            self.key = str(key)
        if self.phpsessid and security_ls_key:
            self.security_ls_key = str(security_ls_key)
            return
        
        if not self.phpsessid or not security_ls_key:
            resp = self.urlopen("/")
            data = resp.read(1024*25)
            resp.close()
            cook = BaseCookie()
            cook.load(resp.headers.get("set-cookie", ""))
            if not self.phpsessid:
                self.phpsessid = cook.get("PHPSESSID")
                if self.phpsessid: self.phpsessid = self.phpsessid.value
            if not self.key:
                self.key = cook.get("key")
                if self.key: self.key = self.key.value
            pos = data.find("var LIVESTREET_SECURITY_KEY =")
            if pos > 0:
                ls_key = data[pos:]
                ls_key = ls_key[ls_key.find("'")+1:]
                self.security_ls_key = ls_key[:ls_key.find("'")]
            self.username = self.parse_userinfo(data)
        
        if login and passwd:
            self.login(login, passwd)
        elif login and self.phpsessid and not self.username:
            self.username = str(login)

    def parse_userinfo(self, raw_data):
        userinfo = raw_data[raw_data.find('<div class="dropdown-user"'):]
        userinfo = userinfo[:userinfo.find("<nav")]
        parser = HTML2XML()
        parser.feed(userinfo)
        userinfo = parser.node.getTag("div")
        if not userinfo: return
        
        username = userinfo.getTag("a", {"class": "username"}).getData().encode("utf-8")
        
        if username:
            return username
    
    def login(self, login, password, return_path=None, remember=True):
        query = "login=" + urllib2.quote(login) + "&password=" + urllib2.quote(password) + "&remember=" + ("on" if remember else "off")
        query += "&return-path=" + urllib2.quote(return_path if return_path else http_host+"/")
        if self.security_ls_key:
            query += "&security_ls_key=" + urllib2.quote(self.security_ls_key)
        
        resp = self.urlopen("/login/ajax-login", query, {"X-Requested-With": "XMLHttpRequest"})
        data = resp.read()
        if data[0] != "{": raise TabunResultError(data)
        data = self.jd.decode(data)
        if data.get('bStateError') != False:
            raise TabunResultError(data.get("sMsg", u"").encode("utf-8"))
        self.username = str(login)
        
        cook = BaseCookie()
        cook.load(resp.headers.get("set-cookie", ""))
        self.key = cook.get("key")
        if self.key: self.key = self.key.value
    
    def check_login(self):
        if not self.phpsessid or not self.security_ls_key:
            raise TabunError("Not logined")
    
    def urlopen(self, url, data=None, headers={}, redir=True):
        if not isinstance(url, urllib2.Request):
            if url[0] == "/": url = http_host + url
            url = urllib2.Request(url, data)
        if self.phpsessid:
            url.add_header('cookie', "PHPSESSID=" + self.phpsessid + ((';key='+self.key) if self.key else ''))
        
        for header, value in headers_example.items(): url.add_header(header, value)
        if headers:
            for header, value in headers.items(): url.add_header(header, value)
        
        try:
            return (self.opener.open if redir else self.noredir.open)(url, timeout=10)
        except urllib2.HTTPError as exc:
            raise TabunError(code=exc.getcode())
        except urllib2.URLError as exc:
            raise TabunError(exc.reason.strerror, -exc.reason.errno if exc.reason.errno else 0)
        except socket.timeout:
            raise TabunError("Timeout", -2)
     
    def send_form(self, url, fields=(), files=(), timeout=None, headers={}, redir=True):
        if not isinstance(url, urllib2.Request):
            if url[0] == "/": url = http_host + url
            url = urllib2.Request(url)
        if self.phpsessid:
            url.add_header('cookie', "PHPSESSID=" + self.phpsessid + ((';key='+self.key) if self.key else ''))
        
        for header, value in headers_example.items(): url.add_header(header, value)
        if headers:
            for header, value in headers.items(): url.add_header(header, value)
            
        content_type, data = encode_multipart_formdata(fields, files)
        url.add_header('content-type', content_type)
        
        try:
            if timeout is None:
                return (self.opener.open if redir else self.noredir.open)(url, data, timeout=20)
            else:
                return (self.opener.open if redir else self.noredir.open)(url, data, timeout, timeout=20)
        except urllib2.HTTPError as exc:
            raise TabunError(code=exc.getcode())
        except urllib2.URLError as exc:
            raise TabunError(exc.reason.strerror, -exc.reason.errno if exc.reason.errno else 0)
        except socket.timeout:
            raise TabunError("Timeout", -2)
       
    def add_post(self, blog_id, title, body, tags, draft=False):
        self.check_login()
        blog_id = int(blog_id if blog_id else 0)
        
        if isinstance(tags, (tuple, list)): tags = u", ".join(tags)
        
        fields = {
            'topic_type': 'topic',
            'security_ls_key': self.security_ls_key,
            'blog_id': str(blog_id),
            'topic_title': unicode(title).encode("utf-8"),
            'topic_text': unicode(body).encode("utf-8"),
            'topic_tags': unicode(tags).encode("utf-8")
        }
        if draft: fields['submit_topic_save'] = "Сохранить в черновиках"
        else: fields['submit_topic_publish'] = "Опубликовать"
        
        link = self.send_form('/topic/add/', fields, redir=False).headers.get('location')
        return parse_post_url(link)
        
    def delete_post(self, post_id, security_ls_key=None, cookie=None):
        self.check_login()
        try:
            return self.urlopen(\
                url='/topic/delete/'+str(int(post_id))+'/?security_ls_key='+self.security_ls_key, \
                headers={"referer": http_host+"/blog/"+str(post_id)+".html"}, \
                redir=False\
            ).getcode() / 100 == 3
        except TabunError:
            return False
            
    def toggle_blog_subscribe(self, blog_id):
        self.check_login()
        blog_id = int(blog_id)
        
        fields = {
            'idBlog': str(blog_id),
            'security_ls_key': self.security_ls_key
        }
        
        data = self.send_form('/blog/ajaxblogjoin/', fields, (), headers={'x-requested-with': 'XMLHttpRequest'}).read()
        
        result = self.jd.decode(data)
        if result['bStateError']: raise TabunResultError(result['sMsg'].encode("utf-8"))
        return result['bState']
        
    def comment(self, post_id, text, reply=0):
        self.check_login()
        post_id = int(post_id)
        url = "/blog/ajaxaddcomment/"
        
        req = "comment_text=" + urllib2.quote(unicode(text).encode("utf-8")) + "&"
        req += "reply=" + str(int(reply)) + "&"
        req += "cmt_target_id=" + str(post_id) + "&"
        req += "security_ls_key=" + urllib2.quote(self.security_ls_key)
        
        data = self.urlopen(url, req).read()
        data = self.jd.decode(data)
        if data['bStateError']: raise TabunResultError(data['sMsg'].encode("utf-8"))
        return data['sCommentId']
        
    def get_posts(self, url="/index/newall/", raw_data=None):
        if not raw_data:
            req = self.urlopen(url)
            url = req.url
            raw_data = req.read()
        
        posts = []

        f = raw_data.find("<rss")
        if f < 250 and f >= 0:
            node = simplexml.XML2Node(raw_data)
            channel = node.getTag("channel")
            if not channel:  raise TabunError("No RSS channel")
            items = channel.getTags("item")
            items.reverse()
            
            for item in items:
                post = parse_rss_post(item)
                if post: posts.append(post)
            
            return posts
        
        else:
            data = raw_data[raw_data.find("<article class="):raw_data.rfind("</article> <!-- /.topic -->")+10]
            if not data: raise TabunError("No post")
            parser = HTML2XML()
            parser.feed(data)
            items = parser.node.getTags("article")
            items.reverse()
            
            for item in items:
                post = parse_post(item, url if ".html" in url else None)
                if post: posts.append(post)
            
            return posts
    
    def get_post(self, post_id, blog=None):
        if blog and blog != 'blog': url="/blog/"+str(blog)+"/"+str(post_id)+".html"
        else: url="/blog/"+str(post_id)+".html"
        
        posts = self.get_posts(url)
        if not posts: return None
        return posts[0]

    def get_comments(self, url="/comments/", raw_data=None):
        """Возвращает массив, содержащий объекты Comment и числа (id комментария) вместо удалённых комментариев."""
        if not raw_data:
            req = self.urlopen(url)
            url = req.url
            raw_data = req.read()
            del req
        blog, post_id = parse_post_url(url)
        
        raw_data = raw_data = raw_data[raw_data.find('<div class="comments'):raw_data.rfind('<!-- /content -->')]
        
        parser = HTML2XML()
        parser.feed(raw_data)
        
        raw_comms = []
        
        div = parser.node.getTag("div")
        if not div: return []
        
        for node in div.getTags("div"):
            if node['class'] == 'comment-wrapper':
                raw_comms.extend(parse_wrapper(node))
                
        for sect in div.getTags("section"):
            if not sect['class']: continue
            if "comment" in sect['class']:
                raw_comms.append(sect)
                
        comms = []
        
        for sect in raw_comms:
            c = parse_comment(sect, post_id, blog)
            if c: comms.append(c)
            else:
                if sect["id"] and sect["id"].find("comment_id_")==0:
                    comms.append(int(sect["id"].rsplit("_",1)[-1]))
                else:
                    print "wtf comment"
        
        return comms

    def get_blogs_list(self, page=1, order_by="blog_rating", order_way="desc", url=None):
        if not url:
            url = "/blogs/" + ("page"+str(page)+"/" if page>1 else "") + "?order=" + str(order_by) + "&order_way=" + str(order_way)
        
        data = self.urlopen(url).read()
        data = data[data.find('<table class="table table-blogs'):data.rfind('</table>')]
        
        parser = HTML2XML()
        parser.feed(data)
        
        node = parser.node.getTag("table")
        if node.getTag("tbody"): node = node.getTag("tbody")
        
        blogs = []
        
        for tr in node.getTags("tr"):
            p = tr.getTag("td", {"class":"cell-name"})
            if not p: continue
            p = p.getTag("p")
            if not p: continue
            a = p.getTag("a")
            
            link = a['href']
            if not link: continue
            
            blog = link[:link.rfind('/')].encode("utf-8")
            blog = blog[blog.rfind('/')+1:]
            
            name = a.getData()
            closed = bool(p.getTag("i", {"class":"icon-synio-topic-private"}))
            
            cell_readers = tr.getTag("td", {"class":"cell-readers"})
            readers = int(cell_readers.getData())
            blog_id = int(cell_readers['id'].rsplit("_",1)[-1])
            rating = float(tr.getTags("td")[-1].getData())
            
            creator = tr.getTag("td", {"class":"cell-name"}).getTag("span", {"class":"user-avatar"}).getTags("a")[-1].getData().encode("utf-8")
            
            blogs.append( Blog(blog_id, blog, name, creator, readers, rating, closed) )
            
        return blogs
        
    def get_posts_and_comments(self, post_id, blog=None, raw_data=None):
        post_id = int(post_id)
        if not raw_data:
            req = self.urlopen("/blog/" + (blog+"/" if blog else "") + str(post_id) + ".html")
            url = req.url
            raw_data = req.read()
            del req
        
        post = self.get_posts(url=url, raw_data=raw_data)
        comments = self.get_comments(url=url, raw_data=raw_data)
        
        return post[0], comments
        
    def get_comments_from(self, post_id, comment_id=0):
        self.check_login()
        post_id = int(post_id)
        comment_id = int(comment_id) if comment_id else 0
        
        url = "/blog/ajaxresponsecomment/"
        
        req = "idCommentLast=" + str(comment_id) + "&"
        req += "idTarget=" + str(post_id) + "&"
        req += "typeTarget=topic&"
        req += "security_ls_key=" + urllib2.quote(self.security_ls_key)
        
        data = self.urlopen(url, req).read()
        #return data
        data = self.jd.decode(data)
        
        if data['bStateError']: raise TabunResultError(data['sMsg'].encode("utf-8"))
        comms = []
        for comm in data['aComments']:
            parser = HTML2XML()
            parser.feed(comm['html'].encode("utf-8"))
            pcomm = parse_comment(parser.node.kids[0], post_id, None, comm['idParent'])
            if pcomm: comms.append(pcomm)
        
        return comms
        
    def get_stream_comments(self):
        self.check_login()
        data = self.urlopen(\
            "/ajax/stream/comment/",\
            "security_ls_key="+urllib2.quote(self.security_ls_key)\
        ).read()
        
        data = self.jd.decode(data)
        if data['bStateError']: raise TabunResultError(data['sMsg'].encode("utf-8"))
        
        parser = HTML2XML()
        parser.feed(data['sText'].encode("utf-8"))
        
        node = parser.node.getTag("ul")
        if not node: return []
        
        items = []
        
        for item in node.getTags("li", {"class": "js-title-comment"}):
            p = item.getTag("p")
            a, blog_a = p.getTags("a")[:2]
            author = a.getData().encode("utf-8")
            blog = blog_a['href'][:-1].rsplit("/",1)[-1].encode("utf-8")
            blog_title = blog_a.getData()
            
            comment_id = int(item.getTag("a")['href'].rsplit("/",1)[-1])
            title = item.getTag("a").getData()
            
            comments_count = int(item.getTag("span").getData())
            
            sitem = StreamItem(blog, blog_title, title, author, comment_id, comments_count)
            items.append(sitem)

        return items

    def get_short_blogs_list(self, raw_data=None):
        if not raw_data:
            raw_data = self.urlopen("/index/newall/").read()
        
        f = raw_data.find('<div class="block-content" id="block-blog-list"')
        if f < 0: return []
        raw_data = raw_data[f:]
        raw_data = raw_data[:raw_data.find("</ul>")]
        
        parser = HTML2XML()
        parser.feed(raw_data)
        node = parser.node.getTag("div")
        if not node: return []
        del parser, raw_data, f
        node = node.getTag("ul")
        
        blogs = []
        
        for item in node.getTags("li"):
            blog_id = item.getTag("input")['onclick'].encode("utf-8")
            blog_id = blog_id[blog_id.find("',")+2:]
            blog_id = int(blog_id[:blog_id.find(")")])
            
            a = item.getTag("a")
            
            blog = a['href'].encode("utf-8")[:-1]
            blog = blog[blog.rfind("/")+1:]
            
            name = a.getData()
            
            closed = bool(item.getTag("i", {"class": u"icon-synio-topic-private"}))
            
            blogs.append( Blog(blog_id, blog, name, "", closed=closed) )
        
        return blogs

def parse_post(item, link=None):
    header = findTag(item, "header", {"class": "topic-header"})
    title = findTag(header, "h1", {"class":"topic-title word-wrap"})
    if not title: return
    if not link:
        link = findTag(title, "a")
        if not link: return
        link = link['href']
        if not link: return
    author = findTag(header, "a", {"rel": "author"})
    if not author: return
    else: author = author.getData().encode("utf-8")
    post_id = int(link[link.rfind("/")+1:link.rfind(".h")])
    
    blog = link[:link.rfind('/')].encode("utf-8")
    blog = blog[blog.rfind('/')+1:]
    
    title = title.getCDATA().strip()
    private = not findTag(header, "a", {"class":"topic-blog private-blog"}) is None
    
    blog_name = findTag(header, "a", {"class": "topic-blog"})
    if blog_name: blog_name = blog_name.getData().strip()
    
    post_time = findTag(item, "time")
    if post_time: post_time = time.strptime(post_time["datetime"], "%Y-%m-%dT%H:%M:%S+04:00")
    else: post_time = time.localtime()
    
    node = findTag(item, "div", {"class":"topic-content text"})
    if not node:
        return
    
    nextbtn = node.getTag("a",{"title":u"Читать дальше"})
    if nextbtn:
        node.delChild(nextbtn)
        
    footer = findTag(item, "footer", {"class":"topic-footer"})
    ntags = findTag(footer, "p")
    if not ntags: return
    tags = []
    for ntag in ntags.getChildren():
        if not ntag: continue
        tags.append(ntag.getData())
    
    if node.data:
        node.data[0] = node.data[0].lstrip()
        node.data[-1] = node.data[-1].rstrip()
    
    return Post(post_time, blog, post_id, author, title, node, tags, short=not nextbtn is None, private=private, blog_name=blog_name)
    
def parse_rss_post(item):
    link = item.getTag("link").getData().encode("utf-8")
    
    title = item.getTag("title").getCDATA().strip()
    if not title: return
    
    author = item.getTag("creator")
    if not author: author = item.getTag("dc:creator")
    
    author = author.getData().encode("utf-8")
    if not author: return
    
    post_id = int(link[link.rfind("/")+1:link.rfind(".h")])
    blog = link[:link.rfind('/')].encode("utf-8")
    blog = blog[blog.rfind('/')+1:]
    
    private = False # в RSS закрытые блоги пока не обнаружены
    
    post_time = item.getTag("pubDate")
    if post_time and post_time.getData(): post_time = time.strptime(post_time.getData().encode("utf-8").split(" ",1)[-1], "%d %b %Y %H:%M:%S +0400")
    else: post_time = time.localtime()
    
    node = item.getTag("description").getCDATA()
    if not node: return
    parser = HTML2XML()
    parser.feed(node.encode("utf-8"))
    node = parser.node
    node['class'] = "topic-content text"
    del parser
    
    nextbtn = node.getTag("a",{"title":u"Читать дальше"})
    if nextbtn:
        node.delChild(nextbtn)

    if node.data:
        node.data[0] = node.data[0].lstrip()
        node.data[-1] = node.data[-1].rstrip()
      
    ntags = item.getTags("category")
    if not ntags: return
    tags = []
    for ntag in ntags:
        if not ntag: continue
        tags.append(ntag.getData())
        
    return Post(post_time, blog, post_id, author, title, node, tags, short=not nextbtn is None, private=private)     

def parse_wrapper(node):
    comms = []
    nodes = [node]
    i=0
    while nodes:
        node = nodes.pop(0)
        sect = node.getTag("section")
        if not sect['class']: break
        if not "comment" in sect['class']: break
        comms.append(sect)
        nodes.extend(node.getTags("div", {"class": "comment-wrapper"}))
    return comms

def parse_comment(node, post_id, blog=None, parent_id=None):
    try:
        body = node.getTag("div", {"class":"comment-content"}).getTag("div")
        if body.data:
            body.data[0] = body.data[0].lstrip()
            body.data[-1] = body.data[-1].rstrip()
        info = node.getTag("ul", {"class":"comment-info"})
        if not info: info = node.getTag("div", {"class":"comment-path"}).getTag("ul", {"class":"comment-info"})
        nick = info.getTags("li")[0].getTags("a")[-1].getData()
        tm = info.getTags("li")[1].getTag("time")['datetime']
        tm = time.strptime(tm, "%Y-%m-%dT%H:%M:%S+04:00")
        
        comment_id = int(info.getTag("li", {"class": "comment-link"}).getTag("a")['href'].rsplit("/",1)[-1])
        post_title = None
        try:
            link = info.getTags("li")
            if not link or link[-1]['id']: link = info
            else: link = link[-1]
            link = link.getTag("a", {"class":"comment-path-topic"})
            post_title = link.getData()
            link = link['href']
            post_id = int(link[link.rfind("/")+1:link.rfind(".h")])
            blog = link[:link.rfind('/')].encode("utf-8")
            blog = blog[blog.rfind('/')+1:]
        except KeyboardInterrupt: raise
        except: pass
        
        if not parent_id:
            parent_id = info.getTag("li", {"class": "goto goto-comment-parent"})
            if parent_id:
                parent_id = int(parent_id.getTag("a")['onclick'].rsplit(",",1)[-1].split(")",1)[0])
            else: parent_id = None
            
    except AttributeError: return
    
    if not body: return
    return Comment(tm, blog, post_id, comment_id, nick, body, parent_id, post_title)

def parse_post_url(link):
    if not link or not "/blog/" in link: return None, None
    post_id = int(link[link.rfind("/")+1:link.rfind(".h")])
    blog = link[:link.rfind('/')].encode("utf-8")
    blog = blog[blog.rfind('/')+1:]
    return blog, post_id
    
def htmlToString(node, with_cutted=True, fancy=True, vk_links=False):
    data = u""
    newlines = 0
    for item in node.getPayload():
        if not item: continue
        if isinstance(item, unicode):
            ndata = item.replace(u"\n", u" ")
            if newlines: ndata = ndata.lstrip()
            data += ndata
            if ndata: newlines = 0
            continue
        
        if item.getName() == "br":
            if newlines < 2:
                data += u"\n"
                newlines += 1
        elif item.getName() == "hr":
            data += "\n=====\n"
            newlines = 1
        
        elif fancy and item['class'] == "spoiler-title":
            continue
        elif fancy and item.getName() == "a" and item['title'] == u"Читать дальше":
            continue
        elif not with_cutted and item.getName() == "a" and item['rel'] == 'nofollow' and not item.getCDATA() and not item.getTag("img"):
            return data.strip()
        elif item.getName() in ("img",):
            continue
        
        elif vk_links and item.getName() == "a" and item['href'] and item['href'].find("://vk.com/") > 0:
            href = item['href']
            addr = href[href.find("com/")+4:]
            if addr[-1] in (".", ")"): addr = addr[:-1]
            
            stop=False
            for c in (u"/", u"?", u"&", u"(", u",", u")", u"|"):
                if c in addr:
                    data += item.getCDATA()
                    stop=True
                    break
            if stop: continue
            
            for typ in (u"wall", u"photo", u"page", u"video", u"topic", u"app"):
                if addr.find(typ) == 0:
                    data += item.getCDATA()
                    stop=True
                    break
            if stop: continue
            
            ndata = item.getData().replace("[", " ").replace("|", " ").replace("]", " ")
            data += " [" + addr + "|" + ndata + "] "
        
        else:
            if item.getName() in ("li", ):
                data += u"• "
            elif data and item.getName() in ("div", "p", "blockquote", "section", "ul", "li", "h1", "h2", "h3", "h4", "h5", "h6") and not newlines:
                data += u"\n"
                newlines = 1
            tmp = htmlToString(item)
            newlines = 0
            
            if item.getName() == "s": # зачёркивание
                tmp1=""
                for x in tmp:
                    tmp1 += x + u'\u0336'
                tmp1 = "<s>" + tmp1 + "</s>"
            elif item.getName() == "blockquote": # цитата
                tmp1 = u" «" + tmp + u"»\n"
                newlines = 1
            else: tmp1 = tmp
            
            data += tmp1
            
            if item.getName() in ("div", "p", "blockquote", "section", "ul", "li", "h1", "h2", "h3", "h4", "h5", "h6") and not newlines:
                data += u"\n"
                newlines = 1
    
    return data.strip()

def node2string(self,fancy=0, oncelist=('br', 'hr', 'img', 'source')):
    # modified simplexml method
    """ Method used to dump node into textual representation.
        if "fancy" argument is set to True produces indented output for readability."""
    s = (fancy-1) * 2 * ' ' + "<" + self.name
    if self.namespace:
        if not self.parent or self.parent.namespace!=self.namespace:
            if 'xmlns' not in self.attrs:
                s = s + ' xmlns="%s"'%self.namespace
    for key in self.attrs.keys():
        val = simplexml.ustr(self.attrs[key])
        s = s + ' %s="%s"' % ( key, simplexml.XMLescape(val) )
    s = s + ">"
    cnt = 0
    if self.kids:
        if fancy: s = s + "\n"
        for a in self.kids:
            if not fancy and (len(self.data)-1)>=cnt: s=s+simplexml.XMLescape(self.data[cnt])
            elif (len(self.data)-1)>=cnt: s=s+simplexml.XMLescape(self.data[cnt].strip())
            if isinstance(a, simplexml.Node):
                s = s + node2string(a, fancy and fancy+1, oncelist)
            elif a:
                s = s + a.__str__()
            cnt=cnt+1
    if not fancy and (len(self.data)-1) >= cnt: s = s + simplexml.XMLescape(self.data[cnt])
    elif (len(self.data)-1) >= cnt: s = s + simplexml.XMLescape(self.data[cnt].strip())
    if self.name in oncelist and not self.kids and s.endswith('>'):
        s=s[:-1]+' />'
        if fancy: s = s + "\n"
    else:
        if fancy and not self.data and self.kids: s = s + (fancy-1) * 2 * ' '
        s = s + "</" + self.name + ">"
        if fancy: s = s + "\n"
    return s
