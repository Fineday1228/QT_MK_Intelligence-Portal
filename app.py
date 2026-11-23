import hashlib
import io
import os
import re
import threading
import zipfile
from datetime import datetime

import pandas as pd
from flask import Flask, Response, abort, jsonify, render_template, request, send_file

from scraper import Scraper


app = Flask(__name__)

DOWNLOAD_TOKEN = os.environ.get("DOWNLOAD_TOKEN", "")
CACHE_DIR = "/tmp/quantec_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

ALL_REPORTS = ["시황", "투자", "경제", "채권", "종목", "산업"]
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
crawl_lock = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


def _normalize_reports(reports):
    """허용된 리포트만 중복 없이 정규화합니다."""
    if not isinstance(reports, list):
        return []
    return [report for report in ALL_REPORTS if report in set(reports)]


def _make_cache_path(date_str, fetch_news, reports):
    """날짜와 선택 항목 조합별로 고유한 캐시 경로를 생성합니다."""
    clean_date = date_str.replace("-", "")
    normalized_reports = sorted(set(reports))
    scope_key = f"news={int(fetch_news)}|reports={','.join(normalized_reports)}"
    scope_hash = hashlib.sha256(scope_key.encode("utf-8")).hexdigest()[:8]
    return os.path.join(CACHE_DIR, f"Quantec_Data_{clean_date}_{scope_hash}.zip")


def build_quantec_zip(date_str, fetch_news, reports):
    """기존 /generate의 크롤링 및 ZIP 생성 로직을 바이트로 반환합니다."""
    date_formatted = date_str.replace("-", "")
    scraper_instance = Scraper(date_formatted)
    memory_file = io.BytesIO()

    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        if fetch_news:
            try:
                news_df = scraper_instance.get_news()
                excel_buffer = io.BytesIO()
                news_df.to_excel(excel_buffer, index=False)
                zf.writestr(f"{date_formatted}_news.xlsx", excel_buffer.getvalue())
            except Exception as exc:
                print(f"Error scraping news: {exc}")

        report_mapping = {
            "시황": "market_info_list",
            "채권": "debenture_list",
            "경제": "economy_list",
            "투자": "invest_list",
            "종목": "company_list",
            "산업": "industry_list",
        }

        all_reports = []
        for report_type in reports:
            try:
                dataframe = scraper_instance.get_reports(
                    report_mapping[report_type], report_type
                )
                if not dataframe.empty:
                    all_reports.append(dataframe)
            except Exception as exc:
                print(f"Error scraping report {report_type}: {exc}")

        if all_reports:
            combined_reports = pd.concat(all_reports, ignore_index=True)
            excel_buffer = io.BytesIO()
            combined_reports.to_excel(excel_buffer, index=False)
            zf.writestr(
                f"{date_formatted}_reports.xlsx", excel_buffer.getvalue()
            )

    memory_file.seek(0)
    return memory_file.getvalue()


def get_or_build_zip(date_str, fetch_news, reports, force=False):
    """캐시가 있으면 반환하고, 없을 때만 락을 걸어 크롤링을 1회 실행합니다."""
    if not DATE_PATTERN.match(date_str):
        abort(400, description="Invalid date format. Use YYYY-MM-DD.")

    normalized_reports = _normalize_reports(reports)
    cache_path = _make_cache_path(date_str, fetch_news, normalized_reports)

    if not force and os.path.exists(cache_path):
        return cache_path

    if not crawl_lock.acquire(blocking=False):
        abort(429, description="Crawling already in progress. Please try again in 2 minutes.")

    tmp_path = f"{cache_path}.tmp"
    try:
        if not force and os.path.exists(cache_path):
            return cache_path

        zip_bytes = build_quantec_zip(
            date_str=date_str,
            fetch_news=fetch_news,
            reports=normalized_reports,
        )

        with open(tmp_path, "wb") as cache_file:
            cache_file.write(zip_bytes)
        os.replace(tmp_path, cache_path)
        return cache_path
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        crawl_lock.release()


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.route("/generate", methods=["POST"])
def generate():
    """기존 웹 화면의 Generate & Download 버튼용 엔드포인트입니다."""
    payload = request.get_json(silent=True) or {}
    date_str = payload.get("date") or datetime.now().strftime("%Y-%m-%d")
    fetch_news = bool(payload.get("fetch_news", True))
    reports = payload.get("reports", ALL_REPORTS)
    force = bool(payload.get("force", False))

    if not fetch_news and not reports:
        return jsonify({"error": "Select at least one data source."}), 400

    zip_path = get_or_build_zip(date_str, fetch_news, reports, force=force)
    clean_date = date_str.replace("-", "")
    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"Quantec_Data_{clean_date}.zip",
        mimetype="application/zip",
    )


@app.route("/download", methods=["GET"])
def download():
    """자동화 및 주소창 수동 백업 다운로드용 엔드포인트입니다."""
    token = request.args.get("token", "")
    if not DOWNLOAD_TOKEN or token != DOWNLOAD_TOKEN:
        abort(403, description="Invalid token")

    date_str = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    fetch_news = request.args.get("fetch_news", "true").lower() == "true"

    reports_param = request.args.get("reports")
    reports = (
        [report.strip() for report in reports_param.split(",") if report.strip()]
        if reports_param
        else ALL_REPORTS
    )
    force = request.args.get("force", "false").lower() == "true"

    zip_path = get_or_build_zip(date_str, fetch_news, reports, force=force)
    clean_date = date_str.replace("-", "")
    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f"Quantec_Data_{clean_date}.zip",
        mimetype="application/zip",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
