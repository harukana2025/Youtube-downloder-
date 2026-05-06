import os
import tempfile
import threading
import shutil
import re
import time
import subprocess
from flask import Flask, request, jsonify, render_template_string, Response
import yt_dlp

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

TEMP_BASE = os.path.join(tempfile.gettempdir(), 'youtube_dl_temp')
os.makedirs(TEMP_BASE, exist_ok=True)

# クッキーファイルの設定
COOKIE_FILE = os.path.join(os.path.dirname(__file__), 'cookies.txt')

def get_ffmpeg_path():
    winget_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WinGet', 'Links', 'ffmpeg.exe')
    if os.path.exists(winget_path):
        return winget_path
    for p in ['C:\\ffmpeg\\bin\\ffmpeg.exe', 'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe']:
        if os.path.exists(p):
            return p
    for p in os.environ.get('PATH', '').split(';'):
        ffpath = os.path.join(p, 'ffmpeg.exe')
        if os.path.exists(ffpath):
            return ffpath
    return None

FFMPEG_PATH = get_ffmpeg_path()
if FFMPEG_PATH:
    print(f"✅ ffmpeg: {FFMPEG_PATH}")

def get_ydl_opts(extra_opts=None):
    opts = {
        'quiet': True,
        'no_warnings': False,
        'retries': 30,
        'sleep_interval': 3,
        'max_sleep_interval': 8,
        'extractor_args': {
            'youtube': {
                'player_client': ['android'],
            }
        },
    }
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
        print(f"🍪 クッキーを使用: {COOKIE_FILE}")
    if extra_opts:
        opts.update(extra_opts)
    return opts

# HTMLテンプレート
NORMAL_HTML = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube DL</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:Segoe UI,system-ui;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);padding:20px;min-height:100vh}
        .container{max-width:1200px;margin:0 auto;background:rgba(255,255,255,0.08);backdrop-filter:blur(15px);border-radius:32px;padding:30px;border:1px solid rgba(255,255,255,0.2)}
        .row{display:flex;gap:30px;flex-wrap:wrap}
        .left{flex:1.2;min-width:280px}
        .right{flex:0.8;min-width:240px;background:rgba(0,0,0,0.3);border-radius:28px;padding:20px}
        video{width:100%;background:#000;border-radius:20px;margin-top:15px}
        input,select,button{width:100%;padding:12px;margin:10px 0;border-radius:40px;border:none;font-size:16px}
        input{background:rgba(255,255,255,0.95)}
        button{background:linear-gradient(135deg,#667eea,#764ba2);color:white;font-weight:bold;cursor:pointer;transition:transform 0.2s}
        button:hover{transform:scale(1.02)}
        .save-btn{background:#28a745}
        .info{color:rgba(255,255,255,0.8);font-size:0.85rem;margin-top:8px}
        .progress{display:none;margin-top:15px}
        .bar{height:6px;background:rgba(255,255,255,0.2);border-radius:3px;overflow:hidden}
        .fill{width:0%;height:100%;background:#28a745;transition:width 0.3s}
        h3{color:white;margin-bottom:15px}
    </style>
</head>
<body>
<div class="container">
    <div class="row">
        <div class="left">
            <input type="text" id="urlInput" placeholder="YouTube URL を入力">
            <button id="infoBtn">🔍 動画情報を取得</button>
            <video id="videoPreview" controls controlslist="nodownload"><source id="videoSource" src=""></video>
            <div id="infoText" class="info"></div>
        </div>
        <div class="right">
            <h3>💾 ダウンロード設定</h3>
            <select id="qualitySelect"></select>
            <div id="progressArea" class="progress"><div class="bar"><div class="fill" id="progressFill"></div></div><div id="progressMsg" class="info"></div></div>
            <div id="saveContainer" style="display:none"><button id="saveBtn" class="save-btn">💾 保存する</button><div id="saveMsg" class="info"></div></div>
        </div>
    </div>
</div>
<script>
let formats=[],selectedItag=null,currentUrl='',videoTitle='';
document.getElementById('infoBtn').onclick=async function(){
    const url=document.getElementById('urlInput').value.trim();
    if(!url){alert('URLを入力');return;}
    currentUrl=url;
    const btn=this;
    btn.disabled=true;
    btn.textContent='取得中...';
    try{
        const res=await fetch('/video_info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
        const data=await res.json();
        if(data.success){
            if(data.is_live){window.location.href='/live/'+encodeURIComponent(url);return;}
            videoTitle=data.title;
            formats=data.formats;
            const qs=document.getElementById('qualitySelect');
            qs.innerHTML='';
            for(let f of formats){
                const opt=document.createElement('option');
                opt.value=f.itag;
                let label = f.height+'p';
                if(f.fps && f.fps > 30) label += f.fps+'fps';
                if(f.has_audio) label += ' ✓音声付き';
                opt.textContent=label;
                qs.appendChild(opt);
            }
            let def=formats.find(f=>f.height===720)||formats.find(f=>f.height===360)||formats[0];
            if(def){selectedItag=def.itag;qs.value=selectedItag;if(def.preview_url){document.getElementById('videoSource').src=def.preview_url;document.getElementById('videoPreview').load();}}
            document.getElementById('infoText').innerHTML='📹 '+data.title+'<br>👁️ '+data.view_count+'<br>⏱️ '+data.duration;
            document.getElementById('saveContainer').style.display='block';
            document.getElementById('progressArea').style.display='none';
        }else alert('取得失敗:'+data.error);
    }catch(e){alert('通信エラー');}
    finally{btn.disabled=false;btn.textContent='🔍 動画情報を取得';}
};
document.getElementById('qualitySelect').onchange=function(){
    const itag=parseInt(this.value);
    const fmt=formats.find(f=>f.itag===itag);
    if(fmt){selectedItag=itag;if(fmt.preview_url){document.getElementById('videoSource').src=fmt.preview_url;document.getElementById('videoPreview').load();}}
};
document.getElementById('saveBtn').onclick=async function(){
    if(!selectedItag||!currentUrl){alert('先に情報取得してください');return;}
    const btn=this;
    btn.disabled=true;
    const pa=document.getElementById('progressArea'),pf=document.getElementById('progressFill'),pm=document.getElementById('progressMsg');
    pa.style.display='block';pf.style.width='0%';pm.innerText='準備中...';
    try{
        const res=await fetch('/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:currentUrl,itag:selectedItag,title:videoTitle})});
        if(!res.ok)throw new Error('サーバーエラー');
        const blob=await res.blob();
        const cd=res.headers.get('Content-Disposition');
        let filename='video.mp4';
        if(cd){const m=cd.match(/filename[*]=?.*?''([^"]+)/);if(m&&m[1])filename=decodeURIComponent(m[1]);}
        const a=document.createElement('a');
        const url=URL.createObjectURL(blob);
        a.href=url;a.download=filename;document.body.appendChild(a);a.click();document.body.removeChild(a);
        URL.revokeObjectURL(url);
        pf.style.width='100%';pm.innerText='✅完了！';
        setTimeout(()=>{pa.style.display='none';btn.disabled=false;},2000);
    }catch(e){alert('失敗:'+e.message);pa.style.display='none';btn.disabled=false;}
};
</script>
</body>
</html>
'''

LIVE_HTML = NORMAL_HTML

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
    return NORMAL_HTML

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
                has_video = f.get('vcodec') != 'none'
                has_audio = f.get('acodec') != 'none'
                height = f.get('height')
                format_id = str(f['format_id'])
                
                # DRCフォーマットを除外し、動画があるフォーマットのみ
                if has_video and height and '-drc' not in format_id:
                    formats.append({
                        'itag': format_id,
                        'height': height,
                        'fps': f.get('fps'),
                        'has_audio': has_audio,
                        'preview_url': f.get('url', '')
                    })
            # 画質の高い順、音声付き優先
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
    
    # 重要: 動画+音声を確実に結合する指定
    # itagが動画のみの場合でもbestaudioを自動追加
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
        
        file_size = os.path.getsize(actual_file)
        if file_size < 100000:
            raise Exception(f'ファイルサイズが異常に小さいです: {file_size} バイト')
        
        with open(actual_file, 'rb') as f:
            file_data = f.read()
        
        from urllib.parse import quote
        encoded_filename = quote(os.path.basename(actual_file))
        response = Response(file_data, mimetype='video/mp4')
        response.headers['Content-Disposition'] = f"attachment; filename=\"{encoded_filename}\"; filename*=UTF-8''{encoded_filename}"
        response.headers['Content-Length'] = str(len(file_data))
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
    print("\\n" + "="*50)
    print("🎬 YouTube DL - 修正版")
    print("📍 http://localhost:5000")
    print("="*50 + "\\n")
    app.run(host='0.0.0.0', port=5000, debug=True)


