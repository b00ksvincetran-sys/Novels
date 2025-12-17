import streamlit as st
import psycopg2
import os
import json
import google.generativeai as genai
import math

# ==============================================================================
# 1. CẤU HÌNH & KẾT NỐI
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
if not SUPABASE_URL: st.error("Thiếu URL DB"); st.stop()

@st.cache_resource
def get_connection():
    return psycopg2.connect(SUPABASE_URL)

conn = get_connection()
if conn.closed != 0: st.cache_resource.clear(); conn = get_connection()
cursor = conn.cursor()

# ==============================================================================
# 2. LOGIC PYTHON (BACKEND)
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

def paginate_text_to_json(text, words_per_page=300):
    """
    Cắt text thành list các đoạn HTML.
    Giảm số từ xuống 300 để vừa khít màn hình điện thoại mà không cần cuộn nhiều.
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
        
        if current_word_count + words_in_p > words_per_page and current_word_count > 0:
            pages.append(current_page)
            current_page = f"<p>{p}</p>"
            current_word_count = words_in_p
        else:
            current_page += f"<p>{p}</p>"
            current_word_count += words_in_p
            
    if current_page: pages.append(current_page)
    
    # Trả về chuỗi JSON để JS đọc được
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

st.set_page_config(page_title=page_title, page_icon="📖", layout="centered", initial_sidebar_state="collapsed") # collapsed sidebar cho rộng

# ==============================================================================
# 4. CSS & JS SIÊU TỐC (CLIENT-SIDE RENDERING)
# ==============================================================================
def render_instant_reader(pages_json, chap_title):
    # CSS: Khóa cứng màn hình, ẩn thanh cuộn, tạo giao diện App
    # JS: Xử lý logic Next/Prev ngay tại trình duyệt
    
    reader_html = f"""
    <style>
        /* 1. Khóa cứng body của Streamlit để không cuộn lung tung */
        iframe {{display: block;}} /* Fix lỗi iframe streamlit */
        
        /* 2. Overlay che toàn màn hình */
        #reader-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background-color: #fdf6e3; /* Màu giấy */
            color: #2c2c2c;
            z-index: 999999; /* Đè lên tất cả */
            display: flex;
            flex-direction: column;
            overflow: hidden; /* Cấm cuộn cấp container */
        }}

        /* 3. Header Cố định */
        #reader-header {{
            height: 50px;
            background-color: #eaddcf;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-family: sans-serif;
            font-size: 14px;
            color: #5b4636;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            flex-shrink: 0;
        }}

        /* 4. Vùng nội dung (Cho phép cuộn nội bộ nếu chữ quá dài) */
        #reader-content {{
            flex: 1;
            padding: 20px 25px;
            font-family: 'Merriweather', 'Times New Roman', serif;
            font-size: 20px;
            line-height: 1.8;
            text-align: justify;
            overflow-y: auto; /* Chỉ cuộn phần chữ nếu cần */
            scroll-behavior: smooth;
        }}
        
        #reader-content p {{
            margin-bottom: 1.2em;
            text-indent: 1.5em;
        }}

        /* 5. Vùng bấm cảm ứng (Invisible Touch Zones) */
        #touch-left {{
            position: fixed; top: 50px; left: 0; width: 30%; bottom: 40px;
            z-index: 1000; cursor: w-resize;
            /* background: rgba(255,0,0,0.1); Debug only */
        }}
        #touch-right {{
            position: fixed; top: 50px; right: 0; width: 70%; bottom: 40px;
            z-index: 1000; cursor: e-resize;
            /* background: rgba(0,255,0,0.1); Debug only */
        }}

        /* 6. Footer thông tin trang */
        #reader-footer {{
            height: 40px;
            background-color: #fdf6e3;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: #888;
            border-top: 1px solid rgba(0,0,0,0.05);
            flex-shrink: 0;
        }}
        
        /* 7. Màn hình kết thúc chương */
        #end-screen {{
            display: none;
            flex: 1;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 20px;
        }}
        .next-chap-btn {{
            background: #4CAF50;
            color: white;
            padding: 15px 30px;
            border-radius: 30px;
            font-size: 18px;
            font-weight: bold;
            border: none;
            box-shadow: 0 4px 10px rgba(0,0,0,0.2);
            cursor: pointer;
            margin-top: 20px;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(1); }}
            50% {{ transform: scale(1.05); }}
            100% {{ transform: scale(1); }}
        }}

        /* Ẩn UI Streamlit gốc */
        header, footer, .stDeployButton {{display: none !important;}}
    </style>

    <div id="reader-overlay">
        <div id="reader-header">{chap_title}</div>
        
        <div id="reader-content">
            </div>

        <div id="end-screen">
            <h2>🎉 Đã hết chương!</h2>
            <p>Bấm nút bên dưới để tải chương tiếp theo.</p>
            <div id="close-overlay-btn" class="next-chap-btn">SANG CHƯƠNG MỚI ⏩</div>
        </div>

        <div id="reader-footer">Trang <span id="pg-num">1</span> / <span id="pg-total">1</span></div>
        
        <div id="touch-left" onclick="prevPage()"></div>
        <div id="touch-right" onclick="nextPage()"></div>
    </div>

    <script>
        // 1. Dữ liệu từ Python
        const pages = {pages_json};
        let currPage = 0;
        const totalPages = pages.length;

        const contentDiv = document.getElementById('reader-content');
        const pgNum = document.getElementById('pg-num');
        const pgTotal = document.getElementById('pg-total');
        const endScreen = document.getElementById('end-screen');
        const touchLeft = document.getElementById('touch-left');
        const touchRight = document.getElementById('touch-right');

        // Init
        pgTotal.innerText = totalPages;
        renderPage(0);

        function renderPage(idx) {{
            // Nếu vượt quá trang cuối -> Hiện màn hình End
            if (idx >= totalPages) {{
                contentDiv.style.display = 'none';
                endScreen.style.display = 'flex';
                pgNum.innerText = "Hết";
                return;
            }}
            
            // Nếu lùi quá trang đầu -> Không làm gì (hoặc có thể báo)
            if (idx < 0) return;

            // Render bình thường
            contentDiv.style.display = 'block';
            endScreen.style.display = 'none';
            contentDiv.innerHTML = pages[idx];
            currPage = idx;
            pgNum.innerText = currPage + 1;
            
            // Tự động cuộn lên đầu (nếu trang trước đang cuộn dở)
            contentDiv.scrollTop = 0;
        }}

        function nextPage() {{
            if (currPage < totalPages) {{
                renderPage(currPage + 1);
            }}
        }}

        function prevPage() {{
            if (currPage > 0) {{
                renderPage(currPage - 1);
            }}
        }}
        
        // Logic bấm nút "Sang Chương Mới"
        document.getElementById('close-overlay-btn').onclick = function() {{
            // 1. Ẩn cái Overlay này đi để lộ nút Streamlit bên dưới
            document.getElementById('reader-overlay').style.display = 'none';
            // 2. (Mẹo) Vì không bấm trực tiếp nút Streamlit từ JS được,
            // ta chỉ cần ẩn overlay, người dùng sẽ thấy nút Streamlit to đùng bên dưới.
        }};
    </script>
    """
    st.components.v1.html(reader_html, height=800, scrolling=False)


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
    
    # Quick Jump
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
        # === CHẾ ĐỘ ĐỌC SIÊU TỐC (INSTANT READER) ===
        
        # 1. Cắt text thành JSON
        pages_json = paginate_text_to_json(final_text, words_per_page=300)
        
        # 2. Render Overlay (Giao diện chính)
        # Hàm này sẽ tạo ra một lớp phủ toàn màn hình.
        # Javascript trong đó sẽ xử lý việc lật trang (0 latency).
        render_instant_reader(pages_json, title)
        
        # 3. Nút Streamlit "Thực" nằm bên dưới Overlay
        # Khi User đọc hết chương -> Overlay tắt -> User thấy nút này -> Bấm để load chương mới
        st.write("") 
        st.write("")
        st.write("") # Spacer để đẩy nút xuống dưới
        
        # Giao diện chờ bên dưới (Chỉ thấy khi overlay tắt)
        st.markdown(f"<h3 style='text-align: center'>Bạn đã đọc xong {title}</h3>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        if c1.button("⬅️ Đọc lại chương này", use_container_width=True):
            st.rerun() # Load lại overlay
            
        if c2.button("CHƯƠNG TIẾP THEO ➡️", type="primary", use_container_width=True, disabled=current_chap_idx>=len(list_indexes)):
            change_chap(current_chap_idx + 1)
            st.rerun()

    else:
        # === CHẾ ĐỘ BIÊN TẬP ===
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