import streamlit as st
import psycopg2
import os
import google.generativeai as genai

# --- 1. XỬ LÝ CẤU HÌNH (Hybrid: Local & Cloud) ---
def get_config():
    supabase_url = None
    api_key = None
    
    # Thử lấy từ file local
    try:
        from Config_local_supabase_Novels import SUPABASE_URL as local_url
        from Config_local_supabase_Novels import GEMINI_API_KEY as local_key
        supabase_url = local_url
        api_key = local_key
    except ImportError:
        pass

    # Nếu không có local, lấy từ Secrets (Cloud)
    if not supabase_url:
        try:
            supabase_url = st.secrets["SUPABASE_URL"]
        except:
            pass
    if not api_key:
        try:
            api_key = st.secrets["GEMINI_API_KEY"]
        except:
            pass
            
    return supabase_url, api_key

SUPABASE_URL, API_KEY = get_config()

if not SUPABASE_URL:
    st.error("❌ Lỗi: Không tìm thấy SUPABASE_URL.")
    st.stop()

# --- 2. KẾT NỐI DATABASE ---
@st.cache_resource
def get_connection():
    return psycopg2.connect(SUPABASE_URL)

conn = get_connection()
cursor = conn.cursor()

# Lấy danh sách chương
cursor.execute("SELECT id, title FROM chapters ORDER BY id ASC")
all_chapters = cursor.fetchall()
chapter_ids = [chap[0] for chap in all_chapters]

if 'current_chap_id' not in st.session_state:
    st.session_state['current_chap_id'] = chapter_ids[0]

current_id = st.session_state['current_chap_id']
current_chap_data = next((item for item in all_chapters if item[0] == current_id), None)
page_title = current_chap_data[1] if current_chap_data else "Web Đọc Truyện"

# --- 3. CẤU HÌNH TRANG ---
st.set_page_config(
    page_title=page_title,
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="expanded" 
)

# Neo đầu trang để cuộn
st.markdown('<div id="trang_chu"></div>', unsafe_allow_html=True)

# --- 4. CSS TÙY CHỈNH (LẤY LẠI BẢN ĐẸP NHẤT) ---
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
            line-height: 1.8;
            text-align: justify;
            margin-bottom: 1.2em;
            text-indent: 2em;
        }}
        /* Nút Lên đầu trang */
        .scroll-btn {{
            display: block; text-align: center; width: 100%; padding: 12px;
            background-color: #f0f2f6; color: #31333F; border-radius: 8px;
            text-decoration: none; font-weight: bold; border: 1px solid #ccc;
            margin-top: 10px;
        }}
        /* Ẩn Decoration thừa */
        [data-testid="stDecoration"] {{display: none;}}
        footer {{visibility: hidden;}}
        .block-container {{padding-top: 2rem;}}
        .stButton button {{font-weight: bold;}}
    </style>
    """, unsafe_allow_html=True)

# --- 5. HÀM HỖ TRỢ ---
def go_to_chap(chap_id):
    st.session_state['current_chap_id'] = chap_id

def save_chapter(chap_id, new_content):
    try:
        # Commit lại connection để chắc chắn dữ liệu mới nhất
        conn.commit() 
        with conn.cursor() as cur:
            cur.execute("UPDATE chapters SET content_edit = %s WHERE id = %s", (new_content, chap_id))
            conn.commit()
        st.toast("✅ Đã lưu thành công!", icon="💾")
        # Không rerun toàn trang để tránh mất vị trí, chỉ load lại data
    except Exception as e:
        st.error(f"Lỗi lưu: {e}")

def ai_rewrite(text):
    if not API_KEY:
        return "❌ Chưa có API Key trong Config/Secrets"
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel('models/gemini-2.5-flash')
        prompt = f"Viết lại văn phong Tiên Hiệp mượt mà, giữ nguyên cốt truyện:\n{text}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Lỗi AI: {e}"

# --- 6. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Cài Đặt")
    
    # CÔNG TẮC BIÊN TẬP (Mặc định Tắt để đọc cho đẹp)
    is_editor_mode = st.toggle("🛠️ Chế độ Biên Tập", value=False)
    
    st.divider()
    
    # Điều hướng
    col_i, col_b = st.columns([3, 1])
    with col_i:
        input_chap = st.number_input("Chương số", 1, len(chapter_ids), current_id, label_visibility="collapsed")
    with col_b:
        if st.button("Go"):
            go_to_chap(input_chap)
            st.rerun()
            
    sel_chap = st.selectbox("Chọn list", chapter_ids, index=chapter_ids.index(current_id), format_func=lambda x: f"Chương {x}")
    if sel_chap != current_id:
        go_to_chap(sel_chap)
        st.rerun()

    st.divider()
    
    # Giao diện (Chỉ hiện khi KHÔNG biên tập cho đỡ rối)
    if not is_editor_mode:
        theme_mode = st.radio("Màu nền:", ["Sáng", "Giấy (Vàng)", "Đêm (Tối)"], index=1)
        font_choice = st.radio("Font chữ:", ["Có chân", "Không chân"], horizontal=True)
        font_size_px = st.slider("Cỡ chữ:", 14, 30, 20)
        
        if theme_mode == "Giấy (Vàng)": bg_var="#fdf6e3"; txt_var="#333333"
        elif theme_mode == "Đêm (Tối)": bg_var="#1a1a1a"; txt_var="#cccccc"
        else: bg_var="#ffffff"; txt_var="#212121"
        
        font_css = "'Merriweather', serif" if font_choice == "Có chân" else "'Arial', sans-serif"
        
        st.markdown(f"<style>:root {{--bg-color: {bg_var}; --text-color: {txt_var}; --font-size: {font_size_px}px;}}</style>", unsafe_allow_html=True)
        local_css(font_css)

# --- 7. HIỂN THỊ CHÍNH ---
cursor.execute("SELECT title, content, content_edit FROM chapters WHERE id = %s", (current_id,))
data = cursor.fetchone()

if data:
    title, raw, edited = data
    
    # --- TRƯỜNG HỢP 1: CHẾ ĐỘ ĐỌC (GIAO DIỆN ĐẸP CŨ) ---
    if not is_editor_mode:
        final_text = edited if (edited and len(edited) > 50) else raw
        
        st.markdown(f"<h2 style='text-align: center; margin-bottom: 20px;'>{title}</h2>", unsafe_allow_html=True)
        
        # Nav trên
        c1, c2, c3 = st.columns([1, 4, 1])
        if c1.button("⬅️"): 
            go_to_chap(chapter_ids[chapter_ids.index(current_id)-1] if chapter_ids.index(current_id)>0 else current_id)
            st.rerun()
        if c3.button("➡️"): 
            go_to_chap(chapter_ids[chapter_ids.index(current_id)+1] if chapter_ids.index(current_id)<len(chapter_ids)-1 else current_id)
            st.rerun()

        # Nội dung giấy
        if final_text:
            paragraphs = final_text.split('\n')
            html_content = "".join([f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()])
            st.markdown(f"""<div class="paper-container"><div class="content-text">{html_content}</div></div>""", unsafe_allow_html=True)
        
        # Nav dưới & Scroll
        c4, c5 = st.columns(2)
        if c4.button("⬅️ Chương Trước"):
            go_to_chap(chapter_ids[chapter_ids.index(current_id)-1] if chapter_ids.index(current_id)>0 else current_id)
            st.rerun()
        if c5.button("Chương Sau ➡️"):
            go_to_chap(chapter_ids[chapter_ids.index(current_id)+1] if chapter_ids.index(current_id)<len(chapter_ids)-1 else current_id)
            st.rerun()
            
        st.markdown("""<a href="#trang_chu" class="scroll-btn" target="_self">⬆️ Lên đầu trang</a>""", unsafe_allow_html=True)

    # --- TRƯỜNG HỢP 2: CHẾ ĐỘ BIÊN TẬP (ADMIN) ---
    else:
        st.title(f"🛠️ Sửa: {title}")
        
        col_L, col_R = st.columns(2)
        with col_L:
            st.info("📄 Gốc (Convert)")
            st.text_area("Gốc", value=raw, height=500, disabled=True, label_visibility="collapsed")
            
        with col_R:
            st.success("📝 Bản Dịch (Edit)")
            with st.form("editor"):
                # Nếu đã có edit thì lấy edit, chưa thì lấy gốc để sửa
                val_to_edit = edited if edited else raw 
                new_content = st.text_area("Nội dung", value=val_to_edit, height=450, label_visibility="collapsed")
                
                b1, b2 = st.columns([1, 1])
                if b1.form_submit_button("💾 LƯU LẠI", type="primary", use_container_width=True):
                    save_chapter(current_id, new_content)
                    
            # Nút AI hỗ trợ (Ngoài form)
            if st.button("🤖 Nhờ AI Dịch lại (Gemini)", use_container_width=True):
                with st.spinner("Đang dịch..."):
                    res = ai_rewrite(raw)
                    if "Lỗi" not in res:
                        save_chapter(current_id, res)
                        st.rerun()
                    else:
                        st.error(res)

else:
    st.error("Lỗi tải chương!")