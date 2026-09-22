import { Activity, CalendarCheck2, Flag, Timer } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getSportDashboard } from "../api";
import { CalendarHeatmap, type HeatDatum } from "../components/CalendarHeatmap";
import { MetricCard } from "../components/MetricCard";
import { ErrorState, LoadingState } from "../components/PageState";
import { Pagination } from "../components/Pagination";
import { RangeControls } from "../components/RangeControls";
import type { Scope, SportDashboard } from "../types";
import { currentMonth, currentYear, formatDate, formatMinutes, formatTime } from "../utils";

export function SportPage({ token, onDisconnect }: { token: string; onDisconnect: () => void }) {
  const [scope, setScope] = useState<Scope>("month");
  const [period, setPeriod] = useState(currentMonth());
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SportDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getSportDashboard(token, scope, period, page));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setError("当前 API Key 无效或已失效。请点击右上角“更换 API Key”后重新验证。");
        return;
      }
      setError(cause instanceof Error ? cause.message : "未知错误");
    } finally {
      setLoading(false);
    }
  }, [onDisconnect, page, period, refreshKey, scope, token]);

  useEffect(() => void load(), [load]);

  const heatData = useMemo<HeatDatum[]>(
    () => data?.heatmap.map((item) => ({
      date: item.date,
      value: item.total_duration_minutes,
      detail: `${formatMinutes(item.total_duration_minutes)}，${item.record_count} 条记录${item.marker_count ? `，${item.marker_count} 个 2 分钟标记` : ""}${item.thirty_minute_marker_count ? `，${item.thirty_minute_marker_count} 个 30 分钟标记` : ""}`,
      marker: item.marker_count > 0,
      yellowMarker: item.thirty_minute_marker_count > 0,
    })) ?? [],
    [data],
  );

  function changeScope(value: Scope) {
    setScope(value);
    setPeriod(value === "year" ? currentYear() : currentMonth());
    setPage(1);
  }

  return (
    <>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <main className="app-shell sport-theme" id="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">Z · SPORT</p>
          <h1>运动记录</h1>
          <p>独立查看运动频率、时长和个人标记。</p>
        </div>
        <button className="quiet-button" type="button" onClick={onDisconnect}>更换 API Key</button>
      </header>
      <RangeControls scope={scope} period={period} onScopeChange={changeScope} onPeriodChange={(value) => { setPeriod(value); setPage(1); }} />

      {loading && !data ? <LoadingState /> : error && !data ? (
        <ErrorState message={error} onRetry={() => setRefreshKey((value) => value + 1)} />
      ) : data ? (
        <>
          <section className="metrics-grid" aria-label="运动概览">
            <MetricCard icon={Activity} label="运动次数" value={`${data.summary.total_records} 次`} hint={`${data.summary.active_days} 个活跃日`} />
            <MetricCard icon={Timer} label="累计时长" value={formatMinutes(data.summary.total_duration_minutes)} hint={`平均 ${formatMinutes(data.summary.average_duration_minutes)}`} />
            <MetricCard icon={CalendarCheck2} label="活跃天数" value={`${data.summary.active_days} 天`} hint="当前统计范围" />
            <MetricCard
              icon={Flag}
              label="特殊标记"
              value={`${data.summary.marker_count + data.summary.thirty_minute_marker_count} 次`}
              hint={`2 分钟红标 ${data.summary.marker_count} · 30 分钟黄标 ${data.summary.thirty_minute_marker_count}`}
              danger={data.summary.marker_count > 0}
            />
          </section>

          <section className="panel heat-panel" aria-labelledby="sport-calendar-title">
            <div className="panel-heading">
              <div><p className="section-kicker">ACTIVITY</p><h2 id="sport-calendar-title">运动分布</h2></div>
              <div className="legend"><span>少</span>{[1, 2, 3, 4, 5].map((level) => <i className={`heat-${level}`} key={level} />)}<span>多</span><i className="marker-legend marker-legend-red" /><span>2 分钟</span><i className="marker-legend marker-legend-yellow" /><span>30 分钟</span></div>
            </div>
            <CalendarHeatmap scope={scope} period={period} data={heatData} variant="sport" />
            {scope === "all" && <p className="history-limit-note">统计指标和下方分页明细覆盖全部历史；为保持页面流畅，热力图只显示最近三年。</p>}
          </section>

          <section className="panel details-panel" aria-labelledby="sport-records-title">
            <div className="panel-heading"><div><p className="section-kicker">DETAILS</p><h2 id="sport-records-title">{scope === "all" ? "完整历史明细" : "运动明细"}</h2>{scope === "all" && <p className="panel-subtitle">通过分页查看全部历史运动记录</p>}</div></div>
            <div className="table-wrap"><table>
              <thead><tr><th>日期</th><th>时间</th><th>类型</th><th>时长</th><th>城市</th><th>标记</th></tr></thead>
              <tbody>
                {data.records.map((record) => (
                  <tr key={record.id} className={record.is_marker ? "marker-row" : record.is_thirty_minute_marker ? "yellow-marker-row" : ""}>
                    <td data-label="日期"><strong>{formatDate(record.occurred_on)}</strong></td>
                    <td data-label="时间">{formatTime(record.occurred_at)}</td>
                    <td data-label="类型">{record.sport_type}</td>
                    <td data-label="时长">{formatMinutes(record.duration_minutes)}</td>
                    <td data-label="城市">{record.city ?? "—"}</td>
                    <td data-label="标记">
                      {record.is_marker ? (
                        <span className="marker-badge"><Flag size={14} aria-hidden="true" />2 分钟标记</span>
                      ) : record.is_thirty_minute_marker ? (
                        <span className="marker-badge yellow-marker-badge"><Flag size={14} aria-hidden="true" />30 分钟标记</span>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
                {!data.records.length && <tr><td className="empty-table" colSpan={6}>当前范围还没有运动记录</td></tr>}
              </tbody>
            </table></div>
            <Pagination value={data.pagination} onChange={setPage} />
          </section>
        </>
      ) : null}
    </main>
    </>
  );
}
