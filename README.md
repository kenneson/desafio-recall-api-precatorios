# Sistema de Precatórios TJPR

Este repositório entrega uma API em FastAPI para acompanhar precatórios judiciais do Estado do Paraná. A solução cobre as quatro etapas do desafio: coleta assistida da fila pública, processamento dos documentos OCR, criação de tarefas futuras e exposição de uma linha do tempo auditável.

## Stack utilizada

- Python 3.11+
- FastAPI
- SQLAlchemy
- SQLite
- Playwright
- Pytest

## Pré-requisitos

- Python 3.11 ou superior.
- Git.
- Acesso ao terminal para instalar dependências.
- Navegador Chromium instalado pelo Playwright para executar a coleta assistida.

## Execução local

Criar e ativar um ambiente virtual é recomendado:

```bash
python -m venv .venv
```

No Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

No Linux/macOS:

```bash
source .venv/bin/activate
```

Instalar as dependências, baixar o navegador usado pelo RPA e subir a API:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m uvicorn src.main:app --reload
```

A documentação interativa da API fica disponível em:

```text
http://127.0.0.1:8000/docs
```

Abrir `http://127.0.0.1:8000/` também redireciona automaticamente para `/docs`.

Para carregar variáveis locais, como configuração opcional de IA, usar:

```bash
python -m uvicorn src.main:app --reload --env-file .env
```

O arquivo `.env.example` contém as variáveis aceitas pela aplicação. Para usar configurações locais, criar um `.env` a partir dele e preencher apenas os valores necessários.

No Windows:

```powershell
Copy-Item .env.example .env
```

No Linux/macOS:

```bash
cp .env.example .env
```

O banco SQLite local é criado em `data/app.db` na primeira execução da API. Se o schema local ficar desatualizado durante o desenvolvimento, remover esse arquivo e subir a API novamente recria o banco a partir dos modelos SQLAlchemy.

## Dependência do RPA

O endpoint `POST /rpa/coletar` usa Playwright com navegador visível para permitir a resolução manual do captcha. Por isso, além de instalar os pacotes Python, é necessário baixar o Chromium usado pelo Playwright:

```bash
python -m playwright install chromium
```

Essa abordagem evita qualquer tentativa de burlar o captcha e mantém a automação aderente ao fluxo permitido: o navegador abre, o usuário conclui a pesquisa manualmente e a aplicação extrai somente os números dos precatórios da página resultante.

## Uso do RPA no portal do TJPR

O RPA foi implementado como coleta assistida. Ele não tenta quebrar captcha nem automatizar campos protegidos do portal.

Ao chamar `POST /rpa/coletar`, a requisição fica aberta enquanto o navegador do Playwright está em uso. O fluxo esperado é:

1. A API abre a página `Precatórios em ordem cronológica de pagamento` do TJPR.
2. A API tenta selecionar automaticamente o `Órgão Devedor` informado no payload, por exemplo `CURITIBA` ou `Estado do Parana`.
3. Caso o portal exija clique manual ou o componente não seja um `select` HTML simples, conferir ou selecionar manualmente o órgão devedor.
4. Manter o campo `Página` com a quantidade desejada de itens, por exemplo `50 itens`.
5. Deixar o campo `N. Precatório/Processo` vazio quando a intenção for coletar a fila geral.
6. Ler a imagem de verificação exibida pelo portal.
7. Digitar o texto da imagem no campo `Texto da imagem`.
8. Clicar no botão `Pesquisar`.
9. Aguardar a tabela/listagem de resultados aparecer na própria página.
10. Depois que a página exibir a tabela, a API extrai os números da própria tabela, fecha o navegador e retorna a resposta no Swagger.

Responsabilidades automáticas:

- abrir o navegador;
- acessar a página pública;
- tentar selecionar o órgão devedor quando o portal expuser esse campo como `select` HTML simples, aceitando texto parcial como `CURITIBA` para a opção `CURITIBA - Regime geral (Art. 100 CF)`;
- aguardar a pesquisa manual;
- extrair preferencialmente o CNJ completo da coluna `Autos do Precatório`, como `0023456-81.2018.8.16.0000`;
- usar o `Ofício Precatório`, como `2024/906061`, quando o CNJ vier mascarado no portal público;
- preservar a ordem em que os números aparecem;
- persistir a coleta em `coleta_precatorios`.

Observação sobre os identificadores: a tabela pública do TJPR costuma exibir `Autos do Precatório` mascarado, por exemplo `000xxxx-95.xxxx.8.16.7000`. Quando isso acontece, a coleta persiste o `Ofício Precatório` disponível para demonstrar a extração real da fila pública, preservando a ordem cronológica. A resposta do endpoint inclui `avisos`, informando que, para processar documentos locais, ainda é necessário usar o número CNJ completo do arquivo em `/documentos`.

Responsabilidades manuais:

- conferir ou selecionar o órgão devedor quando o componente do portal exigir clique manual;
- resolver o captcha;
- clicar em `Pesquisar`;
- aguardar visualmente o carregamento da listagem.

Exemplo de corpo da requisição:

```json
{
  "ente_devedor": "Estado do Parana",
  "timeout_segundos": 180
}
```

Exemplo de resposta quando o CNJ completo está mascarado no portal e a coleta usa `Ofício Precatório`:

```json
{
  "total": 1,
  "numeros": ["2024/906061"],
  "avisos": [
    "CNJ completo nao estava disponivel na tabela publica; coleta persistida com Oficio Precatorio.",
    "Para processar documentos locais, use o numero CNJ do arquivo em /documentos."
  ]
}
```

Se o tempo expirar antes de a tabela aparecer, aumentar `timeout_segundos` e repetir a coleta.

## Testes

```bash
python -m pytest
```

## Endpoints principais

| Método | Endpoint | Status esperado | Finalidade |
| --- | --- | --- | --- |
| `GET` | `/health` | `200 OK` | Verifica se a API está respondendo. |
| `POST` | `/rpa/coletar` | `200 OK` | Abre o portal do TJPR com Playwright, aguarda a interação manual e persiste os números coletados na ordem da tabela. |
| `GET` | `/rpa/coletas` | `200 OK` | Lista os números já coletados pelo RPA, preservando a ordem cronológica capturada. |
| `POST` | `/precatorios/{numero}/processar` | `201 Created` | Localiza o documento `.txt`, extrai os dados estruturados, classifica o status, cria tarefa e registra eventos. |
| `GET` | `/precatorios/{numero}` | `200 OK` | Consulta o estado estruturado atual de um precatório já processado. |
| `GET` | `/precatorios/{numero}/timeline` | `200 OK` | Retorna a linha do tempo com eventos extraídos do documento e eventos adicionados pela API. |
| `POST` | `/precatorios/{numero}/eventos` | `201 Created` | Registra manualmente um novo evento na linha do tempo do precatório. |
| `GET` | `/fila` | `200 OK` | Lista as tarefas pendentes ordenadas por prioridade e ordem de chegada. |
| `POST` | `/fila` | `201 Created` | Insere manualmente uma tarefa futura na fila de processamento. |

## Fluxo principal

1. `POST /rpa/coletar` abre o portal do TJPR com Playwright em modo assistido.
2. O órgão devedor, a verificação de texto e o clique em `Pesquisar` são conduzidos manualmente no navegador aberto quando necessário.
3. A API extrai o CNJ completo da coluna `Autos do Precatório` quando ele estiver disponível; se o CNJ estiver mascarado, extrai o `Ofício Precatório`, preservando a ordem cronológica encontrada.
4. `POST /precatorios/{numero}/processar` localiza o documento em `documentos/`, extrai campos estruturados, classifica o status, salva o estado atual, cria uma tarefa e registra eventos na timeline.
5. `GET /fila` lista tarefas pendentes por prioridade e ordem de chegada.
6. `GET /precatorios/{numero}/timeline` retorna eventos extraídos do documento e atualizações recebidas pela API.

## Evolução preparada para LLM

O processamento de documentos passa por uma camada `DocumentExtractor`. O caminho principal é `RuleBasedDocumentExtractor`, baseado em regras auditáveis e testes automatizados. A estrutura também possui `LlmAssistedDocumentExtractor`, que pode ser ativado por variáveis de ambiente para auxiliar documentos mais variáveis.

O fluxo preparado é:

```text
texto OCR -> parser por regras -> confiança/warnings -> LLM opcional -> validação -> persistência
```

Por padrão, a LLM não é chamada. A integração real fica disponível de forma opt-in por variáveis de ambiente. Quando o parser encontra documento ambíguo, a camada de extração sinaliza baixa confiança e recomendação de revisão por IA. Se o arquivo `.env` estiver com `LLM_ENABLED=true` e uma chave configurada em `GROQ_API_KEY` ou `LLM_API_KEY`, o sistema tenta acionar a LLM para obter uma extração estruturada validada.

Os campos abaixo ficam disponíveis no retorno de `POST /precatorios/{numero}/processar` e `GET /precatorios/{numero}`:

```text
extraction_method
extraction_confidence
extraction_warnings
llm_recommended
```

Quando `llm_recommended` vier como `true`, o documento foi processado pelas regras atuais, mas a API está sinalizando que uma análise por IA ou revisão assistida ainda é recomendada. Quando a LLM é acionada com sucesso, `extraction_method` passa a ser `llm_assisted`.

Por padrão, a chamada real à LLM fica desligada. Para testar com Groq, configurar:

```bash
set LLM_ENABLED=true
set GROQ_API_KEY=sua_chave_groq
set LLM_MODEL=llama-3.3-70b-versatile
```

No PowerShell:

```powershell
$env:LLM_ENABLED="true"
$env:GROQ_API_KEY="sua_chave_groq"
$env:LLM_MODEL="llama-3.3-70b-versatile"
```

Variáveis aceitas:

```text
LLM_ENABLED=false
GROQ_API_KEY=
LLM_API_KEY=
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
LLM_TIMEOUT_SECONDS=30
LLM_CONFIDENCE_THRESHOLD=0.75
```

Quando `LLM_ENABLED=true`, a LLM só é chamada se o parser por regras indicar baixa confiança ou recomendar revisão. Se a chave estiver ausente ou a chamada falhar, a API mantém o resultado por regras e adiciona um aviso em `extraction_warnings`.

## Exemplo de uso

```bash
curl -X POST http://127.0.0.1:8000/precatorios/0023456-81.2018.8.16.0000/processar
curl http://127.0.0.1:8000/fila
curl http://127.0.0.1:8000/precatorios/0023456-81.2018.8.16.0000/timeline
```

## Fluxo sugerido para teste do sistema

1. Subir a API:

```bash
python -m uvicorn src.main:app --reload
```

2. Abrir o Swagger:

```text
http://127.0.0.1:8000/docs
```

3. Rodar a coleta assistida:

```text
POST /rpa/coletar
```

4. Consultar a coleta persistida:

```text
GET /rpa/coletas
```

5. Processar um documento local:

```text
POST /precatorios/0023456-81.2018.8.16.0000/processar
```

6. Ver os dados estruturados:

```text
GET /precatorios/0023456-81.2018.8.16.0000
```

7. Ver fila e timeline:

```text
GET /fila
GET /precatorios/0023456-81.2018.8.16.0000/timeline
```

## Cuidados de segurança

- O número do precatório é validado por regex antes de qualquer operação.
- O caminho do documento é resolvido de forma controlada dentro de `documentos/`, evitando path traversal.
- O banco é acessado por SQLAlchemy ORM, sem concatenação de SQL com entrada externa.
- As entradas e respostas HTTP usam schemas Pydantic.
- Erros inesperados são tratados por handler global, evitando expor traceback ao cliente.
- Datas inválidas vindas de OCR são ignoradas com aviso em `extraction_warnings`, sem derrubar o processamento.
- O Playwright é importado apenas no fluxo de RPA, mantendo o restante da API funcional mesmo sem o navegador instalado.
- Tarefas automáticas pendentes não são duplicadas para o mesmo precatório e a mesma ação.

As decisões de modelagem, taxonomia e prioridade estão detalhadas em `DECISIONS.md`.

by Kenneson Anderson.
