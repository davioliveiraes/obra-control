# ObraControl — frontend (F1)

Fundação técnica em React, TypeScript e Vite: tela inicial em português,
checagem de tipos, lint, formatação, teste de componente e build.
Não implementa funcionalidades empresariais, rotas, autenticação, seleção
de organização ou integração HTTP.

A tela funciona **sem o backend ligado** e sem configuração de banco.
Não é necessário copiar arquivos de `.local/` ou configurações privadas.
Não há variáveis de ambiente consumidas pelo frontend nesta etapa.

## Ambiente

- Windows x64 / PowerShell.
- Node.js **24.21.0 LTS**; requisito: `>=24.21.0 <25`.
- npm **11.19.0**; requisito: `>=11.19.0 <12`.
- Pacote independente: instalação e lockfile em `frontend/`.
- `packageManager` registra npm; `.npmrc` mantém `engine-strict=true`.

O ambiente original tinha Node 22.20.0 e npm 10.9.3. Para esta F1 foi usado
o ZIP oficial portátil de Node 24.21.0, conferido por SHA-256, com npm 11.19.0.
O PATH foi ajustado somente nos processos de validação; a instalação global
permanece intacta. Em um novo terminal, disponibilize as versões requeridas
no PATH antes de executar os comandos. Node 22.20.0 não atende a esta base.

Confira com `node --version` e `npm --version`. Não misture gerenciadores;
o npm mantém `package-lock.json`, sem edição manual.

Versões fixadas:

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

Os engines e peers dessas versões exatas foram consultados no registro npm.
TypeScript 6.0.3 atende à faixa `>=4.8.4 <6.1.0` do typescript-eslint;
TypeScript 7 não foi selecionado. Node 24.21.0 atende ao mínimo 24.15.0
do jsdom 30.0.1. Vite 8 é aceito pelo plugin React 6 e pelo Vitest 5.
Testing Library aceita React 19, seus tipos e DOM 10.

Referências: [Node 24.21.0 LTS](https://nodejs.org/en/blog/release/v24.21.0),
[template Vite](https://vite.dev/guide/),
[typescript-eslint](https://typescript-eslint.io/users/dependency-versions/),
[Vitest](https://vitest.dev/guide/) e
[Testing Library](https://testing-library.com/docs/react-testing-library/setup/).

## Instalação e desenvolvimento

A partir da raiz do repositório, com as versões requeridas no PATH:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Desenvolvimento: **http://127.0.0.1:5173/**.
`strictPort: true` faz o servidor falhar se a porta estiver ocupada,
sem mudar silenciosamente a origem. Use Ctrl+C para encerrar seu servidor.

Para conferir o build:

```powershell
npm run build
npm run preview
```

Preview: **http://127.0.0.1:4173/**, também com host local e porta fixa.
Serve `dist/` para conferência; não é um servidor de produção.

## Comandos

Execute dentro de `frontend/`; o npm executa os scripts na raiz deste pacote.

| Comando                | Implementação               |
| ---------------------- | --------------------------- |
| `npm run dev`          | `vite`                      |
| `npm run typecheck`    | `tsc -b --pretty false`     |
| `npm run lint`         | `eslint . --max-warnings 0` |
| `npm run format`       | `prettier --write .`        |
| `npm run format:check` | `prettier --check .`        |
| `npm run test`         | `vitest run`                |
| `npm run test:watch`   | `vitest`                    |
| `npm run build`        | `tsc -b && vite build`      |
| `npm run preview`      | `vite preview`              |

Verificação reproduzível, executando cada comando separadamente:

```powershell
npm ci
npm ls --depth=0
npm run typecheck
npm run lint
npm run format:check
npm run test
npm run build
```

No PowerShell, capture `$LASTEXITCODE` imediatamente após cada comando nativo
para registrar seu resultado; o sucesso de um comando posterior não valida
o anterior. `npm.cmd` pode ser usado para chamar o mesmo gerenciador
diretamente no Windows, sem alterar políticas de execução.

## Estrutura e qualidade

```text
frontend/
├── .gitattributes
├── .gitignore
├── .npmrc
├── .prettierignore
├── .prettierrc.json
├── README.md
├── eslint.config.js
├── index.html
├── package.json
├── package-lock.json
├── tsconfig.json
├── tsconfig.app.json
├── tsconfig.node.json
├── vite.config.ts
└── src/
    ├── main.tsx
    ├── styles.css
    ├── app/
    │   ├── App.tsx
    │   └── App.test.tsx
    └── test/
        └── setup.ts
```

Base oficial: `create-vite@9.2.1`, template `react-ts`, opção `--eslint`.
Somente os exemplos e assets gerados nesta tarefa foram removidos.
O CSS usa fontes do sistema, sem recursos externos ou identidade definitiva.

`main.tsx` monta a aplicação; `App.tsx` contém a composição mínima.
Os project references do template foram preservados, com `strict: true`
explícito nos dois projetos. `tsconfig.app.json` inclui todo `src/`,
alcançando teste e setup, e mantém `vite/client`. `tsconfig.node.json`
inclui `vite.config.ts`. `tsc -b` verifica ambos; o build só chama o Vite
se essa verificação passar.

ESLint usa flat config e recomendações de JavaScript, TypeScript, React Hooks
e React Refresh. Prettier funciona separadamente, com LF e sem plugin de
lint para formatação. Os comandos se restringem ao frontend. Dependências,
build, caches, arquivos de ambiente e lockfile ficam fora da formatação;
o manifesto, o lockfile e os fontes continuam versionáveis.

O Git local usa `core.autocrlf=true`. `frontend/.gitattributes` fixa LF somente
nos arquivos de texto do frontend, evitando que um novo checkout em Windows
entre em conflito com o Prettier. Nenhuma configuração global foi alterada.

Vitest usa jsdom, imports explícitos, `globals: false`, matchers de
`@testing-library/jest-dom/vitest` e cleanup registrado em `afterEach`.
O teste renderiza App, encontra `main` pelo papel semântico e verifica o
heading acessível "ObraControl" e a mensagem de fundação técnica.
O comando padrão executa uma vez e encerra. Não há Jest, chamadas externas,
snapshots, cobertura obrigatória ou sucesso artificial sem testes.

## Arquivos servidos e API futura

A raiz efetiva do Vite é `frontend/`. `server.fs.strict` está habilitado e
`server.fs.allow` permite somente essa pasta, incluindo seu `node_modules/`.
A lista explícita impede ampliação automática por descoberta de workspace.
A raiz do repositório, `backend/` e `.local/` não são permitidos.
Não há `envDir` externo, proxy, cliente HTTP ou arquivos em `public/`.

**Proposta ainda não implementada:**

1. O navegador acessará o Vite em `http://127.0.0.1:5173/`.
2. O frontend fará chamadas relativas a `/api/v1/`.
3. Um futuro proxy de desenvolvimento encaminhará as chamadas ao Django em
   `http://127.0.0.1:8000/`.
4. A integração precisará validar Host, Origin, cookies e CSRF conforme
   a autenticação por sessão e o contexto de organização existentes.

O proxy do Vite será exclusivo de desenvolvimento. Produção precisará de
configuração própria de hospedagem/proxy, preferencialmente na mesma origem.
Esta F1 não altera CORS, SameSite, CSRF, autenticação, tenant ou settings Django.

## Validação executada em 12/09/2026

Ambiente efetivamente testado: Windows x64, Node 24.21.0 e npm 11.19.0,
com as versões de dependências da tabela acima. Todos os comandos abaixo
foram executados individualmente em `frontend/`, usando `npm.cmd`:

| Comando                | Saída | Resultado                                               |
| ---------------------- | ----- | ------------------------------------------------------- |
| `npm install`          | 0     | Primeiro lockfile gerado                                |
| `npm run format`       | 0     | Somente arquivos do frontend                            |
| `npm ci`               | 0     | Manifesto e lockfile preservados por comparação SHA-256 |
| `npm ls --depth=0`     | 0     | Dependências diretas nas versões selecionadas           |
| `npm run typecheck`    | 0     | Aplicação, teste, setup e configuração TypeScript       |
| `npm run lint`         | 0     | Sem erros ou avisos                                     |
| `npm run format:check` | 0     | Formatação aprovada                                     |
| `npm run test`         | 0     | 1 arquivo e 1 teste aprovados                           |
| `npm run build`        | 0     | HTML, CSS e JavaScript em `dist/`                       |

Instalação e reinstalação reportaram zero vulnerabilidades no npm.
O build final gerou HTML de 0,47 kB, CSS de 0,51 kB e JavaScript de 219,96 kB
(68,76 kB gzip para o JavaScript), conforme os tamanhos exibidos pelo Vite.

Os scripts `dev` e `preview` foram iniciados nos endereços documentados;
ambos responderam HTTP 200. A configuração resolvida confirmou raiz e
workspace em `frontend/`, incluindo `envDir`, e `fs.allow` restrito a essa pasta.
Requisições HEAD a arquivos existentes da raiz e do backend retornaram 403.
A política resolvida também negou os caminhos privados de `.local/`, sem ler
seu conteúdo. Um caminho inexistente usado inicialmente como sonda recebeu
o fallback HTML da SPA; ele foi substituído por verificações apropriadas.

Chrome 152.0.7977.83, headless, validou dev e preview em 360×800 e 1440×900:
React renderizado, conteúdo e papéis acessíveis esperados, `lang="pt-BR"`,
título correto, ausência de overflow horizontal e de erros de console/runtime,
sem recursos externos, Fetch/XHR ou chamadas de API. As quatro capturas foram
inspecionadas visualmente. O primeiro smoke detectou 404 de `favicon.ico`;
o HTML passou a declarar um favicon vazio embutido (`data:,`), e o build,
a formatação e os smoke tests afetados foram repetidos com sucesso.
Os helpers usaram o Node portátil preparado e o Chrome instalado, sem instalar
ferramentas E2E.
Os servidores e o navegador temporários foram encerrados.

Não foram executados Python, Django, a suíte do backend ou cobertura frontend.
Os 702 testes e 97% de cobertura do backend são números históricos relatados,
não uma revalidação desta F1. Integração com a API e produção continuam fora
do escopo; o modo `test:watch` não foi exercitado nesta validação.
