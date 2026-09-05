# ObraControl

Fundação técnica do backend do ObraControl, um monólito modular em Django com
API REST e PostgreSQL. Inclui a fundação de identidade (`accounts.User`) e os
vínculos entre usuários e organizações, com autenticação web por sessão e CSRF.
Ainda não há módulos de negócio ou isolamento multi-tenant automático.

## Requisitos

- Python 3.14
- Docker com Docker Compose
- Git

## Ambiente local

Crie o ambiente virtual na raiz do repositório:

```powershell
py -3.14 --version
py -3.14 -m venv .venv
$Python = ".\.venv\Scripts\python.exe"
```

Use a distribuição oficial CPython para Windows. Distribuições MSYS2 usam uma
ABI diferente e não são compatíveis com todos os wheels binários desta stack.

Instale as dependências sem depender da ativação do ambiente:

```powershell
& $Python -m pip install --upgrade pip
& $Python -m pip install -r backend\requirements\dev.txt
```

Copie o arquivo de exemplo e substitua todos os valores locais necessários:

```powershell
Copy-Item .env.example .env
```

O Docker Compose lê `.env` automaticamente. O Django usa diretamente
`os.environ`; ao executar fora dos containers, exporte as variáveis no processo
ou utilize os fallbacks explicitamente locais de `config.settings.development`.

## PostgreSQL e Django

Inicie somente o PostgreSQL:

```powershell
docker compose up -d db
docker compose ps
```

O exemplo publica o PostgreSQL em `localhost:5433` para evitar conflito com
instalações locais que já usem 5432. Entre os containers, o backend sempre usa
o endereço interno `db:5432`.

Execute o backend localmente:

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings.development"
& $Python backend\manage.py check
& $Python backend\manage.py runserver
```

Ou execute o ambiente de desenvolvimento completo em containers:

```powershell
docker compose up --build
```

O backend fica disponível em `http://localhost:8000/`. A API usa `/api/v1/`, com
os endpoints de autenticação em `/api/v1/auth/`.

## Identidade e migrations (Etapa 2)

`accounts.User` é baseado em `AbstractUser`, com `username` removido e email
obrigatório como `USERNAME_FIELD`. Mantém `BigAutoField`, senhas com hash e os
campos/permissões nativos do Django, sem papéis empresariais.

O manager e o `save()` removem espaços nas extremidades e convertem o email
inteiro para minúsculas. A validação herdada (`clean()`) usa a mesma normalização.
O campo tem `unique=True`, e a constraint `accounts_user_email_ci_unique` sobre
`Lower(email)` impede duplicatas por casing também em escritas que contornam
o `save()`. Operações em lote não normalizam os valores automaticamente.

User representa a pessoa, sem vínculo direto com organização. O vínculo com
empresas fica em Membership, conforme a fundação SaaS descrita abaixo.
Não há CRUD de usuários ou UserAdmin personalizado. A autenticação HTTP está
descrita na Etapa 4 abaixo.

Com as variáveis `POSTGRES_*` exportadas no processo (incluindo a porta **5433**
do exemplo e a senha local escolhida), aplique as migrations explicitamente:

```powershell
& $Python backend\manage.py showmigrations
& $Python backend\manage.py migrate
```

Em um banco legado que já tenha aplicado migrations com o User padrão, pare e
avalie o histórico antes de migrar. Não apague banco/volume nem use migrations
falsas para contornar incompatibilidades. Docker/Compose não executam migrations
automaticamente.

## Organizações e vínculos (Etapa 3)

`organizations.Organization` representa a empresa/tenant no modelo Shared
Database / Shared Schema. Possui apenas identificador `BigAutoField`, `name`
(obrigatório na validação do model, não único), `created_at` e `updated_at`.

`organizations.Membership` associa User e Organization: uma pessoa pode participar
de várias empresas, e cada empresa pode possuir vários usuários. Os vínculos são
consultados por `user.memberships` e `organization.memberships`; User continua
sem `organization_id` e sem role empresarial.

O papel pertence à Membership: `owner`, `admin` ou `member` (padrão), acompanhado
de `is_active=True` e timestamps. Os papéis são apenas dados nesta etapa, sem
regras de autorização, e não alteram `is_staff` ou `is_superuser` do Django.
A constraint PostgreSQL `organizations_membership_org_user_unique` garante um
único vínculo por organização/usuário, inclusive quando ele está inativo.
Excluir qualquer uma das entidades remove suas memberships por `CASCADE`.

Criar uma organização não cria OWNER automaticamente. Não há tenant context,
isolamento automático, middleware multi-tenant, permission classes ou API de
organizações/memberships. As migrations continuam sendo operações explícitas,
usando os comandos documentados acima.

## Autenticação web (Etapa 4)

A API utiliza somente `SessionAuthentication` do DRF, com sessões e autenticação
nativas do Django. Login usa `authenticate()` e `login()`; logout usa `logout()`.
Email é normalizado com `strip()` e `lower()`; a senha não é aparada.

O contrato HTTP dos quatro endpoints, payloads, respostas e requisitos de CSRF
está nas anotações drf-spectacular junto às views. Para gerar e validar o OpenAPI
(saída no terminal, sem adicionar endpoint de documentação):

```powershell
& $Python backend\manage.py spectacular --validate --fail-on-warn
```

Fluxo do cliente, preservando cookies entre requests:

1. Obtenha o token em `GET /api/v1/auth/csrf/`. A resposta contém `csrfToken`
   mascarado, e o middleware estabelece o cookie `csrftoken`.
2. Envie email/senha para `POST /api/v1/auth/login/`, com esse token no header
   `X-CSRFToken` e o cookie CSRF. Login exige CSRF mesmo quando anônimo.
3. Preserve o cookie `sessionid` recebido. `GET /api/v1/auth/me/` passa a resolver
   a identidade pela sessão, retornando só `id`, `email`, `first_name`, `last_name`.
4. Após login, obtenha um novo token pelo endpoint CSRF (ou leia o cookie CSRF
   atualizado), pois o Django rotaciona o token no login. O token anterior não
   serve para as operações seguintes.
5. Envie `POST /api/v1/auth/logout/` com sessão e CSRF atualizados. Após o logout,
   `/me/` volta a negar acesso.

Credenciais rejeitadas (incluindo usuário inativo) retornam `400` e a mesma
mensagem genérica, sem distinguir email inexistente de senha incorreta.
Sem autenticação, `/me/` e logout retornam `403`, conforme SessionAuthentication.
Falhas CSRF retornam `403`; no login, a resposta nativa do Django é HTML.
As respostas não permitem armazenamento em cache (`no-store`).

`sessionid` é HttpOnly; os cookies de sessão e CSRF usam SameSite=Lax. Em produção
ambos têm Secure=True e exigem HTTPS; em desenvolvimento/testes continuam
compatíveis com HTTP local. O cookie CSRF segue o padrão legível do Django.
Não há CORS adicional: a integração React e suas origens serão avaliadas quando
existir uma topologia real; produção deve preferir mesma origem via proxy.

Não há JWT, tokens de API, contexto de organização ou autorização por papéis
empresariais. Esta etapa não implementa limitação de tentativas de login;
proteção contra abuso deve ser definida antes de exposição pública em produção.

## Qualidade e testes

Os testes de identidade e organizações usam PostgreSQL e criam um banco separado
(`test_<POSTGRES_DB>`), removido pelo pytest-django ao terminar. Exporte as mesmas
variáveis de conexão local antes de executar; o usuário do banco precisa de
permissão `CREATEDB`. Não aponte a suíte para um ambiente de produção.

```powershell
& $Python -m ruff check backend
& $Python -m ruff format --check backend
& $Python -m pytest -p no:cacheprovider
& $Python -m coverage run -m pytest -p no:cacheprovider
& $Python -m coverage report -m
```

As factories mínimas ficam em `backend/tests/factories`: `UserFactory`,
`OrganizationFactory` e `MembershipFactory`. UserFactory usa `create_user()` na
persistência e `set_password()` no build; sem senha explícita, a senha é
inutilizável. Os comandos desabilitam somente o cache auxiliar do pytest para
evitar o conflito local de permissões já identificado, sem desabilitar testes.

Instale e execute os hooks do Git:

```powershell
& $Python -m pre_commit install
& $Python -m pre_commit run --all-files
```

## Settings

- `config.settings.development`: desenvolvimento local, com PostgreSQL em
  `localhost` por padrão.
- `config.settings.test`: testes, também com PostgreSQL como banco preferencial.
- `config.settings.production`: produção, sem fallbacks inseguros para secrets,
  hosts ou origens CSRF.
