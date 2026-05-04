from flask import Flask, render_template_string, send_file, request, jsonify
import yt_dlp
import tempfile
import os
import uuid
import threading
import time

app = Flask(__name__)

# シンプルなHTML
HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>YouTubeダウンローダー</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body{font-family:sans-serif;background:#667eea;padding:20px}
        .container{max-width:600px;margin:0 auto;background:white;border-radius:20px;padding:30px}
        input,button{width:100%;padding:12px;margin:10px 0;border-radius:8px}
        button{background:#667eea;color:white;border:none;cursor:pointer}
        .progress{display:none;margin-top:20px}
        .bar{height:20px;background:#e0e0e0;border-radius:10px;overflow:hidden}
        .fill{width:0%;height:100%;background:#667eea}
    </style>
</head>
<body>
    <div class="container">
        <h1>YouTubeダウンローダー</h1>
        <input type="text" id="url" placeholder="YouTube URL">
        <select id="format">
            <option value="mp4">MP4動画</option>
            <option value="mp3">MP3音声</option>
        </select>
        <button onclick="download()">ダウンロード</button>
        <div id="progress" class="progress">
            <div class="bar"><div id="fill" class="fill"></div></div>
            <div id="status"></div>
        </div>
        <div id="result"></div>
    </div>
    <script>
        let taskId = null;
        function download(){
            const url = document.getElementById('url').value;
            const format = document.getElementById('format').value;
            if(!url){alert('URLを入力');return;}
            document.getElementById('progress').style.display='block';
            fetch('/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:url,format:format})})
            .then(r=>r.json()).then(data=>{if(data.task_id){taskId=data.task_id;poll();}})
            .catch(e=>{alert(e.message);});
        }
        function poll(){
            if(!taskId)return;
            fetch('/status/'+taskId).then(r=>r.json()).then(data=>{
                document.getElementById('fill').style.width=data.progress+'%';
                document.getElementById('status').innerText=data.status||'';
                if(data.completed&&data.success){
                    window.location.href=data.download_url;
                }else if(data.completed){
                    alert('エラー:'+data.error);
                }else{
                    setTimeout(poll,1000);
                }
            });
        }
    </script>
</body>
</html>
'''

tasks = {}

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    format_type = data.get('format', 'mp4')
    task_id = str(uuid.uuid4())
    
    tasks[task_id] = {'completed': False, 'success': False, 'progress': 0, 'status': '開始'}
    
    def run():
        try:
            temp_dir = tempfile.gettempdir()
            if format_type == 'mp3':
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
                    'outtmpl': os.path.join(temp_dir, f'{task_id}_%(title)s.%(ext)s'),
                    'progress_hooks': [lambda d: progress_hook(d, task_id)]
                }
            else:
                ydl_opts = {
                    'format': 'best[ext=mp4]/best',
                    'outtmpl': os.path.join(temp_dir, f'{task_id}_%(title)s.%(ext)s'),
                    'progress_hooks': [lambda d: progress_hook(d, task_id)]
                }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if format_type == 'mp3':
                    filename = filename.rsplit('.',1)[0] + '.mp3'
                tasks[task_id]['filepath'] = filename
                tasks[task_id]['success'] = True
                tasks[task_id]['completed'] = True
                tasks[task_id]['progress'] = 100
        except Exception as e:
            tasks[task_id]['error'] = str(e)
            tasks[task_id]['completed'] = True
            tasks[task_id]['success'] = False
    
    def progress_hook(d, task_id):
        if d['status'] == 'downloading':
            if d.get('total_bytes'):
                progress = (d['downloaded_bytes'] / d['total_bytes']) * 100
                tasks[task_id]['progress'] = progress
                tasks[task_id]['status'] = f'ダウンロード中 {int(progress)}%'
        elif d['status'] == 'finished':
            tasks[task_id]['status'] = '変換中'
            tasks[task_id]['progress'] = 95
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    
    return jsonify({'task_id': task_id})

@app.route('/status/<task_id>')
def status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({'completed': True, 'success': False, 'error': 'タスクなし'})
    if task.get('completed') and task.get('success'):
        return jsonify({
            'completed': True,
            'success': True,
            'download_url': f'/download_file/{task_id}',
            'progress': task.get('progress', 100),
            'status': task.get('status', '完了')
        })
    elif task.get('completed'):
        return jsonify({
            'completed': True,
            'success': False,
            'error': task.get('error', 'エラー'),
            'progress': task.get('progress', 0)
        })
    else:
        return jsonify({
            'completed': False,
            'progress': task.get('progress', 0),
            'status': task.get('status', '処理中')
        })

@app.route('/download_file/<task_id>')
def download_file(task_id):
    task = tasks.get(task_id)
    if not task or not task.get('filepath') or not os.path.exists(task['filepath']):
        return 'ファイルが見つかりません', 404
    return send_file(task['filepath'], as_attachment=True)

if __name__ == '__main__':
    import webbrowser
    webbrowser.open('http://localhost:5000')
    print("サーバー起動: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
