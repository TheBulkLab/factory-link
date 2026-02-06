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
import math # 페이지 계산용

# [설정] 경고 무시
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)
warnings.simplefilter(action='ignore', category=DeprecationWarning)

# [1] 기본 설정
st.set_page_config(
    page_title="Factory Link V1.8",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# [2] 커스텀 CSS (스타일링 + 오른쪽 하단 링크)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
    html, body, [class*="css"] {font-family: 'Noto Sans KR', sans-serif;}
    .stApp {background-color: #f8fafc;}
    
    .main-header {
        font-size: 2.2rem; font-weight: 800; color: #1E3A8A; margin-bottom: 0.5rem;
    }
    
    .card-container {
        background-color: white; padding: 1.5rem; border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; margin-bottom: 1rem;
    }
    
    /* [추가] 오른쪽 하단 푸터 링크 스타일 */
    .footer-section {
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #e2e8f0;
        text-align: right; /* 오른쪽 정렬 */
    }
    .footer-link {
        color: #03c75a; /* 네이버 그린 */
        font-weight: bold;
        text-decoration: none;
        background-color: #f0fdf4;
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid #bbf7d0;
        font-size: 0.9rem;
    }
    .footer-link:hover {
        background-color: #dcfce7;
        text-decoration: none;
    }
    
    .stDeployButton {display:none;}
    </style>
""", unsafe_allow_html=True)

IMG_DIR = "images"
if not os.path.exists(IMG_DIR): os.makedirs(IMG_DIR)

# === 데이터 구조 ===
COLS_RESOURCES = ["id", "writer_id", "date", "company", "contact", "region", "complex", "role", "category", "item", "lat", "lon", "desc", "process", "verified", "image_path"]
COLS_USERS = ["user_id", "password_hash", "company_name", "contact", "biz_no", "is_verified", "deal_count", "reputation", "join_date"]
COLS_MESSAGES = ["req_id", "from_user", "to_user", "item_id", "status", "timestamp"]

# === [최적화] 구글 연결 ===
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

# === [최적화] 데이터 로드 ===
def load_data(sheet_name):
    target_cols = []
    if sheet_name == "resources": target_cols = COLS_RESOURCES
    elif sheet_name == "users": target_cols = COLS_USERS
    elif sheet_name == "messages": target_cols = COLS_MESSAGES

    try:
        sh = connect_google_sheet()
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        
        if not data:
            return pd.DataFrame(columns=target_cols)
            
        df = pd.DataFrame(data)
        
        for col in target_cols:
            if col not in df.columns:
                df[col] = ""
        
        # ID 컬럼 문자열 변환 (오류 방지)
        if 'id' in df.columns:
            df['id'] = df['id'].astype(str)
                
        return df
    except Exception:
        return pd.DataFrame(columns=target_cols)

# === 데이터 저장 ===
def save_data(sheet_name, new_data_dict=None, update_df=None):
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

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

# === [데이터] 산단 DB ===
COMPLEX_DB = {
    "수도권": {"시화": [37.3275, 126.7350], "반월": [37.3140, 126.7900], "남동": [37.4050, 126.6900], "평택": [36.9350, 126.8500], "파주LCD": [37.7600, 126.7800], "인천일반": [37.5000, 126.6700], "화성향남": [37.1300, 126.9000], "김포골드": [37.6200, 126.6000]},
    "충청권": {"대산석유": [36.9900, 126.4200], "당진제철": [36.9500, 126.7500], "아산디플": [36.8000, 127.0700], "오창과학": [36.7100, 127.4300], "청주일반": [36.6400, 127.4300], "대덕테크": [36.4300, 127.4000], "서산테크": [36.8500, 126.5000]},
    "경상권": {"울산미포": [35.5000, 129.3500], "온산국가": [35.4300, 129.3300], "포항철강": [35.9900, 129.3700], "구미국가": [36.1100, 128.3600], "창원국가": [35.2100, 128.6600], "대구성서": [35.8400, 128.5000], "부산녹산": [35.0900, 128.8700]},
    "전라/강원": {"여수국가": [34.8200, 127.7000], "광양제철": [34.9300, 127.7300], "군산국가": [35.9500, 126.5500], "광주첨단": [35.2200, 126.8500], "대불국가": [34.7800, 126.4500], "원주문막": [37.3300, 127.8500]}
}
CATEGORIES = ["🏭 유휴설비", "🧪 화학부산물", "📦 자재/스크랩", "🚛 수거/운송", "📊 기타"]

# --- [기능] 하단 푸터 렌더링 함수 ---
def render_footer():
    st.markdown("""
        <div class='footer-section'>
            <span style='color:#64748b; font-size:0.9rem; margin-right:10px;'>앱 이용 문의 및 개선 사항 건의 👉</span>
            <a href='https://cafe.naver.com/zjqlwkd' target='_blank' class='footer-link'>화공재료연구회 네이버 카페</a>
        </div>
    """, unsafe_allow_html=True)

# [2] 로그인 페이지
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = ""

def login_page():
    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<div class='main-header'>Factory Link <span style='font-size:1.5rem; color:#64748B;'>V1.8</span></div>", unsafe_allow_html=True)
        st.markdown("### 대한민국 공단 자원 거래 플랫폼")
        st.markdown("""
        ##### 🚀 우리 공장에 필요한 모든 연결
        
        * 📍 **지도 기반 탐색**: 내 공장 주변의 매물을 지도에서 직관적으로 확인하세요.
        * 🤝 **확실한 신원 인증**: 검증된 기업 회원간의 거래로 신뢰를 더했습니다.
        * 🏭 **산업 맞춤형 매칭**: 유휴 설비부터 자재까지, 공단에 필요한 것만 모았습니다.
        """)
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            t1, t2 = st.tabs(["🔐 로그인", "📝 회원가입"])
            
            # --- 로그인 폼 (오류 수정됨) ---
            with t1:
                with st.form("login_form"):
                    uid = st.text_input("아이디")
                    upw = st.text_input("비밀번호", type="password")
                    
                    # [중요] 버튼이 form 안에 있어야 함
                    login_submitted = st.form_submit_button("로그인", use_container_width=True)
                    
                    if login_submitted:
                        try:
                            users = load_data("users")
                            clean_uid = uid.strip()
                            clean_pw = upw.strip()
                            hashed = hash_password(clean_pw)
                            
                            if users.empty:
                                if clean_uid == "admin" and clean_pw == "1234":
                                    admin_data = {"user_id": "admin", "password_hash": hash_password("1234"), "company_name": "관리자", "contact": "admin@center.com", "biz_no": "-", "is_verified": "TRUE", "deal_count": 999, "reputation": 100.0, "join_date": datetime.now().strftime("%Y-%m-%d")}
                                    save_data("users", new_data_dict=admin_data)
                                    st.success("초기 관리자 생성됨")
                                    time.sleep(1)
                                    st.rerun()
                                else: st.error("회원 정보가 없습니다.")
                            else:
                                user = users[(users['user_id'] == clean_uid) & (users['password_hash'] == hashed)]
                                if not user.empty:
                                    st.session_state['logged_in'] = True
                                    st.session_state['user_id'] = clean_uid
                                    st.session_state['is_admin'] = True if clean_uid == "admin" else False
                                    st.rerun()
                                else: 
                                    st.error(f"정보가 일치하지 않습니다. (입력한 ID: {clean_uid})")
                        except Exception as e:
                            st.error(f"로그인 오류: {e}")

            # --- 회원가입 폼 ---
            with t2:
                st.info("💡 아이디, 비밀번호, 연락처는 **필수** 입력 사항입니다.")
                with st.form("signup_form"):
                    new_id = st.text_input("아이디 (필수)")
                    new_pw = st.text_input("비밀번호 (필수)", type="password")
                    contact = st.text_input("연락처 (필수)")
                    comp_name = st.text_input("기업명 (선택 - 미입력시 개인회원)")
                    
                    signup_submitted = st.form_submit_button("가입신청", use_container_width=True)
                    
                    if signup_submitted:
                        try:
                            users = load_data("users")
                            clean_new_id = new_id.strip()
                            clean_new_pw = new_pw.strip()
                            clean_contact = contact.strip()
                            clean_comp = comp_name.strip() if comp_name else "개인회원"

                            if not clean_new_id or not clean_new_pw or not clean_contact:
                                st.error("🚨 필수 항목을 입력해주세요.")
                            elif not users.empty and clean_new_id in users['user_id'].values:
                                st.error("중복된 아이디입니다.")
                            else:
                                new_user = {
                                    "user_id": clean_new_id, 
                                    "password_hash": hash_password(clean_new_pw), 
                                    "company_name": clean_comp, 
                                    "contact": clean_contact, 
                                    "biz_no": "-", "is_verified": "FALSE", "deal_count": 0, "reputation": 36.5, 
                                    "join_date": datetime.now().strftime("%Y-%m-%d")
                                }
                                save_data("users", new_data_dict=new_user)
                                st.success("가입 완료! 로그인하세요.")
                                st.balloons()
                        except Exception as e:
                            st.error(f"오류 발생: {e}")
                            
    # 로그인 페이지에도 푸터 표시
    render_footer()

# [3] 메인 앱
def main_app():
    with st.sidebar:
        try:
            users = load_data("users")
            curr_user = users[users['user_id'] == st.session_state['user_id']]
            
            if curr_user.empty:
                st.error("사용자 정보 없음")
            else:
                curr_user = curr_user.iloc[0]
                with st.container(border=True):
                    c1, c2 = st.columns([1, 3])
                    with c1: st.write("🏭")
                    with c2:
                        st.write(f"**{curr_user['company_name']}**")
                        if st.session_state.get('is_admin'): st.caption("👑 관리자")
                        else: st.caption(f"⭐ 신뢰도: {curr_user['reputation']}")

            if st.button("🔄 데이터 새로고침", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

            st.divider()
            
            with st.expander("🔧 내 정보 수정"):
                with st.form("profile_update"):
                    st.caption("변경할 정보를 입력하세요")
                    new_comp = st.text_input("기업명", value=curr_user['company_name'])
                    new_contact = st.text_input("연락처", value=curr_user['contact'])
                    new_pw = st.text_input("새 비밀번호 (변경시에만 입력)", type="password")
                    
                    if st.form_submit_button("정보 수정", use_container_width=True):
                        users.loc[users['user_id'] == st.session_state['user_id'], 'company_name'] = new_comp
                        users.loc[users['user_id'] == st.session_state['user_id'], 'contact'] = new_contact
                        
                        if new_pw.strip():
                            users.loc[users['user_id'] == st.session_state['user_id'], 'password_hash'] = hash_password(new_pw)
                        
                        save_data("users", update_df=users)
                        st.success("정보가 수정되었습니다!")
                        time.sleep(1)
                        st.rerun()

            if st.button("로그아웃", use_container_width=True, type="secondary"):
                st.session_state['logged_in'] = False
                st.rerun()
        except Exception as e:
            st.error(f"오류: {e}")
            if st.button("강제 로그아웃"):
                st.session_state['logged_in'] = False
                st.rerun()

    st.markdown("<div class='main-header'>🏭 Factory Link <span style='font-size:1.5rem; color:#64748B;'>V1.8</span></div>", unsafe_allow_html=True)
    
    tabs = st.tabs(["🗺️ 지도 검색", "📝 매물 등록", "🔔 메시지함", "⚙️ 관리자"]) if st.session_state.get('is_admin') else st.tabs(["🗺️ 지도 검색", "📝 매물 등록", "🔔 메시지함"])
    
    # [Tab 1] 지도 검색
    with tabs[0]:
        df = load_data("resources")
        msgs = load_data("messages")
        
        with st.container(border=True):
            c_search, c_filter = st.columns([2, 1])
            with c_search:
                search_kw = st.text_input("🔍 통합 검색 (품목명, 기업명, 내용)", placeholder="예: 반응기, 폐산, 삼성전자")
            with c_filter:
                f_role = st.multiselect("거래 구분", ["팝니다", "삽니다", "수거/운송", "기타"])

            c1, c2 = st.columns(2)
            with c1: 
                all_complexes = []
                for r in COMPLEX_DB: all_complexes += list(COMPLEX_DB[r].keys())
                f_comp = st.multiselect("📍 공단 위치", all_complexes)
            with c2: f_cat = st.multiselect("📦 카테고리", list(CATEGORIES))
        
        m = folium.Map(location=[36.5, 127.8], zoom_start=7)
        marker_cluster = MarkerCluster().add_to(m)
        
        filtered_df = df.copy()
        if not df.empty and 'lat' in df.columns:
            df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
            df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
            df = df.dropna(subset=['lat', 'lon'])

            if search_kw:
                filtered_df = filtered_df[
                    filtered_df['item'].astype(str).str.contains(search_kw) | 
                    filtered_df['company'].astype(str).str.contains(search_kw) |
                    filtered_df['desc'].astype(str).str.contains(search_kw)
                ]
            if f_comp: filtered_df = filtered_df[filtered_df['complex'].isin(f_comp)]
            if f_cat: filtered_df = filtered_df[filtered_df['category'].isin(f_cat)]
            if f_role: filtered_df = filtered_df[filtered_df['role'].isin(f_role)]

            for idx, row in filtered_df.iterrows():
                color = 'blue'
                if row['role'] == "수거/운송": color = 'black'
                elif "설비" in row['category']: color = 'purple'
                elif "부산물" in row['category']: color = 'red'
                
                popup_html = f"<b>{row['item']}</b><br>{row['company']}"
                folium.Marker(
                    [row['lat'], row['lon']], 
                    popup=popup_html, 
                    icon=folium.Icon(color=color, icon='info-sign')
                ).add_to(marker_cluster)
        
        st_folium(m, width=1000, height=400)
        
        st.subheader(f"📋 매물 리스트 ({len(filtered_df)}건)")
        
        if filtered_df.empty:
            st.info("조건에 맞는 매물이 없습니다.")
        else:
            for idx, row in filtered_df.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        verified_mark = "✅" if str(row['verified']) == "TRUE" else ""
                        st.markdown(f"### {verified_mark} {row['item']}")
                        st.caption(f"📍 {row['region']} > {row['complex']} | 📂 {row['category']} | {row['role']}")
                        st.write(row['desc'])
                    with c2:
                        if row['writer_id'] == st.session_state['user_id']:
                            st.button("내 글", disabled=True, key=f"mine_{idx}")
                        else:
                            my_req = msgs[(msgs['from_user'] == st.session_state['user_id']) & (msgs['item_id'] == str(row['id']))] if not msgs.empty else pd.DataFrame()
                            if my_req.empty:
                                if st.button("💬 연락처 요청", key=f"req_{idx}", type="primary", use_container_width=True):
                                    new_msg = {"req_id": int(time.time()), "from_user": st.session_state['user_id'], "to_user": row['writer_id'], "item_id": str(row['id']), "status": "requested", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")}
                                    save_data("messages", new_data_dict=new_msg)
                                    st.rerun()
                            else:
                                stat = my_req.iloc[0]['status']
                                if stat == 'requested': st.button("⏳ 승인 대기", disabled=True, key=f"wait_{idx}", use_container_width=True)
                                elif stat == 'approved': st.button("✅ 승인됨", disabled=True, key=f"appr_{idx}", use_container_width=True)
                                elif stat == 'rejected': st.button("❌ 거절됨", disabled=True, key=f"rej_{idx}", use_container_width=True)

    # [Tab 2] 매물 등록
    with tabs[1]:
        st.subheader("📝 신규 매물 등록")
        with st.form("reg_form"):
            c1, c2 = st.columns(2)
            with c1:
                region = st.selectbox("권역", list(COMPLEX_DB.keys()))
                complex_loc = st.selectbox("산단 선택", list(COMPLEX_DB[region].keys()))
            with c2:
                role = st.selectbox("거래 구분", ["팝니다", "삽니다", "수거/운송", "기타"])
                cat_main = st.selectbox("카테고리", CATEGORIES)
            
            item_name = st.text_input("제목 (예: 500L GL 반응기)")
            process_desc = st.text_input("상세 스펙 / 공정 설명")
            desc = st.text_area("상세 내용 (상태, 연식, 가격 제안 등을 자세히 적어주세요)", height=150)
            
            st.divider()
            company = st.text_input("기업명")
            contact = st.text_input("담당자 연락처 (승인된 회원에게만 공개)")

            if st.form_submit_button("등록 완료", type="primary", use_container_width=True):
                import random
                coords = COMPLEX_DB[region][complex_loc]
                is_ver = "TRUE" if st.session_state.get('is_admin') else "FALSE"
                
                new_data = {
                    "id": str(int(time.time())), 
                    "writer_id": st.session_state['user_id'], "date": datetime.now().strftime("%Y-%m-%d"),
                    "company": company, "contact": contact, "region": region, "complex": complex_loc, "role": role,
                    "category": cat_main, "item": item_name, "lat": coords[0] + random.uniform(-0.02, 0.02), "lon": coords[1] + random.uniform(-0.02, 0.02),
                    "desc": desc, "process": process_desc, "verified": is_ver, "image_path": ""
                }
                save_data("resources", new_data_dict=new_data)
                st.success("등록되었습니다!")
                st.balloons()

    # [Tab 3] 메시지함
    with tabs[2]:
        st.subheader("🔔 메시지 센터")
        msgs = load_data("messages")
        resources = load_data("resources")
        users = load_data("users")
        
        t_in, t_out = st.tabs(["📥 받은 요청", "📤 보낸 요청"])
        
        with t_in:
            if not msgs.empty:
                my_recv = msgs[msgs['to_user'] == st.session_state['user_id']]
                if my_recv.empty: st.info("받은 요청이 없습니다.")
                for idx, row in my_recv.iterrows():
                    req_user = users[users['user_id'] == row['from_user']].iloc[0]
                    res_item = resources[resources['id'] == str(row['item_id'])]
                    title = res_item.iloc[0]['item'] if not res_item.empty else "(삭제됨)"
                    
                    with st.expander(f"🔔 {req_user['company_name']} 님이 연락처를 요청했습니다."):
                        st.write(f"**요청 물품:** {title}")
                        st.caption(f"요청 시간: {row['timestamp']}")
                        
                        if row['status'] == 'requested':
                            c1, c2 = st.columns(2)
                            if c1.button("✅ 수락", key=f"ok_{idx}", use_container_width=True):
                                msgs.loc[idx, 'status'] = 'approved'
                                save_data("messages", update_df=msgs)
                                st.rerun()
                            if c2.button("❌ 거절", key=f"no_{idx}", use_container_width=True):
                                msgs.loc[idx, 'status'] = 'rejected'
                                save_data("messages", update_df=msgs)
                                st.rerun()
                        elif row['status'] == 'approved': st.success("이미 승인했습니다.")
                        elif row['status'] == 'rejected': st.error("거절했습니다.")

        with t_out:
            if not msgs.empty:
                my_sent = msgs[msgs['from_user'] == st.session_state['user_id']]
                if my_sent.empty: st.info("보낸 요청이 없습니다.")
                for idx, row in my_sent.iterrows():
                    res_item = resources[resources['id'] == str(row['item_id'])]
                    if not res_item.empty:
                        target = res_item.iloc[0]
                        st.markdown(f"**To. {target['company']}** ({target['item']})")
                        if row['status'] == 'approved':
                            st.success(f"📞 연락처: **{target['contact']}**")
                        elif row['status'] == 'rejected':
                            st.error("거절됨")
                        else:
                            st.warning("⏳ 승인 대기 중...")
                        st.divider()

    # [Tab 4] 관리자
    if st.session_state.get('is_admin'):
        with tabs[3]:
            st.subheader("⚙️ 관리자 대시보드")
            users = load_data("users")
            resources = load_data("resources")
            
            c1, c2 = st.columns(2)
            c1.metric("👥 총 회원수", len(users))
            c2.metric("📦 등록 매물", len(resources))
            
            st.markdown("### 🔧 회원 정보 통합 관리")
            st.caption("회원 정보를 직접 수정할 수 있습니다. (더블 클릭하여 수정)")
            
            # [기능] 관리자용 회원 정보 수정 (엑셀 스타일)
            edited_users = st.data_editor(
                users, 
                hide_index=True, 
                use_container_width=True,
                disabled=["user_id", "join_date"]
            )
            
            if st.button("회원정보 변경사항 저장", use_container_width=True):
                save_data("users", update_df=edited_users)
                st.success("회원 정보가 업데이트되었습니다.")
            
            st.divider()
            
            # [기능] 관리자용 비밀번호 초기화
            st.markdown("##### 🔐 비밀번호 강제 초기화")
            with st.form("admin_pw_reset"):
                col_u, col_p = st.columns(2)
                target_u = col_u.selectbox("초기화할 회원 ID", users['user_id'].unique())
                new_sys_pw = col_p.text_input("설정할 비밀번호", value="1234")
                if st.form_submit_button("비밀번호 변경"):
                    users.loc[users['user_id'] == target_u, 'password_hash'] = hash_password(new_sys_pw)
                    save_data("users", update_df=users)
                    st.success(f"{target_u} 회원의 비밀번호가 변경되었습니다.")

            st.markdown("---")
            st.markdown("### 🗑️ 매물 삭제 관리 (페이지네이션)")
            
            if not resources.empty:
                # [기능] 10개씩 끊어서 보여주기 + 체크박스로 삭제
                items_per_page = 10
                total_pages = math.ceil(len(resources) / items_per_page)
                
                col_page, col_dummy = st.columns([1, 3])
                with col_page:
                    page = st.number_input("페이지 선택", min_value=1, max_value=total_pages, value=1)
                
                start_idx = (page - 1) * items_per_page
                end_idx = start_idx + items_per_page
                
                page_data = resources.iloc[start_idx:end_idx].copy()
                page_data.insert(0, "선택", False)
                
                st.caption(f"총 {len(resources)}개 중 {start_idx+1}~{min(end_idx, len(resources))}번 매물 표시")
                
                edited_resources_page = st.data_editor(
                    page_data,
                    hide_index=True,
                    use_container_width=True,
                    column_config={"선택": st.column_config.CheckboxColumn(required=True)},
                    disabled=[col for col in resources.columns]
                )
                
                if st.button("선택한 매물 영구 삭제", type="primary", use_container_width=True):
                    selected_rows = edited_resources_page[edited_resources_page["선택"] == True]
                    if not selected_rows.empty:
                        delete_ids = selected_rows['id'].tolist()
                        new_resources = resources[~resources['id'].isin(delete_ids)]
                        save_data("resources", update_df=new_resources)
                        st.success(f"{len(delete_ids)}개의 매물을 삭제했습니다.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("삭제할 매물을 선택해주세요.")
            else:
                st.info("등록된 매물이 없습니다.")

    # 메인 앱 하단에도 푸터 표시
    render_footer()

if st.session_state['logged_in']: main_app()
else: login_page()