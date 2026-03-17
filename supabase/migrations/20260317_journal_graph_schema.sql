-- Journal Graph RAG Schema Extension
-- Adds domain items (graph nodes), edges with decay, temporal anchors,
-- interaction log, snapshots, and diary entries.

-- Domain items (graph nodes for journal entities)
CREATE TABLE domain_items (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL,
  domain            TEXT NOT NULL CHECK (domain IN ('career','wealth','love','social','study','general')),
  title             TEXT NOT NULL,
  item_type         TEXT NOT NULL DEFAULT 'event'
                    CHECK (item_type IN ('event','person','goal','habit','place','class','project')),
  lifecycle_status  TEXT NOT NULL DEFAULT 'active'
                    CHECK (lifecycle_status IN ('active','completed','abandoned','paused')),
  resolved_at       TIMESTAMPTZ,
  resolution_note   TEXT,
  summary           TEXT DEFAULT '',
  context_doc       TEXT DEFAULT '',
  context_doc_stale BOOLEAN DEFAULT TRUE,
  summary_embedding VECTOR(768),
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

-- Edges with decay
CREATE TABLE domain_item_edges (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id           UUID NOT NULL REFERENCES domain_items(id) ON DELETE CASCADE,
  target_id           UUID NOT NULL REFERENCES domain_items(id) ON DELETE CASCADE,
  relation            TEXT NOT NULL,
  strength            REAL DEFAULT 1.0,
  last_reinforced_at  TIMESTAMPTZ DEFAULT NOW(),
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(source_id, target_id, relation)
);

-- Temporal anchors
CREATE TABLE upcoming_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_item_id  UUID NOT NULL REFERENCES domain_items(id) ON DELETE CASCADE,
  label           TEXT NOT NULL,
  target_date     DATE NOT NULL,
  detail          TEXT DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'upcoming'
                  CHECK (status IN ('upcoming','completed','cancelled')),
  source_diary_id UUID,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Append-only journal log
CREATE TABLE domain_item_interactions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_item_id  UUID NOT NULL REFERENCES domain_items(id) ON DELETE CASCADE,
  diary_id        UUID NOT NULL,
  noted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  snippet         TEXT NOT NULL
);

-- Graph snapshots (for visualization + eval)
CREATE TABLE graph_snapshots (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL,
  snapshot_date   DATE NOT NULL,
  snapshot_data   JSONB NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, snapshot_date)
);

-- Journal entries (raw)
CREATE TABLE diary_entries (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  content     TEXT NOT NULL,
  entry_date  DATE NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX idx_di_user ON domain_items(user_id);
CREATE INDEX idx_di_user_status ON domain_items(user_id, lifecycle_status);
CREATE INDEX idx_di_embedding ON domain_items USING hnsw (summary_embedding vector_cosine_ops);
CREATE INDEX idx_di_fts ON domain_items USING GIN (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(context_doc,'')));

CREATE INDEX idx_die_source ON domain_item_edges(source_id);
CREATE INDEX idx_die_target ON domain_item_edges(target_id);

CREATE INDEX idx_ue_item ON upcoming_events(domain_item_id);
CREATE INDEX idx_ue_date ON upcoming_events(target_date);
CREATE INDEX idx_ue_status ON upcoming_events(status);

CREATE INDEX idx_dii_item ON domain_item_interactions(domain_item_id);
CREATE INDEX idx_dii_diary ON domain_item_interactions(diary_id);

CREATE INDEX idx_gs_user_date ON graph_snapshots(user_id, snapshot_date);
CREATE INDEX idx_de_user_date ON diary_entries(user_id, entry_date);

-- ============================================================
-- Triggers — context_doc staleness
-- ============================================================

-- Mark single item stale
CREATE OR REPLACE FUNCTION mark_context_stale()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE domain_items SET context_doc_stale = TRUE, updated_at = NOW()
  WHERE id = NEW.domain_item_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER interaction_stale
  AFTER INSERT ON domain_item_interactions
  FOR EACH ROW EXECUTE FUNCTION mark_context_stale();

CREATE TRIGGER event_stale
  AFTER INSERT ON upcoming_events
  FOR EACH ROW EXECUTE FUNCTION mark_context_stale();

-- Mark BOTH sides of edge stale
CREATE OR REPLACE FUNCTION mark_edge_context_stale()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE domain_items SET context_doc_stale = TRUE, updated_at = NOW()
  WHERE id IN (NEW.source_id, NEW.target_id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER edge_stale
  AFTER INSERT OR UPDATE ON domain_item_edges
  FOR EACH ROW EXECUTE FUNCTION mark_edge_context_stale();

-- ============================================================
-- Entity Resolution SQL Function (RRF: BM25 + Vector)
-- ============================================================

CREATE OR REPLACE FUNCTION resolve_domain_item(
  query_text TEXT,
  query_embedding vector(768),
  p_user_id UUID,
  match_count INT DEFAULT 5
)
RETURNS TABLE (id UUID, title TEXT, domain TEXT, item_type TEXT, score FLOAT)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
  WITH
  fts AS (
    SELECT di.id,
      ts_rank_cd(
        to_tsvector('english', coalesce(di.title,'') || ' ' || coalesce(di.summary,'') || ' ' || coalesce(di.context_doc,'')),
        plainto_tsquery('english', query_text)
      ) AS rank
    FROM domain_items di
    WHERE di.user_id = p_user_id AND di.lifecycle_status = 'active'
      AND to_tsvector('english', coalesce(di.title,'') || ' ' || coalesce(di.summary,'') || ' ' || coalesce(di.context_doc,''))
          @@ plainto_tsquery('english', query_text)
    ORDER BY rank DESC LIMIT match_count * 3
  ),
  fts_ranked AS (
    SELECT fts.id, ROW_NUMBER() OVER (ORDER BY rank DESC) AS rank_pos FROM fts
  ),
  vec AS (
    SELECT di.id, di.summary_embedding <=> query_embedding AS dist
    FROM domain_items di
    WHERE di.user_id = p_user_id AND di.lifecycle_status = 'active'
      AND di.summary_embedding IS NOT NULL
    ORDER BY dist LIMIT match_count * 3
  ),
  vec_ranked AS (
    SELECT vec.id, ROW_NUMBER() OVER (ORDER BY dist) AS rank_pos FROM vec
  ),
  rrf AS (
    SELECT
      COALESCE(f.id, v.id) AS id,
      COALESCE(1.0 / (60 + f.rank_pos), 0.0) + COALESCE(1.0 / (60 + v.rank_pos), 0.0) AS rrf_score
    FROM fts_ranked f FULL OUTER JOIN vec_ranked v ON f.id = v.id
  )
  SELECT di.id, di.title, di.domain, di.item_type, rrf.rrf_score::FLOAT AS score
  FROM rrf JOIN domain_items di ON rrf.id = di.id
  ORDER BY rrf.rrf_score DESC LIMIT match_count;
END;
$$;

-- ============================================================
-- Scoring SQL Function
-- ============================================================

CREATE OR REPLACE FUNCTION score_domain_items(
  p_user_id UUID,
  p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (
  item_id UUID, title TEXT, domain TEXT, item_type TEXT,
  raw_score FLOAT, above_floor BOOLEAN
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
  WITH item_base AS (
    SELECT di.id, di.title, di.domain, di.item_type
    FROM domain_items di
    WHERE di.user_id = p_user_id AND di.lifecycle_status = 'active'
  ),
  recency AS (
    SELECT dii.domain_item_id,
      MAX(dii.noted_at) AS last_seen,
      EXP(-0.03 * EXTRACT(EPOCH FROM p_now - MAX(dii.noted_at)) / 86400) AS recency_signal
    FROM domain_item_interactions dii
    JOIN item_base ib ON dii.domain_item_id = ib.id
    GROUP BY dii.domain_item_id
  ),
  neighbor AS (
    SELECT ib.id AS item_id,
      COALESCE(SUM(
        e.strength * EXP(-0.03 * EXTRACT(EPOCH FROM p_now - e.last_reinforced_at) / 86400)
      ), 0) AS neighbor_signal
    FROM item_base ib
    LEFT JOIN domain_item_edges e ON (e.source_id = ib.id OR e.target_id = ib.id)
    GROUP BY ib.id
  ),
  event_prox AS (
    SELECT ue.domain_item_id,
      MAX(
        CASE WHEN ue.target_date >= p_now::date
        THEN EXP(-0.1 * (ue.target_date - p_now::date))
        ELSE 0 END
      ) AS event_signal
    FROM upcoming_events ue
    JOIN item_base ib ON ue.domain_item_id = ib.id
    WHERE ue.status = 'upcoming'
    GROUP BY ue.domain_item_id
  ),
  freq AS (
    SELECT dii.domain_item_id,
      SUM(EXP(-0.03 * EXTRACT(EPOCH FROM p_now - dii.noted_at) / 86400)) AS freq_signal
    FROM domain_item_interactions dii
    JOIN item_base ib ON dii.domain_item_id = ib.id
    GROUP BY dii.domain_item_id
  ),
  scored AS (
    SELECT ib.id, ib.title, ib.domain, ib.item_type,
      (
        COALESCE(r.recency_signal, 0) * 2.0 +
        COALESCE(n.neighbor_signal, 0) * 1.0 +
        COALESCE(ep.event_signal, 0) * 3.0 +
        COALESCE(f.freq_signal, 0) * 0.5
      ) AS raw_score
    FROM item_base ib
    LEFT JOIN recency r ON r.domain_item_id = ib.id
    LEFT JOIN neighbor n ON n.item_id = ib.id
    LEFT JOIN event_prox ep ON ep.domain_item_id = ib.id
    LEFT JOIN freq f ON f.domain_item_id = ib.id
  ),
  floor_calc AS (
    SELECT *,
      PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY raw_score) OVER () AS graph_median
    FROM scored
  )
  SELECT fc.id, fc.title, fc.domain, fc.item_type,
    fc.raw_score::FLOAT,
    (fc.raw_score > fc.graph_median * 0.1)::BOOLEAN AS above_floor
  FROM floor_calc fc
  ORDER BY fc.raw_score DESC;
END;
$$;

-- ============================================================
-- Extraction SQL Function
-- ============================================================

CREATE OR REPLACE FUNCTION extract_briefing_data(
  p_user_id UUID,
  p_now TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (
  item_id UUID, title TEXT, domain TEXT, item_type TEXT,
  summary TEXT, raw_score FLOAT,
  upcoming_events_json JSONB,
  recent_snippets_json JSONB,
  connections_json JSONB
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  RETURN QUERY
  WITH scored AS (
    SELECT s.item_id, s.title, s.domain, s.item_type, s.raw_score
    FROM score_domain_items(p_user_id, p_now) s
    WHERE s.above_floor = TRUE
  ),
  events AS (
    SELECT ue.domain_item_id,
      jsonb_agg(jsonb_build_object(
        'label', ue.label,
        'target_date', ue.target_date,
        'detail', ue.detail
      ) ORDER BY ue.target_date) AS events_json
    FROM upcoming_events ue
    WHERE ue.domain_item_id IN (SELECT scored.item_id FROM scored)
      AND ue.status = 'upcoming'
    GROUP BY ue.domain_item_id
  ),
  snippets AS (
    SELECT dii.domain_item_id,
      jsonb_agg(jsonb_build_object(
        'snippet', dii.snippet,
        'noted_at', dii.noted_at
      ) ORDER BY dii.noted_at DESC) AS snippets_json
    FROM (
      SELECT *, ROW_NUMBER() OVER (PARTITION BY domain_item_id ORDER BY noted_at DESC) AS rn
      FROM domain_item_interactions
      WHERE domain_item_id IN (SELECT scored.item_id FROM scored)
    ) dii
    WHERE dii.rn <= 3
    GROUP BY dii.domain_item_id
  ),
  connections AS (
    SELECT ib.item_id,
      jsonb_agg(jsonb_build_object(
        'title', other.title,
        'relation', e.relation,
        'effective_strength',
          e.strength * EXP(-0.03 * EXTRACT(EPOCH FROM p_now - e.last_reinforced_at) / 86400)
      ) ORDER BY e.strength * EXP(-0.03 * EXTRACT(EPOCH FROM p_now - e.last_reinforced_at) / 86400) DESC) AS conn_json
    FROM scored ib
    JOIN domain_item_edges e ON (e.source_id = ib.item_id OR e.target_id = ib.item_id)
    JOIN domain_items other ON other.id = CASE
      WHEN e.source_id = ib.item_id THEN e.target_id
      ELSE e.source_id END
    WHERE other.lifecycle_status = 'active'
    GROUP BY ib.item_id
  )
  SELECT s.item_id, s.title, s.domain, s.item_type,
    di.summary, s.raw_score::FLOAT,
    COALESCE(ev.events_json, '[]'::jsonb),
    COALESCE(sn.snippets_json, '[]'::jsonb),
    COALESCE(cn.conn_json, '[]'::jsonb)
  FROM scored s
  JOIN domain_items di ON di.id = s.item_id
  LEFT JOIN events ev ON ev.domain_item_id = s.item_id
  LEFT JOIN snippets sn ON sn.domain_item_id = s.item_id
  LEFT JOIN connections cn ON cn.item_id = s.item_id
  ORDER BY s.domain, s.raw_score DESC;
END;
$$;
