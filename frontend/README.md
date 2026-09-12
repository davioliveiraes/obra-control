# ObraControl — frontend (F2)

Integração local inicial em React, TypeScript e Vite: preparação de CSRF,
consulta da sessão atual e estados de verificação, sessão autenticada,
ausência de sessão e falha com tentativa manual.

A integração real **precisa do Django ligado**. Os testes frontend usam
mocks locais de fetch e continuam independentes do backend.
Não há formulário de login, logout, seleção de organização, rotas ou
módulos empresariais. Não é necessário copiar arquivos de `.local/`,
configurações privadas ou criar variáveis de ambiente para o frontend.

## Ambiente preservado da F1

- Windows x64 / PowerShell.
- Node.js **24.21.0 LTS**; requisito: `>=24.21.0 <25`.
- npm **11.19.0**; requisito: `>=11.19.0 <12`.
- Pacote independente, instalação e lockfile em `frontend/`.
- `packageManager` registra npm; `.npmrc` mantém `engine-strict=true`.

A F2 reutilizou o Node portátil preparado na F1. O ambiente global,
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

Nenhuma dependência foi adicionada ou atualizada na F2:

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
SHA-256 antes e depois de `npm.cmd ci`.

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

Outro terminal, com o Node portátil no PATH:

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

| Operação                                           | Contrato observado                                                                                       |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `GET /api/v1/auth/csrf/`                           | 200 JSON, objeto com `csrfToken` string; token mascarado gerado pelo Django e cookie CSRF                |
| `GET /api/v1/auth/me/` autenticado                 | 200 JSON: `id` inteiro positivo, `email` string, `first_name` e `last_name` strings que podem ser vazias |
| `GET /api/v1/auth/me/` sem sessão                  | 403 JSON com o único campo `detail`, conforme abaixo                                                     |
| `POST /api/v1/auth/login/` com JSON `{}` sem token | 403 HTML de rejeição CSRF                                                                                |
| Mesmo POST com cookies e token válidos             | 400 JSON de validação dos campos obrigatórios, conforme abaixo                                           |

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
`LoginSerializer` valida email e password antes de chamar authenticate;
portanto o JSON `{}` usado na sonda não pode autenticar.
`MeView` usa `IsAuthenticated`, com `SessionAuthentication` do DRF.
Os dois GETs aplicam `never_cache`.

Evidências automatizadas:
[test_auth_api.py](../backend/tests/accounts/test_auth_api.py) verifica
cookies, CSRF anônimo, origem rejeitada, validação de campos e identidade;
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

## Transporte e inicialização

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
Essas categorias são locais, não códigos atribuídos ao backend.

`features/auth/api.ts` usa `cache: "no-store"` e verificações runtime
dos campos e tipos. O bootstrap obtém CSRF, descarta o token de preparação
e consulta `/me/`. Obter CSRF não prova autenticação nem significa que
o GET exija CSRF. O helper continua disponível para obter um token por
operação futura; não há cache global permanente ou mutação de autenticação.

`useSessionBootstrap` mantém estados explícitos. Retry limpa a identidade
anterior e inicia nova verificação. Cleanup aborta requisições obsoletas;
o identificador da tentativa e o sinal impedem resultados atrasados.
StrictMode permanece ativo, com um novo controller por efeito.
Não há polling, retry automático, refresh, redirect ou logout automático.
Nenhum token, identidade ou credencial é persistido em localStorage ou
sessionStorage. A interface apresenta mensagens seguras, sem HTML da API,
tracebacks, cookies ou headers sensíveis.

## Estrutura e testes

Arquivos de aplicação e testes utilizados:

```text
src/
  main.tsx
  styles.css
  app/
    App.tsx
    App.test.tsx
  features/auth/
    api.ts
    api.test.ts
    useSessionBootstrap.ts
    useSessionBootstrap.test.tsx
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
botão de retry e foco visível. O CSS usa fontes do sistema e não carrega
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
Nenhum teste frontend exige Django, contas reais ou chamadas externas.

Regressão backend, na raiz e pelo executor:

```powershell
.\.venv\Scripts\python.exe .\.local\dev_local.py -m pytest -p no:cacheprovider backend/tests/accounts/test_auth_api.py backend/tests/accounts/test_auth_schema.py
.\.venv\Scripts\python.exe .\.local\dev_local.py -m pytest -p no:cacheprovider
```

## Validação da F2 em 12/09/2026

Estado inicial limpo em main, F1 confirmada pelo conteúdo do HEAD
`66fc2d86c6a635c222150df057db93699b24957e`. A referência remota local
origin/main apontava para o mesmo commit; isso não é consulta atual ao remoto.

Comandos executados separadamente, com código de saída capturado:

| Diretório | Comando                                              | Saída | Resultado                                                                                 |
| --------- | ---------------------------------------------------- | ----- | ----------------------------------------------------------------------------------------- |
| frontend  | `npm.cmd ci`                                         | 0     | Instalação reproduzível, zero vulnerabilidades reportadas; manifesto/lockfile preservados |
| frontend  | `npm.cmd ls --depth=0`                               | 0     | Dependências da F1 preservadas                                                            |
| frontend  | `npm.cmd run typecheck`                              | 0     | Aplicação, testes, setup e configuração                                                   |
| frontend  | `npm.cmd run lint`                                   | 0     | Sem erros ou avisos                                                                       |
| frontend  | `npm.cmd run format:check`                           | 0     | Formatação aprovada                                                                       |
| frontend  | `npm.cmd run test`                                   | 0     | **91 testes em 4 arquivos aprovados**                                                     |
| frontend  | `npm.cmd run build`                                  | 0     | Build de produção gerado                                                                  |
| raiz      | executor + `backend\manage.py check`                 | 0     | Nenhum problema                                                                           |
| raiz      | executor + `backend\manage.py showmigrations --plan` | 0     | Todas aplicadas; nenhuma migration executada                                              |
| raiz      | executor + pytest dos dois arquivos de auth acima    | 0     | **24 testes aprovados**                                                                   |
| raiz      | executor + pytest global acima, uma execução         | 0     | **702 testes aprovados**                                                                  |

Também foi executado `npm.cmd run format`, com saída 0, somente no frontend.
Um aviso inicial de lint sobre ref no cleanup foi corrigido, e a verificação
afetada passou. Comandos Git/executor inicialmente bloqueados pela identidade
do sandbox foram repetidos fora dele, sem alterar configuração global.

Build: 20 módulos, HTML 0,46 kB, CSS 0,78 kB e JavaScript 224,50 kB
(70,46 kB gzip para JavaScript), conforme o Vite.
Backend: Python 3.14.7, Django 5.2.17, pytest 9.1.1.
Não foi gerada cobertura nesta etapa; 97% continua sendo dado histórico.

### Smoke real e procedimento de conferência

Foi usado Chrome 152.0.7977.83 headless com perfil temporário sem sessão
pessoal, controlado pelo protocolo do navegador com Node nativo.
Não foram instalados Playwright, Cypress ou outras bibliotecas.

Com Django e o servidor escolhido prontos:

1. Abra dev e preview em 360×800 e 1440×900. Confira main, h1, estágio F2,
   idioma pt-BR, sessão anônima, ausência de overflow e erros JavaScript.
2. Na rede, confirme CSRF 200 JSON e /me 403 JSON com o contrato acima,
   sem fallback HTML. Inspecione apenas presença/atributos do cookie,
   sem registrar valores, Cookie ou Set-Cookie.
3. Após confirmar no código que JSON `{}` não autentica, envie uma sonda
   POST login com esse corpo e sem token: deve rejeitar CSRF.
   Obtenha CSRF na mesma sessão do navegador e repita `{}` com X-CSRFToken:
   deve retornar os erros de email e password acima. Não compare o token
   mascarado com o cookie e não registre seu valor.
4. Bloqueie somente `*/api/v1/*` na rede do navegador e recarregue.
   Confira a mensagem segura e o botão Tentar novamente, sem anonimato
   ou repetição automática. Desbloqueie e acione retry; a consulta deve
   recuperar o estado. Não interrompa servidores preexistentes.

Esse procedimento passou em dev e preview. Em cada origem, houve uma
sonda POST sem token (403 HTML) e outra com token válido (400 JSON com
os dois campos obrigatórios). O cookie csrftoken estava presente em
127.0.0.1, Path /, SameSite=Lax, Secure=false e HttpOnly=false.
Não houve cookie sessionid. Nenhum valor de token/cookie foi registrado.

As quatro capturas de layout e duas de indisponibilidade foram
inspecionadas visualmente. Foco por teclado ficou visível, retry recuperou
a tela e não houve exceção JavaScript não tratada nem console.error da
aplicação. Rejeições HTTP 403/400 e bloqueios de rede esperados foram
separados de erros JavaScript. Somente endpoints de auth foram consultados.

O helper de navegador precisou ajustar a classificação de URLs para não
confundir o módulo client.ts com chamada API e usar Tab real na checagem
de foco. As verificações afetadas foram repetidas, preservando as sondas
POST já executadas, e o smoke final terminou com saída 0.

A configuração resolvida confirmou proxy compartilhado pelo preview e
filesystem restrito. HEAD para arquivos existentes da raiz e backend
retornou 403. A política também negou os caminhos privados de .local
sem ler seu conteúdo.

O ramo autenticado foi validado por mocks com identidade fictícia.
Não havia sessão de teste autorizada para validá-lo no navegador;
nenhuma conta foi criada ou senha alterada. Login completo, rotação
pós-login, logout e produção não foram validados e estão fora desta entrega.
O modo test:watch não foi exercitado; o comando padrão executou e encerrou.

Vite dev e preview encerraram com saída 0. Django foi interrompido
intencionalmente após o smoke (saída 1 do terminal). A conferência final
não encontrou listeners nas portas 8000, 5173 ou 4173 nem processos do
Chrome com o perfil temporário da F2. Servidores preexistentes não foram
interrompidos.
