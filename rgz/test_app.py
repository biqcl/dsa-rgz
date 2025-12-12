# test_app.py
import pytest
import os
import sys
from app import app
import json

# Добавляем путь к текущей директории
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            yield client

def test_register(client):
    """Тест регистрации пользователя"""
    response = client.post('/register', json={
        'username': 'testuser123',
        'password': 'password123'
    })
    # Должен вернуть 201 (создан) или 400 (уже существует)
    assert response.status_code in [201, 400]
    if response.status_code == 201:
        data = json.loads(response.data)
        assert 'message' in data
        assert 'user_id' in data

def test_login(client):
    """Тест входа пользователя"""
    # Сначала регистрируем пользователя
    client.post('/register', json={
        'username': 'loginuser456',
        'password': 'loginpass456'
    })
    
    # Пытаемся войти
    response = client.post('/login', json={
        'username': 'loginuser456',
        'password': 'loginpass456'
    })
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'message' in data

def test_add_expense(client):
    """Тест добавления расхода"""
    # Сначала регистрируем и логиним
    client.post('/register', json={
        'username': 'expenseuser789',
        'password': 'expensepass789'
    })
    
    response = client.post('/add', json={
        'amount': 100.50,
        'category': 'Food',
        'description': 'Lunch'
    })
    assert response.status_code == 201
    data = json.loads(response.data)
    assert 'message' in data
    assert 'expense_id' in data

def test_list_expenses(client):
    """Тест получения списка расходов"""
    response = client.get('/list')
    # Может вернуть 401 (не авторизован) или 200
    assert response.status_code in [200, 401]

if __name__ == '__main__':
    pytest.main([__file__, '-v'])