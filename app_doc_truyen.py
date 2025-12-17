import streamlit as st
import psycopg2
import os
import json
import google.generativeai as genai

# ==============================================================================
# 1. CẤU HÌNH & KẾT NỐI (GIỮ NGUYÊN)
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
# 2. HÀM HỖ TRỢ & LOGIC
# ==============================================================================
def update_url(novel_slug, chap_index):
    st.query_params["truyen"] = novel_slug
    st.query_params["chuong"] = str(chap_index)

def change_chap(new_idx):
    st.session_state['current_chap_idx'] = new_idx
    try:
        slug = novel_id_to_slug[st.session_state['current_novel_id']]
        update_url(slug, new_idx)
    except: pass

def change_novel():
    new_slug = st.session_state.sb_novel_select
    new_id = novel_slug_to_id[new_slug]
    st.session_state['current_novel_id'] = new_id
    st.session_state['current_chap_idx'] = 1 
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

def paginate_text_to_json(text, words_per_page=160):
    """
    Cắt text thành JSON.
    [FIX]: Giảm xuống 160 từ/trang để đảm bảo hiển thị đẹp trên mobile, 
    tránh bị tràn màn hình gây cắt chữ.
    """
    if not text: return json.dumps(["<p>(Chưa có nội dung)</p>"])
    
    paragraphs = text.replace('\\n', '\n').split('\n')
    pages = []
    current_page = ""
    current_word_count = 0
    
    for p in paragraphs:
        p = p.strip()
        if not p: continue
        words_in_p = len(p.split())
        
        # Nếu cộng thêm đoạn này mà lố số từ -> Sang trang mới
        if current_word_count + words_in_p > words_per_page and current_word_count > 0:
            pages.append(current_page)
            current_page = f"<p>{p}</p>"
            current_word_count = words_in_p
        else:
            current_page += f"<p>{p}</p>"
            current_word_count += words_in_p
            
    if current_page: pages.append(current_page)
    return json.dumps(pages)

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
# 3. SETUP DỮ LIỆU
# ==============================================================================
try:
    cursor.execute("SELECT id, title, slug FROM novels ORDER BY title ASC")
    all_novels = cursor.fetchall()
except psycopg2.Error: st.cache_resource.clear(); st.rerun()

if not all_novels: st.warning("Chưa có truyện!"); st.stop()

novel_id_to_slug = {n[0]: n[2] for n in all_novels}
novel_slug_to_id = {n[2]: n[0] for n in all_novels}
novel_id_to_title = {n[0]: n[1] for n in all_novels}

params = st.query_params
url_slug = params.get("truyen", None)
current_novel_id = novel_slug_to_id.get(url_slug, all_novels[0][0])

if 'current_novel_id' not in st.session_state or st.session_state['current_novel_id'] != current_novel_id:
    st.session_state['current_novel_id'] = current_novel_id

cursor.execute("SELECT id, chapter_index, title FROM chapters WHERE novel_id = %s ORDER BY chapter_index ASC", (current_novel_id,))
all_chapters = cursor.fetchall()
if not all_chapters: st.warning("Truyện rỗng."); st.stop()

chap_idx_to_id = {c[1]: c[0] for c in all_chapters}
chap_idx_to_title = {c[1]: c[2] for c in all_chapters}
list_indexes = list(chap_idx_to_id.keys())

url_chap = params.get("chuong", None)
if url_chap and url_chap.isdigit() and int(url_chap) in list_indexes:
    current_chap_idx = int(url_chap)
elif 'current_chap_idx' in st.session_state:
    current_chap_idx = st.session_state['current_chap_idx']
else:
    current_chap_idx = list_indexes[0]

if current_chap_idx not in list_indexes: current_chap_idx = list_indexes[0]
st.session_state['current_chap_idx'] = current_chap_idx
real_chap_id = chap_idx_to_id[current_chap_idx]
page_title = f"Chương {current_chap_idx} | {novel_id_to_title[current_novel_id]}"

st.set_page_config(page_title=page_title, page_icon="📖", layout="centered", initial_sidebar_state="collapsed")

# ==============================================================================
# 4. TRÌNH ĐỌC SÁCH MOBILE (FIX GIAO DIỆN)
# ==============================================================================
def render_instant_reader_mobile(pages_json):
    """
    Đã tinh chỉnh CSS để fix lỗi cắt chữ và khoảng trắng.
    """
    
    html_code = f"""
    <style>
        /* Ẩn bớt UI Streamlit */
        header {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        .block-container {{
            padding: 0 !important;
            margin: 0 !important;
            max-width: 100%;
        }}

        /* CONTAINER CHÍNH */
        #book-container {{
            position: relative;
            width: 100%;
            /* [FIX 1] Dùng height lớn hơn để đảm bảo hiển thị hết trên màn hình dài */
            height: 85vh; 
            background-color: #fdf6e3;
            color: #2c2c2c;
            border-radius: 12px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
            display: flex;
            flex-direction: column;
            overflow: hidden; 
            margin-bottom: 20px;
        }}

        /* HEADER (Số trang) */
        #book-header {{
            height: 35px;
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 20px;
            font-size: 13px;
            color: #8a7f70;
            border-bottom: 1px solid rgba(0,0,0,0.05);
            background: #f7efd2;
        }}

        /* NỘI DUNG */
        #book-content {{
            flex: 1; /* Tự động chiếm hết khoảng trống còn lại */
            padding: 20px 20px; /* [FIX 2] Giảm padding để chữ có nhiều chỗ hơn */
            
            font-family: 'Merriweather', 'Times New Roman', serif;
            font-size: 19px; /* [FIX 3] Giảm 1px để hiển thị nhiều chữ hơn */
            line-height: 1.6; /* Giãn dòng chuẩn sách */
            text-align: justify;
            
            /* [FIX 4] Cho phép cuộn DỰ PHÒNG nhưng ẩn thanh cuộn */
            overflow-y: scroll;
            scrollbar-width: none; /* Firefox */
            -ms-overflow-style: none;  /* IE/Edge */
        }}
        #book-content::-webkit-scrollbar {{ display: none; }} /* Chrome */

        #book-content p {{ margin-bottom: 1.2em; text-indent: 1.5em; }}

        /* CÁC NÚT BẤM ẢO (TOUCH ZONES) */
        .touch-zone {{
            position: absolute;
            top: 40px; 
            bottom: 0;
            z-index: 100;
            cursor: pointer;
            /* background: rgba(0,0,255,0.1); Debug: Bật lên để xem vùng bấm */
        }}
        #zone-left {{ left: 0; width: 35%; }}
        #zone-right {{ right: 0; width: 65%; }}
        
        /* Feedback khi chạm */
        .touch-zone:active {{ background-color: rgba(0,0,0,0.03); }}

        /* Màn hình kết thúc */
        #end-msg {{
            display: none;
            height: 100%;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px;
            text-align: center;
            color: #555;
            animation: fadeIn 0.3s;
        }}
        @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        
        #end-msg h2 {{ color: #d35400; margin-bottom: 10px; }}
        #end-msg .icon {{ font-size: 50px; margin-bottom: 20px; }}

    </style>

    <div id="book-container">
        <div id="book-header">
            Trang <span id="pg-curr" style="margin: 0 4px; font-weight: bold;">1</span> / <span id="pg-total">1</span>
        </div>
        
        <div id="book-content">Loading...</div>
        
        <div id="end-msg">
            <div class="icon">📖✨</div>
            <h2>Hết chương!</h2>
            <p>Vuốt xuống dưới để sang chương tiếp theo 👇</p>
        </div>

        <div id="zone-left" class="touch-zone" onclick="prevPage()"></div>
        <div id="zone-right" class="touch-zone" onclick="nextPage()"></div>
    </div>

    <script>
        const pages = {pages_json};
        let curIdx = 0;
        const total = pages.length;
        
        const elContent = document.getElementById('book-content');
        const elCurr = document.getElementById('pg-curr');
        const elTotal = document.getElementById('pg-total');
        const elEnd = document.getElementById('end-msg');

        elTotal.innerText = total;

        function render() {{
            // Logic hiển thị trang
            if (curIdx >= total) {{
                elContent.style.display = 'none';
                elEnd.style.display = 'flex';
                elCurr.innerText = "End";
                return;
            }}
            
            elContent.style.display = 'block';
            elEnd.style.display = 'none';
            elContent.innerHTML = pages[curIdx];
            elCurr.innerText = curIdx + 1;
            elContent.scrollTop = 0; // Luôn cuộn lên đầu khi qua trang
        }}

        function nextPage() {{
            if (curIdx < total) {{
                curIdx++;
                render();
            }}
        }}

        function prevPage() {{
            if (curIdx > 0) {{
                curIdx--;
                render();
            }}
        }}

        render();
    </script>
    """
    # [FIX 5] Tăng chiều cao Iframe lên 850 để không bị cắt chân trang trên mobile
    st.components.v1.html(html_code, height=850) 

# ==============================================================================
# 5. SIDEBAR
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
    
    # CHỌN CHẾ ĐỘ ĐỌC
    if not is_editor_mode:
        reading_mode = st.radio("Chế độ đọc:", ["📖 Lật trang (Mobile)", "📜 Cuộn dọc (Web)"], index=0)
    
    col_i, col_b = st.columns([3, 1])
    with col_i: input_idx = st.number_input("Chương số", 1, len(list_indexes), current_chap_idx, label_visibility="collapsed")
    with col_b: 
        if st.button("Go"): change_chap(input_idx); st.rerun()
            
    st.selectbox("Danh sách:", list_indexes, index=list_indexes.index(current_chap_idx), 
                 format_func=lambda x: f"Chương {x}: {chap_idx_to_title.get(x, '')[:20]}...",
                 key="sb_chap_select", on_change=lambda: change_chap(st.session_state.sb_chap_select))

# ==============================================================================
# 6. MAIN UI
# ==============================================================================
cursor.execute("SELECT title, content, content_edit FROM chapters WHERE id = %s", (real_chap_id,))
data = cursor.fetchone()

if data:
    title, raw, edited_db = data
    final_text_raw = edited_db if (edited_db and len(edited_db) > 50) else raw
    final_text = clean_content(final_text_raw)

    if not is_editor_mode:
        # Tiêu đề
        st.markdown(f"<h4 style='text-align: center; color: #888; margin-top: -20px; margin-bottom: 5px;'>{title}</h4>", unsafe_allow_html=True)

        # MODE 1: LẬT TRANG MOBILE
        if "Lật trang" in reading_mode:
            # 1. Cắt text (160 từ/trang - Chuẩn mobile)
            pages_json = paginate_text_to_json(final_text, words_per_page=160)
            
            # 2. Render sách
            render_instant_reader_mobile(pages_json)

            # 3. Nút chuyển chương (Bên dưới)
            st.markdown("---")
            c_prev, c_next = st.columns(2)
            if c_prev.button("⬅️ Chương Trước", disabled=current_chap_idx<=1, use_container_width=True):
                change_chap(current_chap_idx - 1); st.rerun()
                
            if c_next.button("CHƯƠNG SAU ⏩", type="primary", disabled=current_chap_idx>=len(list_indexes), use_container_width=True):
                change_chap(current_chap_idx + 1); st.rerun()

        # MODE 2: CUỘN DỌC (GIỮ NGUYÊN)
        else:
            st.markdown("""<style>.paper-scroll {background-color: #fdf6e3; color: #2c2c2c; padding: 30px; border-radius: 8px; font-family: 'Merriweather', serif; font-size: 19px; line-height: 1.6; text-align: justify;}</style>""", unsafe_allow_html=True)

            paragraphs = final_text.replace('\\n', '\n').split('\n')
            full_html = "".join([f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()])
            
            st.markdown(f"""<div class="paper-scroll">{full_html}</div>""", unsafe_allow_html=True)
            
            st.write("")
            c4, c5 = st.columns(2)
            if c4.button("⬅️ Chương Trước", disabled=current_chap_idx<=1, use_container_width=True): 
                change_chap(current_chap_idx - 1); st.rerun()
            if c5.button("Chương Sau ➡️", disabled=current_chap_idx>=len(list_indexes), use_container_width=True): 
                change_chap(current_chap_idx + 1); st.rerun()

    else:
        # BIÊN TẬP
        st.title(f"🛠️ Sửa: {title}")
        cL, cR = st.columns(2)
        with cL: st.text_area("Gốc", value=clean_content(raw), height=600, disabled=True)
        with cR:
            with st.form("edit"):
                new = st.text_area("Nội dung", value=final_text, height=520)
                if st.form_submit_button("💾 LƯU", type="primary", use_container_width=True): 
                    save_chapter(real_chap_id, new); st.rerun()
            if st.button("🤖 AI Rewrite", use_container_width=True):
                res = ai_rewrite(clean_content(raw))
                if "Lỗi" not in res: save_chapter(real_chap_id, res); st.rerun()
                else: st.error(res)
else:
    st.error("Lỗi dữ liệu chương!")