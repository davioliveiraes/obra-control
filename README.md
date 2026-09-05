# ObraControl

Fundação técnica do backend do ObraControl, um monólito modular em Django com
API REST e PostgreSQL. Inclui a fundação de identidade (`accounts.User`), sem
funcionalidades de negócio nem endpoints de autenticação.

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

O backend fica disponível em `http://localhost:8000/`. O namespace reservado
para a futura API é `/api/v1/`; ele ainda não possui endpoints.

## Identidade e migrations (Etapa 2)

`accounts.User` é baseado em `AbstractUser`, com `username` removido e email
obrigatório como `USERNAME_FIELD`. Mantém `BigAutoField`, senhas com hash e os
campos/permissões nativos do Django, sem papéis empresariais.

O manager e o `save()` removem espaços nas extremidades e convertem o email
inteiro para minúsculas. A validação herdada (`clean()`) usa a mesma normalização.
O campo tem `unique=True`, e a constraint `accounts_user_email_ci_unique` sobre
`Lower(email)` impede duplicatas por casing também em escritas que contornam
o `save()`. Operações em lote não normalizam os valores automaticamente.

User representa a pessoa, sem vínculo direto com organização. Esse vínculo será
definido futuramente via Membership; Organization e Membership ainda não existem.
Não há API de usuários, autenticação HTTP implementada ou UserAdmin personalizado.

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

## Qualidade e testes

Os testes de identidade usam PostgreSQL e criam um banco de testes separado
(`test_<POSTGRES_DB>`), removido pelo pytest-django ao terminar. Exporte as mesmas
variáveis de conexão local antes de executar; o usuário do banco precisa de
permissão `CREATEDB`. Não aponte a suíte para um ambiente de produção.

```powershell
& $Python -m ruff check backend
& $Python -m ruff format --check backend
& $Python -m pytest
& $Python -m coverage run -m pytest
& $Python -m coverage report -m
```

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
