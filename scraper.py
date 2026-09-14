import os
import requests
from bs4 import BeautifulSoup as bs
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

# 네이버가 finance.naver.com의 news_list/research 정적 페이지를 폐기하고
# stock.naver.com 의 JSON API로 이전했다 (2026-09 확인). 셀렉터 기반 파싱 대신
# 아래 API를 직접 호출한다.
REPORT_PATH = {
    'market_info_list': 'market',
    'debenture_list': 'debenture',
    'economy_list': 'economy',
    'invest_list': 'invest',
    'company_list': 'company',
    'industry_list': 'industry',
}

class Scraper:
    def __init__(self, target_date):
        self.target_date = target_date
        self.target_datetime = pd.to_datetime(target_date, format='%Y%m%d')
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

    def fetch_article_text(self, office_id, article_id):
        try:
            url = f'https://n.news.naver.com/mnews/article/{office_id}/{article_id}'
            res = self.session.get(url, timeout=3)
            res.encoding = 'utf-8'
            if not res.ok: return ''
            b = bs(res.text, 'lxml')
            news_text = b.find('article', {'id': 'dic_area'})
            text = news_text.get_text().strip() if news_text else ''
            b.decompose()
            return text
        except:
            return ''

    def get_new_page(self, sid):
        try:
            url = f"https://stock.naver.com/api/domestic/news/focus?sid={sid}&page=1&pageSize=30&date={self.target_date}"
            res = self.session.get(url, timeout=5)
            if not res.ok: return pd.DataFrame()
            articles = res.json().get('articles', [])
        except:
            return pd.DataFrame()

        articles = [a for a in articles if str(a.get('date', '')).startswith(self.target_date)][:10]
        text_list = [''] * len(articles)

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_idx = {executor.submit(self.fetch_article_text, a['officeID'], a['articleID']): i for i, a in enumerate(articles)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                text_list[idx] = future.result()

        return pd.DataFrame({'title': [a['title'] for a in articles], 'text': text_list})

    def get_news(self):
        news_all_list = []
        for j in [401, 402, 403, 404, 406, 429]:
            news_temp = self.get_new_page(j)
            if not news_temp.empty:
                news_temp['category'] = j
                news_temp['date'] = self.target_datetime.strftime('%Y-%m-%d')
                news_all_list.append(news_temp)

        return pd.concat(news_all_list, ignore_index=True) if news_all_list else pd.DataFrame()

    def get_reports(self, url_name, report_type):
        path = REPORT_PATH.get(url_name)
        if not path:
            return pd.DataFrame()

        try:
            res = self.session.get(f"https://m.stock.naver.com/api/research/{path}", timeout=5)
            if not res.ok: return pd.DataFrame()
            items = res.json()
        except:
            return pd.DataFrame()

        target_date_str = self.target_datetime.strftime('%Y-%m-%d')
        target_items = [i for i in items if i.get('writeDate') == target_date_str][:5]

        def fetch_report_text(research_id):
            try:
                res = self.session.get(f"https://m.stock.naver.com/api/research/{path}/{research_id}", timeout=5)
                content = res.json().get('researchContent', {}).get('content', '')
                return bs(content, 'lxml').get_text().strip()
            except:
                return ''

        answer = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(fetch_report_text, item['researchId']): item for item in target_items}
            for future in as_completed(futures):
                item = futures[future]
                answer.append({'title': item['title'], 'date': item['writeDate'], 'text': future.result()})

        df = pd.DataFrame(answer)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df['분류'] = report_type
        return df
