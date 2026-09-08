# ObraControl

Fundação técnica do backend do ObraControl, um monólito modular em Django com
API REST e PostgreSQL. Inclui a fundação de identidade (`accounts.User`) e os
vínculos entre usuários e organizações, com autenticação web por sessão e CSRF.
Customers e Projects (obras) possuem isolamento explícito por organização na API.
Possuem também RBAC mínimo por Membership. Não há isolamento automático global
de models/querysets.

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
de `is_active=True` e timestamps. Os papéis não alteram `is_staff` ou `is_superuser`
do Django; sua autorização em Customers/Projects está descrita na Etapa 8 abaixo.
A constraint PostgreSQL `organizations_membership_org_user_unique` garante um
único vínculo por organização/usuário, inclusive quando ele está inativo.
Excluir qualquer uma das entidades remove suas memberships por `CASCADE`.

Criar uma organização não cria OWNER automaticamente. Não há CRUD HTTP de
organizações/memberships ou isolamento automático de querysets. O contexto
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

Não há JWT ou tokens de API. Login não aplica roles empresariais nem seleciona
organização automaticamente. Não há limitação de tentativas de login;
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

Desde a Etapa 8, MEMBER possui somente leitura; OWNER/ADMIN podem escrever.
Não há bypass para superusuários Django, TenantModel ou TenantManager.
O isolamento está nesta API; uso direto do ORM precisa continuar
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
Não há bypass para superusuário. A política de roles da Etapa 8 também se aplica.

Aplique `projects.0001_initial` com o comando explícito `manage.py migrate`
documentado acima. Não há EAP, planejamento detalhado, financeiro, abstrações
tenant genéricas ou novas dependências nesta etapa.

## Autorização por Membership (Etapa 8)

Customers e Projects exigem cumulativamente `IsAuthenticated`,
`HasActiveOrganization` e `IsOrganizationAdminOrReadOnly`:

- OWNER/ADMIN: leitura e escrita (POST, PATCH e DELETE).
- MEMBER: somente leitura (GET, HEAD e OPTIONS).

PUT continua sem implementação. A nova permission usa `SAFE_METHODS` do DRF e
`request.membership` já validada pelo middleware, sem consultas adicionais.
O role continua na Membership, nunca no User ou na sessão. Alterar ADMIN para
MEMBER revoga escrita na próxima request, sem novo login; trocar Organization
troca também o role efetivo. Membership desativada continua invalidando contexto.
Não há bypass por `is_staff`/`is_superuser` nem uso de Django Groups/`has_perm()`.

MEMBER tentando escrever, mesmo com CSRF válido, recebe `403` com
`{"detail": "Seu papel na organização não permite esta operação."}`. Nenhum dado é
criado, alterado ou excluído. A verificação de role ocorre antes de buscar o objeto:
em escrita por MEMBER, IDs próprios, alheios e inexistentes recebem o mesmo `403`.

O queryset tenant-scoped permanece independente do RBAC: em leitura, recurso de
outro tenant retorna `404` para qualquer role; em PATCH/DELETE por OWNER/ADMIN,
também retorna `404`. Role elevado nunca oferece acesso global. Payloads, URLs,
paginação, SessionAuthentication e CSRF permanecem inalterados.

Os testes específicos ficam em `backend/tests/organizations/test_rbac.py` e
exercitam as duas APIs com sessões/CSRF reais. Testes de escrita legítima declaram
OWNER/ADMIN explicitamente; MembershipFactory mantém MEMBER como default.
Não há migrations novas, gestão de membros, convites, roles adicionais, EAP ou
dependências novas nesta etapa.

## EAP / etapas da obra (Etapa 9)

`projects.ProjectStage` é uma adjacency list: cada item pertence obrigatoriamente
a um Project (`project.stages`) e pode ter um parent do mesmo Project
(`stage.children`). Organization não é duplicada: o tenant vem de Project.
Campos: BigAutoField, project, parent opcional, name obrigatório (255, não único),
description opcional, position inteiro não negativo (default 0) e timestamps.
Position pode se repetir; a ordenação determinística é `position, id`.

Rotas: `GET/POST /api/v1/projects/{project_id}/stages/` e
`GET/PATCH/DELETE /api/v1/projects/{project_id}/stages/{id}/`. HEAD/OPTIONS
disponíveis; PUT não implementado. A listagem é plana e completa, sem paginação
ou children recursivos. Não altera as paginações de Customers/Projects.

Primeiro a API resolve Project filtrado por `request.organization`; em seguida,
resolve a etapa dentro desse Project. Project de outro tenant ou etapa de outro
Project na rota retorna `404`. Project é definido apenas pela URL; chaves extras
`project`, `project_id`, `organization` e `organization_id` no payload são ignoradas.
Somente `name`, `description`, `position` e `parent_id` são graváveis.

`parent_id` aceita null para criar/desvincular uma raiz. IDs inexistentes, de outra
obra (inclusive no mesmo tenant) ou de outro tenant recebem o mesmo `400`:
`{"parent_id": ["Etapa pai indisponível."]}`. ProjectStage.clean() verifica o mesmo
Project, self-parent e ciclos percorrendo ancestrais; o serializer invoca essa
validação explicitamente. Não há override de save()/full_clean() automático.
A constraint `projects_projectstage_not_self_parent` bloqueia self-parent no banco.

POST/PATCH/DELETE de etapas usam transação e bloqueiam a linha do Project antes de
validar/gravar. Isso serializa escritas da EAP de uma obra para impedir ciclos
formados por reparentamentos concorrentes. Leituras não bloqueiam a obra. Uso direto
do ORM/admin/scripts precisa respeitar a validação e o mesmo protocolo de escrita;
não há trigger nem constraint de banco para ciclos gerais ou parent × Project.

Parent usa RESTRICT: excluir uma etapa com filhos retorna `409`,
`{"detail": "A etapa possui subetapas e não pode ser excluída."}`, sem remover a
subárvore. Uma leaf pode ser excluída (`204`). Excluir o Project inteiro continua
removendo toda a EAP por CASCADE; validado também via endpoint existente.

São reutilizadas IsAuthenticated, HasActiveOrganization e
IsOrganizationAdminOrReadOnly: MEMBER read-only, OWNER/ADMIN com escrita e CSRF,
sem bypass para superusuário. A revogação de Membership continua valendo na request
seguinte. A migration é `projects.0002_projectstage`; aplicação explícita conforme
comando documentado acima. Não há códigos EAP, reorder/move, status de etapa,
cronograma, progresso, custos, orçamento ou novas dependências.

## Planejamento temporal da EAP (Etapa 10)

`planning.StagePlan` separa as datas planejadas da estrutura da EAP. Possui apenas
BigAutoField, `stage` (OneToOne para ProjectStage, `related_name="plan"`),
`planned_start_date`, `planned_end_date` e timestamps. Project e Organization não
são duplicados: todo contexto deriva de Stage → Project → Organization.
Uma etapa ainda não planejada simplesmente não possui StagePlan.

As duas datas são obrigatórias. A constraint PostgreSQL
`planning_stageplan_planned_dates_order` exige fim >= início, permitindo o mesmo
dia. A API valida também PATCH parcial contra a outra data persistida e retorna
`400` sem alterar o registro. Não há restrições contra as datas globais do Project
ou de parents/children, nem propagação automática de datas.

Rotas: `GET/POST /api/v1/projects/{project_id}/planning/` e
`GET/PATCH/DELETE /api/v1/projects/{project_id}/planning/{id}/`. HEAD/OPTIONS
disponíveis, sem PUT. A lista é plana, completa, sem paginação, filtros ou busca,
ordenada por `stage__position, stage_id`. A paginação de outras APIs não muda.

Project é resolvido exclusivamente no tenant ativo; planos são filtrados por
`stage__project=project`. IDs de Project externos e planos fora do Project da URL
retornam `404`. POST exige stage_id e ambas as datas; a etapa precisa pertencer ao
Project da URL. Stage inexistente, de outra obra ou tenant recebe o mesmo `400`:
`{"stage_id": ["Etapa indisponível."]}`.

Na representação aparecem somente id, stage_id, datas e timestamps. No PATCH,
stage_id é somente leitura: enviá-lo não move o plano. Campos extras stage,
project/project_id e organization/organization_id são ignorados, como nas APIs
anteriores. Somente datas são alteráveis após a criação; não há mass assignment
de tenant ou mudança de etapa por PATCH.

A OneToOne garante unicidade no PostgreSQL, sem constraint redundante. POST
duplicado retorna `400`, `{"stage_id": ["A etapa já possui planejamento."]}`.
Se duas criações passarem pela validação simultaneamente, o INSERT é protegido
por uma transação curta; após rollback, a violação UNIQUE esperada é convertida
para a mesma resposta. Não há locking adicional ou infraestrutura de concorrência.

Excluir StagePlan preserva ProjectStage. Excluir uma leaf pela API da EAP remove
seu planejamento por CASCADE; excluir Project remove toda a EAP e seus planos.
Etapas com filhos continuam protegidas pelo contrato de exclusão da Etapa 9.
IsAuthenticated, HasActiveOrganization e IsOrganizationAdminOrReadOnly continuam
reutilizadas: MEMBER read-only; OWNER/ADMIN com escrita, exigindo CSRF. Sem bypass
de superuser; revogação de Membership invalida acesso na próxima request.

Migration: `planning.0001_initial`, aplicada explicitamente por `manage.py migrate`
conforme documentado acima. Não há progresso/datas reais, dependências entre etapas,
duração armazenada, Gantt engine, custos, orçamento ou novas dependências.

## Itens orçamentários previstos (Etapa 11)

`budgets.BudgetItem` pertence obrigatoriamente a ProjectStage (`CASCADE`,
`stage.budget_items`). A etapa pode possuir vários itens, inclusive com descrições
iguais. Campos persistidos: BigAutoField, stage, description (255), unit (20),
quantity, unit_price e timestamps. Description/unit são obrigatórios, sem strings
vazias ou apenas espaços na API. Unit é texto livre, sem enum ou tabela auxiliar.
Não há Project, Organization ou total duplicados no model.

Quantity usa DecimalField(14, 4), deve ser > 0 e aceita desde `0.0001` até
`9999999999.9999`. Unit price usa DecimalField(14, 2), deve ser >= 0 e aceita até
`999999999999.99`, inclusive preço zero. As constraints PostgreSQL
`budgets_budgetitem_quantity_positive` e `budgets_budgetitem_unit_price_nonnegative`
protegem as regras também em save/update sem full_clean. A API valida limites,
precisão e valores finitos antes de gravar; NaN/Infinity e excesso de casas são
rejeitados com `400`, não arredondados silenciosamente na entrada.

Total é uma property calculada com Decimal: `quantity * unit_price`. Não há coluna
total, float ou total geral persistido. Na API, quantidade, preço e total são
strings decimais com 4/2/2 casas respectivamente. Envie também strings no JSON
para preservar precisão no cliente. Total é read-only e usa ROUND_HALF_UP: por
exemplo, `0.3333 × 3.00 → 1.00` e `1.0050 × 1.00 → 1.01`. A representação permite
22 dígitos inteiros mais 2 decimais, comportando o produto dos limites dos campos.

Rotas: `GET/POST /api/v1/projects/{project_id}/budget/items/` e
`GET/PATCH/DELETE /api/v1/projects/{project_id}/budget/items/{id}/`.
HEAD/OPTIONS disponíveis; sem PUT, summary, filtros ou busca. Lista plana e
completa, sem paginação, ordenada por `stage_id, id`. Outras paginações não mudam.

Project é resolvido pelo tenant ativo; o queryset usa `stage__project=project`.
Project externo ou item fora do Project da URL retorna `404`. POST exige stage_id,
description, unit, quantity e unit_price. Stage é resolvida somente no Project da
URL; ID inexistente, de outro Project ou tenant recebe o mesmo `400`:
`{"stage_id": ["Etapa indisponível."]}`. PATCH pode mudar todos esses cinco campos,
inclusive mover o item entre etapas da mesma obra; Stage omitida é preservada.
Campos extras stage/project/project_id/organization/organization_id são ignorados;
total enviado também é ignorado e sempre recalculado. Nada pode transferir tenant.

São reutilizadas IsAuthenticated, HasActiveOrganization e
IsOrganizationAdminOrReadOnly: MEMBER read-only; OWNER/ADMIN com escrita e CSRF.
Superuser não possui bypass. Membership revogada invalida acesso na próxima request.
Excluir BudgetItem preserva Stage e StagePlan; excluir leaf Stage remove seus itens;
excluir Project remove a EAP e os itens dependentes. Parent com children continua
protegido pelo contrato 409 da EAP. Planning e BudgetItem não alteram um ao outro:
sem signals, sincronização de datas ou distribuição financeira automática.

Migration: `budgets.0001_initial`, aplicada explicitamente com `manage.py migrate`.
Não há Budget/Header, versões, composições, insumos, SINAPI, BDI, encargos,
aprovações, importação/exportação, custos realizados, despesas/receitas, medições
ou cronograma físico-financeiro. Nenhuma dependência nova é necessária.

## Despesas da obra / realizado financeiro (Etapa 12)

`finances.Expense` representa realizado registrado, separado de BudgetItem (previsto).
Possui BigAutoField, Project obrigatório (`PROTECT`, `project.expenses`), Stage
opcional (`SET_NULL`, `stage.expenses`), description (255, obrigatória), amount,
expense_date obrigatória, status, notes opcional e timestamps. Não duplica
Organization nem possui vínculo com BudgetItem. ExpenseFactory cria somente
Project, com stage nula, amount `Decimal("100.00")` e data determinística.

Amount utiliza DecimalField(14, 2), de `0.01` a `999999999999.99`, representado
como string decimal com duas casas na API. A constraint PostgreSQL
`finances_expense_amount_positive` exige amount > 0, também em escritas diretas.
A API rejeita zero, negativos, NaN/Infinity, excesso de casas e valores fora do
limite com 400. Não usa float ou arredondamento silencioso de entrada.
expense_date é a data financeira, independente do instante created_at.

Rotas: `GET/POST /api/v1/projects/{project_id}/expenses/` e
`GET/PATCH /api/v1/projects/{project_id}/expenses/{id}/`. HEAD/OPTIONS disponíveis;
PUT/DELETE não são implementados. Lista `{count, next, previous, results}` em
páginas fixas de 25, ordenada por `-expense_date, -id`, incluindo canceladas.
`page_size` não altera o limite. Sem filtros, busca ou agregados.

Project vem exclusivamente da URL, resolvido por request.organization; Expense
é consultada por `project=project`. Project externo ou despesa fora do Project
da URL retorna 404. POST exige description, amount e expense_date. stage_id
é opcional/nullable e só pode apontar para Stage do mesmo Project. Etapa de outra
obra/tenant e ID inexistente recebem o mesmo 400: `{"stage_id": ["Etapa indisponível."]}`.
PATCH altera stage_id, description, amount, expense_date, status e notes. Stage
omitida é preservada; null transforma a despesa em geral da obra. Campos extras
stage/project/project_id/organization/organization_id são ignorados, nunca
movendo o registro para outro Project ou tenant. A resposta não expõe Project ou
Organization. `Expense.clean()` também valida Stage × Project para forms/validação
explícita; não há full_clean automático em save nem constraint entre tabelas.
Scripts/ORM direto devem respeitar essa invariante e o scoping explicitamente.

ExpenseStatus contém somente active (padrão) e canceled. Cancelamento por PATCH
preserva o registro, amount e Stage; não gera reversão, pagamento ou soft delete.
Não há regra de transição adicional. OWNER/ADMIN têm leitura e POST/PATCH;
MEMBER tem somente leitura. São reutilizadas as três permissions existentes,
sessão e CSRF. OWNER/ADMIN com contexto e CSRF válidos recebem 405 em DELETE/PUT;
para MEMBER, o DRF pode negar métodos unsafe com 403 antes do despacho, inclusive
DELETE. Sem bypass para superuser; Membership revogada interrompe acesso.

Excluir leaf Stage preserva Expense e Project, apenas tornando stage nula.
RESTRICT entre parent/children continua ativo. Desde esta etapa, Project com
qualquer Expense, inclusive canceled, não pode ser excluído: a API de Projects
converte especificamente ProtectedError de Expenses em 409 com
`{"detail": "A obra possui registros financeiros e não pode ser excluída."}`.
A coleta PROTECT do ORM falha antes de executar deletes/SET_NULL; não há exclusão
parcial. Project sem Expense continua deletável com as cascades anteriores.
PROTECT/SET_NULL são políticas do ORM Django; as FKs do PostgreSQL também preservam
integridade referencial, mas não implementam esses comportamentos como triggers.

Expense não altera BudgetItem ou StagePlan: sem signals ou sincronização.
Migration `finances.0001_initial`, aplicada explicitamente com `manage.py migrate`.
Não há receitas, contas a pagar/receber, fluxo de caixa, fornecedores, categorias,
pagamentos, anexos, auditoria completa, previsto × realizado agregado ou novas
dependências. Cancelamento não substitui uma futura trilha de auditoria.

## Resumo de custos previsto × realizado (Etapa 13)

`GET /api/v1/projects/{project_id}/cost-summary/` fornece uma visão somente leitura
do estado acumulado da obra. HEAD/OPTIONS seguem o DRF; não há POST/PATCH/PUT/DELETE,
paginação, filtros temporais ou endpoint global por organização. Os endereços
anteriores de Expenses permanecem inalterados.

A view resolve Project filtrado por request.organization antes de chamar
`finances.services.cost_summary.get_project_cost_summary(project)`. O service
recebe a obra já autorizada, não conhece request/session nem resolve tenant e
retorna somente um dictionary com Decimal. São reutilizadas IsAuthenticated,
HasActiveOrganization e IsOrganizationAdminOrReadOnly: OWNER/ADMIN/MEMBER podem
consultar. Project externo/inexistente retorna 404; sem contexto/Membership ativa,
403. Superuser não tem bypass. GET não exige CSRF e as proteções de escrita das
outras APIs não mudam. Não há cache de resultado; respostas usam no-store.

Resposta: project_id, budget_total, actual_total, variance_amount,
unallocated_actual_total e stages. Os campos monetários são strings decimais
com exatamente duas casas, inclusive `0.00` em ausência de dados:

- budget_total soma todos os BudgetItems do Project, quantizando **cada item**
  (`quantity × unit_price`) com ROUND_HALF_UP antes de somar. Isso coincide com a
  representação da API BudgetItem; a property do model continua sendo o produto
  exato, sem mudança. Dois itens de `0.0050 × 1.00` resultam em `0.02`, não `0.01`.
- actual_total soma todas as Expenses ACTIVE do Project, inclusive sem Stage.
  CANCELED fica fora do realizado, com ou sem Stage.
- variance_amount = budget_total - actual_total; negativo indica realizado acima
  do previsto. Não representa lucro, margem ou fluxo de caixa.
- unallocated_actual_total soma somente Expenses ACTIVE com Stage nula. Elas
  entram no total da obra, mas não em linhas de Stage.
- stages é uma lista plana com stage_id e os três totais diretos: budget_total,
  actual_total e variance_amount. Inclui toda Stage do Project, mesmo sem dados,
  em ordem position, id. Filhos não são somados automaticamente aos pais;
  não há roll-up, recursão ou duplicação da EAP na resposta.

Os totais gerais são acumulados diretamente das fontes, não pela soma das linhas
de Stage. São três SELECTs no service: Stages, BudgetItems e Expenses ACTIVE,
com consolidação em memória por dictionaries. O número não cresce com a quantidade
de etapas; autenticação e resolução do Project ficam fora desse limite do service.
Usa somente Decimal, com contexto local ampliado para somas de múltiplos valores
máximos sem perda de centavos, sem alterar a precisão global do Python.

Nada é persistido ou modificado: sem novos models, migrations, factories de resumo,
signals, dependências, Revenue, percentuais, dashboard ou gráficos. StagePlan não
participa dos cálculos. BudgetItem e Expense continuam independentes e fontes da
verdade; cada consulta recalcula o resumo a partir dos registros atuais.

## Receitas realizadas da obra (Etapa 14)

`finances.Revenue` registra uma entrada financeira já realizada, não contas a
receber, faturamento ou uma promessa futura. Possui BigAutoField, Project obrigatório
(`PROTECT`, `project.revenues`), description obrigatória (255), amount,
revenue_date obrigatória, status, notes opcional e timestamps. Não duplica
Organization e não possui Stage, Customer, contrato ou método de pagamento.

Amount usa DecimalField(14, 2), representado como string com duas casas na API.
A constraint PostgreSQL `finances_revenue_amount_positive` exige amount > 0.
API e model também validam o mínimo `Decimal("0.01")`; a API rejeita zero,
negativos, NaN/Infinity, mais de duas casas e valores acima de `999999999999.99`.
Não utiliza float nem arredonda entradas silenciosamente. revenue_date representa
a data financeira; created_at é o instante de cadastro, independentemente dela.

Rotas: `GET/POST /api/v1/projects/{project_id}/revenues/` e
`GET/PATCH /api/v1/projects/{project_id}/revenues/{id}/`. HEAD/OPTIONS disponíveis;
PUT/DELETE não são implementados e não há destroy mixin. Páginas fixas de 25,
em ordem `-revenue_date, -id`, incluindo canceladas. Sem filtros, busca ou
ordering dinâmico; page_size não aumenta o limite. A paginação de outros módulos
permanece igual.

Project é resolvido na Organization ativa antes de processar o POST; todos os
querysets de Revenue são filtrados pelo Project da URL. Project externo/inexistente
e Revenue fora da obra da rota recebem 404 sem revelar existência. Create associa
`serializer.save(project=project)` no backend. PATCH altera apenas description,
amount, revenue_date, status e notes. Campos extras project/project_id/organization/
organization_id/stage_id/customer_id são ignorados, não controlam relacionamentos
e não aparecem na representação. Receita não pode ser transferida entre obras.

RevenueStatus é independente de ExpenseStatus: active (padrão) e canceled.
Cancelar via PATCH preserva Revenue, amount e Project, sem lançamento inverso,
exclusão, soft delete ou qualquer automação. Não há workflow de transição adicional.
OWNER/ADMIN podem ler e criar/editar, com CSRF válido; MEMBER é read-only.
As três permissions existentes e SessionAuthentication são reutilizadas, sem
bypass para superuser. Revogação de Membership interrompe o acesso na próxima
request. OWNER/ADMIN recebem 405 em PUT/DELETE; MEMBER pode receber 403 por role
antes do despacho de métodos unsafe, conforme o comportamento nativo do DRF.

Project com Revenue, ativa ou cancelada, não pode ser excluído: a proteção
financeira existente agora reconhece Expense **e** Revenue e retorna 409 com
`{"detail": "A obra possui registros financeiros e não pode ser excluída."}`.
Proteções inesperadas continuam sendo propagadas. Nenhuma parte da EAP, Planning
ou Budget é removida quando a exclusão protegida falha. Project sem Expense nem
Revenue continua deletável com as cascades anteriores. PROTECT é a política do
ORM Django, não uma trigger customizada do PostgreSQL.

Expense e Cost Summary permanecem inalterados. Revenue não entra em budget_total,
actual_total ou variance_amount: o resumo continua BudgetItem × Expense ACTIVE.
Teste de regressão comprova o mesmo resultado antes/depois de criar, editar e
cancelar receita, sem modificar Expense, BudgetItem ou StagePlan.

Migration `finances.0002_revenue`. RevenueFactory cria somente Project e sua
Organization, com amount `Decimal("100.00")`, revenue_date `2026-09-05`, active
e notes vazias. Não cria outros registros empresariais nem Membership.
No OpenAPI, `FinancialRecordStatusEnum` nomeia explicitamente os valores
active/canceled para evitar colisão com ProjectStatus. Esse componente de
documentação é compartilhado, mas ExpenseStatus e RevenueStatus permanecem
choices de domínio independentes; campos e valores dos payloads não mudam.
Sem contas a receber/pagar, contratos, medições, DRE, consolidação de fluxo de caixa,
categorias, dashboards, novas dependências ou alterações de migrations históricas.

## Resumo financeiro realizado da obra (Etapa 15)

`GET /api/v1/projects/{project_id}/financial-summary/` retorna somente project_id,
revenue_total, expense_total e realized_balance. HEAD/OPTIONS seguem o DRF;
POST/PATCH/PUT/DELETE não são disponibilizados. Não há filtros temporais,
paginação, breakdown por Stage ou endpoint global multi-Project.

A view resolve Project por request.organization antes de chamar
`finances.services.financial_summary.get_project_financial_summary(project)`.
O service recebe Project autorizado e retorna um dictionary com Decimal,
sem conhecer request, session, usuário, permissões ou Response.
Reutiliza-se IsAuthenticated + HasActiveOrganization + IsOrganizationAdminOrReadOnly.
OWNER/ADMIN/MEMBER podem consultar; superuser não tem bypass. Project externo ou
inexistente retorna 404 equivalente. Membership revogada interrompe a próxima
request. GET não exige CSRF; autenticação e CSRF de escrita permanecem intactos.

- revenue_total: SUM de Revenue ACTIVE do Project; CANCELED é ignorada.
- expense_total: SUM de Expense ACTIVE do Project, com ou sem Stage; CANCELED
  é ignorada. A Stage não interfere no total.
- realized_balance = revenue_total - expense_total. Saldo negativo é válido.
- Sem registros ativos, todos os valores são `0.00`, nunca null.

São dois aggregates `Sum("amount")` no PostgreSQL, sem carregar lançamentos em
Python e sem consultar EAP, BudgetItem ou StagePlan. Testes com 0, 10 e 100 registros
por fonte garantem duas consultas no service; autenticação/resolução do Project
pertencem à camada HTTP e não entram nessa contagem. Não há cache, Redis, N+1,
armazenamento do resumo na sessão ou persistência de totais.

Somente Decimal é usado; valores financeiros saem como strings com exatamente
duas casas. O service utiliza precisão local ampliada na subtração e o serializer
suporta somas maiores que um lançamento individual, sem alterar o contexto global.
Não há conversão para float ou arredondamento de entradas neste resumo.

Cost Summary permanece BudgetItem × Expense ACTIVE, sem Revenue. Financial
Summary não chama Cost Summary: suas fontes são exclusivamente Revenue e Expense.
Teste de regressão confirma que consultar a nova visão não altera Cost Summary,
Project, EAP, Budget, Planning ou lançamentos financeiros.

O saldo realizado representa apenas entradas menos saídas registradas na obra:
não é lucro contábil, saldo bancário, DRE ou fluxo de caixa completo. Sem novos
models, migrations, factories de resumo, dependências, percentuais, dashboard,
contas a pagar/receber, contratos, faturamento ou medições.

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
`OrganizationFactory`, `MembershipFactory`, `CustomerFactory`, `ProjectFactory`,
`ProjectStageFactory`, `StagePlanFactory`, `BudgetItemFactory`, `ExpenseFactory` e
`RevenueFactory`.
BudgetItemFactory
cria somente sua Stage, com unit `un`, quantity `Decimal("1.0000")` e unit_price
`Decimal("10.00")`, sem Planning implícito. StagePlanFactory cria somente sua Stage
(Project/Organization derivam dela) e usa datas determinísticas válidas.
ProjectStageFactory cria Project e mantém parent nulo;
ao fornecer parent, informe explicitamente o mesmo Project, sem correção implícita.
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
