from flask import Flask, render_template, request, jsonify
import subprocess
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os
import uuid
import re
import ast
from math import *

# Ініціалізація Flask
app = Flask(__name__)
app.secret_key = 'dev-secret-key'  # Для Flask-сесій

# Налаштування директорій та файлів
UPLOAD_FOLDER = 'static/plots'
LOG_FOLDER = 'logs'
NUMBAT_FILE = 'numbat_script.nbt'
MAX_PLOT_FILES = 20

# Створення необхідних директорій
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

# Налаштування логування
logging.basicConfig(
    filename=os.path.join(LOG_FOLDER, "numbat_logs.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

SAFE_FUNCTIONS = {
    'sin': sin, 'cos': cos, 'tan': tan,
    'син': sin, 'кос': cos, 'тан': tan,
    'log10': log10, 'log': log, 'лог': log, 'лог10': log10,
    'exp': exp, 'sqrt': sqrt, 'корінь': sqrt,
    'pi': pi, 'e': e
}

def clean_plot_folder():
    try:
        files = [f for f in os.listdir(UPLOAD_FOLDER)
                 if f.endswith('.png') and os.path.isfile(os.path.join(UPLOAD_FOLDER, f))]
        if len(files) > MAX_PLOT_FILES:
            files.sort(key=lambda x: os.path.getmtime(os.path.join(UPLOAD_FOLDER, x)))
            for file in files[:len(files) - MAX_PLOT_FILES]:
                os.remove(os.path.join(UPLOAD_FOLDER, file))
                logging.info(f"Removed old plot file: {file}")
    except Exception as e:
        logging.error(f"Error cleaning plot folder: {e}")

def preprocess_expression(expr):
    if not isinstance(expr, str):
        raise ValueError("Expression must be a string")
    expr = expr.strip().replace("х", "x").replace(",", ".")
    expr = re.sub(r"(\d)\s*([a-zA-Zа-яА-Я])", r"\1*\2", expr)
    expr = re.sub(r"([a-zA-Zа-яА-Я])\s*/\s*([a-zA-Zа-яА-Я])", r"\1/\2", expr)
    expr = re.sub(r"([a-zA-Zа-яА-Я])\s*\*\s*([a-zA-Zа-яА-Я])", r"\1*\2", expr)
    expr = re.sub(r"(\d)\s*\(", r"\1*(", expr)
    expr = expr.replace("^", "**")
    return expr

def safe_eval(expr, x_values=None):
    try:
        parsed_expr = ast.parse(expr, mode='eval')
        for node in ast.walk(parsed_expr):
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCTIONS:
                    raise ValueError(f"Unknown function: {node.func.id}")
            elif isinstance(node, ast.Name) and node.id not in SAFE_FUNCTIONS and node.id != 'x':
                raise ValueError(f"Unknown variable: {node.id}")
            elif isinstance(node, (ast.Attribute, ast.Subscript)):
                raise ValueError("Unsupported expression")

        if x_values is not None:
            return [eval(compile(parsed_expr, '', 'eval'),
                         {'__builtins__': None}, {**SAFE_FUNCTIONS, 'x': x}) for x in x_values]
        return eval(compile(parsed_expr, '', 'eval'), {'__builtins__': None}, SAFE_FUNCTIONS)
    except Exception as e:
        logging.error(f"Evaluation error: {str(e)}")
        raise ValueError(f"Evaluation error: {str(e)}")

def write_numbat_file(task):
    try:
        with open(NUMBAT_FILE, "w", encoding="utf-8") as file:
            file.write(f"let result = {task}\nprint(result)")
    except IOError as e:
        logging.error(f"Failed to write numbat file: {e}")
        raise

def run_numbat():
    try:
        result = subprocess.run(["numbat", NUMBAT_FILE], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return f"❌ Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "⏳ Computation took too long"
    except FileNotFoundError:
        return "❌ Error: Numbat executable not found"
    except Exception as e:
        return f"⚠️ Internal error: {str(e)}"

def generate_plot_filename():
    return f"{uuid.uuid4().hex}.png"

def create_plot_from_function(expr, x_start, x_end):
    try:
        if x_start >= x_end:
            raise ValueError("Start must be less than end")
        x = np.linspace(x_start, x_end, 500)
        y = safe_eval(expr, x)
        plt.figure()
        plt.plot(x, y)
        plt.xlabel('x')
        plt.ylabel('y')
        plt.title(f'Function plot: {expr}')
        plt.grid(True)
        filename = generate_plot_filename()
        path = os.path.join(UPLOAD_FOLDER, filename)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        clean_plot_folder()
        return f"/static/plots/{filename}", None
    except Exception as e:
        return None, str(e)

def create_plot_from_points(x_values, y_values):
    try:
        x = [float(i.strip()) for i in x_values.split(",")]
        y = [float(i.strip()) for i in y_values.split(",")]
        if len(x) != len(y):
            return None, "X and Y values count mismatch"
        plt.figure()
        plt.plot(x, y, marker='o')
        plt.xlabel('x')
        plt.ylabel('y')
        plt.title('Point plot')
        plt.grid(True)
        filename = generate_plot_filename()
        path = os.path.join(UPLOAD_FOLDER, filename)
        plt.savefig(path, bbox_inches='tight')
        plt.close()
        clean_plot_folder()
        return f"/static/plots/{filename}", None
    except Exception as e:
        return None, str(e)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    if not request.is_json:
        return jsonify({"error": "JSON expected"}), 400
    data = request.get_json()
    expression = data.get("expression", "").strip()
    if not expression:
        return jsonify({"error": "Empty expression"}), 400
    try:
        expr = preprocess_expression(expression)
        safe_eval(expr)  # Перевірка
        write_numbat_file(expr)
        result = run_numbat()
        return jsonify({"result": result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

@app.route("/plot", methods=["POST"])
def plot():
    if not request.is_json:
        return jsonify({"error": "JSON expected"}), 400
    data = request.get_json()
    mode = data.get("mode")
    if mode == "function":
        expr = data.get("function_expr", "").strip()
        try:
            x_start = float(data.get("x_start", -10))
            x_end = float(data.get("x_end", 10))
        except ValueError:
            return jsonify({"error": "Invalid X range"}), 400
        if not expr:
            return jsonify({"error": "Empty function expression"}), 400
        url, error = create_plot_from_function(expr, x_start, x_end)
    elif mode == "points":
        x_vals = data.get("x_values", "").strip()
        y_vals = data.get("y_values", "").strip()
        if not x_vals or not y_vals:
            return jsonify({"error": "Missing X or Y values"}), 400
        url, error = create_plot_from_points(x_vals, y_vals)
    else:
        return jsonify({"error": "Invalid mode"}), 400
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"plot_url": url})

if __name__ == "__main__":
    print("🚀 Starting Flask application...")
    print(f"📁 Upload folder: {UPLOAD_FOLDER}")
    print(f"📝 Log folder: {LOG_FOLDER}")
    app.run(debug=True)
