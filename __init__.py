#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import re
import time
from . import utils
import urllib2
import httplib
from socket import timeout as socket_timeout
from json import JSONDecoder
from Cookie import BaseCookie

#: Адрес Табуна. Именно на указанный здесь адрес направляются запросы.
http_host = "http://tabun.everypony.ru"

#: Список полузакрытых блогов. В tabun_api нигде не используется, но может использоваться в использующих его программах.
halfclosed = ("borderline", "shipping", "erpg", "gak", "RPG", "roliplay")

#: Заголовки для HTTP-запросов. Возможно, стоит менять user-agent.
headers_example = {
    "connection": "close",
    "user-agent": "tabun_api/0.4.0; Linux/2.6", 
}

#: Регулярка для парсинга ссылки на пост.
post_url_regex = re.compile(r"/blog/(([A-z0-9_\-\.]{1,})/)?([0-9]{1,}).html")

class NoRedirect(urllib2.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return fp

    http_error_301 = http_error_303 = http_error_307 = http_error_302

class TabunError(Exception):
    """Общее для библиотеки исключение. Содержит атрибут code с всякими разными циферками для разных типов исключения, обычно совпадает с HTTP-кодом ошибки при запросе. А в args[0] или текст, или снова код ошибки."""
    def __init__(self, msg=None, code=0):
        if not msg: msg = str(code)
        Exception.__init__(self, str(msg))
        self.code = int(code)

class TabunResultError(TabunError):
    """Исключение, содержащее текст ошибки, который вернул сервер. Как правило, это текст соответствующих всплывашек на сайте."""
    pass

class Post:
    """Пост."""
    def __init__(self, time, blog, post_id, author, title, draft, vote_count, vote_total, body, tags, short=False, private=False, blog_name=None, poll=None):
        self.time = time
        self.blog = str(blog)
        self.post_id = int(post_id)
        self.author = str(author)
        self.title = unicode(title)
        self.draft = bool(draft)
        self.vote_count = int(vote_count) if not vote_count is None else None
        self.vote_total = int(vote_total) if not vote_total is None else None
        self.body = body
        self.tags = tags
        self.short = bool(short)
        self.private = bool(private)
        self.blog_name = unicode(blog_name) if blog_name else None
        self.poll = poll
        
    def __repr__(self):
        return "<post " + self.blog + "/" + str(self.post_id) + ">"
    
    def __str__(self):
        return self.__repr__()

class Comment:
    """Коммент."""
    def __init__(self, time, blog, post_id, comment_id, author, body, vote, parent_id=None, post_title=None, unread=False):
        self.time = time
        self.blog = str(blog) if blog else None
        self.post_id = int(post_id) if post_id else None
        self.comment_id = int(comment_id)
        self.author = str(author)
        self.body = body
        self.vote = int(vote)
        self.unread = bool(unread)
        if parent_id: self.parent_id = int(parent_id)
        else: self.parent_id = None
        if post_title: self.post_title = unicode(post_title)
        else: self.post_title = None
        
    def __repr__(self):
        return "<comment " + (self.blog + "/" + str(self.post_id) + "/" if self.blog and self.post_id else "") + str(self.comment_id) + ">"

    def __str__(self):
        return self.__repr__()

class Blog:
    """Блог."""
    def __init__(self, blog_id, blog, name, creator, readers=0, rating=0.0, closed=False, description=None, admins=None, moderators=None, vote_count=-1, posts_count=-1):
        self.blog_id = int(blog_id)
        self.blog = str(blog)
        self.name = unicode(name)
        self.creator = str(creator)
        self.readers = int(readers)
        self.rating = int(rating)
        self.closed = bool(closed)
        self.description = description
        self.admins = admins
        self.moderators = moderators
        self.vote_count = int(vote_count)
        self.posts_count = int(posts_count)

    def __repr__(self):
        return "<blog " + self.blog + ">"

    def __str__(self):
        return self.__repr__()

class StreamItem:
    """Элемент «Прямого эфира»."""
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

class UserInfo:
    """Информация о броняше."""
    def __init__(self, user_id, username, realname, skill, rating, userpic=None, gender=None, birthday=None, registered=None, last_activity=None):
        self.user_id = int(user_id)
        self.username = str(username)
        self.realname = unicode(realname) if realname else None
        self.skill = float(skill)
        self.rating = float(rating)
        self.userpic = str(userpic) if userpic else None
        self.gender = ('M' if gender == 'M' else 'F') if gender else None
        self.birthday = birthday
        self.registered = registered
        self.last_activity = last_activity
    
    def __repr__(self):
        return "<userinfo " + self.username + ">"
    
    def __str__(self):
        return self.__repr__()

class Poll:
    """Опрос. Список items содержит кортежи (название ответа, процент проголосовавших, число проголосовавших)."""
    def __init__(self, total, notvoted, items):
        self.total = int(total)
        self.notvoted = int(notvoted)
        self.items = []
        for x in items:
            self.items.append( (unicode(x[0]), float(x[1]), int(x[2])) )
 
class TalkItem:
    """Личное сообщение. В поле date временно содержится голая строка, которую тупо лень парсить из-за чутка кривой вёрстки."""
    def __init__(self, talk_id, recipinets, unread, title, date, body=None, author=None, comments=[]):
        self.talk_id = int(talk_id)
        self.recipinets = map(str, recipinets)
        self.unread = bool(unread)
        self.title = unicode(title)
        self.date = date
        self.body = body
        self.author = str(author) if author else None
        self.comments = comments if comments else []
    
    def __repr__(self):
        return "<talk " + str(self.talk_id) + ">"
    
    def __str__(self):
        return self.__repr__()
 
class User:
    """Через божественные объекты класса User осуществляется всё взаимодействие с Табуном. Почти все функции могут кидаться исключением TabunResultError с текстом ошибки (который на сайте обычно показывается во всплывашке в углу).
    
    Допустимые комбинации параметров (в квадратных скобках опциональные):
    
    * login + passwd [ + phpsessid]
    * phpsessid [+ key] - без куки key разлогинивает через некоторое время
    * login + phpsessid + security_ls_key [+ key] (без запроса к серверу)
    * без параметров (анонимус)
    
    Если у функции есть параметр raw_data, то через него можно передать код страницы, чтобы избежать лишнего парсинга. Если есть параметр url, то при его указании открывается именно указанный url вместо формирования стандартного с помощью других параметров функции.
    
    phpsessid - печенька (cookie), по которой идентифицируется пользователь, security_ls_key - секретный ключ движка livestreet для отправки запросов, key - печенька неизвестного мне назначения. Можно не париться с ними, их автоматически пришлёт сервер во время инициализации объекта. А можно, например, не авторизоваться по логину и паролю, а выдрать из браузера печеньку PHPSESSID и авторизоваться через неё.
    
    У класса также есть следующие поля:
    
    * username — имя пользователя или None
    * talk_unread — число непрочитанных личных сообщений (после update_userinfo)
    * skill — силушка (после update_userinfo)
    * rating — кармушка (после update_userinfo)
    * timeout — таймаут ожидания ответа от сервера (для urllib2.urlopen, по умолчанию 20)
    * phpsessid, security_ls_key, key — ну вы поняли"""
    
    phpsessid = None
    username = None
    security_ls_key = None
    key = None
    timeout = 20
    talk_unread = 0
    skill = 0.0
    rating = 0.0
    
    def __init__(self, login=None, passwd=None, phpsessid=None, security_ls_key=None, key=None):
        
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
            self.update_userinfo(data)
        
        if login and passwd:
            self.login(login, passwd)
        elif login and self.phpsessid and not self.username:
            self.username = str(login)
    
    def update_userinfo(self, raw_data):
        """Парсит имя пользователя, рейтинг и число сообщений и записывает в объект. Возвращает имя пользователя."""
        userinfo = utils.find_substring(raw_data, '<div class="dropdown-user"', "<nav", with_end=False)
        if not userinfo: return
        
        node = utils.parse_html_fragment(userinfo)[0]
        dd_user = node.xpath('//*[@id="dropdown-user"]')
        if not dd_user:
            self.username = None
            self.talk_count = 0
            self.skill = 0.0
            self.rating = 0.0
            return
        dd_user = dd_user[0]
        
        username = dd_user.xpath('a[2]/text()[1]')
        if username and username[0]: self.username = str(username[0])
        else:
            self.talk_count = 0
            self.skill = 0.0
            self.rating = 0.0
            return
        
        talk_count = dd_user.xpath('ul/li[@class="item-messages"]/a[@class="new-messages"]/text()')
        if not talk_count: self.talk_unread = 0
        else: self.talk_unread = int(talk_count[0][1:])
        
        strength = dd_user.xpath('ul[@class="dropdown-user-menu"]/li/span/text()')
        if not strength: self.skill = 0.0
        else: self.skill = float(strength[0])
        
        if len(strength) < 2: self.rating = 0.0
        else: self.rating = float(strength[1])
        
        return self.username
    
    def login(self, login, password, return_path=None, remember=True):
        """Логинится и записывает печеньку key в случае успеха. Параметр return_path нафиг не нужен, remember - галочка «Запомнить меня»."""
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
        """Генерирует исключение, если нет печеньки PHPSESSID или security_ls_key."""
        if not self.phpsessid or not self.security_ls_key:
            raise TabunError("Not logined")
    
    def urlopen(self, url, data=None, headers={}, redir=True):
        """Отправляет HTTP-запрос и возвращает результат urllib2.urlopen (объект urllib.addinfourl). Если указан параметр data, то отправляется POST-запрос. В качестве URL может быть путь с доменом (http://tabun.everypony.ru/), без домена (/index/newall/) или объект urllib2.Request. Если redir установлен в False, то не будет осуществляться переход по перенаправлению (HTTP-коды 3xx). Может кидаться исключением TabunError."""
        if not isinstance(url, urllib2.Request):
            if url[0] == "/": url = http_host + url
            url = urllib2.Request(url, data)
        if self.phpsessid:
            url.add_header('cookie', "PHPSESSID=" + self.phpsessid + ((';key='+self.key) if self.key else ''))
        
        for header, value in headers_example.items():
            url.add_header(header, value)
        if headers:
            for header, value in headers.items():
                if header and value: url.add_header(header, value)
        
        try:
            return (self.opener.open if redir else self.noredir.open)(url, timeout=self.timeout)
        except urllib2.HTTPError as exc:
            raise TabunError(code=exc.getcode())
        except urllib2.URLError as exc:
            raise TabunError(exc.reason.strerror, -exc.reason.errno if exc.reason.errno else 0)
        except httplib.HTTPException as exc:
            raise TabunError("HTTP error", -4)
        except socket_timeout:
            raise TabunError("Timeout", -2)
        except IOError as exc:
            raise TabunError("IOError", -3)
     
    def send_form(self, url, fields=(), files=(), headers={}, redir=True):
        """Формирует multipart/form-data запрос и отправляет его через функцию urlopen."""
        content_type, data = utils.encode_multipart_formdata(fields, files)
        if not isinstance(url, urllib2.Request):
            if url[0] == "/": url = http_host + url
            url = urllib2.Request(url, data)
        url.add_header('content-type', content_type)
        return self.urlopen(url, None, headers, redir)
       
    def add_post(self, blog_id, title, body, tags, draft=False, check_if_error=False):
        """Отправляет пост и возвращает имя блога с номером поста в случае удачи или (None,None) в случае неудачи.
        При check_if_error=True проверяет наличие поста по заголовку даже в случае ошибки (если, например, таймаут или 404, но пост, как иногда бывает, добавляется)."""
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
        
        try:
            link = self.send_form('/topic/add/', fields, redir=False).headers.get('location')
        except TabunError:
            if not check_if_error or not self.username: raise
            url = '/topic/saved/' if draft else '/profile/' + self.username + '/created/topics/'
            
            try: posts = self.get_posts(url)
            except: posts = []
            posts.reverse()
            
            for post in posts[:2]:
                if posts and post.title == unicode(title) and post.author == self.username:
                    return post.blog, post.post_id
            
            return None, None
        else:
            return parse_post_url(link)
        

    def create_blog(self, title, url, description, rating_limit=0, closed=False):
        """Создаёт блог и возвращает его url-имя или None в случае неудачи."""
        self.check_login()
        
        fields = {
            'security_ls_key': self.security_ls_key,
            "blog_title": unicode(title).encode("utf-8"),
            "blog_url": unicode(url).encode("utf-8"),
            "blog_type": "close" if closed else "open",
            "blog_description": unicode(description).encode("utf-8"),
            "blog_limit_rating_topic": str(int(rating_limit)),
            "submit_blog_add": "Сохранить"
        }
        
        link = self.send_form('/blog/add/', fields, redir=False).headers.get('location')
        if not link: return
        if link[-1] == '/': link = link[:-1]
        return link[link.rfind('/') + 1:]

    def edit_blog(self, blog_id, title, description, rating_limit=0, closed=False):
        """Редактирует блог и возвращает его url-имя или None в случае неудачи."""
        self.check_login()
        
        fields = {
            'security_ls_key': self.security_ls_key,
            "blog_title": unicode(title).encode("utf-8"),
            "blog_url": "",
            "blog_type": "close" if closed else "open",
            "blog_description": unicode(description).encode("utf-8"),
            "blog_limit_rating_topic": str(int(rating_limit)),
            "avatar_delete": "",
            "submit_blog_add": "Сохранить"
        }
        
        link = self.send_form('/blog/edit/' + str(int(blog_id)) + '/', fields, redir=False).headers.get('location')
        if not link: return
        if link[-1] == '/': link = link[:-1]
        return link[link.rfind('/') + 1:]

    def delete_blog(self, blog_id):
        """Удаляет блог и возвращает True/False в случае удачи/неудачи."""
        self.check_login()
        return self.urlopen(\
            url='/blog/delete/'+str(int(post_id))+'/?security_ls_key='+self.security_ls_key, \
            headers={"referer": http_host+"/"}, \
            redir=False\
        ).getcode() / 100 == 3

    def preview_post(self, blog_id, title, body, tags):
        """Возвращает HTML-код предпросмотра поста (сам пост плюс мусор типа заголовка «Предпросмотр»)."""
        self.check_login()
        
        fields = {
            'topic_type': 'topic',
            'security_ls_key': self.security_ls_key,
            'blog_id': str(blog_id),
            'topic_title': unicode(title).encode("utf-8"),
            'topic_text': unicode(body).encode("utf-8"),
            'topic_tags': unicode(tags).encode("utf-8")
        }
        
        data = self.send_form('/ajax/preview/topic/', fields, (), headers={'x-requested-with': 'XMLHttpRequest'}).read()
        node = utils.parse_html_fragment(data)[0]
        data = node.text
        result = self.jd.decode(data)
        if result['bStateError']: raise TabunResultError(result['sMsg'].encode("utf-8"))
        return result['sText']
       
    def delete_post(self, post_id):
        """Удаляет пост и возвращает True/False в случае удачи/неудачи."""
        self.check_login()
        return self.urlopen(\
            url='/topic/delete/'+str(int(post_id))+'/?security_ls_key='+self.security_ls_key, \
            headers={"referer": http_host+"/blog/"+str(post_id)+".html"}, \
            redir=False\
        ).getcode() / 100 == 3
            
    def toggle_blog_subscribe(self, blog_id):
        """Подписывается на блог/отписывается от блога и возвращает состояние: True - подписан, False - не подписан."""
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
        
    def comment(self, post_id, text, reply=0, typ="blog"):
        """Отправляет коммент и возвращает его номер. Тип - blog (посты) или talk (личные сообщения)"""
        self.check_login()
        post_id = int(post_id)
        url = "/"+(typ if typ in ("blog", "talk") else "blog")+"/ajaxaddcomment/"
        
        req = "comment_text=" + urllib2.quote(unicode(text).encode("utf-8")) + "&"
        req += "reply=" + str(int(reply)) + "&"
        req += "cmt_target_id=" + str(post_id) + "&"
        req += "security_ls_key=" + urllib2.quote(self.security_ls_key)
        
        data = self.urlopen(url, req).read()
        data = self.jd.decode(data)
        if data['bStateError']: raise TabunResultError(data['sMsg'].encode("utf-8"))
        return data['sCommentId']
        
    def get_posts(self, url="/index/newall/", raw_data=None):
        """Возвращает список постов со страницы или RSS. Если постов нет - кидает исключение TabunError("No post")."""
        if not raw_data:
            req = self.urlopen(url)
            url = req.url
            raw_data = req.read()
        
        posts = []

        f = raw_data.find("<rss")
        if f < 250 and f >= 0:
            node = utils.lxml.etree.fromstring(raw_data)
            channel = node.find("channel")
            if channel is None: raise TabunError("No RSS channel")
            items = channel.findall("item")
            items.reverse()
            
            for item in items:
                post = parse_rss_post(item)
                if post: posts.append(post)
            
            return posts
        
        data = utils.find_substring(raw_data, "<article ", "</article> <!-- /.topic -->", extend=True)
        if not data: raise TabunError("No post")
        items = filter(lambda x:not isinstance(x, (str, unicode)) and x.tag=="article", utils.parse_html_fragment(data))
        items.reverse()
        
        for item in items:
            post = parse_post(item, url if ".html" in url else None)
            if post: posts.append(post)
        
        return posts
    
    def get_post(self, post_id, blog=None):
        """Возвращает пост по номеру. Рекомендуется указать url-имя блога, чтобы избежать перенаправления и лишнего запроса. Если поста нет - кидается исключением TabunError("No post"). В случае проблем с парсингом может вернуть None."""
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
        
        raw_data = utils.find_substring(raw_data, '<div class="comments', '<!-- /content -->', extend=True, with_end=False)
        
        div = utils.parse_html_fragment(raw_data)
        if len(div) == 0: return []
        div = div[0]
        
        raw_comms = []

        for node in div.findall("div"):
            if node.get('class') == 'comment-wrapper':
                raw_comms.extend(parse_wrapper(node))
        
        # for /comments/ page       
        for sect in div.findall("section"):
            if "comment" in sect.get('class', ''):
                raw_comms.append(sect)
                
        comms = []
        
        for sect in raw_comms:
            c = parse_comment(sect, post_id, blog)
            if c: comms.append(c)
            else:
                if sect.get("id", "").find("comment_id_")==0:
                    comms.append(int(sect.get("id").rsplit("_",1)[-1]))
                else:
                    print "wtf comment"
        
        return comms

    def get_blogs_list(self, page=1, order_by="blog_rating", order_way="desc", url=None):
        """Возвращает список объектов Blog."""
        if not url:
            url = "/blogs/" + ("page"+str(page)+"/" if page>1 else "") + "?order=" + str(order_by) + "&order_way=" + str(order_way)
        
        data = self.urlopen(url).read()
        data = utils.find_substring(data, '<table class="table table-blogs', '</table>')
        node = utils.parse_html_fragment(data)
        if not node: return []
        node = node[0]
        if node.find("tbody") is not None: node = node.find("tbody")
        
        blogs = []
        
        #for tr in node.findall("tr"):
        #for p in node.xpath('tr/td[@class="cell-name"]/p'):
        for tr in node.findall("tr"):
            p = tr.xpath('td[@class="cell-name"]/p')
            if len(p) == 0: continue
            p=p[0]
            a = p.find("a")
            
            link = a.get('href')
            if not link: continue
            
            blog = link[:link.rfind('/')].encode("utf-8")
            blog = blog[blog.rfind('/')+1:]
            
            name = unicode(a.text)
            closed = bool(p.xpath('i[@class="icon-synio-topic-private"]'))
            
            cell_readers = tr.xpath('td[@class="cell-readers"]')[0]
            readers = int(cell_readers.text)
            blog_id = int(cell_readers.get('id').rsplit("_",1)[-1])
            rating = float(tr.findall("td")[-1].text)
            
            creator = str( tr.xpath('td[@class="cell-name"]/span[@class="user-avatar"]/a')[-1].text )
            
            blogs.append( Blog(blog_id, blog, name, creator, readers, rating, closed) )
            
        return blogs
    
    def get_blog(self, blog, raw_data=None):
        """Возвращает информацию о блоге. Функция не доделана."""
        if not raw_data:
            req = self.urlopen("/blog/" + str(blog).replace("/", "") + "/")
            url = req.url
            raw_data = req.read()
            del req
        data = utils.find_substring(raw_data, '<div class="blog-top">', '<div class="nav-menu-wrapper">', with_end=False)
        
        node = utils.parse_html_fragment('<div>' + data + '</div>')
        if not node: return
        
        blog_top = node[0].xpath('div[@class="blog-top"]')[0]
        blog_inner = node[0].xpath('div[@id="blog"]/div[@class="blog-inner"]')[0]
        blog_footer = node[0].xpath('div[@id="blog"]/footer[@class="blog-footer"]')[0]
    
        name = blog_top.xpath('h2/text()[1]')[0]
        closed = len(blog_top.xpath('h2/i[@class="icon-synio-topic-private"]')) > 0
    
        vote_item = blog_top.xpath('div/div[@class="vote-item vote-count"]')[0]
        vote_count = int(vote_item.get("title", u"0").rsplit(" ",1)[-1])
        blog_id = int(vote_item.find("span").get("id").rsplit("_",1)[-1])
        vote_total = vote_item.find("span").text
        if vote_total[0] == "+": vote_total = float(vote_total[1:])
        else: vote_total = float(vote_total)
        
        avatar = blog_inner.xpath("header/img")[0].get("src")
        
        content = blog_inner.find("div")
        
        #description = content.find("p") #TODO: <p>a<hr>b - пофиксено Орхидеусом, дописать
        #content.remove(description)
        #content.remove(content.find("hr"))
        #content.remove(content.find("br"))
        
        description = None
        created = None
        posts_count = -1
        readers = -1
        admins = []
        moderators = []
        
        creator = blog_footer.xpath("div/a[2]/text()[1]")[0]
        
        return Blog(blog_id, blog, name, creator, readers, vote_total, closed, description, admins, moderators, vote_count, posts_count)
        
    
    def get_post_and_comments(self, post_id, blog=None, raw_data=None):
        """Возвращает пост и список комментов. По сути просто вызывает функции get_posts и get_comments."""
        post_id = int(post_id)
        if not raw_data:
            req = self.urlopen("/blog/" + (blog+"/" if blog else "") + str(post_id) + ".html")
            url = req.url
            raw_data = req.read()
            del req
        
        post = self.get_posts(url=url, raw_data=raw_data)
        comments = self.get_comments(url=url, raw_data=raw_data)
        
        return post[0] if post else None, comments
        
    def get_comments_from(self, post_id, comment_id=0, typ="blog"):
        """Возвращает комментарии к посту, начиная с определённого номера комментария. На сайте используется для подгрузки новых комментариев. Тип - blog (пост) или talk (личные сообщения)."""
        self.check_login()
        post_id = int(post_id)
        comment_id = int(comment_id) if comment_id else 0
        
        url = "/"+(typ if typ in ("blog", "talk") else "blog")+"/ajaxresponsecomment/"
        
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
            node = utils.parse_html_fragment(comm['html'])
            pcomm = parse_comment(node[0], post_id, None, comm['idParent'])
            if pcomm: comms.append(pcomm)
        
        return comms
        
    def get_stream_comments(self):
        """Возвращает «Прямой эфир» - объекты StreamItem."""
        self.check_login()
        data = self.urlopen(\
            "/ajax/stream/comment/",\
            "security_ls_key="+urllib2.quote(self.security_ls_key)\
        ).read()
        
        data = self.jd.decode(data)
        if data['bStateError']: raise TabunResultError(data['sMsg'].encode("utf-8"))
        
        node = utils.parse_html_fragment(data['sText'])
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
        """Возвращает список объектов Blogs, но у которого указаны только blog_id, имя и закрытость. Зато, в отличие от get_blogs_list, возвращаеются сразу все-все блоги."""
        if not raw_data:
            raw_data = self.urlopen("/index/newall/").read()
        
        raw_data = utils.find_substring(raw_data, '<div class="block-content" id="block-blog-list"', "</ul>")
        if not raw_data: return []
        
        node = utils.parse_html_fragment(raw_data)[0]
        del raw_data
        node = node.find("ul")
        
        blogs = []
        
        for item in node.findall("li"):
            blog_id = str(item.find("input").get('onclick'))
            blog_id = blog_id[blog_id.find("',")+2:]
            blog_id = int(blog_id[:blog_id.find(")")])
            
            a = item.find("a")
            
            blog = str(a.get('href'))[:-1]
            blog = blog[blog.rfind("/")+1:]
            
            name = unicode(a.text)
            
            closed = bool(item.xpath('i[@class="icon-synio-topic-private"]'))
            
            blogs.append( Blog(blog_id, blog, name, "", closed=closed) )
        
        return blogs
        
    def get_people_list(self, page=1, order_by="user_rating", order_way="desc", url=None):
        """Возвращает список броняш - объекты UserInfo."""
        if not url:
            url = "/people/" + ("index/page"+str(page)+"/" if page>1 else "") + "?order=" + str(order_by) + "&order_way=" + str(order_way)

        data = self.urlopen(url).read()
        data = utils.find_substring(data, '<table class="table table-users', '</table>')
        node = utils.parse_html_fragment(data)
        if not node: return []
        node = node[0]
        if node.find("tbody") is not None: node = node.find("tbody")
        
        peoples  = []
        
        for tr in node.findall("tr"):
            username = tr.xpath('td[@class="cell-name"]/div/p[1]/a/text()[1]')
            if not username: continue
            
            realname = tr.xpath('td[@class="cell-name"]/div/p[2]/text()[1]')
            if not realname: realname = None
            else: realname = unicode(realname[0])
            
            skill = tr.xpath('td[@class="cell-skill"]/text()[1]')
            if not skill: continue
            
            rating = tr.xpath('td[@class="cell-rating "]/strong/text()[1]')
            if not rating: rating = tr.xpath('td[@class="cell-rating negative"]/strong/text()[1]')
            if not rating: continue
            
            userpic = tr.xpath('td[@class="cell-name"]/a/img/@src')
            if not userpic: continue
            
            peoples.append(UserInfo(-1, username[0], realname, skill[0], rating[0], userpic=userpic[0]))
            
        return peoples
        
    def get_profile(self, username=None, raw_data=None):
        if not raw_data:
            raw_data = self.urlopen("/profile/" + str(username)).read()
        
        data = utils.find_substring(raw_data, '<div id="content"', '<!-- /content ', extend=True, with_end=False)
        if not data: return
        node = utils.parse_html_fragment(data)
        if not node: return
        node = node[0]
        
        profile = node.xpath('div[@class="profile"]')[0]
        
        username = str(profile.xpath('h2[@itemprop="nickname"]/text()')[0])
        realname = profile.xpath('p[@class="user-name"]/text()')
        
        skill = float(profile.xpath('div[@class="strength"]/div[1]/text()')[0])
        rating = profile.xpath('div[@class="vote-profile"]/div[1]')[0]
        user_id = int(rating.get("id").rsplit("_")[-1])
        rating = float(rating.findall('div')[1].find('span').text.strip().replace('+',''))
        
        userpic = node.xpath('div[@class="profile-info-about"]/a[1]/img')[0].get('src')
        
        birthday = None
        registered = None
        last_activity = None
        gender = None
        
        uls = node.xpath('div[@class="wrapper"]/div[@class="profile-left"]/ul[@class="profile-dotted-list"]/li')
        
        for ul in uls:
            name = ul.find('span').text.strip()
            value = ul.find('strong')
            
            if name == u'Дата рождения:':
                birthday = time.strptime(utils.mon2num(value.text), '%d %m %Y')
            elif name == u'Зарегистрирован:':
                registered = time.strptime(utils.mon2num(value.text), '%d %m %Y, %H:%M')
            elif name == u'Последний визит:':
                last_activity = time.strptime(utils.mon2num(value.text), '%d %m %Y, %H:%M')
            elif name == u'Пол:':
                gender = 'M' if value.text.strip() == u'мужской' else 'F'
        
        return UserInfo(user_id, username, realname[0] if realname else None, skill, rating, userpic, gender, birthday, registered, last_activity)
        
        
        
    def poll_answer(self, post_id, answer=-1):
        """Проголосовать в опросе. -1 - воздержаться. Возвращает новый объект Poll."""
        self.check_login()
        if answer < -1: answer = -1
        if post_id < 0: post_id = 0
        
        fields = {
            "idTopic": str(post_id),
            "idAnswer": str(answer),
            "security_ls_key": self.security_ls_key
        }
        
        data = self.send_form('/ajax/vote/question/', fields, (), headers={'x-requested-with': 'XMLHttpRequest'}).read()
        result = self.jd.decode(data)
        if result['bStateError']: raise TabunResultError(result['sMsg'].encode("utf-8"))
        poll = utils.parse_html_fragment('<div id="topic_question_area_'+str(post_id)+'" class="poll">' + result['sText'] + '</div>')
        return parse_poll(poll[0])
    
    def vote(self, post_id, value=0):
        """Ставит плюсик (1) или минусик (-1) или ничего (0) посту и возвращает его рейтинг."""
        self.check_login()
        
        fields = {
            "idTopic": str(post_id),
            "value": str(value),
            "security_ls_key": self.security_ls_key
        }
        
        data = self.send_form('/ajax/vote/topic/', fields, (), headers={'x-requested-with': 'XMLHttpRequest'}).read()
        result = self.jd.decode(data)
        if result['bStateError']: raise TabunResultError(result['sMsg'].encode("utf-8"))
        return int(result['iRating'])

    def edit_comment(self, comment_id, text):
        """Редактирует комментарий. Ничего не возвращает, потому что не доделал."""
        self.check_login()
        
        fields = {
            "commentId": str(int(comment_id)),
            "text": text.encode("utf-8"),
            "security_ls_key": self.security_ls_key
        }
        
        data = self.send_form('/role_ajax/savecomment/', fields, (), headers={'x-requested-with': 'XMLHttpRequest'}).read()
        result = self.jd.decode(data)
        if result['bStateError']: raise TabunResultError(result['sMsg'].encode("utf-8"))
        #TODO: return
        return None
        
        # int(result['iRating'])

    def get_editable_post(self, post_id, raw_data=None):
        """Возвращает blog_id, заголовок, исходный код поста, список тегов и галочку закрытия комментариев (True/False)."""
        if not raw_data:
            req = self.urlopen("/topic/edit/" + str(int(post_id)) + "/")
            raw_data = req.read()
            del req
        
        raw_data = utils.find_substring(
            raw_data, 
            '<form action="" method="POST" enctype="multipart/form-data" id="form-topic-add"',
            '<div class="topic-preview"',
            extend=True, with_end=False
        )
        
        form = utils.parse_html_fragment(raw_data)
        if len(form) == 0: return None
        form = form[0]
        
        blog_id = form.xpath('p/select[@id="blog_id"]')[0]
        ok = False
        for x in blog_id.findall("option"):
            if x.get("selected") is not None:
                ok = True
                blog_id = int(x.get("value"))
                break
        if not ok: blog_id = 0
        
        title = form.xpath('p/input[@id="topic_title"]')[0].get("value", u"")
        body = form.xpath("textarea")[0].text
        tags = form.xpath('p/input[@id="topic_tags"]')[0].get("value", u"").split(",")
        forbid_comment = bool(form.xpath('p/label/input[@id="topic_forbid_comment"]')[0].get("checked"))
        return blog_id, title, body, tags, forbid_comment

    def edit_post(self, post_id, blog_id, title, body, tags, draft=False):
        """Редактирует пост и возвращает его блог и номер в случае удачи или (None,None) в случае неудачи."""
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
        
        link = self.send_form('/topic/edit/' + str(int(post_id)) + '/', fields, redir=False).headers.get('location')
        return parse_post_url(link)
    
    def invite(self, blog_id, username):
        """Отправляет инвайт в блог с указанным номером указанному пользователю (или пользователям, если указать несколько через запятую). Возвращает словарь, который содержит пары юзернейм-текст ошибки в случае, если кому-то инвайт не отправился. Если всё хорошо, то словарь пустой."""
        self.check_login()
        
        blog_id = int(blog_id if blog_id else 0)
        
        fields = {
            "users": str(username),
            "idBlog": str(blog_id),
            'security_ls_key': self.security_ls_key,
        }
        
        data = self.send_form("/blog/ajaxaddbloginvite/", fields).read()
        result = self.jd.decode(data)
        if result['bStateError']: raise TabunResultError(result['sMsg'].encode("utf-8"))
        
        users = {}
        for x in result['aUsers']:
            if x['bStateError']:
                users[x['sUserLogin']] = x['sMsg']
        
        return users
    
    def get_talk_list(self, raw_data=None):
        """Возвращает список объектов Talk с личными сообщениями."""
        self.check_login()
        if not raw_data:
            req = self.urlopen("/talk/")
            raw_data = req.read()
            del req
        
        raw_data = utils.find_substring(raw_data, '<table ', '</table>')
        if not raw_data: return []
        
        node = utils.parse_html_fragment(raw_data)[0]
        
        elems = []
        
        for elem in node.xpath('//tr')[1:]:
            elem = parse_talk_item(elem)
            if elem: elems.append(elem)
        
        return elems
        
    def get_talk(self, talk_id, raw_data=None):
        """Возвращает объект Talk беседы с переданным номером."""
        self.check_login()
        if not raw_data:
            req = self.urlopen("/talk/read/" + str(int(talk_id)) + "/")
            raw_data = req.read()
            del req
        
        data = utils.find_substring(raw_data, "<article ", "</article>", extend=True)
        if not data: return
        
        item = utils.parse_html_fragment(data)[0]
        title = item.find("header").find("h1").text
        body = item.xpath('div[@class="topic-content text"]')
        if len(body) == 0:
            return
        body = body[0]
        
        recipients = map(lambda x: str(x.text.strip()), item.xpath('div[@class="talk-search talk-recipients"]/header/a[@class="username"]'))
        
        
        footer = item.find("footer")
        author = str(footer.xpath('ul/li[@class="topic-info-author"]/a[2]/text()')[0].strip())
        date = footer.xpath('ul/li[@class="topic-info-date"]/time')[0]
        date = time.strptime(date.get("datetime"), "%Y-%m-%dT%H:%M:%S+04:00")
        
        comments = self.get_comments(raw_data=raw_data)
        
        return TalkItem(talk_id, recipients, False, title, date, body, author, comments)

def parse_post(item, link=None):
    # Парсинг поста. Не надо юзать эту функцию.
    header = item.find("header")
    title = header.find("h1")
    if title is None: return
    if not link:
        link = title.find("a")
        if link is None: return
        link = link.get("href")
        if link is None: return 
    
    author = header.xpath('div/a[@rel="author"]/text()[1]')
    if len(author) == 0: return
    author = str(author[0])
    
    blog, post_id = parse_post_url(link)
    
    title = title.text_content().strip()
    private = bool(header.xpath('div/a[@class="topic-blog private-blog"]'))
    
    blog_name = header.xpath('div/a[@class="topic-blog"]/text()[1]')
    if len(blog_name) > 0: blog_name = unicode(blog_name[0])
    else: blog_name = None
    
    post_time = item.xpath('footer/ul/li[1]/time')
    if not post_time: post_time = item.xpath('header/div[@class="topic-info"]/time') # mylittlebrony.ru
    if post_time: post_time = time.strptime(post_time[0].get("datetime"), "%Y-%m-%dT%H:%M:%S+04:00")
    else: post_time = time.localtime()
    
    node = item.xpath('div[@class="topic-content text"]')
    if len(node) == 0:
        return
    node = node[0]
    
    node.text = node.text.lstrip()
    node.tail = ""
    if len(node) > 0 and node[-1].tail:
        node[-1].tail = node[-1].tail.rstrip()
    elif len(node) == 0 and node.text:
        node.text = node.text.rstrip()
    
    nextbtn = node.xpath(u'a[@title="Читать дальше"][1]')
    if len(nextbtn) > 0:
        node.remove(nextbtn[0])
        
    footer = item.find("footer")
    ntags = footer.find("p")
    tags = []
    if ntags is not None:
        for ntag in ntags.findall("a"):
            if not ntag.text: continue
            tags.append(unicode(ntag.text))
    
    draft = bool(header.xpath('h1/i[@class="icon-synio-topic-draft"]'))
    
    rateelem = header.xpath('div[@class="topic-info"]/div[@class="topic-info-vote"]/div/div[@class="vote-item vote-count"]')
    if rateelem:
        rateelem = rateelem[0]
    
        vote_count = int(rateelem.get("title").rsplit(" ",1)[-1])
        vote_total = rateelem.getchildren()[0]
        if not vote_total.getchildren():
            vote_total = int(vote_total.text.replace("+", ""))
        else:
            vote_total = None
    else:
        vote_count = -1
        vote_total = 0
    
    poll = item.xpath('div[@class="poll"]')
    if poll: poll = parse_poll(poll[0])
    
    return Post(post_time, blog, post_id, author, title, draft, vote_count, vote_total, node, tags, short=len(nextbtn) > 0, private=private, blog_name=blog_name, poll=poll)

def parse_poll(poll):
    # Парсинг опроса. Не надо юзать эту функцию.
    ul = poll.find('ul[@class="poll-result"]')
    if ul is not None:
        items = []
        for li in ul.findall('li'):
            item = [None, 0.0, 0]
            item[0] = li.xpath('dl/dd/text()[1]')[0].strip()
            item[1] = float(li.xpath('dl/dt/strong/text()[1]')[0][:-1])
            item[2] = int(li.xpath('dl/dt/span/text()[1]')[0][1:-1])
            items.append(item)
        poll_total = poll.xpath('div[@class="poll-total"]/text()')[-2:]
        total = int(poll_total[-2].rsplit(" ",1)[-1])
        notvoted = int(poll_total[-1].rsplit(" ",1)[-1])
        return Poll(total, notvoted, items)
    else:
        ul = poll.find('ul[@class="poll-vote"]')
        if ul is None: return
        items = []
        for li in ul.findall('li'):
            item = [None, -1.0, -1]
            item[0] = li.xpath('label/text()[1]')[0].strip()
            items.append(item)
        return Poll(-1, -1, items)
        
 
def parse_rss_post(item):
    # Парсинг rss. Не надо юзать эту функцию.
    link = str(item.find("link").text)
    
    title = unicode(item.find("title").text)
    if title is None:
        return
    
    author = item.find("dc:creator", {"dc": "http://purl.org/dc/elements/1.1/"})
    if author is None:
        return
    
    author = author.text
    
    if not author:
        return
    
    blog, post_id = parse_post_url(link)
    
    private = False # в RSS закрытые блоги пока не обнаружены
    
    post_time = item.find("pubDate")
    if post_time is not None and post_time.text is not None:
        post_time = time.strptime(str(post_time.text).split(" ",1)[-1], "%d %b %Y %H:%M:%S +0400")
    else:
        post_time = time.localtime()
    
    node = item.find("description").text
    if not node: return
    node = utils.parse_html_fragment(u"<div class='topic-content text'>" + node + '</div>')[0]
    
    nextbtn = node.xpath(u'a[@title="Читать дальше"][1]')
    if len(nextbtn) > 0:
        node.remove(nextbtn[0])
      
    ntags = item.findall("category")
    if not ntags: return
    tags = []
    for ntag in ntags:
        if ntag.text: continue
        tags.append(unicode(ntag.text))
        
    return Post(post_time, blog, post_id, author, title, False, 0, 0, node, tags, short=len(nextbtn) > 0, private=private)

def parse_wrapper(node):
    # Парсинг коммента. Не надо юзать эту функцию.
    comms = []
    nodes = [node]
    i=0
    while len(nodes) > 0:
        node = nodes.pop(0)
        sect = node.find("section")
        if not sect.get('class'): break
        if not "comment" in sect.get('class'): break
        comms.append(sect)
        nodes.extend(node.xpath('div[@class="comment-wrapper"]'))
    return comms

def parse_comment(node, post_id, blog=None, parent_id=None):
    # И это тоже парсинг коммента. Не надо юзать эту функцию.
    body = None
    try:
        unread = "comment-new" in node.get("class")
        body = node.xpath('div[@class="comment-content"][1]/div')[0]
        info = node.xpath('ul[@class="comment-info"]')
        if len(info) == 0:
            info = node.xpath('div[@class="comment-path"]/ul[@class="comment-info"]')[0]
        else:
            info = info[0]

        if body is not None:
            body.text = body.text.lstrip()
            body.tail = ""
            if len(body) > 0 and body[-1].tail:
                body[-1].tail = body[-1].tail.rstrip()
            elif len(body) == 0 and body.text:
                body.text = body.text.rstrip()
        
        nick = info.findall("li")[0].findall("a")[-1].text
        tm = info.findall("li")[1].find("time").get('datetime')
        tm = time.strptime(tm, "%Y-%m-%dT%H:%M:%S+04:00")
        
        comment_id = int(info.xpath('li[@class="comment-link"]/a')[0].get('href').rsplit("/",1)[-1])
        post_title = None
        try:
            link = info.findall("li")
            if not link or link[-1].get('id'): link = info
            else: link = link[-1]
            link1 = link.xpath('a[@class="comment-path-topic"]')[0]
            post_title = link1.text
            link2 = link.xpath('a[@class="comment-path-comments"]')[0]
            link2 = link2.get('href')
            blog, post_id = parse_post_url(link2)
        except KeyboardInterrupt: raise
        except: pass
        
        if not parent_id:
            parent_id = info.xpath('li[@class="goto goto-comment-parent"]')
            if len(parent_id) > 0:
                parent_id = parent_id[0].find("a")
                if parent_id.get('onclick'):
                    parent_id = int(parent_id.get('onclick').rsplit(",",1)[-1].split(")",1)[0])
                elif '/comments/' in parent_id.get('href', ''):
                    parent_id = int(parent_id.get('href').rsplit('/',1)[-1])
            else: parent_id = None
        
        vote = info.xpath('li[starts-with(@id, "vote_area_comment")]/span[@class="vote-count"]/text()[1]')
        if vote: vote = int(vote[0].replace("+", ""))
        else: vote = 0
        
    except AttributeError: return
    except IndexError: return
    
    if body is not None: return Comment(tm, blog, post_id, comment_id, nick, body, vote, parent_id, post_title, unread)

def parse_talk_item(node):
    checkbox, recs, title, date = node.findall("td")
    recipients = []
    for x in recs.findall("a"):
        recipients.append( str(x.text.strip()) )
    unread = bool(title.xpath('a/strong'))
    talk_id = title.find("a").get('href')[:-1]
    talk_id = int(talk_id[talk_id.rfind("/")+1:])
    title = title.find("a").text_content()
    date = date.text.strip()
    date = time.strptime(utils.mon2num(date), '%d %m %Y')
    
    return TalkItem(talk_id, recipients, unread, title, date)

def parse_post_url(link):
    """Выдирает блог и номер поста из ссылки. Или возвращает (None,None), если выдрать не удалось."""
    m = post_url_regex.search(link)
    if not m: return None, None
    g = m.groups()
    return (g[1] if g[1] else None), int(g[2])
