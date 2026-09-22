import { AlarmClock, Clock3, Crown, MapPin, MoonStar, TriangleAlert, Trash2, TrendingUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, deleteSleepSession, getSleepDashboard } from "../api";
import { CalendarHeatmap, type HeatDatum } from "../components/CalendarHeatmap";
import { ErrorState, LoadingState } from "../components/PageState";
import { MetricCard } from "../components/MetricCard";
import { Pagination } from "../components/Pagination";
import { RangeControls } from "../components/RangeControls";
import type { Scope, SleepDashboard, SleepSession } from "../types";
import { currentMonth, currentYear, formatDate, formatHours, formatTime } from "../utils";

interface SleepPageProps {
  token: string;
  onDisconnect: () => void;
}

export function SleepPage({ token, onDisconnect }: SleepPageProps) {
  const [scope, setScope] = useState<Scope>("month");
  const [period, setPeriod] = useState(currentMonth());
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SleepDashboard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [deleting, setDeleting] = useState<SleepSession | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const confirmButtonRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getSleepDashboard(token, scope, period, page));
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
  useEffect(() => {
    if (!deleting) return;
    confirmButtonRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !deleteBusy) setDeleting(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [deleteBusy, deleting]);

  function changeScope(value: Scope) {
    setScope(value);
    setPeriod(value === "year" ? currentYear() : currentMonth());
    setPage(1);
  }

  async function confirmDelete() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await deleteSleepSession(token, deleting.anchor_record_id);
      setDeleting(null);
      setRefreshKey((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除失败");
      setDeleting(null);
    } finally {
      setDeleteBusy(false);
    }
  }

  const heatData = useMemo<HeatDatum[]>(
    () => data?.heatmap.map((item) => {
      const awards = [
        item.is_longest_session && "longest",
        item.is_earliest_sleep && "earliest-sleep",
        item.is_earliest_wake && "earliest-wake",
      ].filter(Boolean) as NonNullable<HeatDatum["awards"]>;
      const awardDetail = awards.length
        ? `；${awards.map((award) => award === "longest" ? "睡得最久" : award === "earliest-sleep" ? "最早入睡" : "最早起床").join("、")}`
        : "";
      return {
        date: item.date,
        value: item.duration_hours,
        detail:
          (item.duration_hours === null
            ? `${item.error_count} 条错误数据，未纳入统计`
            : `${formatHours(item.duration_hours)}，${item.session_count} 个完整会话${item.error_count ? `；另有 ${item.error_count} 条错误数据未纳入统计` : ""}`) + awardDetail,
        issue: item.error_count > 0,
        awards,
      };
    }) ?? [],
    [data],
  );

  function errorLabel(record: SleepSession) {
    if (record.error_code === "missing_sleep") return "错误：缺少入睡";
    if (record.error_code === "missing_wake") return "错误：缺少起床";
    return "错误：时长异常";
  }

  return (
    <>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <main className="app-shell" id="main-content">
      <header className="page-header">
        <div>
          <p className="eyebrow">Z · SLEEP</p>
          <h1>睡眠状态</h1>
          <p>以起床当天作为睡眠日，查看这一天实际完成的睡眠。</p>
        </div>
        <button className="quiet-button" type="button" onClick={onDisconnect}>更换 API Key</button>
      </header>

      <RangeControls
        scope={scope}
        period={period}
        onScopeChange={changeScope}
        onPeriodChange={(value) => { setPeriod(value); setPage(1); }}
      />

      {loading && !data ? <LoadingState /> : error && !data ? (
        <ErrorState message={error} onRetry={() => setRefreshKey((value) => value + 1)} />
      ) : data ? (
        <>
          {error && <div className="inline-error" role="alert">{error}</div>}
          {data.summary.incomplete_sessions > 0 && (
            <div className="data-quality-warning" role="status">
              <TriangleAlert size={19} aria-hidden="true" />
              <span>本期有 {data.summary.incomplete_sessions} 条错误数据（缺少入睡或起床事件），未纳入任何睡眠统计；日历以红色感叹号、明细以红色状态标识。</span>
            </div>
          )}
          <section className="metrics-grid" aria-label="睡眠概览">
            <MetricCard icon={MoonStar} label="平均睡眠" value={formatHours(data.summary.average_duration_hours)} hint={`${data.summary.complete_sessions} 个完整会话`} />
            <MetricCard icon={TrendingUp} label="最长一晚" value={formatHours(data.summary.longest_duration_hours)} hint={data.summary.longest_session ? `${formatDate(data.summary.longest_session.date)} · 已在日历标记` : data.summary.incomplete_sessions ? `${data.summary.incomplete_sessions} 条错误数据未统计` : "记录完整"} />
            <MetricCard icon={Clock3} label="平均入睡" value={data.summary.average_sleep_time ?? "—"} hint="北京时间" />
            <MetricCard icon={AlarmClock} label="平均起床" value={data.summary.average_wake_time ?? "—"} hint="北京时间" />
          </section>

          <section className="insight-grid" aria-label="本期睡眠亮点与醒来城市排行">
            <article className="insight-panel" aria-labelledby="sleep-highlights-title">
              <div className="insight-heading">
                <div>
                  <p className="section-kicker">HIGHLIGHTS</p>
                  <h2 id="sleep-highlights-title">本期睡眠亮点</h2>
                </div>
                <span>日历同步标记</span>
              </div>
              <div className="highlight-list">
                <div className="highlight-item">
                  <Crown size={18} aria-hidden="true" />
                  <span>睡得最久</span>
                  <strong>{data.summary.longest_session ? `${formatDate(data.summary.longest_session.date)} · ${formatHours(data.summary.longest_session.duration_hours)}` : "—"}</strong>
                </div>
                <div className="highlight-item">
                  <MoonStar size={18} aria-hidden="true" />
                  <span>最早入睡</span>
                  <strong>{data.summary.earliest_sleep ? `${formatDate(data.summary.earliest_sleep.date)} · ${data.summary.earliest_sleep.time}` : "—"}</strong>
                </div>
                <div className="highlight-item">
                  <AlarmClock size={18} aria-hidden="true" />
                  <span>最早起床</span>
                  <strong>{data.summary.earliest_wake ? `${formatDate(data.summary.earliest_wake.date)} · ${data.summary.earliest_wake.time}` : "—"}</strong>
                </div>
              </div>
            </article>
            <article className="insight-panel city-rank-panel" aria-labelledby="wake-city-title">
              <div className="insight-heading">
                <div>
                  <p className="section-kicker">WAKE UP</p>
                  <h2 id="wake-city-title">醒来城市排行</h2>
                </div>
                <MapPin size={18} aria-hidden="true" />
              </div>
              {data.summary.wake_city_ranking.length ? (
                <ol className="city-ranking">
                  {data.summary.wake_city_ranking.map((item, index) => (
                    <li key={item.city}><span>{index + 1}</span><strong>{item.city}</strong><small>{item.count} 次</small></li>
                  ))}
                </ol>
              ) : <p className="empty-ranking">完整会话暂无起床城市</p>}
            </article>
          </section>

          <section className="panel heat-panel" aria-labelledby="sleep-calendar-title">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">RHYTHM</p>
                <h2 id="sleep-calendar-title">睡眠节律</h2>
              </div>
              <div className="legend" aria-label="睡眠时长图例">
                <span>短</span>{[1, 2, 3, 4, 5].map((level) => <i className={`heat-${level}`} key={level} />)}<span>长</span>
              </div>
            </div>
            <CalendarHeatmap scope={scope} period={period} data={heatData} variant="sleep" />
            <p className="panel-note">颜色越深表示时长越长；皇冠为睡得最久、月亮为最早入睡、闹钟为最早起床；红色感叹号表示当天存在错误数据，未纳入统计。聚焦日期可查看精确数值。颜色不代表医学评价。</p>
            {scope === "all" && <p className="history-limit-note">统计指标和下方分页明细覆盖全部历史；为保持页面流畅，热力图只显示最近三年。</p>}
          </section>

          <section className="panel details-panel" aria-labelledby="sleep-records-title">
            <div className="panel-heading">
              <div>
                <p className="section-kicker">DETAILS</p>
                <h2 id="sleep-records-title">{scope === "all" ? "完整历史明细" : "睡眠明细"}</h2>
                {scope === "all" && <p className="panel-subtitle">通过分页查看全部历史睡眠日</p>}
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>睡眠日</th><th>入睡</th><th>起床</th><th>时长</th><th>位置</th><th>状态</th><th><span className="sr-only">操作</span></th></tr></thead>
                <tbody>
                  {data.records.map((record) => (
                    <tr className={record.is_complete ? undefined : "invalid-row"} key={record.anchor_record_id}>
                      <td data-label="睡眠日"><strong>{formatDate(record.sleep_date)}</strong></td>
                      <td data-label="入睡">{formatTime(record.sleep_at)}</td>
                      <td data-label="起床">{formatTime(record.wake_at)}</td>
                      <td data-label="时长">{formatHours(record.duration_hours)}</td>
                      <td data-label="位置">{record.city ?? record.wifi_name ?? "—"}</td>
                      <td data-label="状态"><span className={`status-pill ${record.is_complete ? "complete" : "invalid"}`}>{record.is_complete ? "完整" : errorLabel(record)}</span></td>
                      <td className="action-cell">
                        <button className="icon-button danger-button" type="button" aria-label={`删除 ${record.sleep_date} 的睡眠会话`} onClick={() => setDeleting(record)}><Trash2 size={17} aria-hidden="true" /></button>
                      </td>
                    </tr>
                  ))}
                  {!data.records.length && <tr><td className="empty-table" colSpan={7}>当前范围还没有睡眠记录</td></tr>}
                </tbody>
              </table>
            </div>
            <Pagination value={data.pagination} onChange={setPage} />
          </section>
        </>
      ) : null}

      {deleting && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => !deleteBusy && setDeleting(null)}>
          <section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="dialog-icon" aria-hidden="true"><Trash2 size={22} /></div>
            <h2 id="delete-title">删除这一天的本地记录？</h2>
            <p>睡眠日 {formatDate(deleting.sleep_date)} 的入睡和起床事件会一并删除。已经同步到 Notion 的副本不会被删除。</p>
            <div className="dialog-actions">
              <button type="button" className="quiet-button" disabled={deleteBusy} onClick={() => setDeleting(null)}>取消</button>
              <button ref={confirmButtonRef} type="button" className="destructive-button" disabled={deleteBusy} onClick={confirmDelete}>{deleteBusy ? "正在删除…" : "确认删除"}</button>
            </div>
          </section>
        </div>
      )}
    </main>
    </>
  );
}
