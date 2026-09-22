import { CalendarDays } from "lucide-react";
import type { Scope } from "../types";

interface RangeControlsProps {
  scope: Scope;
  period: string;
  onScopeChange: (scope: Scope) => void;
  onPeriodChange: (period: string) => void;
}

const options: Array<{ value: Scope; label: string }> = [
  { value: "month", label: "按月" },
  { value: "year", label: "按年" },
  { value: "all", label: "近三年" },
];

export function RangeControls({ scope, period, onScopeChange, onPeriodChange }: RangeControlsProps) {
  return (
    <div className="range-controls">
      <div className="segment" aria-label="统计范围">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={scope === option.value ? "active" : ""}
            aria-pressed={scope === option.value}
            onClick={() => onScopeChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {scope !== "all" && (
        <label className="period-field">
          <CalendarDays size={17} aria-hidden="true" />
          <span className="sr-only">选择{scope === "month" ? "月份" : "年份"}</span>
          <input
            type={scope === "month" ? "month" : "number"}
            min={scope === "year" ? 1970 : undefined}
            max={scope === "year" ? 2100 : undefined}
            value={period}
            onChange={(event) => onPeriodChange(event.target.value)}
          />
        </label>
      )}
    </div>
  );
}
