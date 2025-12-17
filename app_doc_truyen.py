import streamlit as st
import psycopg2
import os
import json
import google.generativeai as genai
import math

# ==============================================================================
# 1. CẤU HÌNH & KẾT NỐI (GIỮ NGUYÊN TỪ CODE CŨ)
# ==============================================================================
def get_config():
    supabase_url = None
    api_key = None
    try:
        from Config_local_supabase_Novels import SUPABASE_URL as local_url
        from Config_local_supabase_Novels import GEMINI_API_KEY as local_key
        supabase_url = local_url
        api_key = local_key
    except ImportError: pass
    
    if not supabase_url:
        try: supabase_url = st.secrets["SUPABASE_URL"]
        except: pass
    if not api_key:
        try: api_key = st.secrets["GEMINI_API_KEY"]
        except: pass
        
    return supabase_url, api_key

SUPABASE_URL, API_KEY = get_config()
if not SUPABASE_URL: st.error("Thiếu Database URL!"); st.stop()

@st.cache_resource
def get_connection():
    return psycopg2.connect(SUPABASE_URL)

conn = get_connection()
if conn.closed != 0: st.cache_resource.clear(); conn = get_connection()
cursor = conn.cursor()

# ==============================================================================
# 2. HÀM HỖ TRỢ (NAVIGATE, CLEAN, PAGINATE)
# ==============================================================================
def update_url(novel_slug, chap_index):
    st.query_params["truyen"] = novel_slug
    st.query_params["chuong"] = str(chap_index)

def change_chap(new_idx):
    st.session_state['current_chap_idx'] = new_idx
    st.session_state['sub_page'] = 0 # Reset về trang 1 khi đổi chương
    try:
        slug = novel_id_to_slug[st.session_state['current_novel_id']]
        update_url(slug, new_idx)
    except: pass

def change_novel():
    new_slug = st.session_state.sb_novel_select
    new_id = novel_slug_to_id[new_slug]
    st.session_state['current_novel_id'] = new_id
    st.session_state['current_chap_idx'] = 1 
    st.session_state['sub_page'] = 0
    update_url(new_slug, 1)

def clean_content(text):
    if not text: return ""
    try:
        data = json.loads(text)
        if isinstance(data, dict): text = data.get("content_edit", data.get("content", ""))
    except: pass
    
    if "<<<BAT_DAU>>>" in text:
        import re
        m = re.search(r"<<<BAT_DAU>>>\s*(.*?)\s*<<<KET_THUC>>>", text, re.DOTALL)
        if m: text = m.group(1).strip()
    return text

def paginate_text(text, words_per_page=350):
    """Cắt text thành list trang (cho chế độ Lật trang)"""
    if not text: return ["(Chưa có nội dung)"]
    paragraphs = text.replace('\\n', '\n').split('\n')
    pages = []
    current_page = ""
    current_word_count = 0
    
    for p in paragraphs:
        p = p.strip()
        if not p: continue
        words_in_p = len(p.split())
        
        if current_word_count + words_in_p > words_per_page and current_word_count > 0:
            pages.append(current_page)
            current_page = f"<p>{p}</p>"
            current_word_count = words_in_p
        else:
            current_page += f"<p>{p}</p>"
            current_word_count += words_in_p
    if current_page: pages.append(current_page)
    return pages

def save_chapter(chap_id, content):
    try:
        if conn.closed != 0: st.cache_resource.clear(); st.rerun()
        with conn.cursor() as cur:
            cur.execute("UPDATE chapters SET content_edit = %s WHERE id = %s", (content, chap_id))
            conn.commit()
        st.toast("✅ Đã lưu!", icon="💾")
    except Exception as e: st.error(f"Lỗi: {e}")

def ai_rewrite(text):
    if not API_KEY: return "❌ Thiếu API Key"
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        res = model.generate_content(f"Viết lại văn phong Tiên Hiệp mượt mà:\n{text}")
        return res.text.strip()
    except Exception as e: return f"Lỗi AI: {e}"

# ==============================================================================
# 3. SETUP DỮ LIỆU BAN ĐẦU
# ==============================================================================
try:
    cursor.execute("SELECT id, title, slug FROM novels ORDER BY title ASC")
    all_novels = cursor.fetchall()
except psycopg2.Error: st.cache_resource.clear(); st.rerun()

if not all_novels: st.warning("Chưa có truyện!"); st.stop()

novel_id_to_slug = {n[0]: n[2] for n in all_novels}
novel_slug_to_id = {n[2]: n[0] for n in all_novels}
novel_id_to_title = {n[0]: n[1] for n in all_novels}

# URL Params
params = st.query_params
url_slug = params.get("truyen", None)
current_novel_id = novel_slug_to_id.get(url_slug, all_novels[0][0])

if 'current_novel_id' not in st.session_state or st.session_state['current_novel_id'] != current_novel_id:
    st.session_state['current_novel_id'] = current_novel_id

# Fetch Chapters
cursor.execute("SELECT id, chapter_index, title FROM chapters WHERE novel_id = %s ORDER BY chapter_index ASC", (current_novel_id,))
all_chapters = cursor.fetchall()
if not all_chapters: st.warning("Truyện rỗng."); st.stop()

chap_idx_to_id = {c[1]: c[0] for c in all_chapters}
chap_idx_to_title = {c[1]: c[2] for c in all_chapters}
list_indexes = list(chap_idx_to_id.keys())

# Current Chapter
url_chap = params.get("chuong", None)
if url_chap and url_chap.isdigit() and int(url_chap) in list_indexes:
    current_chap_idx = int(url_chap)
elif 'current_chap_idx' in st.session_state:
    current_chap_idx = st.session_state['current_chap_idx']
else:
    current_chap_idx = list_indexes[0]

if current_chap_idx not in list_indexes: current_chap_idx = list_indexes[0]
st.session_state['current_chap_idx'] = current_chap_idx

# Init Sub-page (Quan trọng cho chế độ lật trang)
if 'sub_page' not in st.session_state: st.session_state['sub_page'] = 0

real_chap_id = chap_idx_to_id[current_chap_idx]
page_title = f"Chương {current_chap_idx} | {novel_id_to_title[current_novel_id]}"

st.set_page_config(page_title=page_title, page_icon="📖", layout="centered", initial_sidebar_state="expanded")

# ==============================================================================
# 4. CSS DYNAMIC (ĐÃ CHỈNH STYLE GIÃN DÒNG NHƯ BẠN THÍCH)
# ==============================================================================
def local_css(font_family, mode="flip"):
    # Nếu lật trang: Chiều cao tối thiểu 70vh để không bị giật
    # Nếu cuộn: Chiều cao tự động
    height_style = "min-height: 70vh;" if mode == "flip" else "height: auto; overflow: visible;"
    
    st.markdown(f"""
    <style>
        [data-testid="stDecoration"] {{display: none;}} 
        footer {{visibility: hidden;}} 
        .block-container {{padding-top: 1rem; padding-bottom: 5rem;}}
        
        .paper-container {{
            background-color: var(--bg-color);
            color: var(--text-color);
            padding: 30px 40px; /* Padding vừa phải cho điện thoại */
            border-radius: 8px;
            box-shadow: 1px 1px 0px rgba(0,0,0,0.05), 3px 3px 10px rgba(0,0,0,0.1);
            
            font-family: {font_family};
            font-size: var(--font-size);
            
            /* [STYLE BẠN THÍCH] Giãn dòng và căn chỉnh */
            line-height: 1.8; 
            text-align: justify;
            
            {height_style}
            
            border-left: 3px solid rgba(0,0,0,0.1);
        }}
        
        .paper-container p {{ 
            margin-bottom: 1.2em; 
            text-indent: 1.5em; 
        }}
        
        /* Style nút bấm to rõ cho điện thoại */
        .stButton button {{
            width: 100%; 
            border-radius: 12px; 
            font-weight: bold; 
            height: 50px; /* Nút cao dễ bấm */
            border: 1px solid rgba(0,0,0,0.1);
        }}
        
        .scroll-btn {{
            display: block; text-align: center; width: 100%; padding: 12px;
            background-color: #f0f2f6; color: #31333F;
            border-radius: 12px; text-decoration: none; font-weight: bold;
            margin-top: 10px; border: 1px solid #ccc;
        }}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 5. SIDEBAR (MENU)
# ==============================================================================
with st.sidebar:
    st.header("📚 Tủ Sách")
    novel_options = list(novel_slug_to_id.keys())
    try: idx = novel_options.index(current_slug)
    except: idx = 0
    st.selectbox("Truyện:", options=novel_options, format_func=lambda x: novel_id_to_title[novel_slug_to_id[x]], index=idx, key="sb_novel_select", on_change=change_novel)

    st.divider()
    st.header("⚙️ Cài Đặt")
    is_editor_mode = st.toggle("🛠️ Chế độ Biên Tập", value=False)
    
    # [MỚI] CHỌN CHẾ ĐỘ ĐỌC
    if not is_editor_mode:
        reading_mode = st.radio("Chế độ đọc:", ["📖 Lật trang (E-Book)", "📜 Cuộn dọc (Web)"], index=0)
    
    # Quick Jump
    col_i, col_b = st.columns([3, 1])
    with col_i: input_idx = st.number_input("Chương số", 1, len(list_indexes), current_chap_idx, label_visibility="collapsed")
    with col_b: 
        if st.button("Go"): change_chap(input_idx); st.rerun()
            
    st.selectbox("Danh sách:", list_indexes, index=list_indexes.index(current_chap_idx), 
                 format_func=lambda x: f"Chương {x}: {chap_idx_to_title.get(x, '')[:20]}...",
                 key="sb_chap_select", on_change=lambda: change_chap(st.session_state.sb_chap_select))

    if not is_editor_mode:
        st.divider()
        theme = st.radio("Giao diện:", ["Sáng", "Giấy (Vàng)", "Đêm (Tối)"], index=1)
        font = st.radio("Font chữ:", ["Có chân", "Không chân"], index=0, horizontal=True)
        size = st.slider("Cỡ chữ:", 16, 30, 22)
        
        bg, txt = ("#fdf6e3", "#2c2c2c") if theme == "Giấy (Vàng)" else ("#1a1a1a", "#d4d4d4") if theme == "Đêm (Tối)" else ("#ffffff", "#212121")
        font_style = "'Merriweather', serif" if "Có chân" in font else "'Arial', sans-serif"
        
        st.markdown(f"<style>:root {{--bg-color: {bg}; --text-color: {txt}; --font-size: {size}px;}}</style>", unsafe_allow_html=True)
        
        # Inject CSS dựa theo chế độ đọc
        css_mode = "flip" if "Lật trang" in reading_mode else "scroll"
        local_css(font_style, css_mode)

# ==============================================================================
# 6. MAIN UI (HIỂN THỊ)
# ==============================================================================
cursor.execute("SELECT title, content, content_edit FROM chapters WHERE id = %s", (real_chap_id,))
data = cursor.fetchone()

if data:
    title, raw, edited_db = data
    final_text_raw = edited_db if (edited_db and len(edited_db) > 50) else raw
    final_text = clean_content(final_text_raw)

    if not is_editor_mode:
        # Tiêu đề chung
        st.markdown(f"<div id='top_page'></div><h3 style='text-align: center; color: #888; margin-bottom: 10px;'>{title}</h3>", unsafe_allow_html=True)

        # ======================================================================
        # MODE 1: LẬT TRANG (BỐ CỤC ĐIỆN THOẠI)
        # ======================================================================
        if "Lật trang" in reading_mode:
            pages = paginate_text(final_text, words_per_page=350) 
            total_subs = len(pages)
            
            if st.session_state['sub_page'] >= total_subs: st.session_state['sub_page'] = total_subs - 1
            current_sub = st.session_state['sub_page']
            
            # 1. HIỂN THỊ NỘI DUNG SÁCH
            st.markdown(f"""
                <div class="paper-container">
                    {pages[current_sub]}
                </div>
                <div style="text-align: center; font-size: 12px; color: gray; margin-top: 5px; margin-bottom: 10px;">
                    Trang {current_sub + 1} / {total_subs}
                </div>
            """, unsafe_allow_html=True)
            
            # 2. NÚT CHUYỂN TRANG (MŨI TÊN TRÁI - PHẢI)
            # Dùng columns tỷ lệ 1:2:1 hoặc 1:1 tùy sở thích
            c_prev_page, c_prog, c_next_page = st.columns([1, 2, 1])
            
            with c_prev_page:
                # Nút lùi trang trong cùng 1 chương
                if st.button("⬅️", key="btn_prev_page", help="Trang trước"):
                    if current_sub > 0:
                        st.session_state['sub_page'] -= 1; st.rerun()
                    else: st.toast("Đây là trang đầu!")
            
            with c_prog:
                 # Thanh tiến độ của chương hiện tại
                 st.progress((current_sub + 1) / total_subs)

            with c_next_page:
                # Nút sang trang trong cùng 1 chương
                if st.button("➡️", key="btn_next_page", help="Trang sau"):
                    if current_sub < total_subs - 1:
                        st.session_state['sub_page'] += 1; st.rerun()
                    else: st.toast("Đã hết trang, hãy bấm nút dưới để sang chương mới!")

            st.write("") # Spacer

            # 3. NÚT CHUYỂN CHƯƠNG (NẰM DƯỚI CÙNG)
            c_prev_chap, c_next_chap = st.columns(2)
            
            with c_prev_chap:
                if st.button("⬅️ Chương Trước", disabled=current_chap_idx<=1, use_container_width=True):
                    change_chap(current_chap_idx - 1); st.rerun()
            
            with c_next_chap:
                # Logic thông minh: Nếu đang ở trang cuối cùng của chương, nút này sẽ nổi bật hơn
                is_last_page = (current_sub == total_subs - 1)
                btn_type = "primary" if is_last_page else "secondary"
                label = "Chương Sau ⏩" if is_last_page else "Chương Sau ➡️"
                
                if st.button(label, type=btn_type, disabled=current_chap_idx>=len(list_indexes), use_container_width=True):
                    change_chap(current_chap_idx + 1); st.rerun()

        # ======================================================================
        # MODE 2: CUỘN DỌC (GIỮ NGUYÊN NHƯ CŨ)
        # ======================================================================
        else:
            paragraphs = final_text.replace('\\n', '\n').split('\n')
            full_html = "".join([f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()])
            
            # Nav Top
            c1, c2, c3 = st.columns([1, 6, 1])
            if c1.button("⬅️", key="top_prev", disabled=current_chap_idx<=1): change_chap(current_chap_idx - 1); st.rerun()
            if c3.button("➡️", key="top_next", disabled=current_chap_idx>=len(list_indexes)): change_chap(current_chap_idx + 1); st.rerun()

            st.markdown(f"""<div class="paper-container">{full_html}</div>""", unsafe_allow_html=True)
            
            # Nav Bottom
            c4, c5 = st.columns(2)
            if c4.button("⬅️ Chương Trước", disabled=current_chap_idx<=1, use_container_width=True): 
                change_chap(current_chap_idx - 1); st.rerun()
            if c5.button("Chương Sau ➡️", disabled=current_chap_idx>=len(list_indexes), use_container_width=True): 
                change_chap(current_chap_idx + 1); st.rerun()
            
            st.markdown("""<a href="#top_page" class="scroll-btn" target="_self">⬆️ Lên đầu trang</a>""", unsafe_allow_html=True)

    else:
        # === CHẾ ĐỘ BIÊN TẬP (GIỮ NGUYÊN) ===
        st.title(f"🛠️ Sửa: {title}")
        cL, cR = st.columns(2)
        with cL: 
            st.subheader("Raw")
            st.text_area("Gốc", value=clean_content(raw), height=600, disabled=True)
        with cR:
            with st.form("edit"):
                st.subheader("Edit")
                new = st.text_area("Nội dung", value=final_text, height=520)
                if st.form_submit_button("💾 LƯU", type="primary", use_container_width=True): 
                    save_chapter(real_chap_id, new); st.rerun()
            if st.button("🤖 AI Rewrite", use_container_width=True):
                res = ai_rewrite(clean_content(raw))
                if "Lỗi" not in res: save_chapter(real_chap_id, res); st.rerun()
                else: st.error(res)
else:
    st.error("Lỗi dữ liệu chương!")