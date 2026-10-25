# Artigo GIS — serviço 156 de Curitiba

Entrega: **`main.pdf`**, com três páginas de artigo e duas de anexo SQL, no modelo
SBC. A seção 3 contém seleção dos dados, algoritmo, quatro funções GIS,
resultados, visualização e limitações. Os números correspondem à consulta de
25/10/2026. A pergunta considera concentração e proximidade de demandas, sem
classificar pessoas ou bairros por risco criminal.

## Arquivos para consultar

- `main.tex`: fonte do artigo.
- `sql/analise_gis.sql`: SELECT completo reproduzido no anexo.
- `sql/executar_tmux.psql`: execução protegida por `BEGIN READ ONLY`, com saída
  JSON local e encerramento por `ROLLBACK`.
- `resultados/analise.json`: saída original agregada, com metadados, contagens,
  validações, sensibilidade e geometria dos 75 bairros.
- `resultados/indicadores.csv`: todos os indicadores, sem arredondamento para
  apresentação; percentuais são arredondados a duas casas no SQL.
- `resultados/bairros.geojson`: polígonos em EPSG:4326 e indicadores agregados.
- `resultados/mapa_gis.pdf` e `.png`: figura do geoprocessamento.
- `resultados/analise_gis.qgz`: projeto QGIS com dados locais e layout dos dois
  mapas. Pode ser aberto sem conexão com o banco; manter o GeoJSON na mesma pasta.
- `scripts/gerar_resultados.py`: valida o JSON e gera tabela, CSV, GeoJSON, mapas e
  projeto QGIS. Não acessa o banco.
- `scripts/compilar.sh`: compila duas vezes e verifica o limite de páginas e erros
  de referências/diagramação; os auxiliares LaTeX ficam em `/tmp`.

## Reproduzir a consulta (a partir da raiz do repositório)

O servidor é consultado **somente para leitura**, sem criar tabelas, views,
índices ou colunas. Os arquivos de saída são gravados pelo cliente local.

Em um terminal, mantenha o túnel aberto:

```sh
ssh -S none -4 -N -o ExitOnForwardFailure=yes -i keyfile \
  -L 127.0.0.1:5436:127.0.0.1:5433 posttunnel@bigsea.c3sl.ufpr.br
```

Em outro terminal, na raiz do repositório:

```sh
mkdir -p paper/resultados
psql -X -h 127.0.0.1 -p 5436 -U postread -d postgiscwb -W \
  -v ON_ERROR_STOP=on -f paper/sql/executar_tmux.psql
```

Também é possível executar `\i paper/sql/executar_tmux.psql` no psql já aberto
no tmux, desde que seu diretório de trabalho seja a raiz do repositório.
Se uma consulta falhar, execute `ROLLBACK;` para encerrar a transação antes de
tentar novamente. A senha não é incluída nos scripts.

## Gerar os mapas e o PDF

Dependências: Python do sistema com PyQGIS (usado: QGIS 3.34.4), `pdflatex`,
template SBC fornecido, pacotes LaTeX usados em `main.tex`, `pdfinfo` e `rg`.

```sh
QT_QPA_PLATFORM=offscreen /usr/bin/python3 paper/scripts/gerar_resultados.py
sh paper/scripts/compilar.sh
```

A validação confere 75 bairros e IDs distintos, geometrias, cobertura,
atribuição sem ambiguidades, totais, denominadores, densidades e monotonicidade
dos alcances de 100, 250 e 500 m. Falhas interrompem a geração. Se a base mudar,
revisar também os números e as interpretações em `main.tex`: a narrativa é um
relato da consulta datada, não um relatório atualizado automaticamente.

## Definições e resultados da consulta

- Período: `DATA >= '2017-01-01' AND DATA < '2019-01-01'`. Existem 79.203
  registros de 2016 na tabela, que foram excluídos. O recorte contém 63.018
  registros, dos quais 15.841 têm geometria; a última data é 22/11/2018.
- Tipos incluídos: `SOLICITAÇÃO` e `RECLAMAÇÃO`.
- Social: assunto iniciado por `ABORDAGEM SOCIAL DE RUA` (adulto, criança e
  categoria genérica); 2.546 registros, 513 georreferenciados.
- Iluminação: assunto `ILUMINAÇÃO PÚBLICA`, subdivisão `MANUTENÇÃO DE LUMINÁRIAS`;
  6.717 registros, 1.359 georreferenciados. Não são todas as demandas de iluminação.
- Bairros: `limites_legais.divisa_de_bairros`, EPSG:29192 (SAD69 / UTM 22S).
  Pontos em EPSG:4326. Ambos são transformados para EPSG:31982 nos cálculos,
  sem alterar a definição dos dados originais.
- Atribuição: `ST_Covers`; se houver múltiplas correspondências, o SQL escolhe
  o menor `gid` e informa a ambiguidade. A validação exige revisar esse caso
  antes de gerar um novo artigo. Na consulta atual não há ambiguidades ou pontos
  selecionados fora dos bairros.
- Densidades: contagem de registros dividida pela área do bairro em km².
- Proximidade: cada pedido social conta uma vez se houver iluminação a até o
  raio, inclusive em outro bairro. Não há filtro de coincidência temporal.
- Percentual: `100 * registros_sociais_proximos / registros_sociais_do_bairro`.
  Bairro sem registros sociais recebe `NULL`, não 0. Os 18 bairros nessa situação
  aparecem em cinza; zero aparece em branco.
- Totais de proximidade: 155/513 a 100 m (30,21%), 379/513 a 250 m (73,88%) e
  497/513 a 500 m (96,88%). Não usar a média simples dos percentuais dos bairros
  para obter o percentual da cidade.
- O indicador mede pedidos registrados e georreferenciados, não pessoas,
  simultaneidade, crimes, risco de violência ou causalidade. O horário do pedido
  não comprova o horário do acontecimento.
