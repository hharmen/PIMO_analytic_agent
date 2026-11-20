from datetime import datetime, timezone
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.admin.cli import change_admin_role
from app.auth.security import JWT_ALGORITHM, JWT_SECRET
from app.db.migrations import add_user_access_flags
from app.db.models import AdminAudit, Chat, CheckRun, Message, User
from app.db.session import Base, SessionLocal
from tests.conftest import register_and_login


def account(client, admin=False, email=None):
    email = email or f"{uuid4().hex}@example.com"
    headers = register_and_login(client, email)
    user_id = client.get('/auth/me', headers=headers).json()['id']
    if admin:
        with SessionLocal() as db:
            db.get(User, user_id).is_admin = True
            db.commit()
    return headers, user_id, email


@pytest.mark.parametrize('path', ['/admin/summary', '/admin/users', '/admin/audit'])
def test_admin_endpoints_require_server_verified_admin(client, path):
    assert client.get(path).status_code == 401
    headers, user_id, _ = account(client)
    assert client.get(path, headers=headers).status_code == 403
    payload = jwt.decode(headers['Authorization'].split()[1], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    token = jwt.encode({**payload, 'is_admin': True, 'role': 'admin'}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert client.get(path, headers={'Authorization': f'Bearer {token}'}).status_code == 403
    admin_headers, _, _ = account(client, admin=True)
    assert client.get(path, headers=admin_headers).status_code == 200


def test_registration_cannot_assign_privileges(client):
    body = {'email': f'{uuid4().hex}@example.com', 'password': 'password123', 'is_admin': True}
    assert client.post('/auth/register', json=body).status_code == 422
    del body['is_admin']
    result = client.post('/auth/register', json=body)
    assert result.status_code == 201
    assert result.json()['is_admin'] is False and result.json()['is_active'] is True


def test_user_search_pagination_counts_and_private_data(client):
    admin, _, _ = account(client, admin=True)
    prefix = uuid4().hex
    _, first_id, first_email = account(client, email=f'{prefix}.first@example.com')
    _, second_id, _ = account(client, email=f'{prefix}.second@example.com')
    before = client.get('/admin/summary', headers=admin).json()
    with SessionLocal() as db:
        chats = [Chat(user_id=first_id, title='PRIVATE CHAT'), Chat(user_id=first_id, title='OTHER PRIVATE CHAT')]
        db.add_all(chats); db.flush()
        db.add_all([Message(chat_id=chats[0].id, role='user', content='SECRET REQUIREMENTS'),
                    Message(chat_id=chats[0].id, role='assistant', content='SECRET ANSWER'),
                    Message(chat_id=chats[1].id, role='user', content='ANOTHER SECRET')])
        db.add_all([CheckRun(chat_id=chats[0].id, model_json={}, result_json={}, status='PROPERTY_HOLDS'),
                    CheckRun(chat_id=chats[0].id, model_json={}, result_json={}, status='PROPERTY_VIOLATED')])
        db.commit()
        private_chat_id = chats[0].id
    response = client.get('/admin/users', headers=admin, params={'q': prefix, 'limit': 1})
    assert response.status_code == 200
    assert response.json()['total'] == 2 and response.json()['items'][0]['id'] == second_id
    result = client.get('/admin/users', headers=admin, params={'q': prefix, 'limit': 1, 'offset': 1}).json()['items'][0]
    assert result['email'] == first_email
    assert (result['chat_count'], result['message_count'], result['check_count']) == (2, 3, 2)
    assert result['last_activity_at'] is not None
    assert 'password_hash' not in result and 'password' not in result
    assert 'SECRET' not in str(result) and 'PRIVATE CHAT' not in str(result)
    after = client.get('/admin/summary', headers=admin).json()
    assert after['chats'] - before['chats'] == 2
    assert after['messages'] - before['messages'] == 3
    assert after['checks'] - before['checks'] == 2
    assert client.get(f'/chats/{private_chat_id}/messages', headers=admin).status_code == 404


def test_blocking_preserves_history_enforces_access_and_records_audit(client):
    admin, admin_id, _ = account(client, admin=True)
    member, user_id, email = account(client)
    chat = client.post('/chats', headers=member).json()
    endpoint = f'/admin/users/{user_id}'
    assert client.patch(endpoint, headers=member, json={'is_active': False}).status_code == 403
    blocked = client.patch(endpoint, headers=admin, json={'is_active': False})
    assert blocked.status_code == 200 and blocked.json()['is_active'] is False
    client.patch(endpoint, headers=admin, json={'is_active': False})  # idempotent; no duplicate log
    for path in ['/auth/me', '/chats', f'/chats/{chat["id"]}/messages']:
        response = client.get(path, headers=member)
        assert response.status_code == 401 and response.json()['detail']['code'] == 'account_blocked'
    login = client.post('/auth/login', json={'email': email, 'password': 'password123'})
    assert login.status_code == 401 and login.json()['detail']['code'] == 'account_blocked'
    wrong = client.post('/auth/login', json={'email': email, 'password': 'wrong-password'})
    assert wrong.status_code == 401 and wrong.json()['detail'] == 'Неверный email или пароль'
    blocked_list = client.get('/admin/users', headers=admin, params={'q': email, 'state': 'blocked'}).json()
    assert blocked_list['total'] == 1
    assert client.patch(endpoint, headers=admin, json={'is_active': True}).status_code == 200
    assert client.post('/auth/login', json={'email': email, 'password': 'password123'}).status_code == 200
    assert client.get('/chats', headers=member).json()[0]['id'] == chat['id']
    audit = client.get('/admin/audit', headers=admin).json()['items']
    events = [item for item in audit if item['target_id'] == user_id]
    assert [item['action'] for item in events] == ['unblock_user', 'block_user']
    assert all(item['actor_id'] == admin_id for item in events)


def test_admins_are_protected_and_role_updates_are_not_exposed(client):
    admin, user_id, _ = account(client, admin=True)
    _, other_id, _ = account(client, admin=True)
    assert client.patch(f'/admin/users/{user_id}', headers=admin, json={'is_active': False}).status_code == 409
    assert client.patch(f'/admin/users/{other_id}', headers=admin, json={'is_active': False}).status_code == 409
    _, member_id, _ = account(client)
    assert client.patch(f'/admin/users/{member_id}', headers=admin, json={'is_active': True, 'is_admin': True}).status_code == 422
    assert client.patch(f'/admin/users/{member_id}', headers=admin, json={'is_active': 'false'}).status_code == 422
    assert client.patch('/admin/users/2147483647', headers=admin, json={'is_active': False}).status_code == 404


def test_revoking_role_takes_effect_for_existing_jwt(client):
    admin, user_id, _ = account(client, admin=True)
    assert client.get('/admin/users', headers=admin).status_code == 200
    with SessionLocal() as db:
        db.get(User, user_id).is_admin = False
        db.commit()
    assert client.get('/auth/me', headers=admin).status_code == 200
    assert client.get('/admin/users', headers=admin).status_code == 403


def test_search_escapes_wildcards_and_validates_paging(client):
    admin, _, _ = account(client, admin=True)
    email = f'pct%_{uuid4().hex}@example.com'
    account(client, email=email)
    response = client.get('/admin/users', headers=admin, params={'q': '%_'})
    assert response.json()['total'] == 1 and response.json()['items'][0]['email'] == email
    for params in [{'limit': 101}, {'limit': 0}, {'offset': -1}, {'state': 'unknown'}]:
        assert client.get('/admin/users', headers=admin, params=params).status_code == 422


def test_existing_sqlite_database_migrates_without_data_loss_and_keeps_old_inserts_working():
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT, created_at DATETIME)'))
        connection.execute(text("INSERT INTO users VALUES (1, 'legacy@example.com', 'existing-hash', '2026-11-20')"))
        add_user_access_flags(connection)
        add_user_access_flags(connection)
        row = connection.execute(text('SELECT email, password_hash, is_admin, is_active FROM users')).one()
        assert tuple(row) == ('legacy@example.com', 'existing-hash', 0, 1)
        connection.execute(text("INSERT INTO users (id, email, password_hash) VALUES (2, 'older-code@example.com', 'hash')"))
        assert tuple(connection.execute(text('SELECT is_admin, is_active FROM users WHERE id=2')).one()) == (0, 1)
    engine.dispose()


def test_cli_grants_and_revokes_roles_but_protects_the_last_admin():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        users = [User(email='first@example.com', password_hash='hash'), User(email='second@example.com', password_hash='hash')]
        db.add_all(users); db.commit()
        change_admin_role(db, ' FIRST@example.com ', True)
        with pytest.raises(ValueError, match='последнего'):
            change_admin_role(db, users[0].email, False)
        change_admin_role(db, users[1].email, True)
        change_admin_role(db, users[0].email, False)
        assert users[0].is_admin is False and users[1].is_admin is True
        assert db.scalar(select(func.count()).select_from(AdminAudit)) == 3
        with pytest.raises(ValueError, match='не найден'):
            change_admin_role(db, 'missing@example.com', True)
        users[0].is_active = False; db.commit()
        with pytest.raises(ValueError, match='Заблокированный'):
            change_admin_role(db, users[0].email, True)
    engine.dispose()
