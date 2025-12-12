from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)

app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-for-local-only')

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'

# Конфигурация БД
DB_CONFIG = {
    "dbname": "expense_diary",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": "5432"
}

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    
    if user_data:
        return User(user_data['id'], user_data['username'])
    return None

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def log_audit(user_id, action_type, record_id=None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO audit_log (user_id, action_type, record_id)
        VALUES (%s, %s, %s)
    """, (user_id, action_type, record_id))
    conn.commit()
    cur.close()
    conn.close()

# ========== HTML PAGES ==========
@app.route('/')
def home():
    return redirect(url_for('login_page'))

@app.route('/login_page')
def login_page():
    return render_template('login.html')

@app.route('/register_page')
def register_page():
    return render_template('register.html')

@app.route('/add_page')
@login_required
def add_page():
    return render_template('add.html')

@app.route('/list_page')
@login_required
def list_page():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT * FROM expenses 
        WHERE user_id = %s 
        ORDER BY created_at DESC
    """, (current_user.id,))
    expenses = cur.fetchall()
    cur.close()
    conn.close()
    
    log_audit(current_user.id, "view_list")
    return render_template('list.html', expenses=expenses)

# ========== API ENDPOINTS ==========
@app.route('/register', methods=['POST'])
def register():
    if request.is_json:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        return_json = True
    else:
        username = request.form.get('username')
        password = request.form.get('password')
        return_json = False
    
    if not username or not password:
        if return_json:
            return jsonify({"error": "Username and password required"}), 400
        else:
            return render_template('register.html', error="Заполните все поля")
    
    # Проверка длины пароля
    if len(password) < 6:
        if return_json:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        else:
            return render_template('register.html', error="Пароль должен быть минимум 6 символов")
    
    hashed_password = generate_password_hash(password)
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s) RETURNING id",
            (username, hashed_password)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        log_audit(user_id, "registration")
        
        # АВТОМАТИЧЕСКИ ЛОГИНИМ ПОСЛЕ РЕГИСТРАЦИИ
        user = User(user_id, username)
        login_user(user)  # ← ВОТ ЭТОЙ СТРОЧКИ У ВАС НЕТ!
        
        if return_json:
            return jsonify({"message": "User registered", "user_id": user_id}), 201
        else:
            return redirect(url_for('list_page'))  # перенаправляем на список расходов
            
    except psycopg2.IntegrityError:
        if return_json:
            return jsonify({"error": "Username exists"}), 400
        else:
            return render_template('register.html', error="Имя пользователя уже существует")
    except Exception as e:
        print(f"Error in registration: {e}")
        if return_json:
            return jsonify({"error": "Server error"}), 500
        else:
            return render_template('register.html', error="Ошибка сервера")
    finally:
        cur.close()
        conn.close()


@app.route('/login', methods=['POST'])
def login():
    if request.is_json:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        return_json = True
    else:
        username = request.form.get('username')
        password = request.form.get('password')
        return_json = False
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    
    if user_data and check_password_hash(user_data['password'], password):
        user = User(user_data['id'], user_data['username'])
        login_user(user)
        log_audit(user.id, "login")
        
        if return_json:
            return jsonify({"message": "Logged in"}), 200
        else:
            return redirect(url_for('list_page'))
    
    if return_json:
        return jsonify({"error": "Invalid credentials"}), 401
    else:
        return render_template('login.html', error="Неверный логин или пароль")

@app.route('/logout')
@login_required
def logout():
    log_audit(current_user.id, "logout")
    logout_user()
    return redirect(url_for('login_page'))

@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    if request.is_json:
        data = request.json
        amount = data.get('amount')
        category = data.get('category')
        description = data.get('description', '')
        return_json = True
    else:
        amount = request.form.get('amount')
        category = request.form.get('category')
        description = request.form.get('description', '')
        return_json = False
    
    if not amount or not category:
        if return_json:
            return jsonify({"error": "Amount and category required"}), 400
        else:
            return render_template('add.html', error="Заполните сумму и категорию")
    
    try:
        amount = float(amount)
        if amount <= 0:
            if return_json:
                return jsonify({"error": "Amount must be positive"}), 400
            else:
                return render_template('add.html', error="Сумма должна быть положительной")
    except ValueError:
        if return_json:
            return jsonify({"error": "Invalid amount"}), 400
        else:
            return render_template('add.html', error="Введите корректную сумму")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO expenses (user_id, amount, category, description)
        VALUES (%s, %s, %s, %s) RETURNING id
    """, (current_user.id, amount, category, description))
    
    expense_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    log_audit(current_user.id, "add", expense_id)
    
    if return_json:
        return jsonify({"message": "Expense added", "expense_id": expense_id}), 201
    else:
        return redirect(url_for('list_page'))

@app.route('/list', methods=['GET'])
@login_required
def list_expenses():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT * FROM expenses 
        WHERE user_id = %s 
        ORDER BY created_at DESC
    """, (current_user.id,))
    
    expenses = cur.fetchall()
    cur.close()
    conn.close()
    
    log_audit(current_user.id, "view_list")
    return jsonify({"expenses": expenses})

@app.route('/edit/<int:expense_id>', methods=['POST'])
@login_required
def edit_expense(expense_id):
    if request.is_json:
        data = request.json
        return_json = True
    else:
        data = request.form
        return_json = False
    
    amount = data.get('amount')
    category = data.get('category')
    description = data.get('description')
    
    # Проверка принадлежности записи пользователю
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id FROM expenses WHERE id = %s", (expense_id,))
    expense = cur.fetchone()
    
    if not expense or expense['user_id'] != current_user.id:
        cur.close()
        conn.close()
        if return_json:
            return jsonify({"error": "Not authorized"}), 403
        else:
            return redirect(url_for('list_page'))
    
    # ИСПРАВЛЕНИЕ SQL-INJECTION: 
    # Вместо динамического построения запроса f-string используем отдельные проверки
    
    try:
        # Вариант 1: Если переданы все поля
        if amount is not None and category is not None:
            amount_float = float(amount)
            if amount_float <= 0:
                raise ValueError("Amount must be positive")
            
            # Безопасный параметризованный запрос
            cur.execute("""
                UPDATE expenses 
                SET amount = %s, category = %s, description = %s 
                WHERE id = %s
            """, (amount_float, category, description, expense_id))
            
        # Вариант 2: Обновление только суммы
        elif amount is not None:
            amount_float = float(amount)
            if amount_float <= 0:
                raise ValueError("Amount must be positive")
            cur.execute("UPDATE expenses SET amount = %s WHERE id = %s", 
                       (amount_float, expense_id))
            
        # Вариант 3: Обновление только категории
        elif category is not None:
            cur.execute("UPDATE expenses SET category = %s WHERE id = %s", 
                       (category, expense_id))
            
        # Вариант 4: Обновление только описания
        elif description is not None:
            cur.execute("UPDATE expenses SET description = %s WHERE id = %s", 
                       (description, expense_id))
            
        else:
            if return_json:
                return jsonify({"error": "No fields to update"}), 400
            else:
                return redirect(url_for('list_page'))
        
        conn.commit()
        cur.close()
        conn.close()
        
        log_audit(current_user.id, "edit", expense_id)
        
        if return_json:
            return jsonify({"message": "Expense updated"})
        else:
            return redirect(url_for('list_page'))
            
    except ValueError as e:
        cur.close()
        conn.close()
        if return_json:
            return jsonify({"error": str(e)}), 400
        else:
            return redirect(url_for('list_page'))
    except Exception as e:
        cur.close()
        conn.close()
        if return_json:
            return jsonify({"error": "Server error"}), 500
        else:
            return redirect(url_for('list_page'))

@app.route('/delete/<int:expense_id>', methods=['POST'])
@login_required
def delete_expense(expense_id):
    # Проверка принадлежности
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id FROM expenses WHERE id = %s", (expense_id,))
    expense = cur.fetchone()
    
    if not expense or expense['user_id'] != current_user.id:
        cur.close()
        conn.close()
        return jsonify({"error": "Not authorized"}), 403
    
    cur.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    log_audit(current_user.id, "delete", expense_id)
    return jsonify({"message": "Expense deleted"})

@app.route('/audit', methods=['GET'])
@login_required
def get_audit():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT * FROM audit_log 
        WHERE user_id = %s 
        ORDER BY action_time DESC
    """, (current_user.id,))
    
    audit_logs = cur.fetchall()
    cur.close()
    conn.close()
    
    return jsonify({"audit_logs": audit_logs})


@app.route('/edit_page/<int:expense_id>')
@login_required
def edit_page(expense_id):
    """Страница редактирования расхода"""
    # Проверка принадлежности
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM expenses WHERE id = %s", (expense_id,))
    expense = cur.fetchone()
    cur.close()
    conn.close()
    
    if not expense or expense['user_id'] != current_user.id:
        return redirect(url_for('list_page'))
    
    return render_template('edit.html', expense=expense)

@app.route('/update_expense/<int:expense_id>', methods=['POST'])
@login_required
def update_expense(expense_id):
    """Обновление расхода через HTML форму"""
    # Проверка принадлежности
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id FROM expenses WHERE id = %s", (expense_id,))
    expense = cur.fetchone()
    
    if not expense or expense['user_id'] != current_user.id:
        cur.close()
        conn.close()
        return redirect(url_for('list_page'))
    
    # Получаем данные из формы
    amount = request.form.get('amount')
    category = request.form.get('category')
    description = request.form.get('description', '')
    
    # Проверяем данные
    if not amount or not category:
        return redirect(url_for('edit_page', expense_id=expense_id))
    
    try:
        amount = float(amount)
        if amount <= 0:
            return redirect(url_for('edit_page', expense_id=expense_id))
    except ValueError:
        return redirect(url_for('edit_page', expense_id=expense_id))
    
    # Обновляем запись
    cur.execute("""
        UPDATE expenses 
        SET amount = %s, category = %s, description = %s
        WHERE id = %s
    """, (amount, category, description, expense_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    log_audit(current_user.id, "edit", expense_id)
    return redirect(url_for('list_page'))

@app.route('/delete_html/<int:expense_id>', methods=['POST'])
@login_required
def delete_html(expense_id):
    """Удаление расхода для HTML (перенаправляет обратно)"""
    # Проверка принадлежности
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT user_id FROM expenses WHERE id = %s", (expense_id,))
    expense = cur.fetchone()
    
    if not expense or expense['user_id'] != current_user.id:
        cur.close()
        conn.close()
        return redirect(url_for('list_page'))
    
    cur.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    log_audit(current_user.id, "delete", expense_id)
    return redirect(url_for('list_page')) 

if __name__ == '__main__':
    from models import create_tables
    create_tables()
    app.run(debug=False)
