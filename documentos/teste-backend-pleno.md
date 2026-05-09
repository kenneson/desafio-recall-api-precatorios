# Teste Prático — Desenvolvedor Backend Pleno

Prazo de entrega: 48 horas após o recebimento
Uso de IA: permitido e esperado
Entregáveis: repositório no GitHub + README.md + DECISIONS.md

---

## Contexto

Você vai trabalhar num sistema que acompanha precatórios judiciais do Estado do 
Paraná. Precatórios são dívidas reconhecidas judicialmente que o poder público 
tem obrigação de pagar, e eles seguem uma fila cronológica oficial publicada 
pelo próprio TJPR.

O pipeline que você vai construir tem três responsabilidades: coletar essa fila 
do portal público do tribunal, processar os documentos associados a cada 
precatório e manter um histórico auditável de tudo que aconteceu com cada 
um deles.

---

## Etapa 1 — Coleta automatizada (RPA)

O TJPR publica a lista de precatórios em ordem cronológica de pagamento em:

  https://www.tjpr.jus.br/precatorios-em-ordem-cronologica-de-pagamento

Construa um processo automatizado que acesse essa página, percorra a listagem 
e extraia os números dos precatórios mantendo a ordem cronológica original. 
Apenas os números devem ser persistidos nessa etapa — nenhum outro dado da 
página.

O resultado dessa extração é o insumo para a próxima etapa.

---

## Etapa 2 — Processamento de documentos

Para cada número de precatório coletado na etapa anterior, o sistema vai receber 
um documento judicial correspondente. Esses documentos simulam o texto bruto 
extraído via OCR de ofícios e certidões — chegam sem estrutura garantida, com 
variações de linguagem jurídica e campos que nem sempre aparecem da mesma forma.

Os documentos estão na pasta /documentos deste repositório, nomeados pelo número 
do precatório ao qual se referem.

Construa um endpoint que receba o número de um precatório, localize o documento 
correspondente e devolva as informações estruturadas extraídas dele. Entre as 
informações a extrair está o status atual do precatório, que deve ser classificado 
numa taxonomia que você vai definir e documentar. Essa taxonomia precisa ser capaz 
de lidar com as diferentes formas que um mesmo status pode ser expresso num texto 
jurídico.

---

## Etapa 3 — Fila de processamento

Com base no status extraído na etapa anterior, o sistema deve determinar qual ação 
tomar e enfileirar essa tarefa para execução futura. As regras que definem qual 
ação enfileirar e com qual prioridade são decisão sua — mas devem ser coerentes 
com o domínio de precatórios e estar explicadas no DECISIONS.md.

Construa os endpoints necessários para inserir itens nessa fila e consultá-la 
ordenada por prioridade e ordem de chegada.

---

## Etapa 4 — Linha do tempo

Cada precatório acumula eventos ao longo do tempo: quando o processo foi ajuizado, 
quando o ofício foi expedido, quando o status mudou, quando foi processado pelo 
sistema. O sistema precisa expor esses eventos em ordem cronológica.

Construa um endpoint que retorne essa linha do tempo, considerando tanto os eventos 
extraídos do documento original quanto qualquer atualização posterior recebida 
via API.

---

## Documentos de entrada

A pasta /documentos contém os arquivos de texto simulando saídas de OCR. Você vai 
encontrar variações propositais entre eles — campos em posições diferentes, status 
expressos de formas distintas, informações ausentes ou ambíguas. Parte do desafio 
é lidar com essa variabilidade.

---

## O que entregar

- Repositório no GitHub com código funcionando e instruções de execução no README.md
- DECISIONS.md com: a taxonomia de status e o raciocínio por trás dela, as regras 
  da fila e critérios de prioridade, e qualquer decisão relevante que você tomou — 
  inclusive o que deixou de fora conscientemente

Stack, banco de dados, bibliotecas e estrutura do projeto são decisão sua.
