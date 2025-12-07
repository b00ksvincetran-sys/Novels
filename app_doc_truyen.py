import streamlit as st
import psycopg2
import os

# --- 1. XỬ LÝ CẤU HÌNH (Hybrid) ---
def get_supabase_url():
    try:
        from Config_local_supabase_Novels import SUPABASE_URL
        return SUPABASE_URL
    except ImportError:
        pass
    try:
        return st.secrets["SUPABASE_URL"]
    except Exception:
        return None

SUPABASE_URL = get_supabase_url()

if not SUPABASE_URL:
    st.error("❌ Lỗi cấu hình: Không tìm thấy SUPABASE_URL.")
    st.stop()

# --- 2. KẾT NỐI DB ---
@st.cache_resource
def get_connection():
    try:
        return psycopg2.connect(SUPABASE_URL)
    except Exception as e:
        st.error(f"❌ Lỗi kết nối Database: {e}")
        st.stop()

conn = get_connection()
cursor = conn.cursor()

# Lấy danh sách chương
cursor.execute("SELECT id, title FROM chapters ORDER BY id ASC")
all_chapters = cursor.fetchall()
chapter_ids = [chap[0] for chap in all_chapters]

if 'current_chap_id' not in st.session_state:
    if chapter_ids:
        st.session_state['current_chap_id'] = chapter_ids[0]
    else:
        st.error("Database rỗng!")
        st.stop()

current_id = st.session_state['current_chap_id']
current_chap_data = next((item for item in all_chapters if item[0] == current_id), None)
page_title_text = current_chap_data[1] if current_chap_data else "Web Đọc Truyện"

# --- 3. CẤU HÌNH TRANG ---
st.set_page_config(
    page_title=f"{page_title_text}",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="expanded" 
)

# 🔥 QUAN TRỌNG: ĐẶT CÁI "NEO" Ở ĐẦU TRANG 🔥
# Nút bấm ở dưới sẽ tìm đến cái id="trang_chu" này để nhảy lên
st.markdown('<div id="trang_chu"></div>', unsafe_allow_html=True)

# --- 4. CSS TÙY CHỈNH ---
def local_css(font_family):
    st.markdown(f"""
    <style>
        .paper-container {{
            background-color: var(--bg-color);
            color: var(--text-color);
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border: 1px solid rgba(0,0,0,0.05);
            margin-bottom: 20px;
        }}
        .content-text p {{
            font-family: {font_family}; 
            font-size: var(--font-size);
            line-height: 1.8;
            text-align: justify;
            margin-bottom: 1.2em;
            text-indent: 2em;
        }}
        /* Nút Lên đầu trang đẹp */
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
        .scroll-btn:hover {{
            background-color: #e0e2e6;
            color: #31333F;
        }}
        /* Ẩn Decoration */
        [data-testid="stDecoration"] {{display: none;}}
        footer {{visibility: hidden;}}
        .block-container {{padding-top: 2rem;}}
        .stButton button {{font-weight: bold;}}
    </style>
    """, unsafe_allow_html=True)

# --- 5. HÀM ĐIỀU HƯỚNG ---
def go_to_chap(chap_id):
    st.session_state['current_chap_id'] = chap_id

def next_chap():
    curr_idx = chapter_ids.index(st.session_state['current_chap_id'])
    if curr_idx < len(chapter_ids) - 1:
        st.session_state['current_chap_id'] = chapter_ids[curr_idx + 1]

def prev_chap():
    curr_idx = chapter_ids.index(st.session_state['current_chap_id'])
    if curr_idx > 0:
        st.session_state['current_chap_id'] = chapter_ids[curr_idx - 1]

# --- 6. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Cài Đặt")
    
    st.write("📖 **Nhảy trang:**")
    col_input, col_go = st.columns([3, 1])
    with col_input:
        input_chap_num = st.number_input("Số chương", min_value=1, max_value=len(chapter_ids), value=current_id, step=1, label_visibility="collapsed")
    with col_go:
        if st.button("Đi"):
            go_to_chap(input_chap_num)
            st.rerun()

    selected_chap_id = st.selectbox(
        "Chọn từ list:",
        options=chapter_ids,
        format_func=lambda x: next((t for i, t in all_chapters if i == x), f"Chương {x}"),
        index=chapter_ids.index(current_id)
    )
    if selected_chap_id != current_id:
        go_to_chap(selected_chap_id)
        st.rerun()

    st.divider()
    st.write("🎨 **Giao diện:**")
    theme_mode = st.radio("Màu nền:", ["Sáng", "Giấy (Vàng)", "Đêm (Tối)"], index=1)
    font_choice = st.radio("Font chữ:", ["Có chân (Serif)", "Không chân (Sans)"], horizontal=True)
    font_size_px = st.slider("Cỡ chữ:", 14, 30, 20)
    
    if theme_mode == "Giấy (Vàng)":
        bg_var = "#fdf6e3"; text_var = "#333333"
    elif theme_mode == "Đêm (Tối)":
        bg_var = "#1a1a1a"; text_var = "#cccccc"
    else:
        bg_var = "#ffffff"; text_var = "#212121"

    font_css = "'Merriweather', 'Times New Roman', serif" if font_choice == "Có chân (Serif)" else "'Helvetica', 'Arial', sans-serif"

    st.markdown(f"""
    <style>
        :root {{ --bg-color: {bg_var}; --text-color: {text_var}; --font-size: {font_size_px}px; }}
    </style>
    """, unsafe_allow_html=True)
    local_css(font_css)

# --- 7. HIỂN THỊ NỘI DUNG ---
current_idx = chapter_ids.index(current_id)
cursor.execute("SELECT title, content, content_edit FROM chapters WHERE id = %s", (current_id,))
data = cursor.fetchone()

if data:
    title, raw, edited = data
    final_text = edited if (edited and len(edited) > 50) else raw

    st.markdown(f"<h2 style='text-align: center; margin-bottom: 20px;'>{title}</h2>", unsafe_allow_html=True)
    
    # Nút điều hướng TRÊN
    c1, c2, c3 = st.columns([1, 4, 1])
    with c1:
        if current_idx > 0:
            st.button("⬅️", on_click=prev_chap, key="prev_top", use_container_width=True)
    with c3:
        if current_idx < len(chapter_ids) - 1:
            st.button("➡️", on_click=next_chap, key="next_top", use_container_width=True)

    # Nội dung
    if final_text:
        paragraphs = final_text.split('\n')
        html_content = "".join([f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()])
        st.markdown(f"""<div class="paper-container"><div class="content-text">{html_content}</div></div>""", unsafe_allow_html=True)
    else:
        st.warning("Chương này chưa có nội dung.")

    # Nút điều hướng DƯỚI
    c4, c5 = st.columns(2)
    with c4:
        if current_idx > 0:
            st.button("⬅️ Chương Trước", on_click=prev_chap, key="prev_bot", use_container_width=True)
    with c5:
        if current_idx < len(chapter_ids) - 1:
            st.button("Chương Sau ➡️", on_click=next_chap, key="next_bot", use_container_width=True)

    # --- 🔥 NÚT LÊN ĐẦU TRANG (THỦ CÔNG) 🔥 ---
    # Nút này là thẻ <a> HTML, bấm vào nó sẽ tự tìm id="trang_chu" ở trên cùng để nhảy lên
    st.markdown("""
        <a href="#trang_chu" class="scroll-btn" target="_self">
            ⬆️ Lên đầu trang
        </a>
    """, unsafe_allow_html=True)

else:
    st.error("Lỗi tải chương!")