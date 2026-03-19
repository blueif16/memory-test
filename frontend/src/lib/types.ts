export interface DomainItem {
  id: string;
  title: string;
  domain: string;
  item_type: string;
  summary?: string;
  raw_score?: number;
  above_floor?: boolean;
}

export interface Edge {
  source_id: string;
  target_id: string;
  relation: string;
  strength: number;
}

export interface SnapshotData {
  items: DomainItem[];
  edges: Edge[];
  events?: unknown[];
}

export interface Snapshot {
  snapshot_date: string;
  snapshot_data: SnapshotData;
}
