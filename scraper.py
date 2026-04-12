import os
import requests
from bs4 import BeautifulSoup as bs
import pandas as pd
from tqdm import tqdm

class Scraper:
    def __init__(self, target_date):
        # target_date format: 'YYYYMMDD'
        self.target_date = target_date
        self.target_datetime = pd.to_datetime(target_date, format='%Y%m%d')

    def get_new_page(self, news_url):
        A = requests.get(news_url)
        soup = bs(A.content, 'html.parser')
        news_list = soup.select('dd[class=articleSubject]')
        
        title_list = []
        text_list = []
        
        for obj in news_list:
            a_tag = obj.find('a')
            if not a_tag:
                continue
            
            title = a_tag.text.strip()
            title_list.append(title)
            
            link = a_tag.attrs.get('href', '')
            if 'article_id=' in link and 'office_id=' in link:
                try:
                    article_id = link.split('&')[0].split('article_id=')[-1]
                    office_id = link.split('&')[1].split('office_id=')[-1]
                    url = f'https://n.news.naver.com/mnews/article/{office_id}/{article_id}'
                    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
                    b = bs(res.content, 'html.parser')
                    news_text = b.find('article', {'id': 'dic_area'})
                    text = news_text.get_text().strip() if news_text else ''
                    text_list.append(text)
                except Exception as e:
                    text_list.append('')
            else:
                text_list.append('')
                
        news_df = pd.DataFrame({'title': title_list, 'text': text_list})
        return news_df

    def get_news(self):
        news_all_list = []
        # Categories: 401: 시황·전망, 402: 기업·종목분석, 403: 해외증시, 404: 채권·선물, 406: 공시·메모, 429: 환율
        for j in [401, 402, 403, 404, 406, 429]:
            news_url = f"https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3={j}&date={self.target_date}"
            news_temp = self.get_new_page(news_url)
            if not news_temp.empty:
                news_temp['category'] = j
                news_temp['date'] = self.target_datetime.strftime('%Y-%m-%d')
                news_all_list.append(news_temp)

            for i in range(2, 6): # Reduced to 5 pages per category for reasonable web performance
                news_url = f"https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3={j}&date={self.target_date}&page={i}"
                news_temp = self.get_new_page(news_url)
                if not news_temp.empty:
                    news_temp['category'] = j
                    news_temp['date'] = self.target_datetime.strftime('%Y-%m-%d')
                    news_all_list.append(news_temp)
                    
        return pd.concat(news_all_list, ignore_index=True) if news_all_list else pd.DataFrame()

    def get_reports(self, url_name, report_type):
        answer = []
        for num in range(1, 3): # first 2 pages
            try:
                A = requests.get(f"https://finance.naver.com/research/{url_name}.naver?&page={num}")
                soup = bs(A.text, 'html.parser')

                rows = soup.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) > 1:
                        if url_name in ['industry_list', 'company_list']:
                            title_a = cells[1].find('a')
                            if not title_a: continue
                            title = title_a.text
                            href = title_a['href']
                            day = cells[4].text
                        else:
                            title_a = cells[0].find('a')
                            if not title_a: continue
                            title = title_a.text
                            href = title_a['href']
                            day = cells[3].text
                            
                        url = 'https://finance.naver.com/research/' + href
                        
                        res = requests.get(url)
                        sub_soup = bs(res.text, 'html.parser')
                        table = sub_soup.find_all('table')
                        if table:
                            lows = table[0].find_all('p')
                            text = pd.Series([i.text for i in lows]).astype(str).sum()
                        else:
                            text = ''
                            
                        answer.append({'title': title, 'date': day, 'text': text})
            except Exception as e:
                pass
                
        df = pd.DataFrame(answer)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'], format='%y.%m.%d')
            # Filter by target date strictly
            df = df[df['date'] == self.target_datetime]
            df['분류'] = report_type
        return df
