import streamlit as st
import psycopg2
import os

# --- 1. KẾT NỐI SUPABASE (QUAN TRỌNG) ---
# Hàm này sẽ lấy mật khẩu từ "Secrets" của Streamlit để bảo mật
@st.cache_resource
def get_connection():
    # Lấy chuỗi kết nối từ cấu hình bảo mật
    # Khi chạy trên máy: Bạn cần tạo file .streamlit/secrets.toml
    # Khi chạy trên Web: Bạn cần vào Settings -> Secrets để điền
    try:
        return psycopg2.connect(st.secrets["SUPABASE_URL"])
    except Exception as e:
        st.error("❌ Lỗi kết nối Supabase: Chưa cấu hình Secrets!")
        st.stop()

conn = get_connection()
cursor = conn.cursor()

# Lấy danh sách ID và Title
cursor.execute("SELECT id, title FROM chapters ORDER BY id ASC")
all_chapters = cursor.fetchall()
chapter_ids = [chap[0] for chap in all_chapters]

# Khởi tạo Session State
if 'current_chap_id' not in st.session_state:
    if chapter_ids:
        st.session_state['current_chap_id'] = chapter_ids[0]
    else:
        st.error("Database chưa có chương nào!")
        st.stop()

# Tìm tên chương hiện tại cho Tab
current_id = st.session_state['current_chap_id']
current_chap_data = next((item for item in all_chapters if item[0] == current_id), None)
page_title_text = current_chap_data[1] if current_chap_data else "Web Đọc Truyện"

# --- 2. CẤU HÌNH TRANG ---
st.set_page_config(
    page_title=f"{page_title_text}",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 3. CSS TÙY CHỈNH (Giữ nguyên giao diện đẹp của bạn) ---
def local_css(font_family):
    st.markdown(f"""
    <style>
        /* Container giấy */
        .paper-container {{
            background-color: var(--bg-color);
            color: var(--text-color);
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border: 1px solid rgba(0,0,0,0.05);
            margin-bottom: 20px;
        }}

        /* Nội dung truyện */
        .content-text p {{
            font-family: {font_family}; 
            font-size: var(--font-size);
            line-height: 1.6;
            text-align: justify;
            margin-bottom: 1em;
            text-indent: 2em;
        }}
        
        /* Ẩn header mặc định */
        header {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        .block-container {{padding-top: 1rem;}}
        
        /* Chỉnh nút bấm */
        .stButton button {{
            font-weight: bold;
        }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. HÀM ĐIỀU HƯỚNG ---
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

# --- 5. SIDEBAR CÀI ĐẶT ---
with st.sidebar:
    st.header("⚙️ Cài Đặt Đọc")
    
    # 1. Nhảy chương (Nhập số)
    st.write("📖 **Nhảy tới chương:**")
    col_input, col_go = st.columns([3, 1])
    with col_input:
        input_chap_num = st.number_input("Số chương", min_value=1, max_value=len(chapter_ids), value=current_id, step=1, label_visibility="collapsed")
    with col_go:
        if st.button("Đi"):
            go_to_chap(input_chap_num)
            st.rerun()

    # 2. Dropdown chọn chương
    selected_chap_id = st.selectbox(
        "Hoặc chọn từ list:",
        options=chapter_ids,
        format_func=lambda x: next((t for i, t in all_chapters if i == x), f"Chương {x}"),
        index=chapter_ids.index(current_id)
    )
    if selected_chap_id != current_id:
        go_to_chap(selected_chap_id)
        st.rerun()

    st.divider()

    # 3. Giao diện
    st.write("🎨 **Giao diện:**")
    theme_mode = st.radio("Màu nền:", ["Sáng", "Giấy (Vàng)", "Đêm (Tối)"], index=1)
    font_choice = st.radio("Font chữ:", ["Có chân (Serif)", "Không chân (Sans)"], horizontal=True)
    font_size_px = st.slider("Cỡ chữ:", 14, 30, 20)
    
    # Xử lý CSS variable
    if theme_mode == "Giấy (Vàng)":
        bg_var = "#fdf6e3"
        text_var = "#333333"
    elif theme_mode == "Đêm (Tối)":
        bg_var = "#1a1a1a"
        text_var = "#cccccc"
    else:
        bg_var = "#ffffff"
        text_var = "#212121"

    font_css = "'Merriweather', 'Times New Roman', serif" if font_choice == "Có chân (Serif)" else "'Helvetica', 'Arial', sans-serif"

    st.markdown(f"""
    <style>
        :root {{
            --bg-color: {bg_var};
            --text-color: {text_var};
            --font-size: {font_size_px}px;
        }}
    </style>
    """, unsafe_allow_html=True)
    
    local_css(font_css)

# --- 6. PHẦN HIỂN THỊ CHÍNH ---
current_idx = chapter_ids.index(current_id)

# LẤY NỘI DUNG TỪ SUPABASE
# Lưu ý: Postgres dùng %s thay vì ?
cursor.execute("SELECT title, content, content_edit FROM chapters WHERE id = %s", (current_id,))
data = cursor.fetchone()

if data:
    title, raw, edited = data
    
    # Ưu tiên hiển thị bản Edit
    if edited and len(edited) > 50:
        final_text = edited
    else:
        final_text = raw

    # Tiêu đề chương
    st.markdown(f"<h2 style='text-align: center; margin-bottom: 20px;'>{title}</h2>", unsafe_allow_html=True)
    
    # Nút điều hướng TRÊN
    c1, c2, c3 = st.columns([1, 4, 1])
    with c1:
        if current_idx > 0:
            st.button("⬅️", on_click=prev_chap, key="prev_top", use_container_width=True)
    with c3:
        if current_idx < len(chapter_ids) - 1:
            st.button("➡️", on_click=next_chap, key="next_top", use_container_width=True)

    # Nội dung truyện
    if final_text:
        paragraphs = final_text.split('\n')
        html_content = "".join([f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()])

        st.markdown(
            f"""
            <div class="paper-container">
                <div class="content-text">
                    {html_content}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
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

else:
    st.error("Lỗi tải chương!")