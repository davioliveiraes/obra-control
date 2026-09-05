# ObraControl

## Descrição do Projeto
**ObraControl** é um SaaS para gerenciamento de orçamentos e ordens de serviço na construção civil, desenvolvido com foco em produtividade, organização e escalabilidade, utilizando boas práticas de arquitetura de software.

A plataforma tem como objetivo centralizar e automatizar processos essenciais de gestão de obras, permitindo maior controle financeiro, operacional e administrativo para empresas e profissionais da construção civil.

---

## Objetivo
Desenvolver uma solução SaaS que facilite o gerenciamento de orçamentos, ordens de serviço e acompanhamento de obras, promovendo eficiência operacional e melhor organização dos processos internos.

---

## Público-Alvo
- Empresas de construção civil
- Engenheiros civis
- Mestres de obras
- Prestadores de serviços
- Pequenas e médias construtoras

---

## Principais Funcionalidades

### Gestão de Orçamentos
- Cadastro de clientes
- Criação de orçamentos detalhados
- Cálculo automático de custos
- Histórico de orçamentos
- Aprovação e acompanhamento de propostas

### Ordens de Serviço
- Geração de ordens de serviço
- Acompanhamento de status
- Registro de responsáveis
- Controle de prazos
- Histórico de serviços realizados

### Gestão de Obras
- Cadastro de obras e projetos
- Controle de etapas
- Monitoramento de andamento
- Registro de custos por obra

### Dashboard Gerencial
- Indicadores financeiros
- Resumo de serviços em andamento
- Acompanhamento de produtividade
- Relatórios gerenciais

---

## Diferenciais do Sistema
- Centralização das informações em uma única plataforma
- Redução de processos manuais
- Melhor controle de custos e serviços
- Escalabilidade para diferentes portes de empresa
- Interface moderna e intuitiva

---

## Tecnologias Utilizadas

### Backend
- **Python 3.14**
- **Django 5.2 LTS**
- **Django REST Framework**
- **Django ORM**

### Banco de Dados
- **PostgreSQL**

### Infraestrutura
- **Docker**

### Qualidade de Código
- **Pytest**
- **Ruff**
- **Coverage**
- **Pre-commit**

### Frontend
- **React**
- **Tailwind CSS**

---

## Arquitetura
O projeto será desenvolvido como um monólito modular, seguindo boas práticas de organização e manutenção:

- **API / Serializer** → Entrada e validação das requisições
- **Service** → Regras de negócio, quando a complexidade justificar
- **Django ORM** → Persistência padrão no PostgreSQL

Os módulos serão separados por domínio dentro do mesmo backend, sem
microserviços ou camadas cerimoniais antecipadas.

---

## Identidade do Projeto

### Nome
**ObraControl**

### Slogan
**Controle total da sua obra**

A identidade do projeto transmite organização, eficiência e domínio sobre processos da construção civil.

---

## Visão de Futuro
Expandir o ObraControl para se tornar uma plataforma completa de gestão para construção civil, incorporando funcionalidades como:
- Gestão de equipes
- Controle de materiais
- Integração com financeiro
- Aplicativo mobile
- Relatórios avançados
- Inteligência artificial para previsão de custos

---

## Repositório
Sugestão de nome para o repositório:
**obracontrol-api**

---

## Resumo Executivo
O **ObraControl** nasce como uma solução tecnológica para modernizar a gestão de obras, oferecendo controle sobre orçamentos, serviços e processos operacionais. Com uma arquitetura escalável e tecnologias modernas, o sistema visa aumentar a produtividade e reduzir falhas administrativas, contribuindo para uma gestão mais eficiente e profissional no setor da construção civil.
