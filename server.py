import re
from flask import Flask, request, jsonify, send_from_directory, send_file
import os
from pathlib import Path

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB限制
app.config['UPLOAD_FOLDER'] = './uploads'
UPLOAD_FOLDER = './uploads'
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

# 允许跨域访问
@app.after_request
def add_cors(res):
    res.headers['Access-Control-Allow-Origin'] = '*'  # 改为通配符，方便本地测试
    res.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    res.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return res

def get_tree(path):
    # 获取相对于上传目录的相对路径
    relative_path = os.path.relpath(path, UPLOAD_FOLDER)
    
    # 处理根目录情况
    is_root = (relative_path == '.')
    
    name = os.path.basename(path)
    
    if os.path.isfile(path):
        return {
            'name': name,
            'type': 'file',
            'path': relative_path.replace('\\', '/') if not is_root else name
        }
    
    children = []
    for p in os.listdir(path):
        try:
            child_path = os.path.join(path, p)
            children.append(get_tree(child_path))
        except PermissionError:
            continue
    
    return {
        'name': name,
        'type': 'folder',
        'path': relative_path.replace('\\', '/') if not is_root else '',
        'children': children
    }

@app.route('/files')
def list_files():
    try:
        return jsonify(get_tree(UPLOAD_FOLDER)['children'])
    except Exception as e:
        app.logger.error(f"获取文件树失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/file')
def get_file():
    path = request.args.get('path')
    if not path:
        return 'Path parameter is required', 400
    
    # 清理路径中的非法字符
    path = re.sub(r'[\x00-\x1F\x7F]', '', path).strip()
    
    # 转换为绝对路径
    try:
        abs_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, path))
        print(abs_path)
    except Exception as e:
        return f'Invalid path: {str(e)}', 400
    
    # 验证路径是否在UPLOAD_FOLDER下
    if not abs_path.startswith(os.path.abspath(UPLOAD_FOLDER)):
        return 'Access denied', 403
    
    if not os.path.isfile(abs_path):
        return 'File not found', 404
    
    try:
        # 尝试多种编码
        encodings = ['utf-8', 'gbk', 'latin-1']
        for encoding in encodings:
            try:
                with open(abs_path, 'r', encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        
        # 如果所有编码都失败，返回二进制内容
        with open(abs_path, 'rb') as f:
            return f.read()
    except Exception as e:
        app.logger.error(f"Failed to read file {abs_path}: {str(e)}")
        return f'Failed to read file: {str(e)}', 500

@app.route('/upload', methods=['POST'])
def upload():
    if not request.files:
        app.logger.error("No files in request")
        return 'No files uploaded', 400

    try:
        for path, file in request.files.items():
            # 路径安全检查
            if '../' in path or not path:
                app.logger.warning(f"Invalid path detected: {path}")
                continue

            save_path = os.path.join(UPLOAD_FOLDER, path)
            parent_dir = os.path.dirname(save_path)
            
            # 创建父目录（递归创建）
            Path(parent_dir).mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            file.save(save_path)
            app.logger.info(f"Saved: {save_path} ({file.content_length} bytes)")
            
        return jsonify({"status": "success", "count": len(request.files)})
    except Exception as e:
        app.logger.error(f"Upload failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/download')
def download_file():
    path = request.args.get('path')
    if not path:
        return 'Path parameter is required', 400
    
    # 清理路径中的非法字符
    path = re.sub(r'[\x00-\x1F\x7F]', '', path).strip()
    
    try:
        # 转换为绝对路径
        abs_path = os.path.abspath(os.path.join(UPLOAD_FOLDER, path))
    except Exception as e:
        return f'Invalid path: {str(e)}', 400
    
    # 验证路径是否在UPLOAD_FOLDER下（防止路径遍历）
    if not abs_path.startswith(os.path.abspath(UPLOAD_FOLDER)):
        return 'Access denied', 403
    
    if not os.path.isfile(abs_path):
        return 'File not found', 404
    
    # 获取原始文件名
    filename = os.path.basename(abs_path)
    
    try:
        return send_file(
            abs_path,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        app.logger.error(f"Download failed: {str(e)}")
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)