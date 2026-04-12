import os
import requests
from bs4 import BeautifulSoup as bs
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

class Scraper:
    def __init__(self, target_date):
        self.target_date = target_date
        self.target_datetime = pd.to_datetime(target_date, format='%Y%m%d')
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def fetch_article_text(self, link):
        if 'article_id=' in link and 'office_id=' in link:
            try:
                article_id = link.split('&')[0].split('article_id=')[-1]
                office_id = link.split('&')[1].split('office_id=')[-1]
                url = f'https://n.news.naver.com/mnews/article/{office_id}/{article_id}'
                res = self.session.get(url, timeout=5)
                b = bs(res.content, 'html.parser')
                news_text = b.find('article', {'id': 'dic_area'})
                return news_text.get_text().strip() if news_text else ''
            except:
                return ''
        return ''

    def get_new_page(self, news_url):
        A = self.session.get(news_url)
        soup = bs(A.content, 'html.parser')
        news_list = soup.select('dd[class=articleSubject]')
        
        articles = []
        for obj in news_list:
            a_tag = obj.find('a')
            if not a_tag: continue
            title = a_tag.text.strip()
            link = a_tag.attrs.get('href', '')
            articles.append({'title': title, 'link': link})
            
        text_list = [''] * len(articles)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_idx = {executor.submit(self.fetch_article_text, a['link']): i for i, a in enumerate(articles)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                text_list[idx] = future.result()
                
        return pd.DataFrame({'title': [a['title'] for a in articles], 'text': text_list})

    def get_news(self):
        news_all_list = []
        for j in [401, 402, 403, 404, 406, 429]:
            page_urls = [f"https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3={j}&date={self.target_date}"]
            for i in range(2, 4): 
                page_urls.append(f"https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3={j}&date={self.target_date}&page={i}")
            
            for url in page_urls:
                try:
                    news_temp = self.get_new_page(url)
                    if not news_temp.empty:
                        news_temp['category'] = j
                        news_temp['date'] = self.target_datetime.strftime('%Y-%m-%d')
                        news_all_list.append(news_temp)
                except:
                    pass
                    
        return pd.concat(news_all_list, ignore_index=True) if news_all_list else pd.DataFrame()

    def get_reports(self, url_name, report_type):
        answer = []
        for num in range(1, 3):
            try:
                A = self.session.get(f"https://finance.naver.com/research/{url_name}.naver?&page={num}", timeout=5)
                soup = bs(A.text, 'html.parser')
                rows = soup.find_all('tr')
                urls_to_fetch = []
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) > 1:
                        idx = 1 if url_name in ['industry_list', 'company_list'] else 0
                        date_idx = 4 if url_name in ['industry_list', 'company_list'] else 3
                        title_a = cells[idx].find('a')
                        if not title_a: continue
                        title = title_a.text
                        href = title_a['href']
                        day = cells[date_idx].text
                        url = 'https://finance.naver.com/research/' + href
                        urls_to_fetch.append({'title': title, 'date': day, 'url': url})
                        
                def fetch_report_text(url):
                    try:
                        res = self.session.get(url, timeout=5)
                        sub_soup = bs(res.text, 'html.parser')
                        table = sub_soup.find_all('table')
                        if table:
                            lows = table[0].find_all('p')
                            return pd.Series([i.text for i in lows]).astype(str).sum()
                    except:
                        pass
                    return ''
                    
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(fetch_report_text, item['url']): item for item in urls_to_fetch}
                    for future in as_completed(futures):
                        item = futures[future]
                        item['text'] = future.result()
                        answer.append({'title': item['title'], 'date': item['date'], 'text': item['text']})
            except Exception as e:
                pass
                
        df = pd.DataFrame(answer)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'], format='%y.%m.%d')
            df = df[df['date'] == self.target_datetime]
            df['분류'] = report_type
        return df
