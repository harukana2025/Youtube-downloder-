import os
import tempfile
import threading
import shutil
import re
import time
import glob
import requests
from flask import Flask, request, jsonify, render_template_string, Response, send_file
import yt_dlp

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

TEMP_BASE = os.path.join(tempfile.gettempdir(), 'youtube_dl_temp')
os.makedirs(TEMP_BASE, exist_ok=True)

COOKIE_FILE = os.path.join(os.path.dirname(__file__), 'cookies.txt')

def get_ffmpeg_path():
    for p in [
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WinGet', 'Links', 'ffmpeg.exe'),
        'C:\\ffmpeg\\bin\\ffmpeg.exe',
        'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe'
    ]:
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
    }
    if FFMPEG_PATH:
        opts['ffmpeg_location'] = FFMPEG_PATH
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
    if extra_opts:
        opts.update(extra_opts)
    return opts

# 3機能対応HTML
HTML = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✨ YouTube ダウンローダー - 動画/音声/サムネイル ✨</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1300px; margin: 0 auto; }
        .card {
            background: rgba(255, 255, 255, 0.98);
            border-radius: 32px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 {
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            font-size: 2.5rem;
        }
        .mode-switch {
            display: flex;
            gap: 15px;
            justify-content: center;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }
        .mode-btn {
            padding: 12px 30px;
            border-radius: 50px;
            border: 2px solid #667eea;
            background: white;
            color: #667eea;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
        }
        .mode-btn.active {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border-color: transparent;
        }
        .mode-btn:hover { transform: scale(1.05); }
        .row { display: flex; gap: 30px; flex-wrap: wrap; }
        .left { flex: 1.5; min-width: 300px; }
        .right { flex: 1; min-width: 280px; }
        input, select, button {
            width: 100%;
            padding: 14px 20px;
            margin: 10px 0;
            border-radius: 50px;
            border: 2px solid #e0e0e0;
            font-size: 16px;
        }
        button {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            font-weight: bold;
            cursor: pointer;
            border: none;
            transition: all 0.3s;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(102,126,234,0.4); }
        .video-wrapper {
            background: #000;
            border-radius: 20px;
            overflow: hidden;
            margin: 20px 0;
        }
        video { width: 100%; display: block; }
        .info-panel {
            background: linear-gradient(135deg, #f5f7fa, #c3cfe2);
            border-radius: 20px;
            padding: 20px;
            margin-top: 20px;
        }
        .info-item {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 10px 0;
            padding: 5px;
        }
        .thumbnail-preview {
            margin-top: 15px;
            text-align: center;
        }
        .thumbnail-preview img {
            max-width: 100%;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .progress-area { margin-top: 20px; display: none; }
        .progress-bar {
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 15px;
            overflow: hidden;
        }
        .progress-fill {
            width: 0%;
            height: 100%;
            background: linear-gradient(90deg, #28a745, #20c997);
            border-radius: 15px;
            transition: width 0.3s;
        }
        .progress-text { text-align: center; margin-top: 10px; color: #666; font-weight: bold; }
        .loading-spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 0.8s linear infinite;
            margin-right: 10px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .quality-badge {
            display: inline-block;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            margin: 0 5px;
        }
        .thumbnail-options {
            background: #f8f9fa;
            border-radius: 15px;
            padding: 15px;
            margin-top: 15px;
        }
        .size-btns {
            display: flex;
            gap: 10px;
            margin-top: 10px;
            flex-wrap: wrap;
        }
        .size-btn {
            flex: 1;
            padding: 8px;
            margin: 0;
            background: #e0e0e0;
            color: #333;
            font-size: 14px;
        }
        .size-btn.active {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
        }
        @media (max-width: 768px) {
            .card { padding: 20px; }
            .header h1 { font-size: 1.8rem; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>✨ YouTube ダウンローダー ✨</h1>
                <p>動画 | 音声 | サムネイル をダウンロード</p>
                <div>
                    <span class="quality-badge">🎬 動画</span>
                    <span class="quality-badge">🎵 音声</span>
                    <span class="quality-badge">🖼️ サムネイル</span>
                </div>
            </div>

            <!-- 3機能モード切替 -->
            <div class="mode-switch">
                <button class="mode-btn" id="videoModeBtn">🎬 動画ダウンロード</button>
                <button class="mode-btn" id="audioModeBtn">🎵 音声ダウンロード</button>
                <button class="mode-btn" id="thumbnailModeBtn">🖼️ サムネイル</button>
            </div>

            <div class="row">
                <div class="left">
                    <input type="text" id="urlInput" placeholder="YouTube URL を入力してください">
                    <button id="infoBtn">🔍 情報取得</button>
                    
                    <div id="videoContainer" style="display:none">
                        <div class="video-wrapper">
                            <video id="videoPreview" controls><source id="videoSource" src=""></video>
                        </div>
                    </div>
                    
                    <div id="thumbnailPreview" class="thumbnail-preview" style="display:none">
                        <img id="thumbnailImg" alt="サムネイルプレビュー">
                    </div>
                    
                    <div id="infoText" class="info-panel" style="display:none"></div>
                </div>

                <div class="right">
                    <h3 id="downloadLabel" style="margin-bottom: 15px;">⚙️ ダウンロード設定</h3>
                    
                    <!-- 動画モード設定 -->
                    <div id="videoSettings">
                        <select id="qualitySelect"><option value="">画質を選択してください</option></select>
                    </div>
                    
                    <!-- 音声モード設定 -->
                    <div id="audioSettings" style="display:none">
                        <div class="thumbnail-options">
                            <label style="font-weight: bold;">🎵 音声フォーマット</label>
                            <select id="audioFormatSelect">
                                <option value="mp3">MP3 (高音質/汎用)</option>
                                <option value="m4a">M4A (Apple対応)</option>
                                <option value="opus">OPUS (高音質)</option>
                                <option value="wav">WAV (無劣化)</option>
                            </select>
                        </div>
                    </div>
                    
                    <!-- サムネイルモード設定 -->
                    <div id="thumbnailSettings" style="display:none">
                        <div class="thumbnail-options">
                            <label style="font-weight: bold;">🖼️ サムネイルサイズ</label>
                            <div class="size-btns">
                                <button class="size-btn" data-size="default">標準</button>
                                <button class="size-btn" data-size="mqdefault">中画質</button>
                                <button class="size-btn" data-size="hqdefault">高画質</button>
                                <button class="size-btn" data-size="sddefault">HD</button>
                                <button class="size-btn active" data-size="maxresdefault">最大</button>
                            </div>
                            <p style="font-size: 12px; color: #666; margin-top: 10px;">💡 最大サイズは高画質（最大4K）</p>
                        </div>
                    </div>
                    
                    <div id="progressArea" class="progress-area">
                        <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
                        <div class="progress-text" id="progressMsg">準備完了</div>
                    </div>
                    
                    <div id="saveContainer" style="display:none">
                        <button id="saveBtn">💾 ダウンロード開始</button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let formats = [], selectedItag = null, currentUrl = '', videoTitle = '', currentMode = 'video';
        let thumbnails = [], selectedThumbSize = 'maxresdefault';

        // モード切替
        document.getElementById('videoModeBtn').onclick = () => {
            currentMode = 'video';
            document.getElementById('videoModeBtn').classList.add('active');
            document.getElementById('audioModeBtn').classList.remove('active');
            document.getElementById('thumbnailModeBtn').classList.remove('active');
            document.getElementById('videoSettings').style.display = 'block';
            document.getElementById('audioSettings').style.display = 'none';
            document.getElementById('thumbnailSettings').style.display = 'none';
            document.getElementById('saveContainer').style.display = 'none';
            document.getElementById('infoText').style.display = 'none';
            document.getElementById('videoContainer').style.display = 'none';
            document.getElementById('thumbnailPreview').style.display = 'none';
            document.getElementById('downloadLabel').innerHTML = '⚙️ 動画ダウンロード設定';
        };

        document.getElementById('audioModeBtn').onclick = () => {
            currentMode = 'audio';
            document.getElementById('audioModeBtn').classList.add('active');
            document.getElementById('videoModeBtn').classList.remove('active');
            document.getElementById('thumbnailModeBtn').classList.remove('active');
            document.getElementById('videoSettings').style.display = 'none';
            document.getElementById('audioSettings').style.display = 'block';
            document.getElementById('thumbnailSettings').style.display = 'none';
            document.getElementById('saveContainer').style.display = 'none';
            document.getElementById('infoText').style.display = 'none';
            document.getElementById('videoContainer').style.display = 'none';
            document.getElementById('thumbnailPreview').style.display = 'none';
            document.getElementById('downloadLabel').innerHTML = '🎵 音声ダウンロード設定';
        };

        document.getElementById('thumbnailModeBtn').onclick = () => {
            currentMode = 'thumbnail';
            document.getElementById('thumbnailModeBtn').classList.add('active');
            document.getElementById('videoModeBtn').classList.remove('active');
            document.getElementById('audioModeBtn').classList.remove('active');
            document.getElementById('videoSettings').style.display = 'none';
            document.getElementById('audioSettings').style.display = 'none';
            document.getElementById('thumbnailSettings').style.display = 'block';
            document.getElementById('saveContainer').style.display = 'none';
            document.getElementById('infoText').style.display = 'none';
            document.getElementById('videoContainer').style.display = 'none';
            document.getElementById('downloadLabel').innerHTML = '🖼️ サムネイル設定';
        };

        // サムネイルサイズ選択
        document.querySelectorAll('.size-btn').forEach(btn => {
            btn.onclick = () => {
                document.querySelectorAll('.size-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                selectedThumbSize = btn.dataset.size;
                if (thumbnails.length > 0) {
                    updateThumbnailPreview();
                }
            };
        });

        function updateThumbnailPreview() {
            const thumb = thumbnails.find(t => t.size === selectedThumbSize) || thumbnails[0];
            if (thumb && thumb.url) {
                document.getElementById('thumbnailImg').src = thumb.url;
                document.getElementById('thumbnailPreview').style.display = 'block';
            }
        }

        // 情報取得
        document.getElementById('infoBtn').onclick = async function() {
            const url = document.getElementById('urlInput').value.trim();
            if (!url) { alert('URLを入力してください'); return; }
            currentUrl = url;
            const btn = this;
            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner"></span> 情報取得中...';
            
            try {
                const res = await fetch('/video_info', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });
                const data = await res.json();
                if (data.success) {
                    videoTitle = data.title;
                    formats = data.formats || [];
                    thumbnails = data.thumbnails || [];
                    
                    // 画質選択
                    const qs = document.getElementById('qualitySelect');
                    qs.innerHTML = '<option value="">画質を選択してください</option>';
                    for (let f of formats) {
                        const opt = document.createElement('option');
                        opt.value = f.itag;
                        let label = f.height + 'p';
                        if (f.fps && f.fps > 30) label += ' ' + f.fps + 'fps';
                        opt.textContent = label;
                        qs.appendChild(opt);
                    }
                    
                    let def = formats.find(f => f.height === 720) || formats[0];
                    if (def) {
                        selectedItag = def.itag;
                        qs.value = selectedItag;
                        if (def.preview_url) {
                            document.getElementById('videoSource').src = def.preview_url;
                            document.getElementById('videoPreview').load();
                            document.getElementById('videoContainer').style.display = 'block';
                        }
                    }
                    
                    // サムネイル表示
                    if (thumbnails.length > 0) {
                        updateThumbnailPreview();
                    }
                    
                    // 情報パネル
                    document.getElementById('infoText').innerHTML = `
                        <div class="info-item">📹 <strong>${escapeHtml(data.title)}</strong></div>
                        <div class="info-item">👁️ ${formatNumber(data.view_count)} 回再生</div>
                        <div class="info-item">⏱️ ${data.duration || '不明'}</div>
                        <div class="info-item">🖼️ サムネイル: ${thumbnails.length}種類</div>
                    `;
                    document.getElementById('infoText').style.display = 'block';
                    document.getElementById('saveContainer').style.display = 'block';
                } else {
                    alert('失敗: ' + data.error);
                }
            } catch(e) { alert('通信エラー'); }
            finally {
                btn.disabled = false;
                btn.innerHTML = '🔍 情報取得';
            }
        };

        document.getElementById('qualitySelect').onchange = function() {
            const itag = parseInt(this.value);
            const fmt = formats.find(f => f.itag === itag);
            if (fmt && fmt.preview_url) {
                selectedItag = itag;
                document.getElementById('videoSource').src = fmt.preview_url;
                document.getElementById('videoPreview').load();
            }
        };

        // ダウンロード実行
        document.getElementById('saveBtn').onclick = async function() {
            const btn = this;
            btn.disabled = true;
            const pa = document.getElementById('progressArea');
            const pf = document.getElementById('progressFill');
            const pm = document.getElementById('progressMsg');
            pa.style.display = 'block';
            pf.style.width = '0%';
            
            let msgs = { video: '動画ダウンロード中...', audio: '音声抽出中...', thumbnail: 'サムネイル保存中...' };
            pm.innerHTML = msgs[currentMode];
            
            let progress = 0;
            const interval = setInterval(() => {
                if (progress < 90) { progress += 10; pf.style.width = progress + '%'; }
            }, 500);
            
            try {
                let body = { url: currentUrl, title: videoTitle, type: currentMode };
                if (currentMode === 'video') {
                    if (!selectedItag) throw new Error('画質を選択してください');
                    body.itag = selectedItag;
                } else if (currentMode === 'audio') {
                    body.audio_format = document.getElementById('audioFormatSelect').value;
                } else if (currentMode === 'thumbnail') {
                    body.size = selectedThumbSize;
                }
                
                const res = await fetch('/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                
                clearInterval(interval);
                if (!res.ok) { const err = await res.json(); throw new Error(err.error); }
                
                const blob = await res.blob();
                const cd = res.headers.get('Content-Disposition');
                let ext = { video: '.mp4', audio: '.mp3', thumbnail: '.jpg' };
                let filename = videoTitle + ext[currentMode];
                if (cd) { const m = cd.match(/filename[*]=?.*?''([^"]+)/); if (m && m[1]) filename = decodeURIComponent(m[1]); }
                
                const a = document.createElement('a');
                const url = URL.createObjectURL(blob);
                a.href = url; a.download = filename;
                document.body.appendChild(a); a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                pf.style.width = '100%';
                pm.innerHTML = '✅ 完了！';
                setTimeout(() => { pa.style.display = 'none'; btn.disabled = false; }, 2000);
            } catch(e) {
                clearInterval(interval);
                alert('❌ 失敗: ' + e.message);
                pa.style.display = 'none';
                btn.disabled = false;
            }
        };

        function escapeHtml(str) { if (!str) return ''; return str.replace(/[&<>]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[m])); }
        function formatNumber(num) { if (num >= 100000000) return (num / 100000000).toFixed(1) + '億'; if (num >= 10000) return (num / 10000).toFixed(1) + '万'; return num.toString(); }
        
        document.getElementById('urlInput').onkeypress = function(e) { if (e.key === 'Enter') document.getElementById('infoBtn').click(); };
    </script>
</body>
</html>
'''

def sanitize_filename(title):
    name = re.sub(r'[\\/*?:"<>|]', '', title)
    name = re.sub(r'[#%&{}\\[\]~!$^@+/=,]', '_', name)
    name = re.sub(r'_+', '_', name)
    name = name.strip(' ._')[:100]
    return name if name else 'youtube'

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
                format_id = str(f['format_id'])
                if '-drc' in format_id:
                    continue
                if f.get('vcodec') != 'none' and f.get('height'):
                    formats.append({
                        'itag': format_id,
                        'height': f['height'],
                        'fps': f.get('fps'),
                        'preview_url': f.get('url', '')
                    })
            formats.sort(key=lambda x: -x['height'])
            
            # サムネイル情報を収集
            thumbnails = []
            size_map = {
                'default': 'default.jpg',
                'mqdefault': 'mqdefault.jpg',
                'hqdefault': 'hqdefault.jpg',
                'sddefault': 'sddefault.jpg',
                'maxresdefault': 'maxresdefault.jpg'
            }
            video_id = info.get('id', '')
            for size, filename in size_map.items():
                thumb_url = f'https://img.youtube.com/vi/{video_id}/{filename}'
                thumbnails.append({'size': size, 'url': thumb_url})
            
            return jsonify({
                'success': True,
                'title': info.get('title'),
                'view_count': info.get('view_count', 0),
                'duration': info.get('duration_string'),
                'formats': formats,
                'thumbnails': thumbnails,
                'video_id': video_id
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data['url']
    title = data.get('title', 'video')
    download_type = data.get('type', 'video')
    
    if 'youtu.be' in url:
        video_id = url.split('/')[-1].split('?')[0]
        url = f'https://www.youtube.com/watch?v={video_id}'
    
    safe_title = sanitize_filename(title)
    temp_dir = tempfile.mkdtemp(dir=TEMP_BASE)
    
    try:
        if download_type == 'video':
            itag = data.get('itag')
            if not itag:
                return jsonify({'error': '画質が指定されていません'}), 400
            output_template = os.path.join(temp_dir, f'{safe_title}.%(ext)s')
            ydl_opts = get_ydl_opts({
                'format': f'{itag}+bestaudio/best',
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
            })
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
            
            # ファイル検索
            actual_file = None
            for ext in ['.mp4', '.webm', '.mkv']:
                test_path = os.path.join(temp_dir, f'{safe_title}{ext}')
                if os.path.exists(test_path) and os.path.getsize(test_path) > 10000:
                    actual_file = test_path
                    break
            if not actual_file:
                for ext in ['.mp4', '.webm', '.mkv']:
                    pattern = os.path.join(temp_dir, f'*{ext}')
                    files = glob.glob(pattern)
                    for f in files:
                        if os.path.getsize(f) > 10000:
                            actual_file = f
                            break
                    if actual_file:
                        break
            
        elif download_type == 'audio':
            audio_format = data.get('audio_format', 'mp3')
            output_template = os.path.join(temp_dir, f'{safe_title}.%(ext)s')
            ydl_opts = get_ydl_opts({
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': audio_format,
                    'preferredquality': '192',
                }],
            })
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
            
            actual_file = None
            for ext in ['.mp3', '.m4a', '.opus', '.wav']:
                test_path = os.path.join(temp_dir, f'{safe_title}{ext}')
                if os.path.exists(test_path) and os.path.getsize(test_path) > 10000:
                    actual_file = test_path
                    break
            if not actual_file:
                for ext in ['.mp3', '.m4a', '.opus', '.wav']:
                    pattern = os.path.join(temp_dir, f'*{ext}')
                    files = glob.glob(pattern)
                    for f in files:
                        if os.path.getsize(f) > 10000:
                            actual_file = f
                            break
                    if actual_file:
                        break
        
        else:  # thumbnail
            size = data.get('size', 'maxresdefault')
            video_id = data.get('video_id', '')
            if not video_id:
                ydl_opts = get_ydl_opts()
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    video_id = info.get('id', '')
            
            size_map = {
                'default': 'default.jpg',
                'mqdefault': 'mqdefault.jpg',
                'hqdefault': 'hqdefault.jpg',
                'sddefault': 'sddefault.jpg',
                'maxresdefault': 'maxresdefault.jpg'
            }
            filename = size_map.get(size, 'maxresdefault.jpg')
            thumb_url = f'https://img.youtube.com/vi/{video_id}/{filename}'
            
            response = requests.get(thumb_url)
            if response.status_code != 200:
                # フォールバック：高画質がなければ標準を使用
                thumb_url = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
                response = requests.get(thumb_url)
            
            if response.status_code != 200:
                raise Exception('サムネイルが見つかりません')
            
            output_file = os.path.join(temp_dir, f'{safe_title}.jpg')
            with open(output_file, 'wb') as f:
                f.write(response.content)
            actual_file = output_file
        
        if not actual_file or not os.path.exists(actual_file):
            all_files = os.listdir(temp_dir)
            raise Exception(f'出力ファイルが見つかりません。生成: {all_files}')
        
        file_size = os.path.getsize(actual_file)
        if file_size < 1000:
            raise Exception(f'ファイルサイズが異常に小さいです: {file_size} バイト')
        
        with open(actual_file, 'rb') as f:
            file_data = f.read()
        
        from urllib.parse import quote
        encoded_filename = quote(os.path.basename(actual_file))
        
        ext = os.path.splitext(actual_file)[1].lower()
        mime_map = {'.mp4': 'video/mp4', '.webm': 'video/webm', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.opus': 'audio/opus', '.wav': 'audio/wav', '.jpg': 'image/jpeg'}
        mime_type = mime_map.get(ext, 'application/octet-stream')
        
        response = Response(file_data, mimetype=mime_type)
        response.headers['Content-Disposition'] = f"attachment; filename=\"{encoded_filename}\"; filename*=UTF-8''{encoded_filename}"
        return response
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        def cleanup():
            time.sleep(5)
            shutil.rmtree(temp_dir, ignore_errors=True)
        threading.Thread(target=cleanup).start()

if __name__ == '__main__':
    import webbrowser
    webbrowser.open('http://localhost:5000')
    print("\\n" + "="*60)
    print("✨ YouTube ダウンローダー - 3機能統合版 ✨")
    print("📍 http://localhost:5000")
    print("🎬 動画モード: 高画質動画をダウンロード")
    print("🎵 音声モード: MP3/M4A/OPUS/WAV から選択可能")
    print("🖼️ サムネイルモード: 5種類のサイズから選択")
    print("="*60 + "\\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
