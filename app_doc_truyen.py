import streamlit as st
import psycopg2
import os
import json
import google.generativeai as genai

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
if not SUPABASE_URL: st.error("Thiếu Database URL!"); st.stop()

@st.cache_resource
def get_connection():
    return psycopg2.connect(SUPABASE_URL)

conn = get_connection()
if conn.closed != 0: st.cache_resource.clear(); conn = get_connection()
cursor = conn.cursor()

# ==============================================================================
# 2. HÀM LOGIC CỐT LÕI (SYNC STATE)
# ==============================================================================
def update_url(novel_slug, chap_index):
    st.query_params["truyen"] = novel_slug
    st.query_params["chuong"] = str(chap_index)

def change_chap(new_idx):
    """Đổi chương -> Reset trang con -> Update URL"""
    st.session_state['current_chap_idx'] = new_idx
    st.session_state['sub_page'] = 0 
    try:
        slug = novel_id_to_slug[st.session_state['current_novel_id']]
        update_url(slug, new_idx)
    except: pass

def change_novel():
    """Đổi truyện -> Reset về chương 1 -> Update URL"""
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

def paginate_text_to_json(text, words_per_page=150):
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
            pages.append(current_page); current_page = f"<p>{p}</p>"; current_word_count = words_in_p
        else:
            current_page += f"<p>{p}</p>"; current_word_count += words_in_p
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
# 3. LOAD DATA (SINGLE SOURCE OF TRUTH)
# ==============================================================================
# A. Load Novels
try:
    cursor.execute("SELECT id, title, slug FROM novels ORDER BY title ASC")
    all_novels = cursor.fetchall()
except psycopg2.Error: st.cache_resource.clear(); st.rerun()

if not all_novels: st.warning("Chưa có truyện!"); st.stop()

novel_id_to_slug = {n[0]: n[2] for n in all_novels}
novel_slug_to_id = {n[2]: n[0] for n in all_novels}
novel_id_to_title = {n[0]: n[1] for n in all_novels}
novel_slugs_list = list(novel_slug_to_id.keys())

# B. Determine Current Novel (Priority: URL > Session > Default)
params = st.query_params
url_slug = params.get("truyen", None)
current_novel_id = novel_slug_to_id.get(url_slug, all_novels[0][0])

# Cập nhật Session State cho Novel
if 'current_novel_id' not in st.session_state:
    st.session_state['current_novel_id'] = current_novel_id
else:
    # Nếu URL thay đổi, ưu tiên URL
    if url_slug and url_slug in novel_slug_to_id:
        st.session_state['current_novel_id'] = novel_slug_to_id[url_slug]

# C. Load Chapters of Current Novel
curr_nov_id = st.session_state['current_novel_id']
cursor.execute("SELECT id, chapter_index, title FROM chapters WHERE novel_id = %s ORDER BY chapter_index ASC", (curr_nov_id,))
all_chapters = cursor.fetchall()

if not all_chapters: st.warning("Truyện rỗng."); st.stop()

chap_idx_to_id = {c[1]: c[0] for c in all_chapters}
chap_idx_to_title = {c[1]: c[2] for c in all_chapters}
list_indexes = list(chap_idx_to_id.keys())

# D. Determine Current Chapter
url_chap = params.get("chuong", None)
if url_chap and url_chap.isdigit() and int(url_chap) in list_indexes:
    initial_chap = int(url_chap)
elif 'current_chap_idx' in st.session_state:
    initial_chap = st.session_state['current_chap_idx']
else:
    initial_chap = list_indexes[0]

# Validate
if initial_chap not in list_indexes: initial_chap = list_indexes[0]
st.session_state['current_chap_idx'] = initial_chap 

# E. Metadata
real_chap_id = chap_idx_to_id[initial_chap]
page_title = f"Chương {initial_chap} | {novel_id_to_title[curr_nov_id]}"
st.set_page_config(page_title=page_title, page_icon="📖", layout="centered", initial_sidebar_state="collapsed")

# ==============================================================================
# 4. TRÌNH ĐỌC SÁCH MOBILE (V3 FIXED)
# ==============================================================================
def render_instant_reader_mobile(pages_json, font_size_px):
    html_code = f"""
    <style>
        header {{visibility: hidden;}} footer {{visibility: hidden;}}
        .block-container {{padding: 0 !important; margin: 0 !important; max-width: 100%;}}
        
        #book-container {{
            position: relative; width: 100%; height: 85vh;
            background-color: #fdf6e3; color: #2c2c2c;
            border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.1);
            display: flex; flex-direction: column; overflow: hidden; margin-bottom: 20px;
        }}
        #book-header {{
            height: 35px; flex-shrink: 0; display: flex; align-items: center; justify-content: flex-end;
            padding-right: 20px; font-size: 13px; color: #8a7f70;
            border-bottom: 1px solid rgba(0,0,0,0.05); background: #f7efd2;
        }}
        #book-content {{
            flex: 1; padding: 20px; font-family: 'Merriweather', serif;
            font-size: {font_size_px}px; line-height: 1.6; text-align: justify;
            overflow-y: auto; scrollbar-width: none; -ms-overflow-style: none;
        }}
        #book-content::-webkit-scrollbar {{ display: none; }}
        #book-content p {{ margin-bottom: 1.2em; text-indent: 1.5em; }}
        
        .touch-zone {{ position: absolute; top: 40px; bottom: 0; z-index: 100; cursor: pointer; }}
        #zone-left {{ left: 0; width: 35%; }}
        #zone-right {{ right: 0; width: 65%; }}
        .touch-zone:active {{ background-color: rgba(0,0,0,0.03); }}
        
        #end-msg {{
            display: none; height: 100%; flex-direction: column;
            align-items: center; justify-content: center; padding: 20px; text-align: center; color: #555;
        }}
        #end-msg h2 {{ color: #d35400; }}
    </style>

    <div id="book-container">
        <div id="book-header">Trang <span id="pg-curr" style="margin:0 4px;font-weight:bold;">1</span>/<span id="pg-total">1</span></div>
        <div id="book-content">Loading...</div>
        <div id="end-msg"><div style="font-size:50px;">📖✨</div><h2>Hết chương!</h2><p>Vuốt xuống để sang chương mới 👇</p></div>
        <div id="zone-left" class="touch-zone" onclick="prevPage()"></div>
        <div id="zone-right" class="touch-zone" onclick="nextPage()"></div>
    </div>
    <script>
        const pages = {pages_json};
        let curIdx = 0; const total = pages.length;
        const elC = document.getElementById('book-content'), elCur = document.getElementById('pg-curr'), elTot = document.getElementById('pg-total'), elE = document.getElementById('end-msg');
        elTot.innerText = total;
        function render() {{
            if (curIdx >= total) {{ elC.style.display='none'; elE.style.display='flex'; elCur.innerText='End'; return; }}
            elC.style.display='block'; elE.style.display='none';
            elC.innerHTML = pages[curIdx]; elCur.innerText = curIdx + 1; elC.scrollTop = 0;
        }}
        function nextPage() {{ if(curIdx<total) {{ curIdx++; render(); }} }}
        function prevPage() {{ if(curIdx>0) {{ curIdx--; render(); }} }}
        render();
    </script>
    """
    st.components.v1.html(html_code, height=850)

# ==============================================================================
# 5. SIDEBAR (MENU) - FULL SYNC
# ==============================================================================
with st.sidebar:
    st.header("📚 Tủ Sách")
    
    # [SYNC FIX 1] Đồng bộ Dropdown Truyện
    # Tìm index của truyện hiện tại trong danh sách options
    curr_novel_slug = novel_id_to_slug[st.session_state['current_novel_id']]
    try:
        novel_list_idx = novel_slugs_list.index(curr_novel_slug)
    except ValueError: 
        novel_list_idx = 0
        
    st.selectbox(
        "Truyện:", 
        options=novel_slugs_list, 
        index=novel_list_idx,  # <-- Tự động nhảy về đúng truyện
        format_func=lambda x: novel_id_to_title[novel_slug_to_id[x]], 
        key="sb_novel_select", 
        on_change=change_novel
    )

    st.divider()
    st.header("⚙️ Cài Đặt")
    is_editor = st.toggle("🛠️ Biên Tập", value=False)
    
    if not is_editor:
        read_mode = st.radio("Chế độ:", ["📖 Lật trang (Mobile)", "📜 Cuộn dọc (Web)"], index=0)
        font_sz = st.slider("Cỡ chữ:", 14, 26, 19)

    st.write("---")
    st.write("📍 **Điều hướng chương:**")
    
    # [SYNC FIX 2] Đồng bộ Dropdown Chương
    try:
        chap_list_idx = list_indexes.index(st.session_state['current_chap_idx'])
    except ValueError: 
        chap_list_idx = 0

    col_i, col_b = st.columns([3, 1])
    with col_i:
        # Ô nhập số cũng phải lấy giá trị từ session_state
        input_val = st.number_input("Nhập số:", value=st.session_state['current_chap_idx'], label_visibility="collapsed")
    with col_b:
        if st.button("Go"):
            change_chap(input_val)
            st.rerun()

    st.selectbox(
        "Chọn chương:", 
        options=list_indexes, 
        index=chap_list_idx, # <-- Tự động nhảy về đúng chương
        format_func=lambda x: f"Chương {x}: {chap_idx_to_title.get(x, '')[:20]}...",
        key="sb_chap_select", 
        on_change=lambda: change_chap(st.session_state.sb_chap_select)
    )

# ==============================================================================
# 6. MAIN UI
# ==============================================================================
cursor.execute("SELECT title, content, content_edit FROM chapters WHERE id = %s", (real_chap_id,))
data = cursor.fetchone()

if data:
    title, raw, edited_db = data
    final_text = clean_content(edited_db if (edited_db and len(edited_db) > 50) else raw)

    if not is_editor:
        st.markdown(f"<h4 style='text-align: center; color: #888; margin-top: -20px; margin-bottom: 5px;'>{title}</h4>", unsafe_allow_html=True)
        
        # Tìm vị trí hiện tại trong danh sách
        curr_pos = list_indexes.index(st.session_state['current_chap_idx'])
        prev_disabled = (curr_pos == 0)
        next_disabled = (curr_pos == len(list_indexes) - 1)

        # MODE 1: MOBILE FLIP
        if "Lật trang" in read_mode:
            pages_json = paginate_text_to_json(final_text, words_per_page=150)
            render_instant_reader_mobile(pages_json, font_sz)

            st.markdown("---")
            c_prev, c_next = st.columns(2)
            
            if c_prev.button("⬅️ Chương Trước", disabled=prev_disabled, use_container_width=True):
                change_chap(list_indexes[curr_pos - 1]); st.rerun()
                
            if c_next.button("CHƯƠNG SAU ⏩", type="primary", disabled=next_disabled, use_container_width=True):
                change_chap(list_indexes[curr_pos + 1]); st.rerun()

        # MODE 2: WEB SCROLL
        else:
            st.markdown(f"""<style>.paper-scroll {{ background:#fdf6e3;color:#2c2c2c;padding:30px;border-radius:8px;font-family:'Merriweather',serif;font-size:{font_sz}px;line-height:1.6;text-align:justify; }}</style>""", unsafe_allow_html=True)
            paragraphs = final_text.replace('\\n', '\n').split('\n')
            full_html = "".join([f"<p>{p.strip()}</p>" for p in paragraphs if p.strip()])
            st.markdown(f"""<div class="paper-scroll">{full_html}</div>""", unsafe_allow_html=True)
            
            st.write("")
            c4, c5 = st.columns(2)
            if c4.button("⬅️ Trước", disabled=prev_disabled, use_container_width=True): 
                change_chap(list_indexes[curr_pos - 1]); st.rerun()
            if c5.button("Sau ➡️", disabled=next_disabled, use_container_width=True): 
                change_chap(list_indexes[curr_pos + 1]); st.rerun()

    else:
        # EDIT MODE
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