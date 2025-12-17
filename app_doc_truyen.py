import streamlit as st
import psycopg2
import os
import json
import google.generativeai as genai

# --- 1. XỬ LÝ CẤU HÌNH ---
def get_config():
    supabase_url = None
    api_key = None
    # Ưu tiên lấy từ file config local
    try:
        from Config_local_supabase_Novels import SUPABASE_URL as local_url
        from Config_local_supabase_Novels import GEMINI_API_KEY as local_key
        supabase_url = local_url
        api_key = local_key
    except ImportError: pass
    
    # Nếu không có file local, lấy từ Secrets (dùng cho Streamlit Cloud)
    if not supabase_url:
        try: supabase_url = st.secrets["SUPABASE_URL"]
        except: pass
    if not api_key:
        try: api_key = st.secrets["GEMINI_API_KEY"]
        except: pass
        
    return supabase_url, api_key

SUPABASE_URL, API_KEY = get_config()
if not SUPABASE_URL: 
    st.error("Chưa cấu hình Database URL!")
    st.stop()

# --- [FIX QUAN TRỌNG] QUẢN LÝ KẾT NỐI AN TOÀN ---
@st.cache_resource
def get_connection():
    """Tạo kết nối mới và lưu vào cache"""
    return psycopg2.connect(SUPABASE_URL)

# Lấy kết nối từ cache
conn = get_connection()

# KIỂM TRA SỨC KHỎE KẾT NỐI
# Nếu kết nối đã bị đóng (closed != 0), xóa cache và kết nối lại ngay lập tức
if conn.closed != 0:
    st.cache_resource.clear()
    conn = get_connection()

# Bây giờ an toàn để lấy cursor
cursor = conn.cursor()

# --- 2. HÀM CẬP NHẬT URL KIỂU MỚI ---
def update_url(novel_slug, chap_index):
    st.query_params["truyen"] = novel_slug
    st.query_params["chuong"] = str(chap_index)

# --- 3. LẤY DANH SÁCH TRUYỆN ---
try:
    cursor.execute("SELECT id, title, slug FROM novels ORDER BY title ASC")
    all_novels = cursor.fetchall()
except psycopg2.Error:
    # Phòng trường hợp rớt mạng giữa chừng
    st.cache_resource.clear()
    st.rerun()

if not all_novels:
    st.warning("Chưa có truyện nào!")
    st.stop()

novel_id_to_slug = {n[0]: n[2] for n in all_novels}
novel_slug_to_id = {n[2]: n[0] for n in all_novels}
novel_id_to_title = {n[0]: n[1] for n in all_novels}

# --- 4. XỬ LÝ ĐIỀU HƯỚNG TỪ URL ---
params = st.query_params
url_slug = params.get("truyen", None)
url_chap = params.get("chuong", None)

current_novel_id = None
if url_slug and url_slug in novel_slug_to_id:
    current_novel_id = novel_slug_to_id[url_slug]
else:
    current_novel_id = all_novels[0][0]

if 'current_novel_id' not in st.session_state or st.session_state['current_novel_id'] != current_novel_id:
    st.session_state['current_novel_id'] = current_novel_id

# --- 5. LẤY DANH SÁCH CHƯƠNG ---
cursor.execute("SELECT id, chapter_index, title FROM chapters WHERE novel_id = %s ORDER BY chapter_index ASC", (current_novel_id,))
all_chapters = cursor.fetchall()

if not all_chapters:
    st.warning("Truyện này chưa có chương nào.")
    st.stop()

chap_idx_to_id = {c[1]: c[0] for c in all_chapters}
chap_idx_to_title = {c[1]: c[2] for c in all_chapters}
list_indexes = list(chap_idx_to_id.keys())

current_chap_idx = 1
if url_chap and url_chap.isdigit() and int(url_chap) in list_indexes:
    current_chap_idx = int(url_chap)
elif 'current_chap_idx' in st.session_state and st.session_state['current_chap_idx'] in list_indexes:
    current_chap_idx = st.session_state['current_chap_idx']
else:
    current_chap_idx = list_indexes[0]

st.session_state['current_chap_idx'] = current_chap_idx
current_slug = novel_id_to_slug[current_novel_id]

if params.get("truyen") != current_slug or params.get("chuong") != str(current_chap_idx):
    update_url(current_slug, current_chap_idx)

real_chap_id = chap_idx_to_id[current_chap_idx]
page_title = f"Chương {current_chap_idx} | {novel_id_to_title[current_novel_id]}"

# --- 6. CẤU HÌNH TRANG ---
st.set_page_config(page_title=page_title, page_icon="📖", layout="centered", initial_sidebar_state="expanded")
st.markdown('<div id="trang_chu"></div>', unsafe_allow_html=True)

# --- CSS & JS ---
# --- CSS & JS ---
def local_css(font_family):
    st.markdown(f"""
    <style>
        /* Khung giấy: Màu nền, đổ bóng nhẹ */
        .paper-container {{ 
            background-color: var(--bg-color); 
            color: var(--text-color); 
            padding: 40px; 
            border-radius: 8px; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
            border: 1px solid rgba(0,0,0,0.05); 
            margin-bottom: 20px; 
        }}
        
        /* Nội dung truyện: Tinh chỉnh chuẩn quốc tế */
        .content-text p {{ 
            font-family: {font_family}; 
            font-size: var(--font-size); 
            
            /* [THAY ĐỔI QUAN TRỌNG TẠI ĐÂY] */
            line-height: 1.6;        /* Chuẩn quốc tế (Medium/Kindle): 1.6 thay vì 2.0 */
            margin-bottom: 1.2em;    /* Khoảng cách đoạn vừa phải hơn */
            
            text-align: justify;     /* Căn đều 2 bên cho đẹp mắt */
            text-indent: 2em;        /* Thụt đầu dòng */
        }}
        
        /* Nút cuộn lên đầu trang */
        .scroll-btn {{ 
            display: block; 
            text-align: center; 
            width: 100%; 
            padding: 12px; 
            background-color: #f0f2f6; 
            color: #31333F; 
            border-radius: 8px; 
            text-decoration: none; 
            font-weight: bold; 
            border: 1px solid #ccc; 
            margin-top: 10px; 
        }}
        
        /* Ẩn các thành phần thừa của Streamlit */
        [data-testid="stDecoration"] {{display: none;}} 
        footer {{visibility: hidden;}} 
        .block-container {{padding-top: 2rem;}} 
        .stButton button {{font-weight: bold;}}
    </style>
    """, unsafe_allow_html=True)

# --- 7. LOGIC HÀM ---

def clean_content(text):
    if not text: return ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("content_edit", data.get("content", ""))
        return str(data)
    except json.JSONDecodeError:
        return text

def change_chap(new_idx):
    st.session_state['current_chap_idx'] = new_idx
    update_url(novel_id_to_slug[current_novel_id], new_idx)

def change_novel():
    new_slug = st.session_state.sb_novel_select
    new_id = novel_slug_to_id[new_slug]
    st.session_state['current_novel_id'] = new_id
    st.session_state['current_chap_idx'] = 1 
    update_url(new_slug, 1)

def save_chapter(chap_id, content):
    try:
        # Kiểm tra kết nối trước khi lưu
        if conn.closed != 0:
            st.cache_resource.clear()
            st.rerun()
            
        conn.commit()
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
        res = model.generate_content(f"Viết lại văn phong Tiên Hiệp mượt mà. Chỉ trả về nội dung truyện, không trả về JSON, không lời dẫn:\n{text}")
        return res.text.strip()
    except Exception as e: return f"Lỗi AI: {e}"

# --- 8. SIDEBAR ---
with st.sidebar:
    st.header("📚 Tủ Sách")
    
    novel_options = list(novel_slug_to_id.keys())
    try:
        current_slug_idx = novel_options.index(current_slug)
    except:
        current_slug_idx = 0
    
    st.selectbox(
        "Đang đọc:", 
        options=novel_options,
        format_func=lambda x: novel_id_to_title[novel_slug_to_id[x]],
        index=current_slug_idx,
        key="sb_novel_select",
        on_change=change_novel
    )

    st.divider()
    st.header("⚙️ Cài Đặt")
    is_editor_mode = st.toggle("🛠️ Chế độ Biên Tập", value=False)
    
    col_i, col_b = st.columns([3, 1])
    with col_i:
        input_idx = st.number_input("Chương số", 1, len(list_indexes), current_chap_idx, label_visibility="collapsed")
    with col_b:
        if st.button("Go"):
            change_chap(input_idx)
            st.rerun()
            
    def on_chap_select():
        change_chap(st.session_state.sb_chap_select)
        
    st.selectbox("Danh sách:", list_indexes, index=list_indexes.index(current_chap_idx), 
                 format_func=lambda x: f"Chương {x}: {chap_idx_to_title.get(x, '')[:20]}...",
                 key="sb_chap_select", on_change=on_chap_select)

    if not is_editor_mode:
        st.divider()
        theme = st.radio("Màu nền:", ["Sáng", "Giấy (Vàng)", "Đêm (Tối)"], index=1)
        font = st.radio("Font:", ["Có chân", "Không chân"], horizontal=True)
        size = st.slider("Cỡ chữ:", 14, 30, 22)
        
        bg, txt = ("#fdf6e3", "#2c2c2c") if theme == "Giấy (Vàng)" else ("#1a1a1a", "#d4d4d4") if theme == "Đêm (Tối)" else ("#ffffff", "#212121")
        font_style = "'Merriweather', serif" if font == "Có chân" else "'Arial', sans-serif"
        
        st.markdown(f"<style>:root {{--bg-color: {bg}; --text-color: {txt}; --font-size: {size}px;}}</style>", unsafe_allow_html=True)
        local_css(font_style)

# --- 9. HIỂN THỊ NỘI DUNG ---
cursor.execute("SELECT title, content, content_edit FROM chapters WHERE id = %s", (real_chap_id,))
data = cursor.fetchone()

if data:
    title, raw, edited_db = data
    
    final_content_to_show = clean_content(edited_db) if (edited_db and len(edited_db) > 50) else clean_content(raw)

    has_prev = current_chap_idx > 1
    has_next = current_chap_idx < len(list_indexes)

    if not is_editor_mode:
        st.markdown(f"<h2 style='text-align: center; margin-bottom: 30px;'>{title}</h2>", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([1, 6, 1])
        if c1.button("⬅️", disabled=not has_prev): 
            change_chap(current_chap_idx - 1); st.rerun()
        if c3.button("➡️", disabled=not has_next): 
            change_chap(current_chap_idx + 1); st.rerun()

        if final_content_to_show:
            paragraphs = final_content_to_show.replace('\\n', '\n').split('\n')
            html_content = "".join([f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()])
            
            st.markdown(f"""<div class="paper-container"><div class="content-text">{html_content}</div></div>""", unsafe_allow_html=True)
        else:
            st.info("Chương này chưa có nội dung.")
        
        c4, c5 = st.columns(2)
        if c4.button("⬅️ Chương Trước", disabled=not has_prev, use_container_width=True): 
            change_chap(current_chap_idx - 1); st.rerun()
        if c5.button("Chương Sau ➡️", disabled=not has_next, use_container_width=True): 
            change_chap(current_chap_idx + 1); st.rerun()
            
        st.markdown("""<a href="#trang_chu" class="scroll-btn" target="_self">⬆️ Lên đầu trang</a>""", unsafe_allow_html=True)

    else:
        # CHẾ ĐỘ BIÊN TẬP
        st.title(f"🛠️ Sửa: {title}")
        cL, cR = st.columns(2)
        with cL: 
            st.subheader("Bản Convert gốc")
            st.text_area("Raw", value=clean_content(raw), height=600, disabled=True)
        with cR:
            with st.form("edit"):
                st.subheader("Bản Dịch/Edit")
                new = st.text_area("Nội dung", value=final_content_to_show, height=520)
                if st.form_submit_button("💾 LƯU NỘI DUNG", type="primary", use_container_width=True): 
                    save_chapter(real_chap_id, new)
                    st.rerun()
            
            if st.button("🤖 AI Viết Lại (Gemini)", use_container_width=True):
                with st.spinner("Đang viết lại..."):
                    res = ai_rewrite(clean_content(raw))
                    if "Lỗi" not in res: 
                        save_chapter(real_chap_id, res)
                        st.rerun()
                    else: st.error(res)
else:
    st.error("Lỗi dữ liệu chương!")