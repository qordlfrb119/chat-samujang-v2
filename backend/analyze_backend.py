from flask import Flask, request, jsonify, render_template
from bs4 import BeautifulSoup
import openai
import os

app = Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")
openai.api_key = os.getenv("OPENAI_API_KEY")


# 상세페이지 추출
def extract_detail_info(html):
    soup = BeautifulSoup(html, "html.parser")

    def tx(id):  # 텍스트 추출 축약함수
        tag = soup.find(id=id)
        return tag.get_text(strip=True) if tag else None

    def to_num(txt):
        return int(''.join(filter(str.isdigit, txt))) if txt else None

    감정가 = to_num(tx("mf_wfm_mainFrame_spn_gdsDtlSrchAeeEvlAmt"))
    return {
        "사건번호": tx("mf_wfm_mainFrame_spn_gdsDtlSrchUserCsNo"),
        "소재지": tx("mf_wfm_mainFrame_gen_lstSt_0_spn_gdsDtlSrchStCtt"),
        "감정가": 감정가,
        "최저매각가": tx("mf_wfm_mainFrame_spn_gdsDtlSrchlwsDspsl"),
        "매각기일": tx("mf_wfm_mainFrame_spn_gdsDtlSrchDspslDxdy"),
        "물건비고": tx("mf_wfm_mainFrame_spn_gdsDtlSrchRmk"),
        "예상낙찰가": {
            "실거주용": {
                "하한": f"{int(감정가 * 0.9):,}원" if 감정가 else None,
                "상한": f"{감정가:,}원" if 감정가 else None
            },
            "투자용": {
                "하한": f"{int(감정가 * 0.65):,}원" if 감정가 else None,
                "상한": f"{int(감정가 * 0.8):,}원" if 감정가 else None
            }
        }
    }

# 매각물건명세서에서 임차인 정보 추출
def extract_tenant_info(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")  # 일단 첫 테이블 대상 (후에 구조 파악 후 ID로 정밀 타겟팅 가능)

    임차인정보 = []
    if table:
        rows = table.find_all("tr")[1:]  # 헤더 제외
        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 5:
                임차인정보.append({
                    "임차인": cols[0],
                    "전입일자": cols[1],
                    "확정일자": cols[2],
                    "보증금": cols[3],
                    "배당요구": cols[4]
                })

    return {"세입자정보": 임차인정보}


# GPT 권리분석 요청
def analyze_with_gpt(merged_info):
    prompt = f"""
[사건 상세 정보 및 임차인 내역 분석]

사건 정보:
{merged_info}

위 정보를 기반으로 아래 항목에 대해 전문가처럼 공손하게 분석해주세요:

1. 세입자 중 대항력과 우선변제권이 있는 사람이 있는가?
2. 배당요구 여부에 따라 낙찰자가 인수할 위험이 있는가?
3. 낙찰자가 주의해야 할 점은?
4. 종합적으로 안전/주의/위험 중 어떤 수준인가?

→ 꼭 초보자 눈높이에 맞게 쉽고 친절하게 설명해주세요.
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "너는 부동산 경매 권리분석 전문가야. 초보자도 이해할 수 있게 설명해줘."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        return f"GPT 분석 실패: {str(e)}"


# 🔥 API 라우트
@app.route("/api/analyze", methods=["POST"])
def analyze():
    files = request.files.getlist("file")

    if len(files) != 2:
        return jsonify({"error": "상세페이지와 매각물건명세서 HTML 2개를 업로드해야 합니다."}), 400

    detail_html = ""
    memo_html = ""

    for file in files:
        name = file.filename
        content = file.read().decode("utf-8")
        if "명세서" in name or "물건명세서" in name:
            memo_html = content
        else:
            detail_html = content

    detail_info = extract_detail_info(detail_html)
    tenant_info = extract_tenant_info(memo_html)

    merged = {**detail_info, **tenant_info}
    merged["권리분석GPT"] = analyze_with_gpt(merged)

    return jsonify(merged)

# 기본 페이지
@app.route("/")
def index():
    return render_template("index.html")

# 실행
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
