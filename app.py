from flask import Flask, render_template, request, jsonify
import subprocess
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import uuid
import re
import ast
from math import *

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/plots'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
numbat_file = "calc.nbt"

# Ліміт файлів графіків
MAX_PLOT_FILES = 50

logging.basicConfig(
    filename="numbat_logs.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

# Безпечні математичні функції
SAFE_FUNCTIONS = {
    'sin': sin, 'cos': cos, 'tan': tan,
    'log10': log10, 'log': log, 'exp': exp,
    'sqrt': sqrt, 'pi': pi, 'e': e
}

def clean_plot_folder():
    files = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if f.endswith('.png')]
    if len(files) > MAX_PLOT_FILES:
        files.sort(key=lambda x: os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], x)))
        for file in files[:len(files)-MAX_PLOT_FILES]:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], file))

def preprocess_expression(expr):
    expr = re.sub(r"(\d)\s*([a-zA-Z])", r"\1*\2", expr)
    expr = re.sub(r"([a-zA-Z])\s*/\s*([a-zA-Z])", r"\1/\2", expr)
    expr = re.sub(r"([a-zA-Z])\s*\*\s*([a-zA-Z])", r"\1*\2", expr)
    expr = re.sub(r"(\d)\s*\(", r"\1*(", expr)
    expr = expr.replace("^", "**")
    return expr

def safe_eval(expr, x_values=None):
    try:
        if x_values is not None:
            return [eval(expr, {'__builtins__': None}, {**SAFE_FUNCTIONS, 'x': x}) for x in x_values]
        return eval(expr, {'__builtins__': None}, SAFE_FUNCTIONS)
    except Exception as e:
        raise ValueError(f"Помилка обчислення: {str(e)}")

def write_numbat_file(task):
    with open(numbat_file, "w", encoding="utf-8") as file:
        file.write("let result = " + task + "\nprint(result)")

def run_numbat():
    try:
        result = subprocess.run(
            ["numbat", numbat_file],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            logging.error(f"Помилка Numbat: {error_msg}")
            return f"❌ Помилка: {error_msg}"
        
        output = result.stdout.strip()
        logging.info(f"Успішне обчислення: {output}")
        return output
    except subprocess.TimeoutExpired:
        return "⏳ Обчислення зайняло занадто багато часу"
    except Exception as e:
        logging.error(f"Помилка виконання: {str(e)}")
        return f"⚠️ Внутрішня помилка: {str(e)}"

def generate_plot_filename():
    return f"{uuid.uuid4().hex}.png"

def create_plot_from_function(expr, x_start, x_end):
    try:
        x = np.linspace(x_start, x_end, 500)
        y = safe_eval(expr, x)
        
        plt.figure()
        plt.plot(x, y)
        plt.grid(True)
        
        filename = generate_plot_filename()
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        plt.savefig(path)
        plt.close()
        
        clean_plot_folder()
        return f"/static/plots/{filename}", None
    except Exception as e:
        return None, str(e)

def create_plot_from_points(x_values, y_values):
    try:
        x = [float(i.strip()) for i in x_values.split(",") if i.strip()]
        y = [float(i.strip()) for i in y_values.split(",") if i.strip()]
        
        if len(x) != len(y):
            return None, "Кількість X і Y значень не співпадає"
        if len(x) < 2:
            return None, "Потрібно щонайменше 2 точки"
            
        plt.figure()
        plt.plot(x, y, marker='o')
        plt.grid(True)
        
        filename = generate_plot_filename()
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        plt.savefig(path)
        plt.close()
        
        clean_plot_folder()
        return f"/static/plots/{filename}", None
    except Exception as e:
        return None, f"Помилка обробки точок: {str(e)}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/calculate", methods=["POST"])
def calculate():
    if not request.is_json:
        return jsonify({"error": "Очікується JSON"}), 400
    
    data = request.get_json()
    expression = data.get("expression", "").strip()
    
    if not expression:
        return jsonify({"error": "Пустий вираз"}), 400
    
    try:
        processed_expr = preprocess_expression(expression)
        write_numbat_file(processed_expr)
        result = run_numbat()
        return jsonify({"result": result})
    except Exception as e:
        logging.error(f"Помилка обчислення: {str(e)}")
        return jsonify({"error": f"Помилка обробки: {str(e)}"}), 500

@app.route("/plot", methods=["POST"])
def plot():
    if not request.is_json:
        return jsonify({"error": "Очікується JSON"}), 400
    
    data = request.get_json()
    mode = data.get("mode")
    
    if mode == "function":
        expr = data.get("function_expr", "").strip()
        try:
            x_start = float(data.get("x_start", -10))
            x_end = float(data.get("x_end", 10))
        except ValueError:
            return jsonify({"error": "Невірний діапазон X"}), 400
            
        if not expr:
            return jsonify({"error": "Пустий вираз функції"}), 400
            
        url, error = create_plot_from_function(expr, x_start, x_end)
    elif mode == "points":
        x_vals = data.get("x_values", "").strip()
        y_vals = data.get("y_values", "").strip()
        
        if not x_vals or not y_vals:
            return jsonify({"error": "X або Y значення відсутні"}), 400
            
        url, error = create_plot_from_points(x_vals, y_vals)
    else:
        return jsonify({"error": "Невірний режим"}), 400
    
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"plot_url": url})

if __name__ == "__main__":
    app.run(debug=True)