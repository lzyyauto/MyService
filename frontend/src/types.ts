export type Scope = "month" | "year" | "all";

export interface Pagination {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface SleepSession {
  anchor_record_id: string;
  sleep_record_id: string | null;
  wake_record_id: string | null;
  sleep_date: string;
  sleep_at: string | null;
  wake_at: string | null;
  duration_hours: number | null;
  is_complete: boolean;
  error_code: "missing_sleep" | "missing_wake" | "invalid_duration" | null;
  city: string | null;
  wifi_name: string | null;
}

export interface SleepDashboard {
  scope: Scope;
  period: string | null;
  summary: {
    total_sessions: number;
    complete_sessions: number;
    incomplete_sessions: number;
    average_duration_hours: number | null;
    longest_duration_hours: number | null;
    shortest_duration_hours: number | null;
    average_sleep_time: string | null;
    average_wake_time: string | null;
    longest_session: { date: string; duration_hours: number } | null;
    earliest_sleep: { date: string; time: string } | null;
    earliest_wake: { date: string; time: string } | null;
    wake_city_ranking: Array<{ city: string; count: number }>;
  };
  heatmap: Array<{
    date: string;
    duration_hours: number | null;
    session_count: number;
    complete_count: number;
    error_count: number;
    is_longest_session: boolean;
    is_earliest_sleep: boolean;
    is_earliest_wake: boolean;
  }>;
  records: SleepSession[];
  pagination: Pagination;
}

export interface SportRecord {
  id: string;
  sport_type: string;
  duration_minutes: number;
  occurred_at: string;
  occurred_on: string;
  city: string | null;
  is_marker: boolean;
  is_thirty_minute_marker: boolean;
}

export interface SportDashboard {
  scope: Scope;
  period: string | null;
  summary: {
    total_records: number;
    total_duration_minutes: number;
    average_duration_minutes: number | null;
    active_days: number;
    marker_count: number;
    thirty_minute_marker_count: number;
    by_type: Array<{
      sport_type: string;
      count: number;
      total_duration_minutes: number;
    }>;
  };
  heatmap: Array<{
    date: string;
    total_duration_minutes: number;
    record_count: number;
    marker_count: number;
    thirty_minute_marker_count: number;
  }>;
  records: SportRecord[];
  pagination: Pagination;
}
