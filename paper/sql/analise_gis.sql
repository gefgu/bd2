-- Consulta de leitura: categorias, bairros, densidades e proximidade.
WITH fonte AS MATERIALIZED (
 SELECT "SOLICITACAO" id, "DATA" data, geom,
  UPPER(BTRIM("TIPO")) tipo, UPPER(BTRIM("ASSUNTO")) assunto,
  UPPER(BTRIM("SUBDIVISAO")) subdivisao
 FROM public.bd2_156_enzo_gustavo
), periodo AS MATERIALIZED (
 SELECT * FROM fonte WHERE data >= DATE '2017-01-01' AND data < DATE '2019-01-01'
), selecao AS MATERIALIZED (
 SELECT *, CASE WHEN assunto = 'ILUMINAÇÃO PÚBLICA'
  THEN 'iluminacao' ELSE 'social' END categoria
 FROM periodo WHERE tipo IN ('SOLICITAÇÃO', 'RECLAMAÇÃO') AND (
  assunto LIKE 'ABORDAGEM SOCIAL DE RUA%' OR
  (assunto = 'ILUMINAÇÃO PÚBLICA' AND subdivisao = 'MANUTENÇÃO DE LUMINÁRIAS'))
), bairros AS MATERIALIZED (
 SELECT gid, nome, ST_Transform(geom, 31982) geom
 FROM limites_legais.divisa_de_bairros
), pontos AS MATERIALIZED (
 SELECT id, categoria, ST_Transform(geom, 31982) geom FROM selecao
 WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
  AND ST_IsValid(geom) AND ST_SRID(geom) = 4326
), vinculos AS MATERIALIZED (
 SELECT p.*, v.gid, v.n FROM pontos p LEFT JOIN LATERAL (
  SELECT MIN(b.gid) gid, COUNT(*) n FROM bairros b
  WHERE ST_Covers(b.geom, p.geom)
 ) v ON TRUE
), urbanos AS MATERIALIZED (
 SELECT * FROM vinculos WHERE gid IS NOT NULL
), proximidade AS MATERIALIZED (
 SELECT s.id, s.gid, r.raio, EXISTS (
  SELECT 1 FROM urbanos l WHERE l.categoria = 'iluminacao'
   AND ST_DWithin(s.geom, l.geom, r.raio)
 ) perto FROM urbanos s CROSS JOIN (VALUES (100), (250), (500)) r(raio)
 WHERE s.categoria = 'social'
), contagens AS (
 SELECT gid, COUNT(*) FILTER (WHERE categoria = 'social') n_social,
  COUNT(*) FILTER (WHERE categoria = 'iluminacao') n_luz
 FROM urbanos GROUP BY gid
), alcances AS (
 SELECT gid, COUNT(*) FILTER (WHERE perto AND raio = 100) n_100,
  COUNT(*) FILTER (WHERE perto AND raio = 250) n_250,
  COUNT(*) FILTER (WHERE perto AND raio = 500) n_500
 FROM proximidade GROUP BY gid
), indicadores AS (
 SELECT b.gid, b.nome, b.geom, ST_Area(b.geom) / 1000000.0 area_km2,
  COALESCE(c.n_social, 0) n_social, COALESCE(c.n_luz, 0) n_luz,
  COALESCE(a.n_100, 0) n_100, COALESCE(a.n_250, 0) n_250,
  COALESCE(a.n_500, 0) n_500,
  ROUND(100.0 * COALESCE(a.n_100, 0) / NULLIF(c.n_social, 0), 2) pct_100,
  ROUND(100.0 * COALESCE(a.n_250, 0) / NULLIF(c.n_social, 0), 2) pct_250,
  ROUND(100.0 * COALESCE(a.n_500, 0) / NULLIF(c.n_social, 0), 2) pct_500,
  COALESCE(c.n_social, 0) / NULLIF(ST_Area(b.geom) / 1000000.0, 0) dens_social,
  COALESCE(c.n_luz, 0) / NULLIF(ST_Area(b.geom) / 1000000.0, 0) dens_luz
 FROM bairros b LEFT JOIN contagens c USING (gid) LEFT JOIN alcances a USING (gid)
), cobertura AS (
 SELECT categoria, COUNT(*) total, COUNT(geom) com_geom FROM selecao GROUP BY categoria
), sensibilidade AS (
 SELECT raio, COUNT(*) total, COUNT(*) FILTER (WHERE perto) proximos,
  ROUND(100.0 * COUNT(*) FILTER (WHERE perto) / NULLIF(COUNT(*), 0), 2) pct
 FROM proximidade GROUP BY raio
), anos AS (
 SELECT EXTRACT(YEAR FROM data)::int ano, COUNT(*) total, COUNT(geom) com_geom
 FROM fonte GROUP BY 1
)
-- JSON agrega somente indicadores de bairros; nao exporta pontos ou textos pessoais.
SELECT jsonb_build_object(
 'metadados', jsonb_build_object('consulta_em', CURRENT_TIMESTAMP,
  'banco', CURRENT_DATABASE(), 'postgis', PostGIS_Full_Version(),
  'srid_calculo', 31982, 'inicio', DATE '2017-01-01', 'fim_exclusivo', DATE '2019-01-01'),
 'resumo', jsonb_build_object(
  'total_tabela', (SELECT COUNT(*) FROM fonte),
  'geocodificados_tabela', (SELECT COUNT(geom) FROM fonte),
  'total_periodo', (SELECT COUNT(*) FROM periodo),
  'geocodificados_periodo', (SELECT COUNT(geom) FROM periodo),
  'primeira_data', (SELECT MIN(data) FROM periodo),
  'ultima_data', (SELECT MAX(data) FROM periodo),
  'anos', (SELECT jsonb_agg(to_jsonb(anos) ORDER BY ano) FROM anos),
  'cobertura', (SELECT jsonb_agg(to_jsonb(cobertura) ORDER BY categoria) FROM cobertura),
  'sensibilidade', (SELECT jsonb_agg(to_jsonb(sensibilidade) ORDER BY raio) FROM sensibilidade),
  'bairros_com_social', (SELECT COUNT(*) FROM indicadores WHERE n_social > 0)),
 'validacao', jsonb_build_object(
  'ids_nulos', (SELECT COUNT(*) FROM periodo WHERE id IS NULL),
  'ids_repetidos', (SELECT COUNT(id) - COUNT(DISTINCT id) FROM periodo),
  'pontos_fora', (SELECT COUNT(*) FROM vinculos WHERE gid IS NULL),
  'pontos_ambiguos', (SELECT COUNT(*) FROM vinculos WHERE n > 1),
  'geometrias_descartadas', (SELECT COUNT(geom) FROM selecao) - (SELECT COUNT(*) FROM pontos),
  'bairros', (SELECT COUNT(*) FROM bairros),
  'bairros_ids_distintos', (SELECT COUNT(DISTINCT gid) FROM bairros),
  'bairros_invalidos', (SELECT COUNT(*) FROM bairros WHERE NOT ST_IsValid(geom)),
  'bairros_sem_geom', (SELECT COUNT(*) FROM bairros WHERE geom IS NULL OR ST_IsEmpty(geom))),
 'bairros', jsonb_build_object('type', 'FeatureCollection', 'features', (
  SELECT jsonb_agg(jsonb_build_object('type', 'Feature', 'id', i.gid,
   'properties', to_jsonb(i) - 'geom',
   'geometry', ST_AsGeoJSON(ST_Transform(i.geom, 4326), 8)::jsonb) ORDER BY i.gid)
  FROM indicadores i))
);
