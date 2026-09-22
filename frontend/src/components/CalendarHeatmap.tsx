import { AlarmClock, Crown, MoonStar } from "lucide-react";
import type { Scope } from "../types";

type SleepAward = "longest" | "earliest-sleep" | "earliest-wake";

export interface HeatDatum {
  date: string;
  value: number | null;
  detail: string;
  marker?: boolean;
  yellowMarker?: boolean;
  issue?: boolean;
  awards?: SleepAward[];
}

interface CalendarHeatmapProps {
  scope: Scope;
  period: string;
  data: HeatDatum[];
  variant: "sleep" | "sport";
}

const weekdays = ["一", "二", "三", "四", "五", "六", "日"];

function sleepLevel(value: number | null): number {
  if (value === null) return 0;
  if (value < 6) return 1;
  if (value < 7) return 2;
  if (value < 8) return 3;
  if (value < 9) return 4;
  return 5;
}

function sportLevel(value: number | null): number {
  if (!value) return 0;
  if (value < 15) return 1;
  if (value < 30) return 2;
  if (value < 60) return 3;
  if (value < 90) return 4;
  return 5;
}

function cellClass(item: HeatDatum | undefined, variant: "sleep" | "sport") {
  const level = variant === "sleep" ? sleepLevel(item?.value ?? null) : sportLevel(item?.value ?? null);
  return `heat-cell heat-${level}${item?.marker ? " has-red-marker" : ""}${item?.yellowMarker ? " has-yellow-marker" : ""}${item?.issue ? " has-issue" : ""}`;
}

function awardLabel(award: SleepAward): string {
  if (award === "longest") return "睡得最久";
  if (award === "earliest-sleep") return "最早入睡";
  return "最早起床";
}

function AwardIcons({ awards }: { awards: SleepAward[] | undefined }) {
  if (!awards?.length) return null;
  return (
    <span className="heat-awards" aria-hidden="true">
      {awards.map((award) => {
        const Icon = award === "longest" ? Crown : award === "earliest-sleep" ? MoonStar : AlarmClock;
        return <Icon key={award} size={13} strokeWidth={2.4} />;
      })}
    </span>
  );
}

export function CalendarHeatmap({ scope, period, data, variant }: CalendarHeatmapProps) {
  const byDate = new Map(data.map((item) => [item.date, item]));
  const label = variant === "sleep" ? "睡眠时长" : "运动时长";

  if (scope !== "month") {
    return (
      <div className="heat-strip" aria-label={`${label}热力图`}>
        {data.length ? (
          data.map((item) => (
            <span
              key={item.date}
              className={cellClass(item, variant)}
              tabIndex={0}
              aria-label={`${item.date}，${item.detail}`}
              title={`${item.date} · ${item.detail}`}
            >
              <AwardIcons awards={item.awards} />
              {item.marker && <i className="heat-marker heat-marker-red" aria-hidden="true" />}
              {item.yellowMarker && <i className="heat-marker heat-marker-yellow" aria-hidden="true">30</i>}
              {item.issue && <b aria-hidden="true">!</b>}
            </span>
          ))
        ) : (
          <p className="empty-inline">当前范围还没有数据</p>
        )}
      </div>
    );
  }

  const [year, month] = period.split("-").map(Number);
  const days = new Date(year, month, 0).getDate();
  const firstWeekday = (new Date(year, month - 1, 1).getDay() + 6) % 7;

  return (
    <div className="calendar" aria-label={`${period} ${label}日历`}>
      {weekdays.map((day) => (
        <div className="weekday" key={day} aria-hidden="true">
          {day}
        </div>
      ))}
      {Array.from({ length: firstWeekday }).map((_, index) => (
        <span className="calendar-spacer" key={`spacer-${index}`} />
      ))}
      {Array.from({ length: days }).map((_, index) => {
        const day = index + 1;
        const date = `${period}-${String(day).padStart(2, "0")}`;
        const item = byDate.get(date);
        return (
          <div
            className={cellClass(item, variant)}
            key={date}
            tabIndex={0}
            aria-label={`${date}，${item?.detail ?? "无记录"}`}
            title={`${date} · ${item?.detail ?? "无记录"}`}
          >
            <span>{day}</span>
            <AwardIcons awards={item?.awards} />
            {item?.marker && <i className="heat-marker heat-marker-red" aria-hidden="true" />}
            {item?.yellowMarker && <i className="heat-marker heat-marker-yellow" aria-hidden="true">30</i>}
            {item?.issue && <b aria-hidden="true">!</b>}
          </div>
        );
      })}
    </div>
  );
}
