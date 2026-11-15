# Лабораторна робота №10 — Flask + Gunicorn + Nginx (Docker Compose)

Багатоконтейнерне середовище: `backend` (Flask + Gunicorn, SQLite у змонтованому каталозі `data/`)
та `nginx` (реверс-проксі, єдина точка входу). Сервіси з'єднані мережею `web`.

## Вимоги
- Docker Engine та Docker Compose v2 (`docker info`, `docker compose version`)
- Bash (Linux / WSL), `curl`

## Підготовка
```bash
cp .env.example .env
# згенерувати ключ і вписати його в .env після SECRET_KEY=
python3 -c 'import secrets; print(secrets.token_hex(32))'
mkdir -p data
```
Схема БД створюється застосунком автоматично (`CREATE TABLE IF NOT EXISTS`), наявні записи не очищуються.

## Запуск
```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps -a
docker compose logs --tail=50 backend nginx
docker compose exec nginx nginx -t
curl -i http://127.0.0.1:8080/health
```
Застосунок: <http://127.0.0.1:8080/> (опублікований лише порт Nginx, лише на localhost).

## Зупинка
```bash
docker compose stop          # зупинити
docker compose down          # видалити контейнери та мережу (дані в ./data лишаються)
```

## Перевірка готовності та відновлення після відмови
```bash
docker compose stop backend
curl -i http://127.0.0.1:8080/health     # очікується 502 Bad Gateway
docker compose logs --tail=30 nginx
docker compose start backend
docker compose ps -a                     # дочекатися healthy
docker compose exec nginx nginx -s reload   # (після nginx -t) оновити адресу backend
curl -i http://127.0.0.1:8080/health     # 200 {"status":"ok"}
```

## Перевірка збереження даних
1. Зареєструватися, увійти, створити нотатку на `/notes`.
2. `docker compose down && docker compose up -d`
3. Увійти знову — нотатка має бути на місці.

## Podman
Замінити `docker compose` на `podman compose`; на SELinux-системах додати `:Z` до bind mount `./data`.
