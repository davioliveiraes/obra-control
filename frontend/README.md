# ObraControl — frontend (F3)

Login e logout com a sessão existente do Django, sobre a integração React,
TypeScript e Vite da F2. A identidade é confirmada por `/me/`; resultados
incertos oferecem uma verificação por leitura, sem repetir mutações.

A implementação e os testes independentes estão prontos. **A validação
positiva no navegador ainda depende de uma conta local de teste autorizada.**
Os resultados atuais estão na seção da F3; o fechamento da F2 foi preservado
integralmente como registro histórico.

A integração real **precisa do Django ligado**. Os testes frontend usam
mocks locais de fetch e continuam independentes do backend.
Inicie Django e aguarde a mensagem de prontidão antes de testar a integração.
Na ausência de sessão, o 403 JSON de /me e a mensagem "Nenhuma sessão
autenticada" são esperados, acompanhados do formulário de entrada.
Durante a consulta aparece "Verificando sessão…"; durante as ações,
"Entrando…" ou "Saindo…". Se a API estiver indisponível, a tela oferece
"Tentar novamente"; inicie o backend e acione esse botão.
Não há seleção de organização, rotas ou módulos empresariais.
Não é necessário copiar arquivos de `.local/`,
configurações privadas ou criar variáveis de ambiente para o frontend.

## Ambiente preservado da F1

- Windows x64 / PowerShell.
- Node.js **24.21.0 LTS**; requisito: `>=24.21.0 <25`.
- npm **11.19.0**; requisito: `>=11.19.0 <12`.
- Pacote independente, instalação e lockfile em `frontend/`.
- `packageManager` registra npm; `.npmrc` mantém `engine-strict=true`.

A F2 e a F3 reutilizaram o Node portátil preparado na F1. O ambiente global,
Node 22.20.0 e npm 10.9.3, não foi atualizado. Para usar a instalação
portátil disponível neste ambiente, ajuste somente o terminal atual:

```powershell
$nodeF1 = Join-Path $env:TEMP 'obracontrol-f1-dcab8a7ff8fb4bb6b0f4705420e20231\node-v24.21.0-win-x64'
$env:PATH = "$nodeF1;$env:PATH"
Get-Command node, npm.cmd
node --version
npm.cmd --version
```

Esse caminho é temporário e específico do ambiente validado; se não
existir, disponibilize a versão requerida antes de executar os comandos.
Não use silenciosamente o Node global incompatível. Não misture
gerenciadores nem edite o lockfile manualmente.

Nenhuma dependência foi adicionada ou atualizada na F2 ou na F3:

| Pacote                          | Versão  |
| ------------------------------- | ------- |
| react / react-dom               | 19.3.0  |
| @types/react / @types/react-dom | 19.3.0  |
| @types/node                     | 24.13.4 |
| typescript                      | 6.0.3   |
| vite                            | 8.3.0   |
| @vitejs/plugin-react            | 6.1.1   |
| eslint                          | 10.10.0 |
| @eslint/js                      | 10.0.1  |
| typescript-eslint               | 8.70.0  |
| eslint-plugin-react-hooks       | 7.1.1   |
| eslint-plugin-react-refresh     | 0.5.6   |
| globals                         | 17.12.0 |
| prettier                        | 3.9.6   |
| vitest                          | 5.0.0   |
| jsdom                           | 30.0.1  |
| @testing-library/react          | 16.3.3  |
| @testing-library/dom            | 10.4.1  |
| @testing-library/jest-dom       | 7.0.1   |

A base oficial `react-ts` do Vite entregue na F1 foi preservada, sem novo
scaffold. Manifesto e lockfile permaneceram idênticos, conferidos por
SHA-256 antes e depois de `npm.cmd ci` na implementação anterior da F2.
Os fechamentos da F2 e da F3 reconferiram os hashes, sem reinstalar dependências.

## Iniciar os serviços locais

Terminal do backend, a partir da raiz:

```powershell
Set-Location C:\Users\Davil\obra-control
.\.venv\Scripts\python.exe .\.local\dev_local.py backend\manage.py check
.\.venv\Scripts\python.exe .\.local\dev_local.py backend\manage.py runserver 127.0.0.1:8000 --noreload
```

Todo comando Python deve ser argumento desse executor. Ele utiliza a
configuração privada já existente e o PostgreSQL configurado.
Não copie essa configuração nem a exponha em logs. Não recrie o ambiente
e não aplique migrations automaticamente. Para inspecionar o estado:

```powershell
.\.venv\Scripts\python.exe .\.local\dev_local.py backend\manage.py showmigrations --plan
```

Outro terminal, com o Node portátil no PATH. `npm.cmd ci` é para preparar
uma instalação a partir do lockfile; não é necessário reinstalar a cada execução:

```powershell
Set-Location C:\Users\Davil\obra-control\frontend
npm.cmd ci
npm.cmd run dev
```

Abra **http://127.0.0.1:5173/**. Para conferir o build, mantendo Django ligado:

```powershell
npm.cmd run build
npm.cmd run preview
```

Preview: **http://127.0.0.1:4173/**. Os servidores usam host local e
`strictPort: true`; uma porta ocupada causa falha, sem trocar a origem.
Encerre somente os processos iniciados por você. No terminal interativo
do Vite, `q` seguido de Enter encerra o servidor; o runserver informa
CTRL-BREAK no Windows.

## Comandos de qualidade

Execute cada comando separadamente dentro de `frontend/`:

| Comando                    | Implementação               |
| -------------------------- | --------------------------- |
| `npm.cmd run dev`          | `vite`                      |
| `npm.cmd run typecheck`    | `tsc -b --pretty false`     |
| `npm.cmd run lint`         | `eslint . --max-warnings 0` |
| `npm.cmd run format`       | `prettier --write .`        |
| `npm.cmd run format:check` | `prettier --check .`        |
| `npm.cmd run test`         | `vitest run`                |
| `npm.cmd run test:watch`   | `vitest`                    |
| `npm.cmd run build`        | `tsc -b && vite build`      |
| `npm.cmd run preview`      | `vite preview`              |

Verificação reproduzível:

```powershell
npm.cmd ci
npm.cmd ls --depth=0
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run format:check
npm.cmd run test
npm.cmd run build
```

Capture `$LASTEXITCODE` imediatamente após cada comando nativo.
O sucesso do comando seguinte não valida o anterior. `npm.cmd` chama
o gerenciador diretamente no Windows, sem alterar políticas do PowerShell.

## Contratos confirmados no backend

As URLs são montadas por [config/urls.py](../backend/config/urls.py) e
[accounts/api/urls.py](../backend/apps/accounts/api/urls.py).
As implementações estão em [views.py](../backend/apps/accounts/api/views.py),
e os campos em [serializers.py](../backend/apps/accounts/api/serializers.py).

| Operação                                                     | Contrato observado                                                                                            |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `GET /api/v1/auth/csrf/`                                     | 200 JSON, objeto com `csrfToken` string; token mascarado gerado pelo Django e cookie CSRF                     |
| `GET /api/v1/auth/me/` autenticado                           | 200 JSON: `id` inteiro positivo, `email` string, `first_name` e `last_name` strings que podem ser vazias      |
| `GET /api/v1/auth/me/` sem sessão                            | 403 JSON com o único campo `detail`, conforme abaixo                                                          |
| `POST /api/v1/auth/login/` com JSON `{}` sem token           | 403 HTML de rejeição CSRF                                                                                     |
| Mesmo POST com cookies e token válidos                       | 400 JSON de validação dos campos obrigatórios, conforme abaixo                                                |
| `POST /api/v1/auth/login/` com email/password válidos e CSRF | 200 JSON com os mesmos quatro campos de identidade de /me; a interface ainda exige nova consulta /me          |
| Mesmo POST com credenciais rejeitadas                        | 400 JSON: `{"detail":"Credenciais inválidas."}`, sem distinguir conta inexistente, inativa ou senha incorreta |
| `POST /api/v1/auth/logout/` autenticado e com CSRF           | 204, sem corpo; não há objeto JSON de sucesso                                                                 |
| Logout sem sessão                                            | 403 JSON com o mesmo detail de ausência de autenticação; a operação não confirma saída                        |
| Logout autenticado com CSRF inválido                         | 403 JSON com detail de rejeição CSRF do DRF; permanece erro da operação                                       |

Resposta anônima confirmada na configuração local em português:

```json
{
  "detail": "As credenciais de autenticação não foram fornecidas."
}
```

Resposta da sonda com CSRF válido e corpo vazio:

```json
{
  "email": ["Este campo é obrigatório."],
  "password": ["Este campo é obrigatório."]
}
```

`LoginView` aplica `csrf_protect` ao dispatch, inclusive para anônimos.
`LoginSerializer` exige `email` e `password` antes de chamar authenticate;
portanto o JSON `{}` usado na sonda não pode autenticar. A senha usa
`trim_whitespace=False`. A normalização do email fica com o backend;
o frontend envia os valores digitados, sem transformar a senha.
`LoginView` usa `authenticate` e `login` do Django, que renova a sessão e
rotaciona CSRF. `LogoutView` usa `logout` do Django e exige `IsAuthenticated`.
`MeView` também usa `IsAuthenticated`, com `SessionAuthentication` do DRF.
Os dois GETs aplicam `never_cache`. Somente os status exatos documentados
satisfazem o contrato; outro 2xx é uma resposta inválida.

Evidências automatizadas:
[test_auth_api.py](../backend/tests/accounts/test_auth_api.py) verifica
cookies, CSRF anônimo, origem rejeitada, validação de campos, credenciais,
identidade, rotação de CSRF e logout (incluindo token antigo recusado,
sessão preservada após a recusa e invalidação da sessão após saída válida);
[test_auth_schema.py](../backend/tests/accounts/test_auth_schema.py) verifica
o schema gerado pelo drf-spectacular, SessionAuth e requisitos CSRF.
A configuração pertinente está em
[settings/base.py](../backend/config/settings/base.py).
Não foi criado contrato alternativo ou arquivo OpenAPI no frontend.

O transporte não interpreta autorização. Apenas `getCurrentUser` reconhece
o 403 de `/me/` com esse objeto e essa mensagem **completa e exata**.
O backend não retorna um código de erro legível por máquina que permita
essa classificação. A implementação depende do contrato atual em pt-br:
uma mudança de idioma ou formato resulta em erro, não em anonimato.
Sessão ausente, expirada, revogada ou usuário inativo podem produzir a
mesma resposta; não é possível distingui-los por esse contrato.
Outros 403, inclusive os da preparação CSRF, permanecem erros.

Não existem campos organization, role ou access_token nesse contrato.
Os nomes HTTP são preservados, inclusive `csrfToken`; não há conversor
global entre camelCase e snake_case.

## Proxy, Host, Origin e cookies

O navegador chama caminhos relativos `/api/v1/...` na origem do Vite.
Somente esse prefixo é encaminhado a **http://127.0.0.1:8000**,
preservando o caminho e as barras finais, sem rewrite.

`changeOrigin: false` mantém o Host recebido pelo Vite.
Origin também é preservado. Na implementação instalada do Vite 8.3.0,
os headers de entrada são copiados e Host só é substituído quando
`changeOrigin` está habilitado. O preview herda `server.proxy`,
confirmado na configuração resolvida, sem duplicar a definição.

Na configuração efetiva inspecionada:

- `ALLOWED_HOSTS` permite localhost e 127.0.0.1;
  `USE_X_FORWARDED_HOST` está desabilitado.
- `CSRF_TRUSTED_ORIGINS` contém apenas `http://localhost:8000`.
  As origens do Vite não precisam ser adicionadas nesta topologia:
  Django recebe Host e Origin correspondentes, incluindo a porta,
  e aceita essa origem pela comparação com `request.get_host()`.
- O cookie `csrftoken` usa Path `/`, SameSite=Lax, Secure=false,
  HttpOnly=false e nenhum Domain configurado.
- O cookie de sessão `sessionid` usa Path `/`, SameSite=Lax,
  Secure=false, HttpOnly=true e nenhum Domain configurado.
  Nenhum cookie de sessão foi criado nas sondas anônimas.
- `CSRF_USE_SESSIONS` está desabilitado.

O navegador recebeu o cookie CSRF na origem local. Cookies não são
separados por porta; esta topologia usa consistentemente 127.0.0.1.
Não houve necessidade de cookieDomainRewrite, cookiePathRewrite,
CORS amplo, alteração de SameSite ou ajuste no backend.

A raiz, o workspace e o envDir resolvidos continuam em `frontend/`.
`server.fs.strict` está habilitado e `server.fs.allow` contém somente
essa pasta, incluindo suas dependências. Raiz do repositório, backend
e `.local/` ficam fora da área permitida. Não há envDir externo,
variável VITE_API_URL ou cópia de configuração privada.

Referências:
[proxy do Vite](https://vite.dev/config/server-options#server-proxy),
[proxy do preview](https://vite.dev/config/preview-options#preview-proxy) e
[CSRF do Django](https://docs.djangoproject.com/en/5.2/ref/csrf/).

O proxy de desenvolvimento/preview é local. O build não incorpora esse
servidor; produção precisa de configuração própria de hospedagem,
HTTPS, encaminhamento da API e validação de Host, Origin e cookies.
O preview não é servidor de produção.

## Transporte e coordenação da sessão

`shared/api/client.ts` expõe uma função `request` com fetch nativo.
Ela aceita somente caminhos internos normalizados sob `/api/v1/`;
URLs externas, escapes e separadores codificados ambíguos são rejeitados.

Credenciais e modo são sempre `same-origin`, Accept é JSON e
`redirect: "error"` impede seguir redirects inesperados.
O chamador não pode sobrescrever essas proteções nem adicionar headers
arbitrários. JSON define Content-Type quando há corpo; GET não aceita corpo.
POST, PUT, PATCH e DELETE exigem token explícito e enviam X-CSRFToken.
Leituras não enviam esse header. Não há Authorization nem manipulação
manual do cookie de sessão.

Cada requisição tem timeout de **15 segundos**, incluindo a leitura do
corpo, e aceita AbortSignal. Timers e listeners são removidos ao terminar.
Cancelamento do chamador e timeout abortam o fetch e são distintos de
falha de rede, inclusive se um mock ignorar o sinal.

`ApiError.failure` diferencia HTTP, rede, timeout, cancelamento,
requisição inválida e resposta inválida. Somente HTTP carrega o status
real e o payload JSON como `unknown`. Corpo HTML/texto ou JSON ilegível
não apaga o status de um erro HTTP nem é exposto pela mensagem.
204 não lê JSON; sucesso HTML, JSON malformado ou vazio é inválido.
Um 204 não satisfaz os objetos obrigatórios de CSRF e identidade.
A F3 adicionou a opção `expectedStatus`: a funcionalidade auth exige 200
para CSRF, login e /me, e 204 para logout. Essa conferência ocorre somente
para sucesso HTTP, preservando status e payload reais de 4xx/5xx.
O ajuste pequeno evita aceitar um 2xx inesperado como login ou logout;
possui testes de regressão e não acrescenta decisões de autenticação ao transporte.
Essas categorias são locais, não códigos atribuídos ao backend.

`features/auth/api.ts` usa `cache: "no-store"` e valida campos e tipos em
runtime. O bootstrap obtém CSRF, descarta o token de preparação e consulta
`/me/`. Obter CSRF não prova autenticação nem significa que GET exija CSRF.
Cada operação obtém seu token; não há cache global permanente.

`useAuthSession` evolui o hook de bootstrap da F2. App monta uma única
instância, sem provider ou store global. Os estados são checking, anonymous,
signing-in, authenticated, signing-out e error. Somente authenticated contém
usuário; períodos de operação/verificação removem a identidade anterior da tela
e do estado. Guardas síncronas também impedem ações concorrentes antes de
React renderizar os botões desabilitados.

1. **Entrada:** obtenha CSRF, envie POST login com email/password e token
   explícito, valide status 200 e identidade no corpo. Descarte essa identidade
   para apresentação; obtenha CSRF novamente após a rotação e consulte /me.
   Só então publique a identidade atual, ou anonimato se /me confirmar isso.
2. **Saída:** obtenha CSRF, envie POST logout e exija 204 sem JSON. A identidade
   anterior já está removida durante a operação e não é restaurada. Leia CSRF
   e /me para confirmar o estado atual. Se /me válido indicar autenticação,
   apresente essa identidade e avise que a saída não foi confirmada.
3. **Recuperação:** rejeição conhecida de login volta ao formulário com erro
   seguro; falha antes do CSRF não envia POST. Se o POST pode ter sido enviado
   e houver timeout, falha de rede, resposta inesperada ou falha na confirmação,
   mostre resultado não confirmado e **Verificar sessão**. Esse botão faz
   somente GET CSRF e GET /me. Não reenvia senha nem repete logout.
   Falhas dessa leitura continuam como erro e permitem tentativa manual.

O 400 com o detail exato de credenciais vira "E-mail ou senha inválidos".
Erros 400 estruturados exclusivamente por email/password recebem mensagens
de campo controladas, associadas por aria-describedby e aria-invalid.
O 403 de login é tratado como rejeição da proteção CSRF desse endpoint;
403 de logout continua erro, sem presumir anonimato. Outros formatos
inesperados não são transformados em credenciais inválidas.

`LoginForm` só é montado após anonimato confirmado, com labels, campos
obrigatórios, autocompletar e submissão por teclado. Não aplica política
de cadastro à senha. Ela fica no input e na execução transitória da tentativa,
é limpa ao terminar e não é guardada para reenvio. O email pode permanecer
após rejeição conhecida. Quando autenticado, há apenas o email confirmado,
"Sair" e o aviso de módulos ainda indisponíveis.

Cleanup aborta requisições obsoletas; a identidade da operação e o sinal
impedem resultados atrasados, inclusive se um mock ignorar abort. StrictMode
permanece ativo com novo controller por efeito. Mutações só ocorrem por ações
explícitas. Abortar no navegador não desfaz uma mutação recebida pelo servidor.
Não há polling, retry automático, refresh, redirect, sincronização entre abas
ou logout automático. Nenhum token, identidade ou credencial é persistido em
localStorage ou sessionStorage. Mensagens não expõem HTML da API, tracebacks,
objetos brutos, cookies ou headers sensíveis.

## Estrutura e testes

Arquivos de aplicação e testes utilizados:

```text
src/
  main.tsx
  styles.css
  app/
    App.tsx
    App.test.tsx
    App.auth.test.tsx
  features/auth/
    api.ts
    api.test.ts
    useAuthSession.ts
    useAuthSession.test.tsx
    LoginForm.tsx
    SessionStatus.tsx
  shared/api/
    client.ts
    client.test.ts
  test/
    apiFixtures.ts
    setup.ts
```

`main.tsx` monta a aplicação; App contém somente composição.
A tela preserva main/h1 e usa região de sessão, status/alert,
formulário, botões de entrada/saída/verificação e foco visível. O CSS usa fontes do sistema e não carrega
recursos externos ou identidade visual definitiva.

Os project references e `strict: true` da F1 foram preservados:
`tsconfig.app.json` inclui todo src, testes e setup, com `vite/client`;
`tsconfig.node.json` inclui Vite/Vitest. `tsc -b` verifica ambos.
O build só executa Vite após a checagem de tipos.

ESLint mantém flat config, TypeScript, React Hooks e React Refresh.
Prettier é separado e limitado ao frontend. As regras existentes ignoram
dependências, build, caches e arquivos locais; o lockfile fica a cargo
do npm. `.gitattributes` mantém LF nos textos do frontend.

Vitest usa jsdom, imports explícitos, globals desabilitados e cleanup
em afterEach. O setup também restaura mocks, globals substituídos e timers.
Os testes cobrem transporte, validação runtime, resposta anônima exata,
identidade fictícia, falhas, retry, respostas obsoletas e StrictMode.
A F3 inclui integração dos componentes com fetch simulado: formulário e senha
sem transformação, erros de campo/gerais, duplicidade, sequência CSRF/login/
novo CSRF/me, logout 204, remoção de identidade e resultados incertos com
recuperação somente por leitura. Os testes anteriores úteis foram mantidos.
Nenhum teste frontend exige Django, contas reais ou chamadas externas.

Regressão backend, na raiz e pelo executor:

```powershell
.\.venv\Scripts\python.exe .\.local\dev_local.py -m pytest -p no:cacheprovider backend/tests/accounts/test_auth_api.py backend/tests/accounts/test_auth_schema.py
.\.venv\Scripts\python.exe .\.local\dev_local.py -m pytest -p no:cacheprovider
```

## Fechamento da F2 — 12/09/2026

Este fechamento começou com o Git limpo em main, HEAD
`5928561fd59a8b2f74a978365a39f1fa0fa26cbc`, com a F2 já commitada.
Os arquivos funcionais foram conferidos no HEAD. A referência local
origin/main apontava para o mesmo commit; não houve consulta ao remoto.

O usuário apresentou aprovação de tipos, lint, formatação, 91 testes,
build e navegação anônima. Esses relatos não são execuções deste fechamento.
O README e o registro sanitizado de navegador da implementação anterior
foram consultados como evidência anterior. Os contratos, o ambiente e
o helper de navegador foram reaproveitados; os comandos e cenários abaixo
foram **executados novamente neste fechamento**, sem modificar código
funcional, reinstalar dependências ou alterar o lockfile.

### Comandos executados agora

Cada comando foi executado separadamente, com `$LASTEXITCODE` capturado:

| Diretório | Comando                                    | Saída | Resultado                                         |
| --------- | ------------------------------------------ | ----- | ------------------------------------------------- |
| frontend  | `npm.cmd ls --depth=0`                     | 0     | Todas as versões existentes preservadas           |
| frontend  | `npm.cmd run typecheck`                    | 0     | Aplicação, testes, setup e configuração aprovados |
| frontend  | `npm.cmd run lint`                         | 0     | Sem erros ou avisos                               |
| frontend  | `npm.cmd run format:check`                 | 0     | Aprovado; repetido após consolidar este README    |
| frontend  | `npm.cmd run test`                         | 0     | **91 testes em 4 arquivos aprovados**             |
| frontend  | `npm.cmd run build`                        | 0     | Build gerado antes do preview                     |
| raiz      | executor + `backend\manage.py check`       | 0     | Nenhum problema                                   |
| raiz      | executor + `-m pytest -p no:cacheprovider` | 0     | **702 testes aprovados**, uma execução global     |

Nos comandos da raiz, “executor” significa o prefixo obrigatório
`.\.venv\Scripts\python.exe .\.local\dev_local.py`; os comandos completos
estão nas seções de execução e regressão acima.

Antes de pytest, foram conferidos `pyproject.toml`, settings de teste e
o fixture de banco do pytest-django instalado. A inspeção pelo executor
confirmou PostgreSQL, nome de teste separado do banco de desenvolvimento,
prefixo test_ e ausência de mirror. O runner usa setup_databases e
teardown_databases; não existe substituição local desse fixture.
A execução confirmou `config.settings.test (from ini)` e incluiu
`test_auth_api.py` e `test_auth_schema.py`.
Não foi necessário repeti-los isoladamente para diagnóstico.

Backend: Python 3.14.7, Django 5.2.17 e pytest 9.1.1.
Não foram aplicadas migrations ao banco de desenvolvimento.
A criação e limpeza do banco de testes ficaram com o runner existente.
**Cobertura não foi medida neste fechamento**; 97% é histórico.

Build: 20 módulos, HTML 0,46 kB, CSS 0,78 kB e JavaScript 224,50 kB
(70,46 kB gzip para JavaScript), conforme o Vite.

Git e consulta de portas inicialmente encontraram restrições de identidade
do sandbox; as leituras foram repetidas fora dele, sem mudar configuração
global. A leitura do lockfile com ConvertFrom-Json do PowerShell foi
incompatível com a chave vazia do formato npm; a leitura final com
JSON.parse do Node passou. Nenhum desses ajustes alterou o projeto.

### Procedimento de smoke real

Use perfil temporário sem sessão pessoal. O fechamento utilizou Chrome
152.0.7977.83 headless com protocolo do navegador e Node nativo, sem instalar
bibliotecas E2E. As chamadas abaixo devem ocorrer com fetch nativo **no
contexto da página**, por caminhos relativos, mantendo cookies e Origin
naturais do navegador.

1. Inicie Django, aguarde a prontidão e só então abra dev ou preview.
   Confira main, h1, estágio F2, idioma pt-BR e sessão anônima em
   360×800 e 1440×900. Confira CSRF 200 JSON e /me 403 JSON, sem fallback HTML.
2. Inspecione apenas presença e atributos do cookie, sem registrar valores,
   Cookie, Set-Cookie, HAR ou capturas de tokens.
3. Depois de confirmar que `LoginSerializer` rejeita `{}` antes de autenticar,
   envie uma única sonda POST login com JSON `{}` e sem X-CSRFToken.
   Use fetch nativo: o transporte da aplicação corretamente impede esse
   envio sem token. Confirme a rejeição CSRF.
4. Obtenha novo token em /csrf na mesma sessão do navegador e repita
   exatamente `{}` com X-CSRFToken. Confirme os erros de email e password
   documentados no contrato; um 400 isolado não basta. Mantenha o token
   somente na memória da verificação e não o compare ao valor do cookie.
5. Com a aplicação carregada, bloqueie apenas `*/api/v1/*` no navegador e
   recarregue para iniciar nova consulta. Confira erro seguro, sem anonimato
   nem repetição automática. Remova o bloqueio e clique em Tentar novamente:
   a recuperação deve ocorrer sem recarregar a página inteira.

Para preview, gere o build antes de iniciar:

```powershell
npm.cmd run build
npm.cmd run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

### Resultados reais por origem

| Origem                           | GET /csrf/                            | GET /me/                         | POST login `{}` sem token | POST login `{}` com token válido        |
| -------------------------------- | ------------------------------------- | -------------------------------- | ------------------------- | --------------------------------------- |
| Desenvolvimento — 127.0.0.1:5173 | 200 JSON, csrfToken válido e no-store | 403 JSON, contrato anônimo exato | 403 HTML, rejeição CSRF   | 400 JSON, email e password obrigatórios |
| Preview — 127.0.0.1:4173         | 200 JSON, csrfToken válido e no-store | 403 JSON, contrato anônimo exato | 403 HTML, rejeição CSRF   | 400 JSON, email e password obrigatórios |

Os caminhos completos são os da seção de contratos. Em ambas as origens,
a resposta positiva foi exatamente `email: ["Este campo é obrigatório."]`
e `password: ["Este campo é obrigatório."]`. Os logs correspondentes do
Django confirmaram falta de token nas sondas negativas. Foram realizados
dois POSTs por origem, sem autenticar, fornecer senhas ou criar contas.
Os GETs e o POST de validação retornaram JSON da API, não HTML da SPA.

O cookie csrftoken foi recebido com domínio local 127.0.0.1, Path /,
SameSite=Lax, Secure=false e HttpOnly=false, conforme as configurações
efetivas consultadas pelo executor. Não houve cookie sessionid.
Nenhum valor de token/cookie foi registrado.

Dev e preview renderizaram corretamente em 360×800 e 1440×900, com main/h1,
mensagem anônima, sem overflow horizontal ou conteúdo empresarial.
As quatro capturas de layout e duas de indisponibilidade foram inspecionadas.
Houve zero exceções JavaScript não tratadas e zero chamadas console.error
da aplicação; respostas HTTP negativas e bloqueios de rede esperados
foram mantidos e avaliados separadamente, sem suprimir logs.

A falha controlada e o retry passaram nas duas origens. A tela mostrou
erro seguro, o foco por teclado ficou visível e o clique recuperou a
sessão anônima. `performance.timeOrigin` permaneceu igual durante o retry,
confirmando recuperação sem recarregar a página inteira.
O helper de navegador encerrou com saída 0.

A configuração resolvida confirmou proxy herdado pelo preview, Host
preservado e filesystem restrito ao frontend. HEAD para arquivos existentes
da raiz e backend recebeu 403. A política negou caminhos privados de .local
sem ler seu conteúdo. O ECONNREFUSED relatado antes de iniciar Django não
se reproduziu com os servidores prontos; não foi tratado como defeito atual.

### Limites e preservação

O ramo authenticated foi validado pelos testes frontend com identidade
fictícia. Não foi validado com sessão real no navegador. As sondas de POST
comprovam CSRF e validação de campos neste cenário; não comprovam login
completo, rotação pós-login ou logout. Esses fluxos, organizações, módulos
empresariais e produção continuam fora da entrega. test:watch e cobertura
não foram executados neste fechamento.

Não foram encontradas pendências dentro do escopo de fechamento da F2.
Somente este README foi consolidado; nenhum ajuste funcional foi necessário.
Manifesto, lockfile, backend e .local foram preservados. Não houve staging,
commit, push ou avanço para F3.

Não havia servidores nas portas 8000, 5173 e 4173 no início. Os três processos
usados neste fechamento foram próprios e tiveram prontidão e respostas
confirmadas. Dev e preview encerraram com saída 0; Django foi interrompido
intencionalmente após o smoke (saída 1 do terminal). A conferência final
encontrou as três portas livres e nenhum processo do Chrome deste fechamento.
Somente o perfil temporário criado nesta execução foi removido, após validar
seu caminho. Nenhum servidor ou perfil do usuário foi encerrado.

## Etapa F3 — 13/09/2026

### Estado inicial e preservação

A inspeção começou com Git limpo em main, HEAD
`010e353c60f472fd9500372f7fd09af21763bc3d`.
O fechamento documental da F2 já estava incorporado a esse commit; não havia
alteração pendente no README. A implementação F2 foi confirmada pelo conteúdo
e pelo histórico, em `5928561fd59a8b2f74a978365a39f1fa0fa26cbc`.
A branch estava um commit à frente da referência **local** origin/main,
que ainda apontava para 5928561; não houve consulta ao servidor remoto.

Os 91 testes frontend e 702 backend relatados pelo usuário foram tratados
como evidência anterior. O ambiente e o helper de navegador existentes foram
reaproveitados; os resultados abaixo vêm de execuções desta F3.

As mudanças ficam no frontend: cliente e teste de status esperado, auth API
e testes, hook renomeado para useAuthSession com os testes preservados,
LoginForm, SessionStatus, App, testes de integração, CSS, título HTML e README.
Não houve alteração em Vite/proxy, backend, autenticação Django, banco,
infraestrutura, .local, manifesto ou lockfile; nenhuma dependência foi instalada.

### Comandos e resultados desta execução

Ambiente efetivo: Node 24.21.0 e npm 11.19.0 portáteis, Python 3.14.7,
Django 5.2.17 e pytest 9.1.1. Cada comando nativo teve
`$LASTEXITCODE` capturado imediatamente.

| Diretório | Comando                                    | Saída final | Resultado                                                 |
| --------- | ------------------------------------------ | ----------- | --------------------------------------------------------- |
| frontend  | `npm.cmd ls --depth=0`                     | 0           | Dependências e versões preservadas                        |
| frontend  | `npm.cmd run typecheck`                    | 0           | Aplicação, testes e configurações aprovados               |
| frontend  | `npm.cmd run lint`                         | 0           | Sem erros ou avisos                                       |
| frontend  | `npm.cmd run format:check`                 | 0           | Aprovado, repetido após documentação                      |
| frontend  | `npm.cmd run test`                         | 0           | **144 testes em 5 arquivos aprovados**                    |
| frontend  | `npm.cmd run build`                        | 0           | Build gerado antes de validar preview                     |
| raiz      | executor + `backend\manage.py check`       | 0           | Nenhum problema                                           |
| raiz      | executor + `-m pytest -p no:cacheprovider` | 0           | **702 testes aprovados em 293,77 s**, uma execução global |

O executor é exatamente `.\.venv\Scripts\python.exe .\.local\dev_local.py`,
conforme os comandos completos acima. A suíte incluiu os 23 testes de
`test_auth_api.py` e o teste de `test_auth_schema.py`.

Antes da regressão foram conferidos pyproject.toml, settings de teste,
fixtures e a configuração efetiva pelo executor: PostgreSQL, banco de teste
separado com prefixo test_ e sem mirror. Pytest confirmou
`config.settings.test (from ini)`. Criação e limpeza do banco de teste
ficaram com o runner; nenhuma migration foi aplicada ao banco de desenvolvimento.
**Cobertura não foi medida nesta F3**; 97% permanece histórico.
Não foram executados npm ci, test:watch ou atualização de dependências nesta etapa.

A primeira execução de lint retornou 1 por uma atualização de estado
alcançável a partir do efeito de bootstrap. A leitura foi separada da
publicação no callback assíncrono; lint, tipos e testes foram repetidos e
aprovados, mantendo a regra de React Hooks e StrictMode.

Build: 21 módulos, HTML 0,44 kB, CSS 1,18 kB e JavaScript 229,76 kB
(71,87 kB gzip para JavaScript), conforme o Vite. Artefatos ficam ignorados
em dist, fora do versionamento.

### Navegador com Django real

Foi utilizado Chrome 152.0.7977.83 com perfil temporário, protocolo do
navegador e Node nativo, sem novas bibliotecas. As chamadas partiram das
origens abaixo, com caminhos relativos pelo proxy existente.
Não foi disponibilizada conta autorizada durante esta execução; nenhuma
credencial real foi procurada, nenhuma conta foi criada ou senha alterada.

| Verificação real                                             | Desenvolvimento — 127.0.0.1:5173                                         | Preview — 127.0.0.1:4173                         |
| ------------------------------------------------------------ | ------------------------------------------------------------------------ | ------------------------------------------------ |
| Bootstrap                                                    | CSRF 200 JSON válido; /me 403 JSON anônimo exato                         | Mesmo resultado                                  |
| Formulário                                                   | Apresentado após anonimato confirmado                                    | Mesmo resultado                                  |
| Layout                                                       | 360×800 e 1440×900, sem overflow horizontal                              | Mesmo resultado                                  |
| Teclado                                                      | Foco visível, Tab entre campos e Enter envia                             | Mesmo resultado                                  |
| Uma tentativa inválida controlada                            | Novo CSRF 200; um POST login 400 JSON; "E-mail ou senha inválidos"       | Mesmo resultado                                  |
| Após a rejeição                                              | Senha limpa, email preservado, botão habilitado; nenhum retry automático | Mesmo resultado                                  |
| API temporariamente bloqueada no navegador                   | Estado de erro, sem formulário nem falso anonimato                       | Mesmo resultado                                  |
| API liberada e Tentar novamente                              | Recuperação sem recarregar a página inteira                              | Mesmo resultado                                  |
| Login válido, rotação CSRF, sessão após reload e logout real | **Não executados: dependem de conta autorizada**                         | **Não executados: dependem de conta autorizada** |

A tentativa negativa usou dados sintéticos transitórios. Não foram salvos
corpos de login, tokens, cookies, headers sensíveis ou HAR. O cookie
csrftoken estava presente em 127.0.0.1, Path /, SameSite=Lax, Secure=false
e HttpOnly=false; seus valores não foram registrados. Não houve sessionid
nesse cenário, portanto seus atributos efetivos após login não foram comprovados.

Os GETs e o POST de credenciais inválidas vieram da API como JSON, sem
fallback HTML da SPA. A mensagem de credenciais inválidas só é publicada
após o contrato exato desse 400. Houve zero exceções JavaScript não tratadas
e zero console.error da aplicação. Rejeições HTTP esperadas e bloqueio
controlado de rede foram distinguidos desses erros.

As seis capturas sanitizadas de layout e rejeição foram inspecionadas.
Na recuperação, performance.timeOrigin permaneceu igual após o clique;
o Django não foi interrompido para simular falha. O helper terminou com
saída 0. Uma tentativa inicial do helper retornou 1 porque o evento de
teclado CDP não incluía o texto de Enter e não enviou POST; a simulação
de teclado foi corrigida e o cenário repetido sem alterar a aplicação.

### Validação autenticada ainda pendente

Os testes frontend comprovam por simulação o login válido, novo CSRF
após login, identidade somente após /me, reload por bootstrap, logout,
falhas de confirmação, timeout, resultados incertos e operações atrasadas.
Os testes backend executados comprovam o mecanismo Django e a recusa do
token antigo após login no banco de testes. Isso **não substitui o fluxo
autenticado completo no navegador pelo proxy**.

Com uma conta local de teste autorizada, sem enviar senha pelo chat:

1. Abra dev em perfil temporário sem sessão pessoal. Antes da entrada,
   obtenha um token CSRF no contexto da página e mantenha-o apenas em memória.
2. Insira as credenciais diretamente no formulário e envie por teclado.
   Confira o POST 200, novo GET CSRF, /me 200 e a identidade esperada,
   sem copiar a identidade, payload, token ou headers para registros.
3. Inspecione somente presença e atributos de sessionid; espere Path /,
   SameSite=Lax, Secure=false e HttpOnly=true nesta configuração local.
4. Faça uma única sonda POST logout com o token anterior ao login, cookies
   atuais e Origin natural. Espere rejeição CSRF 403 e confirme por /me que
   a sessão continua autenticada. Não compare strings de tokens mascarados.
5. Recarregue e confirme a sessão sem reenviar credenciais. Acione Sair na
   interface: novo CSRF, POST logout 204 vazio e leituras confirmando /me
   anônimo. Recarregue e confirme que a identidade não reaparece.
6. Repita no preview com build atual, em largura estreita e desktop,
   verificando foco, teclado, mensagens e ausência de exceções não tratadas.
   Remova somente o perfil temporário e encerre somente servidores próprios.

Não há validação autenticada integral da F3 enquanto esses cenários reais
não forem executados. Organizações, módulos empresariais, sincronização entre
abas e produção não foram implementados ou validados.

### Revisão e encerramento

O fechamento da F2 foi preservado integralmente. Manifesto, lockfile e índice
do Git mantiveram seus hashes SHA-256 iniciais. A revisão incluiu arquivos
novos, diff --check e ausência de alterações em backend e .local. Nenhum
segredo ou artefato gerado foi incluído entre os arquivos da entrega.
As alterações da F3 permanecem no diretório de trabalho, sem staging,
commit, push ou avanço de etapa.

Não havia servidores nas portas 8000, 5173 e 4173 no início. Todos os três
servidores usados nesta F3 foram próprios, tiveram prontidão confirmada e
foram encerrados: dev e preview com saída 0; Django interrompido após o
smoke, com saída 1 do terminal. A conferência final encontrou as três portas
livres e nenhum processo do Chrome desse perfil. Somente o perfil temporário
da F3 foi removido, após validar seu caminho; nenhum processo ou perfil do
usuário foi encerrado.
