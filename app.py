import streamlit as st
from streamlit_folium import st_folium
import folium
from folium.plugins import MarkerCluster
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import hashlib
import time
from datetime import datetime
import os
import warnings
import math
import random

# [설정] 경고 무시
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)
warnings.simplefilter(action='ignore', category=DeprecationWarning)

# [1] 기본 설정
st.set_page_config(
    page_title="Factory Link 1.5 (Beta)",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# [2] 다크 모드 상태 관리
if 'dark_mode' not in st.session_state:
    st.session_state['dark_mode'] = False

# [3] 스타일링 (다크 모드 지원 + 우측 하단 링크 + 법적 고지)
def apply_css(is_dark):
    if is_dark:
        bg_color = "#1e1e1e"
        text_color = "#ffffff"
        card_bg = "#2d2d2d"
        border_color = "#404040"
        header_color = "#60a5fa"
        footer_bg = "#374151"
        footer_text = "#ffffff"
    else:
        bg_color = "#f8fafc"
        text_color = "#1e293b"
        card_bg = "#ffffff"
        border_color = "#e2e8f0"
        header_color = "#1E3A8A"
        footer_bg = "rgba(255, 255, 255, 0.95)"
        footer_text = "#03c75a"

    st.markdown(f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
        html, body, [class*="css"] {{
            font-family: 'Noto Sans KR', sans-serif;
            color: {text_color};
        }}
        .stApp {{background-color: {bg_color};}}
        
        .main-header {{
            font-size: 2.2rem; font-weight: 800; color: {header_color}; margin-bottom: 0.5rem;
        }}
        
        /* 카드 및 컨테이너 스타일 */
        .card-container {{
            background-color: {card_bg}; padding: 1.5rem; border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05); border: 1px solid {border_color}; margin-bottom: 1rem;
        }}
        
        /* 법적 고지 박스 */
        .legal-box {{
            background-color: {card_bg};
            padding: 15px;
            border-radius: 8px;
            font-size: 0.8rem;
            color: {text_color};
            opacity: 0.8;
            margin-top: 50px;
            margin-bottom: 50px;
            border: 1px solid {border_color};
        }}
        .legal-title {{ font-weight: bold; margin-bottom: 5px; }}

        /* 우측 하단 고정 링크 */
        .footer-fixed {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background-color: {footer_bg};
            padding: 12px 18px;
            border-radius: 30px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            border: 1px solid {border_color};
            z-index: 9999;
            font-size: 0.9rem;
            transition: transform 0.2s;
        }}
        .footer-fixed:hover {{ transform: translateY(-3px); }}
        .footer-fixed a {{ color: {footer_text}; font-weight: bold; text-decoration: none; }}
        
        /* 상태 뱃지 */
        .status-badge {{ padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }}
        .status-wait {{ background-color: #fef3c7; color: #92400e; }}
        .status-ok {{ background-color: #dcfce7; color: #166534; }}
        .status-no {{ background-color: #fee2e2; color: #991b1b; }}
        
        .stDeployButton {{display:none;}}
        </style>
    """, unsafe_allow_html=True)

IMG_DIR = "images"
if not os.path.exists(IMG_DIR): os.makedirs(IMG_DIR)

# === 데이터 구조 ===
COLS_RESOURCES = ["id", "writer_id", "date", "company", "contact", "region", "complex", "role", "category", "item", "lat", "lon", "desc", "process", "verified", "image_path"]
COLS_USERS = ["user_id", "password_hash", "company_name", "contact", "biz_no", "is_verified", "deal_count", "reputation", "join_date"]
COLS_MESSAGES = ["req_id", "from_user", "to_user", "item_id", "status", "timestamp"]

# === 구글 연결 ===
@st.cache_resource
def connect_google_sheet():
    if "gcp_service_account" not in st.secrets:
        st.error("🚨 Secrets 설정 오류: [gcp_service_account] 헤더가 누락되었습니다.")
        st.stop()
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("Factory_DB") 

# === [안정화] 데이터 로드 (재시도 + 캐시) ===
@st.cache_data(ttl=30, show_spinner=False)
def load_data(sheet_name):
    target_cols = []
    if sheet_name == "resources": target_cols = COLS_RESOURCES
    elif sheet_name == "users": target_cols = COLS_USERS
    elif sheet_name == "messages": target_cols = COLS_MESSAGES

    for attempt in range(3): # 3회 재시도
        try:
            sh = connect_google_sheet()
            worksheet = sh.worksheet(sheet_name)
            data = worksheet.get_all_records()
            if not data: return pd.DataFrame(columns=target_cols)
            df = pd.DataFrame(data)
            for col in target_cols:
                if col not in df.columns: df[col] = ""
            if 'id' in df.columns: df['id'] = df['id'].astype(str)
            return df
        except Exception:
            time.sleep(1)
            continue
    return pd.DataFrame(columns=target_cols)

# === 데이터 저장 ===
def save_data(sheet_name, new_data_dict=None, update_df=None):
    try:
        sh = connect_google_sheet()
        worksheet = sh.worksheet(sheet_name)
        if update_df is not None:
            df = update_df
        else:
            current_data = worksheet.get_all_records()
            df = pd.DataFrame(current_data)
            if df.empty:
                if sheet_name == "resources": df = pd.DataFrame(columns=COLS_RESOURCES)
                elif sheet_name == "users": df = pd.DataFrame(columns=COLS_USERS)
                elif sheet_name == "messages": df = pd.DataFrame(columns=COLS_MESSAGES)
            new_row = pd.DataFrame([new_data_dict])
            df = pd.concat([df, new_row], ignore_index=True)
        
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())
        st.cache_data.clear() # 캐시 초기화
    except Exception as e:
        st.error(f"저장 실패: {e}")

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

# === [데이터] 산단 DB ===
REGION_DB = {
    "수도권 (서울/경기/인천)": [37.4, 127.0],
    "충청권 (대전/세종/충남북)": [36.6, 127.3],
    "경상권 (부산/대구/울산/경남북)": [35.5, 128.8],
    "전라권 (광주/전남북)": [35.5, 127.0],
    "강원/제주/기타": [37.5, 128.3]
}
# [수정] 요청하신 '분석/기타' 반영
CATEGORIES = ["🏭 유휴설비", "🧪 화학부산물", "📦 자재/스크랩", "🚛 수거/운송", "📊 분석/기타"]

# --- 법적 책임 고지 ---
def render_legal_notice():
    st.markdown("""
        <div class="legal-box">
            <div class="legal-title">⚖️ 법적 고지 및 책임 제한</div>
            'Factory Link'는 자원 직거래 정보 공유 플랫폼(통신판매중개자)입니다.<br>
            <b>화공재료연구회</b>는 거래의 당사자가 아니며, 상품 품질, 결제, 배송 등 거래 전반에 대해 어떠한 보증도 하지 않습니다.<br>
            모든 거래의 책임은 당사자에게 있으므로 신중하게 거래하시기 바랍니다.
        </div>
    """, unsafe_allow_html=True)

# --- 우측 하단 푸터 ---
def render_footer():
    st.markdown("""
        <div class='footer-fixed'>
            💡 문의/건의: <a href='https://cafe.naver.com/zjqlwkd' target='_blank'>화공재료연구회 카페</a>
        </div>
    """, unsafe_allow_html=True)

# [2] 로그인 페이지
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = ""

def login_page():
    apply_css(False) # 로그인 화면은 라이트 모드 고정
    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<div class='main-header'>Factory Link <span style='font-size:1.5rem; color:#64748B;'>1.5 (Beta)</span></div>", unsafe_allow_html=True)
        st.markdown("### 대한민국 공단 자원 거래 플랫폼")
        st.markdown("""
        ##### 🚀 우리 공장에 필요한 모든 연결
        * 📍 **지도 기반 탐색**: 내 공장 주변 매물을 직관적으로 확인
        * 🤝 **검증된 기업**: 인증된 기업 간의 안전한 직거래
        * 🏭 **산업 맞춤형**: 설비부터 부산물, 자재까지 특화
        """)
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            t1, t2 = st.tabs(["🔐 로그인", "📝 회원가입"])
            
            with t1:
                with st.form("login_form"):
                    uid = st.text_input("아이디")
                    upw = st.text_input("비밀번호", type="password")
                    if st.form_submit_button("로그인", use_container_width=True):
                        try:
                            users = load_data("users")
                            c_uid, c_pw = uid.strip(), upw.strip()
                            hashed = hash_password(c_pw)
                            
                            # 일반 로그인
                            user = pd.DataFrame()
                            if not users.empty:
                                user = users[(users['user_id'] == c_uid) & (users['password_hash'] == hashed)]
                            
                            if not user.empty:
                                st.session_state['logged_in'] = True
                                st.session_state['user_id'] = c_uid
                                st.session_state['is_admin'] = True if c_uid == "admin" else False
                                st.rerun()
                            # 관리자 강제 복구
                            elif c_uid == "admin" and c_pw == "1234":
                                admin_data = {"user_id": "admin", "password_hash": hash_password("1234"), "company_name": "관리자", "contact": "system", "biz_no": "-", "is_verified": "TRUE", "deal_count": 999, "reputation": 100.0, "join_date": datetime.now().strftime("%Y-%m-%d")}
                                if users.empty or "admin" not in users['user_id'].values:
                                    save_data("users", new_data_dict=admin_data)
                                st.session_state.update({'logged_in': True, 'user_id': "admin", 'is_admin': True})
                                st.success("관리자 접속 성공"); time.sleep(1); st.rerun()
                            else: st.error("정보가 일치하지 않습니다.")
                        except Exception as e: st.error(f"오류: {e}")

            with t2:
                st.info("아이디, 비밀번호, 연락처는 필수입니다.")
                with st.form("signup_form"):
                    new_id = st.text_input("아이디 (필수)")
                    new_pw = st.text_input("비밀번호 (필수)", type="password")
                    contact = st.text_input("연락처 (필수)")
                    comp_name = st.text_input("기업명")
                    if st.form_submit_button("가입신청", use_container_width=True):
                        try:
                            users = load_data("users")
                            if not new_id.strip() or not new_pw.strip() or not contact.strip():
                                st.error("필수 항목 누락")
                            elif not users.empty and new_id.strip() in users['user_id'].values:
                                st.error("이미 존재하는 아이디")
                            else:
                                new_user = {"user_id": new_id.strip(), "password_hash": hash_password(new_pw.strip()), "company_name": comp_name.strip() or "개인회원", "contact": contact.strip(), "biz_no": "-", "is_verified": "FALSE", "deal_count": 0, "reputation": 36.5, "join_date": datetime.now().strftime("%Y-%m-%d")}
                                save_data("users", new_data_dict=new_user)
                                st.success("가입 완료!"); st.balloons()
                        except Exception as e: st.error(f"오류: {e}")
    render_footer()

# [3] 메인 앱
def main_app():
    # CSS 적용 (다크 모드 반영)
    apply_css(st.session_state['dark_mode'])
    
    users = load_data("users")
    curr_user = pd.Series()

    if not users.empty:
        user_rows = users[users['user_id'] == st.session_state['user_id']]
        if not user_rows.empty: curr_user = user_rows.iloc[0]
    
    # 안정화: 데이터 로드 실패 시 재시도 유도
    if curr_user.empty:
        if st.session_state['user_id'] == 'admin':
            curr_user = pd.Series({'company_name': '관리자', 'contact': 'system', 'is_verified': 'TRUE'})
        elif users.empty:
            st.warning("⚠️ 서버 연결 중... (잠시 후 다시 시도해주세요)")
            if st.button("🔄 연결 재시도"): st.cache_data.clear(); st.rerun()
            return
        else:
            st.error("회원 정보 오류. 다시 로그인해주세요."); time.sleep(2); st.session_state['logged_in'] = False; st.rerun(); return

    with st.sidebar:
        try:
            with st.container(border=True):
                c1, c2 = st.columns([1, 3])
                with c1: st.write("🏭")
                with c2:
                    st.write(f"**{curr_user.get('company_name', '사용자')}**")
                    if st.session_state.get('is_admin'): st.caption("👑 관리자")
                    else: st.caption(f"⭐ 신뢰도: {curr_user.get('reputation', 36.5)}")
            
            # 인증 배지
            if str(curr_user.get('is_verified', 'FALSE')).upper() == "TRUE":
                st.success("✅ 인증 회원입니다")

            # 다크 모드 토글
            is_dark = st.toggle("🌙 다크 모드", value=st.session_state['dark_mode'])
            if is_dark != st.session_state['dark_mode']:
                st.session_state['dark_mode'] = is_dark
                st.rerun()

            col_refresh, col_clear = st.columns(2)
            with col_refresh:
                if st.button("🔄 새로고침", use_container_width=True):
                    st.cache_data.clear(); st.rerun()
            with col_clear:
                if st.button("🗑️ 캐시 삭제", use_container_width=True):
                    st.cache_data.clear(); st.cache_resource.clear(); st.rerun()

            st.divider()
            
            with st.expander("📘 이용 가이드"):
                st.markdown("""
                * **검색:** 지도 및 필터를 사용하여 매물 확인
                * **거래:** [연락처 요청] -> 승인 시 연락처 공개
                * **등록:** 권역 선택만으로 간편 등록
                * **인증:** 관리자 승인 시 [인증 회원] 배지 획득
                """)

            with st.expander("🔧 내 정보 수정"):
                with st.form("profile_update"):
                    new_comp = st.text_input("기업명", value=curr_user.get('company_name', ''))
                    new_contact = st.text_input("연락처", value=curr_user.get('contact', ''))
                    new_pw = st.text_input("새 비번", type="password")
                    if st.form_submit_button("저장", use_container_width=True):
                        users.loc[users['user_id'] == st.session_state['user_id'], 'company_name'] = new_comp
                        users.loc[users['user_id'] == st.session_state['user_id'], 'contact'] = new_contact
                        if new_pw.strip():
                            users.loc[users['user_id'] == st.session_state['user_id'], 'password_hash'] = hash_password(new_pw)
                        save_data("users", update_df=users)
                        st.success("수정 완료"); time.sleep(1); st.rerun()

            if st.button("로그아웃", use_container_width=True, type="secondary"):
                st.session_state['logged_in'] = False; st.rerun()
        except Exception: pass

    st.markdown("<div class='main-header'>🏭 Factory Link <span style='font-size:1.5rem; color:#64748B;'>1.5 (Beta)</span></div>", unsafe_allow_html=True)
    
    tabs = st.tabs(["🗺️ 지도 검색", "📝 매물 등록", "📂 내 거래 관리", "🔔 수신 메시지함", "⚙️ 관리자"]) if st.session_state.get('is_admin') else st.tabs(["🗺️ 지도 검색", "📝 매물 등록", "📂 내 거래 관리", "🔔 수신 메시지함"])
    
    # [Tab 1] 지도 검색
    with tabs[0]:
        df = load_data("resources")
        msgs = load_data("messages")
        
        with st.container(border=True):
            c_search, c_filter = st.columns([2, 1])
            with c_search: search_kw = st.text_input("🔍 통합 검색", placeholder="품목, 기업, 내용 등")
            with c_filter: f_role = st.multiselect("거래 구분", ["팝니다", "삽니다", "수거/운송", "기타"])
            c1, c2 = st.columns(2)
            with c1: f_region = st.multiselect("📍 지역", list(REGION_DB.keys()))
            with c2: f_cat = st.multiselect("📦 카테고리", list(CATEGORIES))
        
        tile = "CartoDB dark_matter" if st.session_state['dark_mode'] else "OpenStreetMap"
        m = folium.Map(location=[36.5, 127.8], zoom_start=7, tiles=tile)
        marker_cluster = MarkerCluster().add_to(m)
        
        filtered = df.copy()
        if not df.empty and 'lat' in df.columns:
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce'); df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
            filtered = df.dropna(subset=['lat', 'lon'])
            if search_kw: filtered = filtered[filtered.astype(str).apply(lambda x: x.str.contains(search_kw)).any(axis=1)]
            if f_region: filtered = filtered[filtered['region'].isin(f_region)]
            if f_cat: filtered = filtered[filtered['category'].isin(f_cat)]
            if f_role: filtered = filtered[filtered['role'].isin(f_role)]

            for _, row in filtered.iterrows():
                color = 'blue'
                if row['role'] == "수거/운송": color = 'black'
                elif "설비" in row['category']: color = 'purple'
                elif "부산물" in row['category']: color = 'red'
                folium.Marker([row['lat'], row['lon']], popup=f"<b>{row['item']}</b><br>{row['company']}", icon=folium.Icon(color=color, icon='info-sign')).add_to(marker_cluster)
        
        st_folium(m, width=1000, height=400)
        st.subheader(f"📋 매물 리스트 ({len(filtered)}건)")
        
        if filtered.empty: st.info("매물이 없습니다.")
        else:
            for idx, row in filtered.iterrows():
                label = f"[{row['role']}] {row['item']} - {row['company']}"
                with st.expander(label):
                    st.markdown(f"#### 🏭 {row['item']}")
                    c1, c2 = st.columns(2)
                    with c1: st.write(f"**지역:** {row['region']}"); st.write(f"**카테고리:** {row['category']}")
                    with c2: 
                        st.write(f"**등록일:** {row['date']}")
                        ver = "✅ 인증회원" if str(row['verified'])=="TRUE" else "미인증"
                        st.write(f"**상태:** {ver}")
                    st.divider()
                    if row['process']: st.info(f"**공정:** {row['process']}")
                    st.write(row['desc'])
                    st.divider()
                    
                    if row['writer_id'] == st.session_state['user_id']:
                        st.button("내 글", disabled=True, key=f"my_{idx}")
                    else:
                        my_req = msgs[(msgs['from_user'] == st.session_state['user_id']) & (msgs['item_id'] == str(row['id']))] if not msgs.empty else pd.DataFrame()
                        if my_req.empty:
                            if st.button("💬 연락처 요청 (클릭)", key=f"req_{idx}", type="primary", use_container_width=True):
                                new_msg = {"req_id": int(time.time()), "from_user": st.session_state['user_id'], "to_user": row['writer_id'], "item_id": str(row['id']), "status": "requested", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")}
                                save_data("messages", new_data_dict=new_msg); st.rerun()
                        else:
                            stt = my_req.iloc[0]['status']
                            if stt == 'approved': st.success("✅ 승인됨! 메시지함 확인")
                            elif stt == 'rejected': st.error("❌ 거절됨")
                            else: st.warning("⏳ 승인 대기 중")

    # [Tab 2] 매물 등록
    with tabs[1]:
        st.subheader("📝 신규 매물 등록")
        c1, c2 = st.columns(2)
        with c1: region = st.selectbox("권역", list(REGION_DB.keys()))
        with c2: role = st.selectbox("구분", ["팝니다", "삽니다", "수거/운송", "기타"])
        cat = st.selectbox("카테고리", CATEGORIES)
        
        title = st.text_input("제목 (예: 500L 반응기)")
        proc = st.text_input("공정 스펙 (선택)")
        desc = st.text_area("상세 내용 (상태, 가격 등)", height=150)
        st.divider()
        company = st.text_input("기업명", value=curr_user.get('company_name',''))
        contact = st.text_input("연락처", value=curr_user.get('contact',''))
        
        if st.button("등록 완료", type="primary", use_container_width=True):
            if not title or not desc: st.error("제목과 내용은 필수입니다.")
            else:
                lat = REGION_DB[region][0] + random.uniform(-0.1, 0.1)
                lon = REGION_DB[region][1] + random.uniform(-0.1, 0.1)
                is_ver = "TRUE" if (st.session_state.get('is_admin') or str(curr_user.get('is_verified')).upper()=="TRUE") else "FALSE"
                new_data = {"id": str(int(time.time())), "writer_id": st.session_state['user_id'], "date": datetime.now().strftime("%Y-%m-%d"), "company": company, "contact": contact, "region": region, "role": role, "category": cat, "item": title, "lat": lat, "lon": lon, "desc": desc, "process": proc, "verified": is_ver, "image_path": ""}
                save_data("resources", new_data_dict=new_data)
                st.success("등록됨!"); st.balloons(); time.sleep(1); st.rerun()

    # [Tab 3] 내 거래 관리
    with tabs[2]:
        st.subheader("📂 내 거래 관리")
        ts, tb = st.tabs(["📤 판매 내역", "📥 구매/요청 내역"])
        with ts:
            res = load_data("resources")
            my_res = res[res['writer_id'] == st.session_state['user_id']] if not res.empty else pd.DataFrame()
            if my_res.empty: st.info("등록된 매물이 없습니다.")
            else:
                for _, r in my_res.iterrows():
                    with st.expander(f"[{r['role']}] {r['item']}"):
                        st.write(r['desc'])
                        if st.button("🗑️ 삭제", key=f"del_{r['id']}"):
                            save_data("resources", update_df=res[res['id'] != r['id']]); st.success("삭제됨"); st.rerun()
        with tb:
            msgs = load_data("messages")
            res = load_data("resources")
            my_req = msgs[msgs['from_user'] == st.session_state['user_id']] if not msgs.empty else pd.DataFrame()
            if my_req.empty: st.info("요청 내역이 없습니다.")
            else:
                for _, req in my_req.iterrows():
                    tgt = res[res['id'] == str(req['item_id'])]
                    t_item = tgt.iloc[0] if not tgt.empty else None
                    if t_item is not None:
                        stat = req['status']
                        color = "status-wait" if stat=='requested' else "status-ok" if stat=='approved' else "status-no"
                        txt = "승인 대기" if stat=='requested' else "승인됨" if stat=='approved' else "거절됨"
                        cont = f"📞 {t_item['contact']}" if stat=='approved' else "🔒 비공개"
                        
                        with st.container(border=True):
                            c1, c2 = st.columns([3, 1])
                            c1.markdown(f"**{t_item['item']}** ({t_item['company']})")
                            c1.markdown(f"👉 {cont}")
                            c2.markdown(f'<span class="status-badge {color}">{txt}</span>', unsafe_allow_html=True)

    # [Tab 4] 수신함
    with tabs[3]:
        st.subheader("🔔 수신 메시지함")
        msgs = load_data("messages")
        res = load_data("resources")
        users = load_data("users")
        my_in = msgs[msgs['to_user'] == st.session_state['user_id']] if not msgs.empty else pd.DataFrame()
        
        if my_in.empty: st.info("받은 요청이 없습니다.")
        else:
            for i, row in my_in.iterrows():
                sender = users[users['user_id'] == row['from_user']].iloc[0] if not users.empty else None
                item = res[res['id'] == str(row['item_id'])].iloc[0] if not res.empty else None
                if sender is not None and item is not None:
                    with st.expander(f"🔔 {sender['company_name']} -> {item['item']}"):
                        st.caption(f"요청 시간: {row['timestamp']}")
                        if row['status'] == 'requested':
                            c1, c2 = st.columns(2)
                            if c1.button("수락", key=f"y_{i}"):
                                msgs.loc[i, 'status'] = 'approved'; save_data("messages", update_df=msgs); st.rerun()
                            if c2.button("거절", key=f"n_{i}"):
                                msgs.loc[i, 'status'] = 'rejected'; save_data("messages", update_df=msgs); st.rerun()
                        else: st.write(f"상태: {row['status']}")

    # [Tab 5] 관리자
    if st.session_state.get('is_admin'):
        with tabs[4]:
            st.subheader("⚙️ 관리자")
            users = load_data("users")
            res = load_data("resources")
            
            st.caption("회원 정보 수정 (is_verified -> TRUE/FALSE)")
            ed_users = st.data_editor(users, hide_index=True, disabled=["user_id"], column_config={"is_verified": st.column_config.SelectboxColumn("인증", options=["TRUE", "FALSE"], required=True)})
            if st.button("저장"): save_data("users", update_df=ed_users); st.success("저장됨"); time.sleep(1); st.rerun()
            
            st.divider()
            st.caption("비밀번호 리셋")
            with st.form("pw_rst"):
                u = st.selectbox("ID", users['user_id'].unique())
                p = st.text_input("새 비번", value="1234")
                if st.form_submit_button("변경"):
                    users.loc[users['user_id']==u, 'password_hash'] = hash_password(p)
                    save_data("users", update_df=users); st.success("변경됨")
            
            st.divider()
            st.caption("매물 삭제 (10개씩)")
            if not res.empty:
                pg = st.number_input("페이지", 1, math.ceil(len(res)/10), 1)
                sl = res.iloc[(pg-1)*10 : pg*10].copy()
                sl.insert(0, "선택", False)
                ed_res = st.data_editor(sl, hide_index=True)
                if st.button("삭제"):
                    dels = ed_res[ed_res['선택']]['id'].tolist()
                    save_data("resources", update_df=res[~res['id'].isin(dels)]); st.success("삭제됨"); st.rerun()

    render_legal_notice()
    render_footer()

if st.session_state['logged_in']: main_app()
else: login_page()