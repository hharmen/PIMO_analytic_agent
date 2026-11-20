# Развёртывание на сервере (показ команде и экспертам)

Временный стенд на Ubuntu 22.04 без домена. Наружу открыт только Caddy (порты 80 и 443),
он сам получает HTTPS-сертификат Let's Encrypt. Остальные сервисы (core, checker, file_service,
MinIO, PostgreSQL) доступны только внутри Docker-сети.

Домена нет - используем [sslip.io](https://sslip.io): адрес `203-0-113-5.sslip.io` указывает на IP
`203.0.113.5`. На такой адрес Let's Encrypt выдаёт обычный сертификат.

## 1. Docker

**Если на сервере есть VPN или другие сервисы - файрвол (ufw, iptables) не трогать.** Включённый ufw
с правилами только для SSH/80/443 закроет порт VPN.

Docker при установке меняет iptables и может выставить политику `FORWARD DROP` - тогда VPN-клиенты
теряют интернет через сервер. Поэтому до установки:

```bash
sudo mkdir -p /etc/docker
echo '{ "ip-forward-no-drop": true }' | sudo tee /etc/docker/daemon.json
```

Затем, если Docker ещё не установлен (`docker --version`):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # затем перелогиниться
```

Порты 80 и 443 должны быть свободны (`sudo ss -ltnp | grep -E ':(80|443)\s'`) и открыты у облачного
провайдера (группа безопасности). Порт 80 нужен Let's Encrypt для проверки адреса.

## 2. Код и настройки

```bash
git clone https://github.com/hharmen/PIMO_analytic_agent.git
cd PIMO_analytic_agent
cp deploy/.env.example .env
nano .env
```

В `.env`:
- `SITE_ADDRESS` - IP сервера через sslip.io, точки заменить на дефисы;
- `JWT_SECRET`, `POSTGRES_PASSWORD`, `MINIO_PASSWORD` - сгенерировать `openssl rand -hex 32`;
- `LLM_API_KEY` - ключ LLM МАИ.

Без этих значений стек не запустится и напишет, чего не хватает. Core в режиме production
не стартует со слабым `JWT_SECRET`. Пароль PostgreSQL применяется при первом запуске
(когда база создаётся); менять его потом в `.env` бесполезно.

## 3. Запуск

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Сайт: `https://<SITE_ADDRESS>`. Первый запрос может идти несколько секунд, пока Caddy получает сертификат.

Назначить себе администратора (сначала зарегистрироваться на сайте):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec core python -m app.admin.cli grant you@example.com
```

Регистрация открыта. Лишние аккаунты блокируются в админ-панели (`/#/admin`):
каждый запрос к агенту тратит ключ LLM МАИ.

## Обновление и остановка

```bash
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f core   # логи
docker compose -f docker-compose.yml -f docker-compose.prod.yml down           # остановить, данные остаются
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v        # удалить всё вместе с данными
```

Чтобы не писать оба `-f` каждый раз: `export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml`.
