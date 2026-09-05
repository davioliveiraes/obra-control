# ObraControl

Fundação técnica do backend do ObraControl, um monólito modular em Django com
API REST e PostgreSQL. Inclui a fundação de identidade (`accounts.User`) e os
vínculos entre usuários e organizações, com autenticação web por sessão e CSRF.
Customers e Projects (obras) possuem isolamento explícito por organização na API.
Não há isolamento automático global de models/querysets.

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

Criar uma organização não cria OWNER automaticamente. Não há CRUD HTTP de
organizações/memberships, RBAC ou isolamento automático de querysets. O contexto
de sessão está descrito na Etapa 5 abaixo. As migrations continuam sendo operações
explícitas, usando os comandos documentados acima.

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

Não há JWT, tokens de API ou autorização por papéis empresariais. Login não
seleciona organização automaticamente. Não há limitação de tentativas de login;
proteção contra abuso deve ser definida antes de exposição pública em produção.

## Organização ativa na sessão (Etapa 5)

O usuário escolhe explicitamente uma organização acessível. Entre os dados de
tenant, somente `current_organization_id` é armazenado na sessão Django; os dados
nativos de autenticação permanecem nela. Nome, role, Membership e objetos não são
armazenados. Nada foi adicionado ao User.

`OrganizationContextMiddleware` executa após AuthenticationMiddleware e define
sempre `request.organization` e `request.membership`. Com seleção ativa, consulta
Membership filtrando simultaneamente usuário autenticado, organização e
`is_active=True`, usando `select_related("organization")`. Sem seleção, não há
consulta de Membership. Sessões anônimas não resolvem tenant.

Se a Membership for desativada/removida, a organização excluída ou o ID da sessão
for inválido, o contexto fica vazio e a chave é removida na próxima request.
O papel retornado vem do banco a cada request, nunca de um cache na sessão.

Todas as operações abaixo exigem sessão autenticada:

- `GET /api/v1/organizations/`: lista somente vínculos ativos do usuário como
  `{id, name, role}`, sem selecionar automaticamente uma organização.
- `GET /api/v1/organizations/current/`: retorna o contexto revalidado; sem contexto,
  retorna `404` com `{"detail": "Nenhuma organização selecionada."}`.
- `PUT /api/v1/organizations/current/`: recebe `{"organization_id": <id>}` e exige
  CSRF. Seleciona apenas mediante Membership ativa. Organização inexistente, alheia
  ou vínculo inativo retornam o mesmo `403`, `{"detail": "Organização indisponível."}`.
  Tentativas inválidas preservam a seleção anterior, desde que continue válida.
- `DELETE /api/v1/organizations/current/`: exige CSRF, remove a seleção e retorna
  `204`, sem encerrar a autenticação. É idempotente mesmo sem seleção anterior.

O fluxo é login → listagem → seleção explícita → consulta → troca ou remoção.
Logout limpa naturalmente a seleção junto com a sessão. Requests sem sessão
recebem `403`. Os contratos também estão no OpenAPI, validado pelo comando acima.

Isso valida apenas o contexto e o acesso à listagem/seleção de organizações:
não adiciona RBAC, isolamento automático de models/querysets, header de tenant,
cache, tokens ou módulos de negócio.

## Clientes por organização (Etapa 6)

`customers.Customer` pertence obrigatoriamente a uma Organization (`CASCADE`,
acessível por `organization.customers`). Possui `BigAutoField`, nome obrigatório,
email e telefone opcionais e timestamps. Nomes e emails não são únicos.

A API exige `IsAuthenticated` e `HasActiveOrganization`, que utiliza o contexto
validado pelo middleware. Todas as consultas, inclusive GET/PATCH/DELETE por ID,
filtram `Customer.objects` por `request.organization` antes de localizar o objeto.
IDs de outro tenant retornam `404`, sem revelar sua existência. Sem contexto ativo,
o acesso retorna `403`; revogar a Membership interrompe o acesso na request seguinte.

Rotas disponíveis:

- `GET /api/v1/customers/`: lista paginada em `{count, next, previous, results}`.
- `POST /api/v1/customers/`: cria cliente e retorna `201`.
- `GET /api/v1/customers/{id}/`: consulta um cliente.
- `PATCH /api/v1/customers/{id}/`: atualização parcial.
- `DELETE /api/v1/customers/{id}/`: exclusão real, retornando `204`.

Payload de criação: `name`, `email` e `phone` (somente `name` é obrigatório).
Nome vazio ou apenas espaços é rejeitado. A resposta contém `id`, `name`, `email`,
`phone`, `created_at` e `updated_at`. Organization não é exposta nem gravável pelo
serializer; chaves extras `organization`/`organization_id` são ignoradas, conforme
o comportamento padrão do DRF. A criação sempre usa `request.organization` e o
PATCH não permite transferir clientes. Escritas continuam exigindo CSRF.

Paginação exclusiva de Customers: 25 itens por página, `?page=2`, ordem por
`name, id`; `page_size` enviado pelo cliente não altera o limite. Organizations
continua retornando a lista simples anterior. Não há busca, filtros ou PUT.

OWNER, ADMIN e MEMBER ativos possuem o mesmo acesso nesta etapa. Não há bypass
para superusuários Django, RBAC, TenantModel, TenantManager ou segundo módulo
empresarial. O isolamento está nesta API; uso direto do ORM precisa continuar
explicitamente filtrado pelo tenant. O schema OpenAPI documenta os contratos.

## Obras por organização (Etapa 7)

`projects.Project` representa uma obra e pertence obrigatoriamente a uma
Organization (`CASCADE`, `organization.projects`). Mantém BigAutoField, nome
obrigatório não único, descrição opcional, datas planejadas opcionais e timestamps.
`ProjectStatus` possui somente `planning` (padrão), `active`, `completed` e `canceled`.
Não há workflow ou transições automáticas.

O cliente é opcional (`customer_id`, aceita `null`) e deve pertencer à mesma
organização. Excluir Customer, inclusive pela API existente, mantém a obra com
cliente nulo (`SET_NULL`, relação inversa `customer.projects`). A API resolve
`customer_id` exclusivamente no queryset de Customers de `request.organization`.
Cliente de outro tenant e ID inexistente retornam o mesmo `400` com
`{"customer_id": ["Cliente indisponível."]}`. PATCH pode definir, trocar ou remover
o cliente, mas não transferir a obra entre tenants.

`Project.clean()` também verifica a coerência Customer × Organization em validações
explícitas/forms. Isso não substitui o queryset tenant-aware da API nem cria uma
garantia entre tabelas no banco: uso direto de `save()`, `update()` ou operações
em lote precisa respeitar essa invariante; `save()` não chama `full_clean()`.

A constraint PostgreSQL `projects_project_planned_dates_order` exige fim >= início
quando ambas as datas existem, permitindo igualdade e qualquer combinação com
datas nulas. O serializer retorna `400` em datas invertidas, inclusive ao combinar
um PATCH parcial com a outra data persistida.

Rotas: `GET/POST /api/v1/projects/` e `GET/PATCH/DELETE /api/v1/projects/{id}/`.
HEAD/OPTIONS disponíveis, sem PUT. Exigem `IsAuthenticated` e
`HasActiveOrganization`; escritas mantêm CSRF. Listagem, retrieve, PATCH e DELETE
usam queryset filtrado por `request.organization`; IDs de outro tenant retornam
`404`. Criação associa essa organização no backend. Campos extras `organization`,
`organization_id`, `tenant` e `tenant_id` são ignorados e nunca escolhem o contexto.

Somente `name` é obrigatório no POST. Campos públicos: `id`, `name`, `customer_id`,
`status`, `description`, `planned_start_date`, `planned_end_date`, `created_at` e
`updated_at`; identificador e timestamps são somente leitura. Organization não
é exposta. O contrato detalhado está no OpenAPI gerado pelas views/serializer.

Paginação exclusiva de Projects: 25 itens, `?page=2`, ordem `name, id`, sem tamanho
arbitrário de página, filtros, busca ou ordenação dinâmica. Contratos de Customers
e Organizations permanecem iguais. Revogação de Membership interrompe o acesso
na próxima request; troca de organização altera consultas e criações seguintes.
Não há bypass para superusuário nem diferenças de autorização entre roles.

Aplique `projects.0001_initial` com o comando explícito `manage.py migrate`
documentado acima. Não há EAP, planejamento detalhado, financeiro, RBAC, abstrações
tenant genéricas ou novas dependências nesta etapa.

## Qualidade e testes

Os testes de identidade, organizações, clientes e obras usam PostgreSQL e banco separado
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
`OrganizationFactory`, `MembershipFactory`, `CustomerFactory` e `ProjectFactory`.
ProjectFactory cria Organization e mantém Customer nulo por padrão; ao fornecer
Customer nos testes, informe explicitamente a mesma Organization. CustomerFactory
cria somente a organização necessária, sem usuários/memberships implícitos.
UserFactory usa `create_user()` na
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
