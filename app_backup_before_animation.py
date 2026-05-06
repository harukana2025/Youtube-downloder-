import os
import tempfile
import threading
import shutil
import re
import time
from flask import Flask, request, jsonify, render_template_string, Response
import yt_dlp

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

TEMP_BASE = os.path.join(tempfile.gettempdir(), 'youtube_dl_temp')
os.makedirs(TEMP_BASE, exist_ok=True)

COOKIE_FILE = os.path.join(os.path.dirname(__file__), 'cookies.txt')

def get_ydl_opts(extra_opts=None):
    opts = {
        'quiet': True,
        'no_warnings': False,
        'retries': 30,
    }
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
        print(f"🍪 クッキーを使用: {COOKIE_FILE}")
    if extra_opts:
        opts.update(extra_opts)
    return opts

HTML = '''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>YouTube DL</title>
<style>
body{font-family:system-ui;background:#0f0c29;padding:20px;color:#eee}
.container{max-width:900px;margin:0 auto;background:rgba(255,255,255,0.1);padding:30px;border-radius:20px}
input,select,button{width:100%;padding:12px;margin:10px 0;border-radius:8px;border:none;font-size:16px}
button{background:#e94560;color:white;cursor:pointer}
.save-btn{background:#0f3460}
video{width:100%;background:#000;border-radius:8px;margin-top:15px}
</style>
</head>
<body>
<div class="container">
    <h2>📥 YouTube Downloader</h2>
    <input type="text" id="url" placeholder="YouTube URL を入力">
    <button id="info">🔍 情報取得</button>
    <div id="videoArea" style="display:none">
        <video id="preview" controls></video>
        <select id="quality"></select>
        <button id="download" class="save-btn">💾 ダウンロード</button>
    </div>
    <div id="infoText"></div>
    <div id="progressArea" style="display:none"><progress id="progressBar" value="0" max="100"></progress><div id="progressMsg"></div></div>
</div>
<script>
let formats=[],selectedItag=null,currentUrl='',videoTitle='';
document.getElementById('info').onclick=async()=>{
    const url=document.getElementById('url').value.trim();
    if(!url) return alert('URLを入力');
    currentUrl=url;
    document.getElementById('info').disabled=true;
    try{
        const res=await fetch('/video_info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
        const data=await res.json();
        if(data.success){
            videoTitle=data.title;
            formats=data.formats;
            const sel=document.getElementById('quality');
            sel.innerHTML='';
            for(let f of formats){
                const opt=document.createElement('option');
                opt.value=f.itag;
                opt.textContent=f.height+'p'+(f.fps?f.fps+'fps':'')+(f.has_audio?' ✓音声あり':'');
                sel.appendChild(opt);
            }
            if(formats.length){
                selectedItag=formats[0].itag;
                sel.value=selectedItag;
                if(formats[0].preview_url){
                    document.getElementById('preview').src=formats[0].preview_url;
                    document.getElementById('preview').load();
                }
            }
            document.getElementById('infoText').innerHTML='📹 '+data.title+'<br>👁️ '+data.view_count;
            document.getElementById('videoArea').style.display='block';
        }else alert('失敗:'+data.error);
    }catch(e){alert('通信エラー');}
    finally{document.getElementById('info').disabled=false;}
};
document.getElementById('quality').onchange=(e)=>{
    selectedItag=parseInt(e.target.value);
    const fmt=formats.find(f=>f.itag===selectedItag);
    if(fmt&&fmt.preview_url){
        document.getElementById('preview').src=fmt.preview_url;
        document.getElementById('preview').load();
    }
};
document.getElementById('download').onclick=async()=>{
    if(!selectedItag) return alert('画質を選択');
    const btn=document.getElementById('download');
    btn.disabled=true;
    const pa=document.getElementById('progressArea');
    const pb=document.getElementById('progressBar');
    const pm=document.getElementById('progressMsg');
    pa.style.display='block';
    pb.value=0;
    pm.innerText='準備中...';
    try{
        const res=await fetch('/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:currentUrl,itag:selectedItag,title:videoTitle})});
        if(!res.ok)throw new Error('サーバーエラー');
        const blob=await res.blob();
        const a=document.createElement('a');
        a.href=URL.createObjectURL(blob);
        a.download='video.mp4';
        a.click();
        URL.revokeObjectURL(a.href);
        pb.value=100;
        pm.innerText='完了！';
        setTimeout(()=>{pa.style.display='none';btn.disabled=false;},2000);
    }catch(e){alert('失敗:'+e.message);pa.style.display='none';btn.disabled=false;}
};
</script>
</body>
</html>
'''

def sanitize_filename(title):
    name = re.sub(r'[\\/*?:"<>|]', '', title)
    name = re.sub(r'[#%&{}\\[\]~!$^@+/=,;]', '_', name)
    name = re.sub(r'_+', '_', name)
    if len(name) > 100:
        name = name[:100]
    name = name.strip(' ._')
    if not name:
        name = 'video'
    return name

@app.route('/')
def index():
    return HTML

@app.route('/video_info', methods=['POST'])
def video_info():
    data = request.get_json()
    url = data['url']
    if 'youtu.be' in url:
        video_id = url.split('/')[-1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    ydl_opts = get_ydl_opts()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = []
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('height'):
                    format_id = str(f['format_id'])
                    if '-drc' not in format_id:
                        formats.append({
                            'itag': format_id,
                            'height': f['height'],
                            'fps': f.get('fps'),
                            'has_audio': f.get('acodec') != 'none',
                            'preview_url': f.get('url', '')
                        })
            formats.sort(key=lambda x: (-x['height'], -x['has_audio']))
            is_live = info.get('is_live', False) or info.get('live_status') == 'is_live'
            return jsonify({
                'success': True,
                'title': info.get('title'),
                'view_count': info.get('view_count', 0),
                'duration': info.get('duration_string'),
                'formats': formats,
                'is_live': is_live,
                'video_id': info.get('id')
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data['url']
    itag = data['itag']
    title = data.get('title', 'video')
    
    if 'youtu.be' in url:
        video_id = url.split('/')[-1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    safe_title = sanitize_filename(title)
    temp_dir = tempfile.mkdtemp(dir=TEMP_BASE)
    output_file = os.path.join(temp_dir, f'{safe_title}.mp4')
    
    ydl_opts = get_ydl_opts({
        'format': f'{itag}+bestaudio/best',
        'outtmpl': output_file,
        'merge_output_format': 'mp4',
    })
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
        
        actual_file = output_file
        if not os.path.exists(output_file):
            base = os.path.splitext(output_file)[0]
            for ext in ['.mp4', '.webm', '.mkv']:
                test_path = base + ext
                if os.path.exists(test_path):
                    actual_file = test_path
                    break
        
        if not os.path.exists(actual_file):
            raise Exception('ファイルが見つかりません')
        
        with open(actual_file, 'rb') as f:
            file_data = f.read()
        
        from urllib.parse import quote
        encoded_filename = quote(os.path.basename(actual_file))
        response = Response(file_data, mimetype='video/mp4')
        response.headers['Content-Disposition'] = f"attachment; filename=\"{encoded_filename}\"; filename*=UTF-8''{encoded_filename}"
        return response
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        def cleanup():
            time.sleep(5)
            shutil.rmtree(temp_dir, ignore_errors=True)
        threading.Thread(target=cleanup).start()

if __name__ == '__main__':
    import webbrowser
    webbrowser.open('http://localhost:5000')
    print("\n" + "="*50)
    print("🎬 YouTube DL - 修正版")
    print("📍 http://localhost:5000")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
