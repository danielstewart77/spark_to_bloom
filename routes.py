import os
import markdown
from flask import render_template, Flask
from markupsafe import Markup

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
    return render_template('home.html')

@app.route('/about', methods=['GET'])
def about():
    return render_template('about.html')

@app.route('/pullrequests', methods=['GET'])
def pullrequests():
    return render_template('pullrequests.html')

@app.route('/pages/<path:subpath>', methods=['GET'])
def page(subpath):
    md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates/pages', subpath)
    md_path = os.path.normpath(md_path)
    
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    html_content = markdown.markdown(md_content, extensions=['fenced_code', 'codehilite'])
    return render_template("page.html", content=Markup(html_content))

@app.route('/pr/<path:subpath>', methods=['GET'])
def blog_article(subpath):
    md_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates/pr', subpath)
    md_path = os.path.normpath(md_path)
    
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    html_content = markdown.markdown(md_content, extensions=['fenced_code', 'codehilite'])
    return render_template("pr.html", content=Markup(html_content))

if __name__ == '__main__':
    app.run(
        host='0.0.0.0', port=808080
    )
