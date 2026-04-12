from flask import Flask, render_template, request, send_file, jsonify
import pandas as pd
from scraper import Scraper
import os
import zipfile
import io

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    target_date = data.get('date') # Format: YYYY-MM-DD
    fetch_news = data.get('fetch_news', False)
    selected_reports = data.get('reports', [])
    
    if not target_date:
        return jsonify({"error": "No date provided"}), 400
        
    date_formatted = target_date.replace('-', '') # YYYYMMDD
    scraper_instance = Scraper(date_formatted)
    
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        if fetch_news:
            try:
                news_df = scraper_instance.get_news()
                excel_buffer = io.BytesIO()
                news_df.to_excel(excel_buffer, index=False)
                zf.writestr(f'{date_formatted}_news.xlsx', excel_buffer.getvalue())
            except Exception as e:
                print(f"Error scraping news: {e}")
            
        if selected_reports:
            report_mapping = {
                '시황': 'market_info_list',
                '채권': 'debenture_list',
                '경제': 'economy_list',
                '투자': 'invest_list',
                '종목': 'company_list',
                '산업': 'industry_list'
            }
            
            all_reports = []
            for r_type in selected_reports:
                if r_type in report_mapping:
                    try:
                        df = scraper_instance.get_reports(report_mapping[r_type], r_type)
                        if not df.empty:
                            all_reports.append(df)
                    except Exception as e:
                        print(f"Error scraping report {r_type}: {e}")
            
            if all_reports:
                combined_reports = pd.concat(all_reports, ignore_index=True)
                excel_buffer = io.BytesIO()
                combined_reports.to_excel(excel_buffer, index=False)
                zf.writestr(f'{date_formatted}_reports.xlsx', excel_buffer.getvalue())
                
    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'Quantec_Data_{date_formatted}.zip'
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)
