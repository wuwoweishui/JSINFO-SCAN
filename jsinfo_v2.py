from aiomultiprocess import Pool
import asyncio
import aiohttp
import argparse
import os
import re
from urllib.parse import urlparse
from loguru import logger
from html import unescape
from tldextract import extract
from aiohttp import TCPConnector
import argparse
import sys

def parse_args():
    parser = argparse.ArgumentParser(epilog='\tUsage:\npython ' + sys.argv[0] + " -d www.baidu.com --keyword baidu")
    parser.add_argument("--depth", help="Scrapy depth.")
    parser.add_argument("-f", "--file", help="File of domain or target you want to scrapy",required=True)
    parser.add_argument("--keyword", help="Keywords of domain regexp",required=True)
    parser.add_argument("-o","--output", help="Saving domains file.")
    return parser.parse_args()

class JSINFO():

    def __init__(self,domain,keyword,domain_output,depth):
        if not domain.startswith(('http://','https://')):
            self.domain = 'http://'+domain
        else:
            self.domain = domain
        self.keywords = keyword
        self.domain_output = domain_output
        self.links_new = {}
        self.links = []
        self.count = 1
        self.links.append(self.domain)
        self.links_new[self.domain] = self.count
        self.headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'}
        self.domains = []
        self.jslinks = []
        self.apis = []
        if depth:
            self.maxcount = depth
        else:
            self.maxcount = 8
        self.rootdomains = []
        self.extract_links = []
        self.rootdomains.append(self.domain)
        self.link_pattern = re.compile('href="(.*?)"',re.S)
        self.js_pattern = re.compile('<script.*?src="(.*?)"',re.S)
        self.js_text_pattern = re.compile('<script.*?>(.*?)</script>',re.S)
        self.js_ip_pattern = re.compile('([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})',re.S)
        # start the work
    
    def run(self):
        loop = asyncio.get_event_loop()
        n = 1
        while len(list(self.links_new.keys())) > 0:
            if len(list(self.links_new.keys())) < 50:
                logger.info('-----------------------------------------------------------------------------------')
                logger.info('|正在进行第{}次迭代'.format(n))
                logger.info('|当前url列表数量：{}'.format(len(list(self.links_new.keys()))))
                logger.info('|当前域名数量：{}'.format(len(self.domains)))
                logger.info('|当前根域名数量：{}'.format(len(self.rootdomains)))
                logger.info('|已解析链接数量：{}'.format(len(self.extract_links)-len(list(self.links_new.keys()))))
                logger.info('-----------------------------------------------------------------------------------')
                n+=1
                i = 0
                tasks = []
                del_list = []
                while i < len(self.links_new):
                    for k,v in self.links_new.items():
                        if v>=self.maxcount:
                            del_list.append(k)
                            i += 1
                            continue
                        else:
                            i+=1
                            del_list.append(k)
                            tasks.append(k)
                for del_key in del_list:
                    self.links_new.pop(del_key)
                tasks_loop = [asyncio.ensure_future(self.find_link(url))for url in tasks]
                self.count +=1
                if tasks_loop:
                    loop.run_until_complete(asyncio.wait(tasks_loop))
                else:
                    break
            else:
                logger.info('-----------------------------------------------------------')
                logger.info('|正在进行第{}次迭代'.format(n))
                logger.info('|当前url列表数量：{}'.format(len(list(self.links_new.keys()))))
                logger.info('|当前域名数量：{}'.format(len(self.domains)))
                logger.info('|当前根域名数量：{}'.format(len(self.rootdomains)))
                logger.info('|已解析链接数量：{}'.format(len(self.extract_links)-len(list(self.links_new.keys()))))
                logger.info('-----------------------------------------------------------')
                n+=1
                i = 0 
                tasks = []
                del_list = []
                while i<=50:
                    for k,v in self.links_new.items():
                        if v > self.maxcount:
                            del_list.append(k)
                            # self.links_new.pop(k)
                            continue
                        else:
                            if i <= 50:
                                i+=1
                                del_list.append(k)
                                tasks.append(k)
                            else:
                                break
                    break
                for del_key in del_list:
                    if del_key in self.links_new:
                        self.links_new.pop(del_key)
                tasks_loop = [asyncio.ensure_future(self.find_link(url))for url in tasks]
                self.count += 1
                if tasks_loop:
                    loop.run_until_complete(asyncio.wait(tasks_loop))
                else:
                    break
            
        logger.info('all subdomain\'s count：{}'.format(len(self.domains)))
        if self.domain_output:
            with open(self.domain_output,'a+') as f:
                for domain in self.domains:
                    f.write(domain+'\n')



    async def find_link(self,link):
        sem = asyncio.Semaphore(1024)
        try:
            async with aiohttp.ClientSession() as session:
                async with sem:
                    async with session.get(link,timeout=20,headers=self.headers) as resp:
                        resp = await resp.text("utf-8","ignore")
        except Exception as e:
            logger.warning('resolve {} fail，exception：{}',link,e)
            return
        links = re.findall(self.link_pattern,resp)
        try:
            parse_url = urlparse(link)
        except:
            return
        script_urls = self.parse_url(re.findall(self.js_pattern,resp),parse_url)
        script_text = re.findall(self.js_text_pattern,resp)
        self.parse_url(links,parse_url)
        for js_url in script_urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with sem:
                        async with session.get(js_url,timeout=20,headers=self.headers) as resp:
                            resp = await resp.text("utf-8","ignore")
            except Exception as e:
                logger.warning('resolve {} fail，exception：{}',link,e)
            if resp:
                script_text.append(resp)
        self.extract_js(script_text,parse_url)
        
        
    
    def extract_js(self,script_text,parse_url):
        func_apis = []
        #logger.info('extract {} in js now',parse_url.netloc)
        pattern = r"""
		(?:"|')                               # Start newline delimiter
		(
			((?:[a-zA-Z]{1,10}://|//)           # Match a scheme [a-Z]*1-10 or //
			[^"'/]{1,}\.                        # Match a domainname (any character + dot)
			[a-zA-Z]{2,}[^"']{0,})              # The domainextension and/or path
			|
			((?:/|\.\./|\./)                    # Start with /,../,./
			[^"'><,;| *()(%%$^/\\\[\]]          # Next character can't be...
			[^"'><,;|()]{1,})                   # Rest of the characters can't be
			|
			([a-zA-Z0-9_\-/]{1,}/               # Relative endpoint with /
			[a-zA-Z0-9_\-/]{1,}                 # Resource name
			\.(?:[a-zA-Z]{1,4}|action)          # Rest + extension (length 1-4 or action)
			(?:[\?|/][^"|']{0,}|))              # ? mark with parameters
			|
			([a-zA-Z0-9_\-]{1,}                 # filename
			\.(?:php|asp|aspx|jsp|json|
				action|html|js|txt|xml)             # . + extension
			(?:\?[^"|']{0,}|))                  # ? mark with parameters
		)
		(?:"|')                               # End newline delimiter
		"""
        pattern = re.compile(pattern, re.VERBOSE)
        for text in script_text:
            results = re.finditer(pattern, str(text))
            if results:
                for match in results:
                    match = match.group().strip('"').strip("'")
                    if match not in func_apis and match not in self.apis:
                        self.apis.append(match)
                        func_apis.append(match)
        self.parse_url(func_apis,parse_url)
                
    
    def parse_url(self,urls,parse_url):
        func_js = []
        #logger.info('parse {} links now',parse_url.netloc)
        black_type = ['jpg','png','css','apk','ico','jpeg','exe','gif','avi','mp3','mp4']
        JSExclusionList = ['jquery', 'google-analytics','gpt.js']
        for url in urls:
            url = unescape(url)
            filename = os.path.basename(url)
            # start solve black type
            if filename.split('.')[-1:][0] in black_type:
                continue
            elif 'javascript:' in url:
                continue
            elif filename.split('.')[0:1] in JSExclusionList:
                continue
            # start solve url scheme
            if url.startswith('////'):
                url = 'http:' + url[2:]
            elif url.startswith('//'):
                url = 'http:' + url
            elif url.startswith('/'):
                url = parse_url.scheme + '://' + parse_url.netloc + url
            elif url.startswith('./'):
                url = parse_url.scheme + '://' + parse_url.netloc + parse_url.path + url[1:]
            elif 'http://' in url or 'https://' in url:
                url = url
            else:
                url = parse_url.scheme + '://' + parse_url.netloc + parse_url.path + '/' + url
            extract_domain = extract(url)
            root_domain = extract_domain.domain + '.' + extract_domain.suffix
            if url:
                if url not in self.extract_links:
                    for keyword in self.keywords:
                        if keyword in root_domain:
                            self.links_new[url] = self.count
                            #self.links.append(url)
                            self.extract_links.append(url)
            try:
                parse_netloc = urlparse(url).netloc
            except:
                continue
            if parse_netloc:
                for keyword in self.keywords:
                    if keyword in parse_netloc:
                        if keyword in root_domain:
                            if parse_netloc not in self.domains:
                                if 'en.alibaba.com' not in parse_netloc:
                                    self.domains.append(parse_netloc)
                                    logger.info('Collect a new domain：{}',parse_netloc)
                            if 'http://' + parse_netloc + '/' not in self.extract_links and 'http://' + parse_netloc not in self.extract_links and 'https://' + parse_netloc not in self.extract_links and 'https://' + parse_netloc +'/' not in self.extract_links:
                                #self.links.append('http://' + parse_netloc + '/')
                                if 'en.alibaba.com' not in 'http://' + parse_netloc + '/':
                                    self.links_new['http://' + parse_netloc + '/'] = self.count
                                    self.extract_links.append('http://' + parse_netloc + '/')
                            if root_domain not in self.rootdomains:
                                self.rootdomains.append(root_domain)
                if url not in func_js and url not in self.jslinks:
                    self.jslinks.append(url)
                    func_js.append(url)
        return func_js
            
                        

if __name__ == "__main__":
    args = parse_args()
    domain_file = args.file
    output = args.output
    keywords = args.keyword.split(',')
    depth = args.depth
    domains = []
    with open(domain_file,'r+') as f1:
        for domain in f1:
            domains.append(domain.strip())
    for domain in domains:
        JSINFO(domain,keywords,output,depth).run()
