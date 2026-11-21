"""Read-only integration diagnostics; explicit public URLs, robots respected."""
import json,re
from radar import HttpClient,text
urls=['https://jobs.ge/en/','https://jobs.ge/en/?id=764254&view=jobs','https://dataforcecommunity.transperfect.com/projects','https://www.oneforma.com/projects/','https://jobs.concentrix.com/']
client=HttpClient({'jobs.ge','dataforcecommunity.transperfect.com','www.oneforma.com','jobs.concentrix.com'})
for url in urls:
    try:
        code,body=client.get(url)
        clean=re.sub(r'<(script|style)\b[^>]*>.*?</\1>','',body,flags=re.S|re.I)
        print(json.dumps({'url':url,'code':code,'snippet':clean[:2000],'text':text(clean)[:13000],'cards':re.findall(r'<tr\b[^>]*>.*?</tr>',body,re.S)[:7],'links':re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',clean,re.S)[:100]},ensure_ascii=False))
    except Exception as e:print(json.dumps({'url':url,'error':str(e)}))
