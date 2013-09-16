#!/usr/bin/env python2
# -*- coding: utf-8 -*-

try:
    import simplexml
except:
    from xmpp import simplexml

from HTMLParser import HTMLParser

class HTML2XML(HTMLParser):
    blacklist = ('script', 'embed', 'object')
    once = ('br','hr','img', 'source')
    
    def __init__(self):
        self.node = simplexml.Node("div")
        self.current = self.node
        self.tagList = []
        self.black_mode = False
        HTMLParser.__init__(self)
    
    def handle_starttag(self, tag, attrs):
        if self.black_mode: return
        tag = tag.lower()
        
        ats = {}
        for x in attrs:
            ats[x[0].decode("utf-8").lower()] = (x[1].decode("utf-8") if x[1] else x[0])
        
        if tag in self.once:
            self.current.addChild(tag, ats) # одиночные теги
        else:
            if tag in self.blacklist: self.black_mode = True
            self.current = self.current.addChild(tag, ats)
            self.tagList.append(tag)
    
    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.once or not tag in self.tagList: return
        if tag in self.blacklist:
            self.black_mode = False
        if self.black_mode: return
        
        while self.current.getName().encode('utf-8') != tag and self.current!=self.node:
            self.current = self.current.getParent()
            self.tagList.pop()
        
        if self.current == self.node: return
        self.current = self.current.getParent()
        self.tagList.pop()
    
    def handle_data(self, data):
        if self.black_mode: return
        if not data.strip(): return
        data=data.replace("\r","").replace("\n", " ")
        
        #if self.current.getName()==u's':
        #    data1=""
        #    for x in data.decode("utf-8","ignore"):
        #        data1 += x + u'\u0336' # зачёркивание юникодом
        #    self.current.addData(data1)
        #else:
        self.current.addData(data)
            
    def handle_charref(self, name):
        try:
            self.current.addData(unichr(int(name)))
        except: pass
    
    def handle_entityref(self, name):
        if name == "lt":
            self.current.addData("<")
        elif name == "gt":
            self.current.addData(">")
        elif name == "amp":
            self.current.addData("&")
        elif name == "nbsp":
            self.current.addData(" ")
        elif name == "quot":
            self.current.addData('"')
        
            
def findTag(node, name, args={}, ignore=[]):
    tags = node.getTags(name, args)
    for tag in tags:
        if tag and not tag in ignore: return tag
    for x in node.getChildren():
        if not x: continue
        tag = findTag(x, name, args, ignore)
        if tag and not tag in ignore: return tag

def findTags(node, name, args={}, count=0):
    tags = node.getTags(name, args)
    for x in node.getChildren():
        if count and len(tags) >= count: return tags[:count]
        if not x: continue
        tags.extend(findTags(x, name, args, count-len(tags) if count else 0))
    return tags
      
def unescape(s):
    # worse function
    return s.replace("&lt;", "<").\
        replace("&gt;", ">").\
        replace("&quot;", "\"").\
        replace("&#39;", "'").\
        replace("&amp;", "&")
