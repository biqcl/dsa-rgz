import pytest
from app import app
import json
import psycopg2

# Конфигурация базы данных для тестов (такая же как в app.py)
TEST_DB_CONFIG = {
    "dbname": "expense_diary",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": "5432"
}

def create_test_tables():
    """Создает таблицы для тестов (очищает и создает заново)"""
    try:
        conn = psycopg2.connect(**TEST_DB_CONFIG)
        cur = conn.cursor()
        
        # Очищаем существующие таблицы
        cur.execute("DROP TABLE IF EXISTS audit_log CASCADE")
        cur.execute("DROP TABLE IF EXISTS expenses CASCADE")
        cur.execute("DROP TABLE IF EXISTS users CASCADE")
        
        # Создаем таблицы заново
        cur.execute("""
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
        """)
        
        cur.execute("""
            CREATE TABLE expenses (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                amount DECIMAL(10,2) NOT NULL,
                category VARCHAR(50) NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE audit_log (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                action_type VARCHAR(20) NOT NULL,
                record_id INTEGER,
                action_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Тестовые таблицы созданы")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка создания тестовых таблиц: {e}")
        return False

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Фикстура: создает таблицы перед всеми тестами"""
    print("\n🔧 Настраиваю тестовую базу данных...")
    success = create_test_tables()
    if not success:
        pytest.exit("Не удалось создать тестовые таблицы")
    yield
    print("\n🧹 Тесты завершены, база очищена")

@pytest.fixture
def client():
    """Фикстура для тестового клиента Flask"""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            yield client

# ========== ТЕСТЫ ==========

def test_register(client):
    """Тест регистрации пользователя"""
    response = client.post('/register', json={
        'username': 'testuser1',
        'password': 'password123'
    })
    
    # Проверяем успешную регистрацию
    assert response.status_code == 201
    data = json.loads(response.data)
    assert 'message' in data
    assert 'user_id' in data
    print(f"✅ Пользователь зарегистрирован: ID {data['user_id']}")

def test_register_duplicate(client):
    """Тест регистрации с существующим именем"""
    # Первая регистрация
    client.post('/register', json={
        'username': 'duplicateuser',
        'password': 'password123'
    })
    
    # Вторая попытка с тем же именем
    response = client.post('/register', json={
        'username': 'duplicateuser',
        'password': 'password456'
    })
    
    # Должна быть ошибка
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    print("✅ Дубликат пользователя корректно отклонен")

def test_login(client):
    """Тест входа пользователя"""
    # Сначала регистрируем
    client.post('/register', json={
        'username': 'loginuser',
        'password': 'mypassword'
    })
    
    # Пытаемся войти
    response = client.post('/login', json={
        'username': 'loginuser',
        'password': 'mypassword'
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['message'] == 'Logged in'
    print("✅ Вход выполнен успешно")

def test_login_wrong_password(client):
    """Тест входа с неверным паролем"""
    client.post('/register', json={
        'username': 'wrongpassuser',
        'password': 'correct123'
    })
    
    response = client.post('/login', json={
        'username': 'wrongpassuser',
        'password': 'wrongpassword'
    })
    
    assert response.status_code == 401
    data = json.loads(response.data)
    assert 'error' in data
    print("✅ Неверный пароль корректно отклонен")

def test_add_expense(client):
    """Тест добавления расхода"""
    # Сначала регистрируем и логиним
    client.post('/register', json={
        'username': 'expenseuser',
        'password': 'expensepass'
    })
    
    response = client.post('/add', json={
        'amount': 1500.75,
        'category': 'Food',
        'description': 'Продукты на неделю'
    })
    
    assert response.status_code == 201
    data = json.loads(response.data)
    assert 'message' in data
    assert 'expense_id' in data
    print(f"✅ Расход добавлен: ID {data['expense_id']}")

def test_add_expense_invalid(client):
    """Тест добавления расхода с некорректными данными"""
    client.post('/register', json={
        'username': 'invaliduser',
        'password': 'password123'
    })
    
    # Пытаемся добавить расход без обязательных полей
    response = client.post('/add', json={
        'amount': 0,  # Неположительная сумма
        'category': ''
    })
    
    assert response.status_code == 400
    print("✅ Некорректный расход отклонен")

def test_list_expenses(client):
    """Тест получения списка расходов"""
    # Сначала регистрируем
    client.post('/register', json={
        'username': 'listuser',
        'password': 'listpass'
    })
    
    # Добавляем несколько расходов
    client.post('/add', json={'amount': 100, 'category': 'Food'})
    client.post('/add', json={'amount': 200, 'category': 'Transport'})
    
    # Получаем список
    response = client.get('/list')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'expenses' in data
    assert len(data['expenses']) == 2
    print(f"✅ Получено {len(data['expenses'])} расходов")

def test_edit_expense(client):
    """Тест редактирования расхода"""
    # Регистрируем и добавляем расход
    client.post('/register', json={
        'username': 'edituser',
        'password': 'editpass'
    })
    
    add_response = client.post('/add', json={
        'amount': 1000,
        'category': 'Food',
        'description': 'Обед'
    })
    expense_id = json.loads(add_response.data)['expense_id']
    
    # Редактируем
    response = client.post(f'/edit/{expense_id}', json={
        'amount': 1200,
        'category': 'Restaurant',
        'description': 'Ужин в ресторане'
    })
    
    assert response.status_code == 200
    print("✅ Расход успешно отредактирован")

def test_delete_expense(client):
    """Тест удаления расхода"""
    client.post('/register', json={
        'username': 'deleteuser',
        'password': 'deletepass'
    })
    
    add_response = client.post('/add', json={
        'amount': 500,
        'category': 'Shopping'
    })
    expense_id = json.loads(add_response.data)['expense_id']
    
    # Удаляем
    response = client.post(f'/delete/{expense_id}')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['message'] == 'Expense deleted'
    print("✅ Расход успешно удален")

def test_audit_log(client):
    """Тест получения логов аудита"""
    client.post('/register', json={
        'username': 'audituser',
        'password': 'auditpass'
    })
    
    # Добавляем расход чтобы создать запись в аудите
    client.post('/add', json={'amount': 300, 'category': 'Test'})
    
    # Получаем логи
    response = client.get('/audit')
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'audit_logs' in data
    # Должна быть хотя бы одна запись (регистрация + добавление)
    assert len(data['audit_logs']) >= 1
    print(f"✅ Получено {len(data['audit_logs'])} записей аудита")

def test_unauthorized_access(client):
    """Тест доступа без авторизации"""
    # Пытаемся получить список без входа
    response = client.get('/list')
    assert response.status_code == 401  # Unauthorized
    print("✅ Неавторизованный доступ корректно отклонен")

if __name__ == '__main__':
    # Для запуска тестов напрямую
    pytest.main([__file__, '-v'])
    