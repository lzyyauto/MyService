import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Pagination as PaginationData } from "../types";

interface PaginationProps {
  value: PaginationData;
  onChange: (page: number) => void;
}

export function Pagination({ value, onChange }: PaginationProps) {
  const totalPages = Math.max(value.total_pages, 1);
  return (
    <nav className="pagination" aria-label="记录翻页">
      <button
        type="button"
        onClick={() => onChange(value.page - 1)}
        disabled={value.page <= 1}
        aria-label="上一页"
      >
        <ChevronLeft size={18} aria-hidden="true" />
      </button>
      <span>
        第 {value.page} / {totalPages} 页 · {value.total_items} 条
      </span>
      <button
        type="button"
        onClick={() => onChange(value.page + 1)}
        disabled={value.page >= totalPages}
        aria-label="下一页"
      >
        <ChevronRight size={18} aria-hidden="true" />
      </button>
    </nav>
  );
}
