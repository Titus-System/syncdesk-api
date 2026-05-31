# SyncDesk API

Backend e API Gateway da plataforma SyncDesk, desenvolvido com FastAPI, Python, PostgreSQL, MongoDB e Docker.

A API centraliza os principais recursos da plataforma, incluindo autenticação, usuários, permissões, empresas, produtos, chamados, chat, chatbot, arquivos, notificações, métricas e integrações de infraestrutura.

## Repositório

```text
https://github.com/Titus-System/syncdesk-api
```

## Tecnologias

| Tecnologia | Uso |
| --- | --- |
| Python 3.12+ | Linguagem principal do backend |
| FastAPI | Framework da API |
| Uvicorn | Servidor ASGI para execução local |
| Poetry | Gerenciamento de dependências Python |
| SQLAlchemy 2 Async | ORM e acesso assíncrono ao PostgreSQL |
| PostgreSQL | Banco relacional principal |
| Alembic | Controle de migrations do PostgreSQL |
| MongoDB | Banco usado por recursos como chat e conversas |
| Motor / Beanie | Integração assíncrona com MongoDB |
| JWT | Autenticação e autorização |
| Passlib / Argon2 | Hash de senhas |
| WebSocket | Comunicação em tempo real |
| MinIO / S3 | Armazenamento de arquivos |
| Resend | Envio de e-mails |
| Prometheus | Coleta de métricas |
| Grafana | Visualização de métricas |
| Loki / Promtail | Logs centralizados |
| Docker | Containerização |
| Docker Compose | Orquestração local dos serviços |
| pytest | Testes automatizados |
| Ruff, Bandit e mypy | Qualidade, segurança e tipagem |

## Estrutura do projeto

```text
app/
|-- api/
|-- core/
|-- db/
|   |-- mongo/
|   `-- postgres/
|-- domains/
|   |-- auth/
|   |-- chatbot/
|   |-- companies/
|   |-- files/
|   |-- health/
|   |-- live_chat/
|   |-- notifications/
|   |-- products/
|   `-- ticket/
|-- infra/
|-- schemas/
|-- seed/
`-- main.py

alembic/
|-- versions/
`-- env.py

deploy/
|-- alertmanager/
|-- grafana/
|-- loki/
|-- prometheus/
|-- promtail/
`-- Dockerfile

docs/
tests/
scripts/
logs/
```

| Pasta | Responsabilidade |
| --- | --- |
| `app/api/` | Roteador principal da API |
| `app/core/` | Configurações globais, segurança, logs, métricas, middlewares e storage |
| `app/db/` | Configuração e dependências de banco para PostgreSQL e MongoDB |
| `app/domains/` | Módulos de negócio organizados por domínio |
| `app/infra/` | Integrações externas, como e-mail e storage S3 |
| `app/schemas/` | Schemas compartilhados |
| `app/seed/` | Scripts de seed para dados iniciais |
| `alembic/` | Migrations do PostgreSQL |
| `deploy/` | Arquivos de Docker, observabilidade e deploy |
| `tests/` | Testes automatizados |
| `docs/` | Documentações auxiliares da API |

## Pré-requisitos

- Python 3.12+
- Poetry
- Docker
- Docker Compose
- PostgreSQL
- MongoDB
- MinIO, quando forem usados recursos de arquivos
- Arquivo `.env` configurado

Para desenvolvimento local, o fluxo recomendado é executar a API com Poetry e subir PostgreSQL/MongoDB via Docker.

## Instalação e execução local

Clone o repositório:

```bash
git clone https://github.com/Titus-System/syncdesk-api.git
cd syncdesk-api
```

Instale as dependências:

```bash
poetry install
```

Crie o arquivo de ambiente:

```bash
cp .env.example .env
```

No Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Revise as variáveis do arquivo `.env`.

Suba os bancos com Docker:

```bash
docker compose up -d db mongo
```

Caso utilize recursos de arquivos, suba também o MinIO, se ele estiver disponível no `docker-compose.yaml`:

```bash
docker compose up -d db mongo minio
```

Aplique as migrations, se necessário:

```bash
poetry run alembic upgrade head
```

Na primeira execução, rode o seed:

```bash
poetry run python -m app.seed.run_seed
```

Execute a API localmente:

```bash
poetry run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

A API ficará disponível em:

```text
http://localhost:8000
```

Documentação Swagger:

```text
http://localhost:8000/docs
```

Documentação ReDoc:

```text
http://localhost:8000/redoc
```

## Variáveis de ambiente

O projeto usa um arquivo `.env` na raiz do projeto.

Antes de executar a API, copie o `.env.example` para `.env` e revise as variáveis conforme o ambiente local.

Exemplo baseado no `.env.example`:

```env
PROJECT_NAME=syncdesk_api
PROJECT_DESCRIPTION=Backend e API GATEWAY para o projeto SyncDesk
PROJECT_VERSION=1.0.0

ENVIRONMENT=development

WEB_FRONTEND_URL=http://localhost:3000
MOBILE_FRONTEND_URL=syncdesk://

CORS_ALLOW_ORIGINS=["https://app.example.com","http://localhost:3000"]
CORS_ALLOW_CREDENTIALS=False
CORS_ALLOW_METHODS=["GET","POST","PUT","PATCH","DELETE"]
CORS_ALLOW_HEADERS=["Authorization","Content-Type"]

POSTGRES_USER=syncdesk_user
POSTGRES_PASSWORD=supersecretpassword
POSTGRES_DB=syncdesk_db
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

MONGO_INITDB_ROOT_USERNAME=mongouser
MONGO_INITDB_ROOT_PASSWORD=mongopassword
MONGO_USER=mongouser
MONGO_PASSWORD=mongopassword
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB=syncdesk_db

JWT_SECRET_KEY=sua_chave_secreta_aqui
ACCESS_TOKEN_SIGNING_KEY=your_access_token_siging_key
REFRESH_TOKEN_SIGNING_KEY=your_refresh_token_siging_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
SESSION_EXPIRE_DAYS=180

DEFAULT_ROLE_NAME=user

MAX_CHAT_MESSAGE_CONTENT_SIZE=2000

PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=30
INVITE_TOKEN_EXPIRE_HOURS=72

RESET_TOKEN_HMAC_SECRET=your-very-secret-token

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
S3_ENDPOINT_URL=http://localhost:9000
S3_PUBLIC_ENDPOINT_URL=http://localhost:9000
S3_REGION=us-east-1
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_DEFAULT=syncdesk-files
S3_PRESIGNED_UPLOAD_EXPIRES_SECONDS=300
S3_PRESIGNED_DOWNLOAD_EXPIRES_SECONDS=300
S3_CORS_ALLOWED_ORIGINS=*

RESEND_API_KEY=your-resend-api-key
RESEND_FROM_EMAIL=no_reply@syncdesk.pro
RUN_RESEND_INTEGRATION_TESTS=False
RESEND_TEST_TO_EMAIL=
```

Principais variáveis:

| Variável | Descrição |
| --- | --- |
| `ENVIRONMENT` | Ambiente da aplicação |
| `WEB_FRONTEND_URL` | URL do frontend web |
| `MOBILE_FRONTEND_URL` | URL ou deep link do app mobile |
| `CORS_ALLOW_ORIGINS` | Origens permitidas para chamadas CORS |
| `POSTGRES_USER` | Usuário do PostgreSQL |
| `POSTGRES_PASSWORD` | Senha do PostgreSQL |
| `POSTGRES_DB` | Nome do banco PostgreSQL |
| `POSTGRES_HOST` | Host do PostgreSQL |
| `POSTGRES_PORT` | Porta do PostgreSQL |
| `MONGO_USER` | Usuário do MongoDB |
| `MONGO_PASSWORD` | Senha do MongoDB |
| `MONGO_HOST` | Host do MongoDB |
| `MONGO_PORT` | Porta do MongoDB |
| `MONGO_DB` | Nome do banco MongoDB |
| `JWT_SECRET_KEY` | Chave secreta usada pelo JWT |
| `ACCESS_TOKEN_SIGNING_KEY` | Chave de assinatura do access token |
| `REFRESH_TOKEN_SIGNING_KEY` | Chave de assinatura do refresh token |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Tempo de expiração do access token |
| `SESSION_EXPIRE_DAYS` | Duração da sessão |
| `S3_ENDPOINT_URL` | Endpoint interno do MinIO/S3 |
| `S3_PUBLIC_ENDPOINT_URL` | Endpoint público do MinIO/S3 |
| `S3_BUCKET_DEFAULT` | Bucket padrão para arquivos |
| `RESEND_API_KEY` | Chave da integração com Resend |
| `RESEND_FROM_EMAIL` | E-mail remetente usado pela aplicação |

## Execução com Docker Compose

Também é possível executar a API, os bancos e os serviços auxiliares via Docker Compose.

Crie o arquivo `.env`:

```bash
cp .env.example .env
```

No Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Suba todos os serviços:

```bash
docker compose up --build
```

Ou em segundo plano:

```bash
docker compose up -d --build
```

Verifique os logs da API:

```bash
docker compose logs -f api
```

Pare os serviços:

```bash
docker compose down
```

Para parar os serviços e remover os volumes locais:

```bash
docker compose down -v
```

Use `docker compose down -v` apenas quando puder apagar os dados locais dos bancos.

## Comandos úteis

| Comando | Descrição |
| --- | --- |
| `poetry install` | Instala as dependências do projeto |
| `poetry run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload` | Executa a API localmente com reload |
| `poetry run python -m app.seed.run_seed` | Executa o seed inicial |
| `poetry run alembic upgrade head` | Aplica migrations pendentes |
| `poetry run pytest` | Executa os testes |
| `poetry run ruff check .` | Executa lint com Ruff |
| `docker compose up -d db mongo` | Sobe PostgreSQL e MongoDB |
| `docker compose up -d --build` | Sobe todos os serviços em background |
| `docker compose logs -f api` | Exibe logs da API |
| `docker compose down` | Para os containers |
| `docker compose down -v` | Para containers e remove volumes |

## Documentação da API

Com a API em execução, acesse:

```text
http://localhost:8000/docs
```

A documentação interativa permite visualizar e testar os endpoints diretamente pelo navegador.

## Principais áreas da API

Os endpoints principais ficam abaixo do prefixo:

```text
/api
```

| Área | Descrição |
| --- | --- |
| `/api/auth` | Login, registro, refresh token, logout e usuário atual |
| `/api/users` | Gestão de usuários |
| `/api/roles` | Gestão de papéis |
| `/api/permissions` | Gestão de permissões |
| `/api/tickets` | Gestão de chamados |
| `/api/live-chat` | Conversas e chat em tempo real |
| `/api/chatbot` | Fluxos de chatbot e triagem |
| `/api/products` | Gestão de produtos |
| `/api/companies` | Gestão de empresas |
| `/api/files` | Upload, download e gestão de arquivos |

## Banco de dados

A aplicação utiliza dois bancos:

| Banco | Uso |
| --- | --- |
| PostgreSQL | Dados relacionais, autenticação, usuários, permissões, tickets e entidades principais |
| MongoDB | Dados não relacionais, conversas, mensagens e recursos relacionados a chat |

O PostgreSQL usa migrations com Alembic.

Para aplicar migrations:

```bash
poetry run alembic upgrade head
```

O seed inicial deve ser executado na primeira configuração do ambiente:

```bash
poetry run python -m app.seed.run_seed
```

## Armazenamento de arquivos

Recursos de arquivos usam MinIO/S3.

Variáveis principais:

```env
S3_ENDPOINT_URL=http://localhost:9000
S3_PUBLIC_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_DEFAULT=syncdesk-files
```

Caso o projeto seja executado totalmente via Docker, confirme no `docker-compose.yaml` quais portas e nomes de serviços estão sendo usados.

## Testes

Para rodar os testes:

```bash
poetry run pytest
```

Para rodar um arquivo específico:

```bash
poetry run pytest tests/caminho/do/teste.py
```

## Observações para Windows

Ao rodar localmente no Windows, verifique principalmente:

- IP usado pelo app mobile
- Porta da API
- Firewall
- Containers ativos
- Variáveis do `.env`

A API deve ser executada com:

```bash
--host 0.0.0.0 --port 8000
```

Isso permite acesso por outros dispositivos ou pelo emulador Android.

Para o mobile no Android Emulator:

```env
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000/api
```

Para celular físico na mesma rede:

```env
EXPO_PUBLIC_API_BASE_URL=http://SEU_IP_LOCAL:8000/api
```

Para descobrir o IP no Windows:

```powershell
ipconfig
```

Se o app não conseguir acessar a API, verifique se o firewall permite conexões na porta `8000`.

## Solução de problemas

### A API não sobe

Verifique se as dependências foram instaladas:

```bash
poetry install
```

Confirme se o arquivo `.env` existe na raiz do projeto.

Verifique se PostgreSQL e MongoDB estão rodando:

```bash
docker compose ps
```

### Erro de conexão com PostgreSQL

Verifique as variáveis:

```env
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
POSTGRES_HOST=
POSTGRES_PORT=
```

Se a API estiver rodando localmente com Poetry e os bancos estiverem no Docker, normalmente o host deve ser:

```env
POSTGRES_HOST=localhost
```

### Erro de conexão com MongoDB

Verifique as variáveis:

```env
MONGO_USER=
MONGO_PASSWORD=
MONGO_HOST=
MONGO_PORT=
MONGO_DB=
```

Se as credenciais foram alteradas depois da criação do volume, recrie os volumes:

```bash
docker compose down -v
docker compose up -d db mongo
```

Depois rode novamente o seed:

```bash
poetry run python -m app.seed.run_seed
```

### Seed falha por falta de tabela

Rode as migrations:

```bash
poetry run alembic upgrade head
```

Depois execute novamente:

```bash
poetry run python -m app.seed.run_seed
```

### Porta 8000 já está em uso

Use outra porta:

```bash
poetry run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8001 --reload
```

Se mudar a porta da API, ajuste também a URL no frontend web ou mobile.

### Mobile não acessa a API local

Confirme que a API foi iniciada com:

```bash
--host 0.0.0.0
```

No emulador Android, use:

```env
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000/api
```

No celular físico, use:

```env
EXPO_PUBLIC_API_BASE_URL=http://SEU_IP_LOCAL:8000/api
```

Verifique também o firewall do Windows.

### Docker não atualiza dados depois de mudar credenciais

Se o banco já tinha volume criado, as credenciais antigas podem continuar salvas.

Para resetar:

```bash
docker compose down -v
docker compose up -d --build
```

Use esse comando apenas quando puder apagar os dados locais.

## Observações de desenvolvimento

- O modo mais comum de desenvolvimento é executar a API localmente com Poetry e subir os bancos via Docker.
- O modo totalmente via Docker é útil para simular o ambiente completo.
- O seed deve ser executado na primeira configuração local.
- As migrations são gerenciadas pelo Alembic.
- A documentação principal da API fica em `/docs`.
- Para integração com o mobile local, a porta `8000` precisa estar acessível.
