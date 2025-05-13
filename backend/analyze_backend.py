from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from bs4 import BeautifulSoup
import openai
import os

app = Flask(__name__, template_folder="../frontend/templates", static_folder="../frontend/static")

openai.api_key = os.getenv("OPENAI_API_KEY")

# HTML에서 주요 정보 추출
def extract_info_from_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")

    def extract_text_by_id(soup, element_id):
        tag = soup.find(id=element_id)
        return tag.get_text(strip=True) if tag else None

    def parse_price(text):
        if text:
            return int(''.join(filter(str.isdigit, text)))
        return None

    appraisal_price_text = extract_text_by_id(soup, "mf_wfm_mainFrame_spn_gdsDtlSrchAeeEvlAmt")
    appraisal_price = parse_price(appraisal_price_text)
    note = extract_text_by_id(soup, "mf_wfm_mainFrame_spn_gdsDtlSrchRmk")
    gpt_analysis = analyze_with_gpt(note) if note else None

    return {
        "사건번호": extract_text_by_id(soup, "mf_wfm_mainFrame_spn_gdsDtlSrchUserCsNo"),
        "법원": extract_text_by_id(soup, "mf_wfm_mainFrame_spn_gdsDtlSrchCondCortNm"),
        "물건종류": extract_text_by_id(soup, "mf_wfm_mainFrame_spn_gdsDtlSrchGdsKnd"),
        "소재지": extract_text_by_id(soup, "mf_wfm_mainFrame_gen_lstSt_0_spn_gdsDtlSrchStCtt"),
        "감정가": appraisal_price_text,
        "최저매각가격": extract_text_by_id(soup, "mf_wfm_mainFrame_spn_gdsDtlSrchlwsDspsl"),
        "매각기일": extract_text_by_id(soup, "mf_wfm_mainFrame_spn_gdsDtlSrchDspslDxdy"),
        "물건비고": note,
        "청구금액": extract_text_by_id(soup, "mf_wfm_mainFrame_spn_gdsDtlSrchClmAmt"),
        "예상낙찰가": {
            "실거주용": {
                "하한": f"{int(appraisal_price * 0.9):,}원" if appraisal_price else None,
                "상한": f"{appraisal_price:,}원" if appraisal_price else None
            },
            "투자용": {
                "하한": f"{int(appraisal_price * 0.65):,}원" if appraisal_price else None,
                "상한": f"{int(appraisal_price * 0.8):,}원" if appraisal_price else None
            }
        },
        "권리분석멘트": gpt_analysis
    }

# GPT 분석 생성
def analyze_with_gpt(note):
    prompt = f"""
다음은 부동산 경매 물건의 '물건비고' 항목입니다:
\"\"\"{note}\"\"\"
이 내용을 바탕으로 권리 분석을 해주세요.
1. 위험 요소가 있다면 강조해주세요.
2. 법적 안정성이 있다면 근거를 설명해주세요.
3. 입찰자가 반드시 준비하거나 확인해야 할 사항을 조언해주세요.
4. 전체 종합 의견을 '초보자도 이해할 수 있도록' 쉬운 표현으로 정리해주세요.
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "너는 부동산 경매 분석 전문가이자 초보자의 눈높이를 잘 아는 조언가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message['content'].strip()
    except Exception as e:
        return f"GPT 분석 실패: {str(e)}"

# HTML 업로드 API
@app.route("/api/analyze", methods=["POST"])
def analyze():
    if 'file' not in request.files:
        return jsonify({"error": "HTML 파일을 업로드해주세요."}), 400

    file = request.files['file']
    html_content = file.read().decode("utf-8")
    result = extract_info_from_html(html_content)
    return jsonify(result)

# 질문 API
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    analysis = data.get("analysis", "")
    question = data.get("question", "")

    if not analysis or not question:
        return jsonify({"error": "분석 결과와 질문이 모두 필요합니다."}), 400

    prompt = f"""
다음은 부동산 경매 물건에 대한 GPT의 분석 결과입니다:
\"\"\"{analysis}\"\"\"

사용자가 이에 대해 다음과 같은 질문을 했습니다:
\"\"\"{question}\"\"\"

위 분석 내용을 참고하여 질문에 친절하고 정확하게 대답해주세요.
"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "너는 경매 전문가이며 분석 내용을 바탕으로 사용자 질문에 응답하는 조언가야."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return jsonify({"answer": response.choices[0].message['content'].strip()})
    except Exception as e:
        return jsonify({"error": f"GPT 응답 실패: {str(e)}"}), 500

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
