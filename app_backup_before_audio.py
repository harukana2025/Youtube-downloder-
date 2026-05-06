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
if os.path.exists(COOKIE_FILE):
    print(f"🍪 クッキーを読み込みました")

def get_ydl_opts(extra_opts=None):
    opts = {
        'quiet': True,
        'no_warnings': False,
        'retries': 30,
    }
    if os.path.exists(COOKIE_FILE):
        opts['cookiefile'] = COOKIE_FILE
    if extra_opts:
        opts.update(extra_opts)
    return opts

# アニメーション付きHTML
HTML = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>✨ YouTube DL - 動画ダウンローダー ✨</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', 'Poppins', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            position: relative;
            overflow-x: hidden;
        }

        /* アニメーション背景 */
        .bg-animation {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
            overflow: hidden;
        }

        .bg-animation div {
            position: absolute;
            display: block;
            width: 20px;
            height: 20px;
            background: rgba(255, 255, 255, 0.1);
            bottom: -150px;
            animation: floatUp 15s infinite;
            border-radius: 50%;
        }

        @keyframes floatUp {
            0% {
                transform: translateY(0) rotate(0deg);
                opacity: 1;
            }
            100% {
                transform: translateY(-1000px) rotate(720deg);
                opacity: 0;
            }
        }

        /* メインコンテナ */
        .container {
            max-width: 1200px;
            margin: 0 auto;
            position: relative;
            z-index: 1;
            animation: fadeInUp 0.8s ease-out;
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        /* カードデザイン */
        .card {
            background: rgba(255, 255, 255, 0.98);
            backdrop-filter: blur(10px);
            border-radius: 32px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }

        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 30px 70px rgba(0, 0, 0, 0.4);
        }

        /* ヘッダー */
        .header {
            text-align: center;
            margin-bottom: 40px;
            animation: slideInDown 0.6s ease;
        }

        @keyframes slideInDown {
            from {
                opacity: 0;
                transform: translateY(-50px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .header h1 {
            font-size: 3rem;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            margin-bottom: 10px;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.8; }
        }

        .header p {
            color: #666;
            font-size: 1.1rem;
        }

        /* レイアウト */
        .row {
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }

        .left {
            flex: 1.5;
            min-width: 300px;
        }

        .right {
            flex: 1;
            min-width: 280px;
        }

        /* 入力フィールド */
        .input-group {
            margin-bottom: 20px;
            animation: slideInRight 0.5s ease;
        }

        @keyframes slideInRight {
            from {
                opacity: 0;
                transform: translateX(30px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }

        input, select, button {
            width: 100%;
            padding: 14px 20px;
            margin: 10px 0;
            border-radius: 50px;
            border: 2px solid #e0e0e0;
            font-size: 16px;
            transition: all 0.3s ease;
            font-family: inherit;
        }

        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            transform: scale(1.02);
        }

        input:hover {
            transform: scale(1.02);
        }

        /* ボタン */
        button {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            font-weight: bold;
            cursor: pointer;
            border: none;
            position: relative;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        button::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            width: 0;
            height: 0;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.5);
            transform: translate(-50%, -50%);
            transition: width 0.6s, height 0.6s;
        }

        button:hover::before {
            width: 300px;
            height: 300px;
        }

        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }

        button:active {
            transform: translateY(0);
        }

        .save-btn {
            background: linear-gradient(135deg, #f093fb, #f5576c);
        }

        /* 動画プレビュー */
        .video-wrapper {
            background: #000;
            border-radius: 20px;
            overflow: hidden;
            margin: 20px 0;
            position: relative;
            animation: zoomIn 0.6s ease;
        }

        @keyframes zoomIn {
            from {
                opacity: 0;
                transform: scale(0.9);
            }
            to {
                opacity: 1;
                transform: scale(1);
            }
        }

        video {
            width: 100%;
            display: block;
            transition: transform 0.3s ease;
        }

        video:hover {
            transform: scale(1.02);
        }

        /* 情報パネル */
        .info-panel {
            background: linear-gradient(135deg, #f5f7fa, #c3cfe2);
            border-radius: 20px;
            padding: 20px;
            margin-top: 20px;
            animation: slideInLeft 0.5s ease;
        }

        @keyframes slideInLeft {
            from {
                opacity: 0;
                transform: translateX(-30px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }

        .info-item {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 10px 0;
            padding: 8px;
            border-radius: 12px;
            transition: background 0.3s ease;
        }

        .info-item:hover {
            background: rgba(255, 255, 255, 0.5);
            transform: translateX(5px);
        }

        .info-icon {
            font-size: 1.5rem;
        }

        /* プログレスバー */
        .progress-area {
            margin-top: 20px;
            display: none;
            animation: fadeIn 0.5s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        .progress-bar {
            width: 100%;
            height: 30px;
            background: #e0e0e0;
            border-radius: 15px;
            overflow: hidden;
            position: relative;
        }

        .progress-fill {
            width: 0%;
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 15px;
            transition: width 0.3s ease;
            position: relative;
            overflow: hidden;
        }

        .progress-fill::after {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            bottom: 0;
            right: 0;
            background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
            animation: shimmer 1.5s infinite;
        }

        @keyframes shimmer {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }

        .progress-text {
            text-align: center;
            margin-top: 10px;
            color: #666;
            font-weight: bold;
        }

        /* ローディングスピナー */
        .loading-spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 0.8s linear infinite;
            margin-right: 10px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* レスポンシブ */
        @media (max-width: 768px) {
            .card {
                padding: 20px;
            }
            .header h1 {
                font-size: 2rem;
            }
        }

        /* ツールチップ */
        [data-tooltip] {
            position: relative;
            cursor: pointer;
        }

        [data-tooltip]:before {
            content: attr(data-tooltip);
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            padding: 5px 10px;
            background: #333;
            color: white;
            border-radius: 5px;
            font-size: 12px;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s;
            z-index: 10;
        }

        [data-tooltip]:hover:before {
            opacity: 1;
        }

        /* 品質バッジ */
        .quality-badge {
            display: inline-block;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            margin-left: 8px;
        }
    </style>
</head>
<body>
    <!-- アニメーション背景 -->
    <div class="bg-animation" id="bgAnimation"></div>

    <div class="container">
        <div class="card">
            <div class="header">
                <h1>✨ YouTube 動画ダウンローダー ✨</h1>
                <p>高画質・高速ダウンロード | アカウント連携可能</p>
                <div style="margin-top: 10px;">
                    <span class="quality-badge">🎵 音声付き</span>
                    <span class="quality-badge">🚀 高速</span>
                    <span class="quality-badge">🔒 安全</span>
                </div>
            </div>

            <div class="row">
                <div class="left">
                    <div class="input-group">
                        <input type="text" id="urlInput" placeholder="🎬 YouTube URL を入力してください" data-tooltip="YouTubeの動画URLを貼り付け">
                        <button id="infoBtn" class="glow-btn">
                            <span>🔍 動画情報を取得</span>
                        </button>
                    </div>
                    
                    <div id="videoContainer" style="display:none">
                        <div class="video-wrapper">
                            <video id="videoPreview" controls>
                                <source id="videoSource" src="">
                            </video>
                        </div>
                    </div>
                    
                    <div id="infoText" class="info-panel" style="display:none"></div>
                </div>

                <div class="right">
                    <h3 style="margin-bottom: 15px; color: #667eea;">⚙️ ダウンロード設定</h3>
                    <select id="qualitySelect">
                        <option value="">画質を選択してください</option>
                    </select>
                    
                    <div id="progressArea" class="progress-area">
                        <div class="progress-bar">
                            <div class="progress-fill" id="progressFill"></div>
                        </div>
                        <div class="progress-text" id="progressMsg">準備完了</div>
                    </div>
                    
                    <div id="saveContainer" style="display:none">
                        <button id="saveBtn" class="save-btn">
                            <span>💾 ダウンロード開始</span>
                        </button>
                    </div>
                    
                    <div style="margin-top: 20px; padding: 15px; background: #f0f0f0; border-radius: 15px;">
                        <small style="color: #666;">💡 ヒント: 高画質ダウンロードには時間がかかる場合があります</small>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let formats = [];
        let selectedItag = null;
        let currentUrl = '';
        let videoTitle = '';

        // 背景アニメーション生成
        function createBackgroundBubbles() {
            const bg = document.getElementById('bgAnimation');
            const bubbleCount = 50;
            for (let i = 0; i < bubbleCount; i++) {
                const bubble = document.createElement('div');
                const size = Math.random() * 60 + 10;
                bubble.style.width = size + 'px';
                bubble.style.height = size + 'px';
                bubble.style.left = Math.random() * 100 + '%';
                bubble.style.animationDelay = Math.random() * 15 + 's';
                bubble.style.animationDuration = (Math.random() * 10 + 10) + 's';
                bg.appendChild(bubble);
            }
        }
        createBackgroundBubbles();

        // ボタンアニメーション
        function animateButton(btn) {
            btn.style.transform = 'scale(0.98)';
            setTimeout(() => {
                btn.style.transform = '';
            }, 200);
        }

        // 動画情報取得
        document.getElementById('infoBtn').onclick = async function() {
            const url = document.getElementById('urlInput').value.trim();
            if (!url) {
                alert('🎬 YouTube URLを入力してください');
                return;
            }
            
            currentUrl = url;
            const btn = this;
            animateButton(btn);
            btn.disabled = true;
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="loading-spinner"></span> 情報取得中...';
            
            try {
                const res = await fetch('/video_info', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });
                const data = await res.json();
                
                if (data.success) {
                    if (data.is_live) {
                        window.location.href = '/live/' + encodeURIComponent(url);
                        return;
                    }
                    
                    videoTitle = data.title;
                    formats = data.formats;
                    
                    // 画質選択ドロップダウンを更新
                    const qs = document.getElementById('qualitySelect');
                    qs.innerHTML = '<option value="">画質を選択してください</option>';
                    
                    for (let f of formats) {
                        const opt = document.createElement('option');
                        opt.value = f.itag;
                        let label = '';
                        if (f.height === 2160) label = '🎬 4K (2160p)';
                        else if (f.height === 1440) label = '🎬 2K (1440p)';
                        else if (f.height === 1080) label = '🎬 Full HD (1080p)';
                        else if (f.height === 720) label = '📺 HD (720p)';
                        else if (f.height === 480) label = '📺 SD (480p)';
                        else if (f.height === 360) label = '📱 360p';
                        else label = f.height + 'p';
                        
                        if (f.fps && f.fps > 30) label += ' 🎯' + f.fps + 'fps';
                        if (f.has_audio) label += ' 🔊';
                        opt.textContent = label;
                        qs.appendChild(opt);
                    }
                    
                    // デフォルトで720pを選択（なければ360p）
                    let def = formats.find(f => f.height === 720) || formats.find(f => f.height === 360) || formats[0];
                    if (def) {
                        selectedItag = def.itag;
                        qs.value = selectedItag;
                        if (def.preview_url) {
                            document.getElementById('videoSource').src = def.preview_url;
                            document.getElementById('videoPreview').load();
                            document.getElementById('videoContainer').style.display = 'block';
                        }
                    }
                    
                    // 情報パネルを表示
                    const infoDiv = document.getElementById('infoText');
                    infoDiv.style.display = 'block';
                    infoDiv.innerHTML = `
                        <div class="info-item">
                            <span class="info-icon">📹</span>
                            <span><strong>${escapeHtml(data.title)}</strong></span>
                        </div>
                        <div class="info-item">
                            <span class="info-icon">👁️</span>
                            <span>${formatNumber(data.view_count)} 回再生</span>
                        </div>
                        <div class="info-item">
                            <span class="info-icon">⏱️</span>
                            <span>${data.duration || '不明'}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-icon">🎨</span>
                            <span>${formats.length} 種類の画質</span>
                        </div>
                    `;
                    
                    document.getElementById('saveContainer').style.display = 'block';
                    document.getElementById('progressArea').style.display = 'none';
                    
                    // アニメーション効果
                    infoDiv.style.animation = 'none';
                    setTimeout(() => {
                        infoDiv.style.animation = 'slideInLeft 0.5s ease';
                    }, 10);
                    
                } else {
                    alert('❌ 情報取得失敗: ' + data.error);
                }
            } catch(e) {
                alert('❌ 通信エラー: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        };
        
        // 画質選択変更時
        document.getElementById('qualitySelect').onchange = function() {
            const itag = parseInt(this.value);
            const fmt = formats.find(f => f.itag === itag);
            if (fmt) {
                selectedItag = itag;
                if (fmt.preview_url) {
                    document.getElementById('videoSource').src = fmt.preview_url;
                    document.getElementById('videoPreview').load();
                }
                // 選択時のフィードバック
                this.style.transform = 'scale(1.02)';
                setTimeout(() => {
                    this.style.transform = '';
                }, 200);
            }
        };
        
        // ダウンロード実行
        document.getElementById('saveBtn').onclick = async function() {
            if (!selectedItag || !currentUrl) {
                alert('先に動画情報を取得してください');
                return;
            }
            
            const btn = this;
            animateButton(btn);
            btn.disabled = true;
            
            const pa = document.getElementById('progressArea');
            const pf = document.getElementById('progressFill');
            const pm = document.getElementById('progressMsg');
            
            pa.style.display = 'block';
            pf.style.width = '0%';
            pm.innerHTML = '🚀 ダウンロード準備中...';
            
            // プログレスバーアニメーション
            let progress = 0;
            const interval = setInterval(() => {
                if (progress < 90) {
                    progress += 10;
                    pf.style.width = progress + '%';
                }
            }, 500);
            
            try {
                const res = await fetch('/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: currentUrl,
                        itag: selectedItag,
                        title: videoTitle
                    })
                });
                
                clearInterval(interval);
                
                if (!res.ok) {
                    const error = await res.json();
                    throw new Error(error.error || 'サーバーエラー');
                }
                
                const blob = await res.blob();
                const cd = res.headers.get('Content-Disposition');
                let filename = 'video.mp4';
                if (cd) {
                    const m = cd.match(/filename[*]=?.*?''([^"]+)/);
                    if (m && m[1]) filename = decodeURIComponent(m[1]);
                }
                
                const a = document.createElement('a');
                const url = URL.createObjectURL(blob);
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                pf.style.width = '100%';
                pm.innerHTML = '✅ ダウンロード完了！';
                
                // 完了アニメーション
                pf.style.background = 'linear-gradient(90deg, #28a745, #20c997)';
                
                setTimeout(() => {
                    pa.style.display = 'none';
                    btn.disabled = false;
                    pf.style.background = '';
                }, 3000);
                
            } catch(e) {
                clearInterval(interval);
                alert('❌ ダウンロード失敗: ' + e.message);
                pa.style.display = 'none';
                btn.disabled = false;
            }
        };
        
        // エスケープ処理
        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/[&<>]/g, function(m) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[m];
            });
        }
        
        // 数値フォーマット
        function formatNumber(num) {
            if (num >= 100000000) return (num / 100000000).toFixed(1) + '億';
            if (num >= 10000) return (num / 10000).toFixed(1) + '万';
            return num.toString();
        }
        
        // Enterキーで情報取得
        document.getElementById('urlInput').onkeypress = function(e) {
            if (e.key === 'Enter') {
                document.getElementById('infoBtn').click();
            }
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
    print("\\n" + "="*60)
    print("✨ YouTube DL - アニメーション版 ✨")
    print("📍 http://localhost:5000")
    print("🎨 アニメーション効果を適用しました")
    print("="*60 + "\\n")
    app.run(host='0.0.0.0', port=5000, debug=True)
