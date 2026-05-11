"use client";

import React from "react";
import { useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import {
  buildTimelineData,
  DEFAULT_HISTORY_LOOKBACK_DAYS,
  filterRecordsByDateRange,
  getServiceColor,
  MAX_HISTORY_LOOKBACK_DAYS,
  MIN_HISTORY_LOOKBACK_DAYS,
  normalizeLookbackInput,
  type DateRangeFilter,
  type RunRecord,
  type TimelineDatum,
} from "./history-timeline";

type LogTailResponse = {
  tail?: string;
  isTruncated?: boolean;
  error?: string;
};

type DetailItem = {
  label: string;
  value: string;
};

const ALL_FILTER_VALUE = "__all__";

type HistoryResponse = {
  records: RunRecord[];
};

type CalendarDay = {
  iso: string;
  dayOfMonth: number;
  isCurrentMonth: boolean;
};

function parseIsoDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    return null;
  }

  const [, yearText, monthText, dayText] = match;
  const year = Number(yearText);
  const monthIndex = Number(monthText) - 1;
  const day = Number(dayText);
  const date = new Date(year, monthIndex, day);

  if (
    Number.isNaN(date.getTime()) ||
    date.getFullYear() !== year ||
    date.getMonth() !== monthIndex ||
    date.getDate() !== day
  ) {
    return null;
  }

  return date;
}

function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function shiftMonth(monthIso: string, delta: number): string {
  const baseDate = parseIsoDate(monthIso);
  if (!baseDate) {
    return monthIso;
  }

  return toIsoDate(new Date(baseDate.getFullYear(), baseDate.getMonth() + delta, 1));
}

function buildCalendarDays(monthIso: string): CalendarDay[] {
  const monthDate = parseIsoDate(monthIso);
  if (!monthDate) {
    return [];
  }

  const firstDayOfMonth = startOfMonth(monthDate);
  const firstVisibleDate = new Date(firstDayOfMonth);
  firstVisibleDate.setDate(firstVisibleDate.getDate() - firstDayOfMonth.getDay());

  return Array.from({ length: 42 }, (_, index) => {
    const current = new Date(firstVisibleDate);
    current.setDate(firstVisibleDate.getDate() + index);
    return {
      iso: toIsoDate(current),
      dayOfMonth: current.getDate(),
      isCurrentMonth: current.getMonth() === firstDayOfMonth.getMonth(),
    };
  });
}

function isDateWithinRange(dateIso: string, range: DateRangeFilter): boolean {
  if (!range.from || !range.until) {
    return false;
  }

  return dateIso >= range.from && dateIso <= range.until;
}

function formatCalendarMonth(value: string): string {
  const date = parseIsoDate(value);
  if (!date) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
  }).format(date);
}

function formatCalendarDayLabel(value: string): string {
  const date = parseIsoDate(value);
  if (!date) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "Not finished";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDuration(durationMs: number | null): string {
  if (durationMs === null) {
    return "Running";
  }

  if (durationMs < 1_000) {
    return `${durationMs} ms`;
  }

  const totalSeconds = durationMs / 1_000;
  if (totalSeconds < 60) {
    return `${totalSeconds.toFixed(totalSeconds >= 10 ? 0 : 1)} s`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return `${minutes}m ${seconds}s`;
}

function formatCompactDuration(durationMs: number): string {
  if (durationMs < 1_000) {
    return `${durationMs}ms`;
  }

  const totalSeconds = durationMs / 1_000;
  if (totalSeconds < 60) {
    return `${totalSeconds.toFixed(totalSeconds >= 10 ? 0 : 1)}s`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.round(totalSeconds % 60);
  return `${minutes}m ${seconds}s`;
}

function formatLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatValue(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  return String(value);
}

function formatDateFilterValue(value: string): string {
  if (!value) {
    return "";
  }

  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function formatActiveDateRange(range: DateRangeFilter): string {
  const { from, until } = range;
  if (from && until) {
    return `${formatDateFilterValue(from)} - ${formatDateFilterValue(until)}`;
  }
  if (from) {
    return `Start: ${formatDateFilterValue(from)}`;
  }
  return "";
}

function buildSummaryItems(record: RunRecord): string[] {
  const items = [
    `Run ID ${record.run_id}`,
    `Duration ${formatDuration(record.duration_ms)}`,
  ];

  if (record.failure_code) {
    items.push(`Failure ${record.failure_code}`);
  }

  if (record.exit_code !== null) {
    items.push(`Exit ${record.exit_code}`);
  }

  for (const [key, value] of Object.entries(record.metadata)) {
    items.push(`${formatLabel(key)} ${formatValue(value)}`);
  }

  return items;
}

function buildDetailItems(record: RunRecord): DetailItem[] {
  return [
    { label: "Service", value: record.service },
    { label: "Run ID", value: record.run_id },
    { label: "Result", value: record.result || "Pending" },
    { label: "Started", value: formatDateTime(record.started_at) },
    { label: "Finished", value: formatDateTime(record.finished_at) },
    { label: "Duration", value: formatDuration(record.duration_ms) },
    { label: "Exit code", value: formatValue(record.exit_code) },
    { label: "Failure code", value: formatValue(record.failure_code) },
    { label: "Command", value: record.command },
    { label: "Log path", value: record.log_path },
  ];
}

function TimelineTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: TimelineDatum }> }) {
  const datum = payload?.[0]?.payload;
  if (!active || !datum) {
    return null;
  }

  return (
    <div className="timeline-tooltip">
      <strong>{datum.service}</strong>
      <span>{formatDateTime(datum.startedAt)}</span>
      <span>{formatCompactDuration(datum.durationMs)}</span>
      <span>{datum.runId}</span>
      <span>{datum.result || "pending"}</span>
    </div>
  );
}

export default function Home(): ReactElement {
  const todayMonth = toIsoDate(startOfMonth(new Date()));
  const [records, setRecords] = useState<RunRecord[]>([]);
  const [lookbackDays, setLookbackDays] = useState(DEFAULT_HISTORY_LOOKBACK_DAYS);
  const [lookbackInput, setLookbackInput] = useState(String(DEFAULT_HISTORY_LOOKBACK_DAYS));
  const [dateRange, setDateRange] = useState<DateRangeFilter>({ from: "", until: "" });
  const [isDatePickerOpen, setIsDatePickerOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(todayMonth);
  const [selectedService, setSelectedService] = useState(ALL_FILTER_VALUE);
  const [selectedResult, setSelectedResult] = useState(ALL_FILTER_VALUE);
  const [runQuery, setRunQuery] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");

  const [logText, setLogText] = useState("");
  const [isTruncated, setIsTruncated] = useState(false);
  const [isFullLogLoaded, setIsFullLogLoaded] = useState(false);
  const [isLoadingFullLog, setIsLoadingFullLog] = useState(false);
  const [logLoadError, setLogLoadError] = useState<string | null>(null);
  const [error, setError] = useState("");
  const runListScrollRef = useRef<HTMLDivElement>(null);
  const runCardRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  useEffect(() => {
    setError("");
    void fetch(`/api/history?lookbackDays=${lookbackDays}`)
      .then((response) => response.json())
      .then((payload: HistoryResponse) => {
        setRecords(payload.records || []);
      })
      .catch(() => setError("Failed to load run history."));
  }, [lookbackDays]);

  const services = useMemo(
    () => [...new Set(records.map((record) => record.service).filter(Boolean))].sort(),
    [records],
  );
  const results = useMemo(
    () => [...new Set(records.map((record) => record.result || "").filter(Boolean))].sort(),
    [records],
  );

  const baseFilteredRecords = useMemo(() => {
    const query = runQuery.trim().toLowerCase();
    const matchesNonDateFilters = records.filter((record) => {
      if (selectedService !== ALL_FILTER_VALUE && record.service !== selectedService) {
        return false;
      }
      if (selectedResult !== ALL_FILTER_VALUE && (record.result || "") !== selectedResult) {
        return false;
      }
      if (query && !record.run_id.toLowerCase().includes(query)) {
        return false;
      }
      return true;
    });
    return filterRecordsByDateRange(matchesNonDateFilters, dateRange);
  }, [dateRange, records, runQuery, selectedResult, selectedService]);

  const timelineData = useMemo(() => buildTimelineData(baseFilteredRecords), [baseFilteredRecords]);
  const timelineLabelsByRunId = useMemo(() => {
    return new Map(timelineData.map((entry) => [entry.runId, entry.startedAtLabel]));
  }, [timelineData]);
  const filtered = useMemo(() => {
    return [...baseFilteredRecords].sort((left, right) => {
      const leftTs = Date.parse(left.started_at);
      const rightTs = Date.parse(right.started_at);
      const leftSafeTs = Number.isFinite(leftTs) ? leftTs : Number.NEGATIVE_INFINITY;
      const rightSafeTs = Number.isFinite(rightTs) ? rightTs : Number.NEGATIVE_INFINITY;
      if (leftSafeTs !== rightSafeTs) {
        return rightSafeTs - leftSafeTs;
      }

      return right.run_id.localeCompare(left.run_id);
    });
  }, [baseFilteredRecords]);
  const calendarDays = useMemo(() => buildCalendarDays(visibleMonth), [visibleMonth]);
  const defaultVisibleMonth = useMemo(() => {
    const latestEntry = timelineData[timelineData.length - 1];
    if (!latestEntry) {
      return todayMonth;
    }

    const latestDate = parseIsoDate(latestEntry.startedAt.slice(0, 10));
    return latestDate ? toIsoDate(startOfMonth(latestDate)) : todayMonth;
  }, [timelineData, todayMonth]);

  useEffect(() => {
    if (dateRange.from) {
      setVisibleMonth(toIsoDate(startOfMonth(parseIsoDate(dateRange.from) ?? new Date())));
    }
  }, [dateRange.from]);

  useEffect(() => {
    if (!dateRange.from && !isDatePickerOpen) {
      setVisibleMonth(defaultVisibleMonth);
    }
  }, [dateRange.from, defaultVisibleMonth, isDatePickerOpen]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    if (!filtered.some((record) => record.run_id === selectedRunId)) {
      setSelectedRunId("");
    }
  }, [filtered, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }

    const selectedCard = runCardRefs.current.get(selectedRunId);
    const runListContainer = runListScrollRef.current;
    if (!selectedCard || !runListContainer) {
      return;
    }

    const containerRect = runListContainer.getBoundingClientRect();
    const selectedRect = selectedCard.getBoundingClientRect();
    const selectedTopWithinContainer = selectedRect.top - containerRect.top;
    const targetScrollTop = runListContainer.scrollTop + selectedTopWithinContainer;
    runListContainer.scrollTo({ top: Math.max(0, targetScrollTop), behavior: "smooth" });
  }, [selectedRunId]);

  const selected = filtered.find((record) => record.run_id === selectedRunId) || null;
  const selectedMetadata = selected ? Object.entries(selected.metadata) : [];
  const selectedSummaryItems = selected ? buildDetailItems(selected) : [];

  useEffect(() => {
    if (!selected) {
      setLogText("");
      setIsTruncated(false);
      setIsFullLogLoaded(false);
      setIsLoadingFullLog(false);
      setLogLoadError(null);
      return;
    }

    setLogText("");
    setIsTruncated(false);
    setIsFullLogLoaded(false);
    setIsLoadingFullLog(false);
    setLogLoadError(null);

    void fetch(`/api/log-tail?logPath=${encodeURIComponent(selected.log_path)}`)
      .then((response) => response.json())
      .then((payload: LogTailResponse) => {
        if (payload.error) {
          setLogLoadError(payload.error);
          setLogText("");
          setIsTruncated(false);
          return;
        }
        setLogText(payload.tail || "");
        setIsTruncated(Boolean(payload.isTruncated));
      })
      .catch(() => {
        setLogLoadError("Failed to load log tail.");
        setLogText("");
        setIsTruncated(false);
      });
  }, [selected]);

  const commitLookbackInput = (): void => {
    const normalized = normalizeLookbackInput(lookbackInput);
    setLookbackInput(String(normalized));
    setLookbackDays((current) => (current === normalized ? current : normalized));
  };

  const handleDateRangeSelection = (selectedDateIso: string): void => {
    setDateRange((current) => {
      if (!current.from || current.until) {
        return { from: selectedDateIso, until: "" };
      }

      if (selectedDateIso < current.from) {
        return { from: selectedDateIso, until: current.from };
      }

      return { from: current.from, until: selectedDateIso };
    });
  };

  const clearDateRange = (): void => {
    setDateRange({ from: "", until: "" });
    setVisibleMonth(todayMonth);
  };

  const hasCompletedDateRange = Boolean(dateRange.from && dateRange.until);
  const dateRangeButtonLabel = dateRange.from ? formatActiveDateRange(dateRange) : "Select date range";

  const handleLoadFullLog = (): void => {
    if (!selected || !isTruncated || isLoadingFullLog || isFullLogLoaded) {
      return;
    }

    setIsLoadingFullLog(true);
    setLogLoadError(null);

    void fetch(`/api/log-full?logPath=${encodeURIComponent(selected.log_path)}`)
      .then(async (response) => {
        if (!response.ok) {
          const payload = (await response.json()) as { error?: string };
          throw new Error(payload.error || "Failed to load full log.");
        }
        return response.text();
      })
      .then((text) => {
        setLogText(text);
        setIsFullLogLoaded(true);
        setIsTruncated(false);
      })
      .catch((err: unknown) => {
        setLogLoadError(err instanceof Error ? err.message : "Failed to load full log.");
      })
      .finally(() => {
        setIsLoadingFullLog(false);
      });
  };

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div className="header-title-block">
          <p className="eyebrow">Robin App</p>
          <h1>History Dashboard</h1>
          <p className="header-subtitle">
            {filtered.length} visible of {records.length} total run records
          </p>
        </div>

        <section className="filter-bar" aria-label="Run history filters">
          <label className="filter-field filter-lookback">
            <span>History lookback (days)</span>
            <input
              type="number"
              min={MIN_HISTORY_LOOKBACK_DAYS}
              max={MAX_HISTORY_LOOKBACK_DAYS}
              inputMode="numeric"
              value={lookbackInput}
              onChange={(event) => setLookbackInput(event.target.value)}
              onBlur={commitLookbackInput}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  commitLookbackInput();
                }
              }}
            />
          </label>

          <label className="filter-field">
            <span>Service</span>
            <select value={selectedService} onChange={(event) => setSelectedService(event.target.value)}>
              <option value={ALL_FILTER_VALUE}>All services</option>
              {services.map((service) => (
                <option key={service} value={service}>
                  {service}
                </option>
              ))}
            </select>
          </label>

          <label className="filter-field">
            <span>Result</span>
            <select value={selectedResult} onChange={(event) => setSelectedResult(event.target.value)}>
              <option value={ALL_FILTER_VALUE}>All results</option>
              {results.map((result) => (
                <option key={result} value={result}>
                  {result}
                </option>
              ))}
            </select>
          </label>

          <label className="filter-field filter-search">
            <span>Run ID</span>
            <input
              value={runQuery}
              onChange={(event) => setRunQuery(event.target.value)}
              placeholder="Search run ID"
            />
          </label>

          <div className="filter-field filter-date-range">
            <span>Date range</span>
            <div className="date-range-picker">
              <button
                type="button"
                className={`date-range-trigger${isDatePickerOpen ? " open" : ""}`}
                aria-expanded={isDatePickerOpen}
                aria-haspopup="dialog"
                aria-label="Date range"
                onClick={() =>
                  setIsDatePickerOpen((current) => {
                    if (!current && !dateRange.from) {
                      setVisibleMonth(defaultVisibleMonth);
                    }
                    return !current;
                  })
                }
              >
                <span>{dateRangeButtonLabel}</span>
              </button>
              {isDatePickerOpen ? (
                <div className="date-range-popover" role="dialog" aria-label="Date range picker">
                  <div className="date-range-popover-header">
                    <button
                      type="button"
                      className="date-nav-button"
                      aria-label="Previous month"
                      onClick={() => setVisibleMonth((current) => shiftMonth(current, -1))}
                    >
                      Prev
                    </button>
                    <strong>{formatCalendarMonth(visibleMonth)}</strong>
                    <button
                      type="button"
                      className="date-nav-button"
                      aria-label="Next month"
                      onClick={() => setVisibleMonth((current) => shiftMonth(current, 1))}
                    >
                      Next
                    </button>
                  </div>
                  <p className="date-range-guidance">
                    {dateRange.from && !dateRange.until ? "Select the end date." : "Select the start date."}
                  </p>
                  <div className="date-grid-weekdays" aria-hidden="true">
                    {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((weekday) => (
                      <span key={weekday}>{weekday}</span>
                    ))}
                  </div>
                  <div className="date-grid">
                    {calendarDays.map((day) => {
                      const isStart = day.iso === dateRange.from;
                      const isEnd = day.iso === dateRange.until;
                      const isInRange = isDateWithinRange(day.iso, dateRange);
                      const className = [
                        "date-cell",
                        day.isCurrentMonth ? "" : "outside-month",
                        isInRange ? "in-range" : "",
                        isStart ? "range-start" : "",
                        isEnd ? "range-end" : "",
                      ]
                        .filter(Boolean)
                        .join(" ");

                      return (
                        <button
                          key={day.iso}
                          type="button"
                          className={className}
                          aria-label={`Choose ${formatCalendarDayLabel(day.iso)}`}
                          onClick={() => handleDateRangeSelection(day.iso)}
                        >
                          {day.dayOfMonth}
                        </button>
                      );
                    })}
                  </div>
                  <div className="date-range-popover-actions">
                    <button type="button" className="date-picker-action" onClick={clearDateRange}>
                      Clear
                    </button>
                    <button
                      type="button"
                      className="date-picker-action primary"
                      onClick={() => setIsDatePickerOpen(false)}
                    >
                      Apply
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </section>
      </header>

      {error ? <p className="banner-error">{error}</p> : null}

      <section className="timeline-panel" aria-label="Run timeline">
        <div className="timeline-status-row">
          <div className="timeline-legend">
            {services.map((service) => (
              <span key={service} className="timeline-legend-item">
                <span className="timeline-legend-swatch" style={{ backgroundColor: getServiceColor(service) }} />
                {service}
              </span>
            ))}
          </div>
          <span className={`timeline-range-chip${dateRange.from || dateRange.until ? " active" : ""}`}>
            {dateRange.from
              ? hasCompletedDateRange
                ? `Filtered dates: ${formatActiveDateRange(dateRange)}`
                : `Date range start selected: ${formatDateFilterValue(dateRange.from)}`
              : "Showing full loaded window"}
          </span>
        </div>

        <div className="timeline-chart-shell">
          {timelineData.length ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={timelineData} margin={{ top: 8, right: 12, left: 0, bottom: 12 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(188, 199, 214, 0.5)" />
                <XAxis
                  dataKey="runId"
                  minTickGap={24}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value: string) => timelineLabelsByRunId.get(value) ?? value}
                />
                <YAxis
                  width={48}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value: number) => formatCompactDuration(value)}
                />
                <Tooltip content={<TimelineTooltip />} cursor={{ fill: "rgba(23, 92, 211, 0.08)" }} />
                <Bar
                  dataKey="durationMs"
                  radius={[6, 6, 0, 0]}
                  onClick={(data) => {
                    const datum = data.payload as TimelineDatum | undefined;
                    if (datum) {
                      setSelectedRunId(datum.runId);
                    }
                  }}
                >
                  {timelineData.map((entry) => {
                    const isSelected = entry.runId === selectedRunId;
                    return (
                      <Cell
                        key={entry.runId}
                        className={`timeline-bar-cell${isSelected ? " selected" : ""}`}
                        fill={entry.color}
                        fillOpacity={isSelected ? 1 : 0.5}
                        stroke={isSelected ? entry.color : "none"}
                        strokeWidth={isSelected ? 2 : 0}
                      />
                    );
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="list-empty-state timeline-empty-state">
              <h3>No runs in the loaded history window</h3>
              <p>Increase the history lookback days if you want to load older run records.</p>
            </div>
          )}
        </div>
      </section>

      <section className="workspace">
        <aside className="run-list-pane">
          <div className="pane-header">
            <h2>Run Records</h2>
            <p>{filtered.length} shown</p>
          </div>

          <div ref={runListScrollRef} className="run-list-scroll">
            {filtered.length ? (
              filtered.map((record) => {
                const isSelected = record.run_id === selectedRunId;
                return (
                  <button
                    key={record.run_id}
                    ref={(node) => {
                      if (node) {
                        runCardRefs.current.set(record.run_id, node);
                        return;
                      }

                      runCardRefs.current.delete(record.run_id);
                    }}
                    type="button"
                    className={`run-card${isSelected ? " selected" : ""}`}
                    aria-label={`Run record ${record.run_id}`}
                    onClick={() => setSelectedRunId(record.run_id)}
                  >
                    <div className="run-card-topline">
                      <span className="service-pill">{record.service}</span>
                      <span className={`result-pill result-${record.result || "pending"}`}>
                        {record.result || "pending"}
                      </span>
                    </div>

                    <div className="run-card-primary">
                      <span>{formatDateTime(record.started_at)}</span>
                      <span>{formatDuration(record.duration_ms)}</span>
                    </div>

                    <div className="run-card-summary">
                      {buildSummaryItems(record).map((item) => (
                        <span key={item} className="summary-chip">
                          {item}
                        </span>
                      ))}
                    </div>

                    {record.message ? <p className="run-card-message">{record.message}</p> : null}
                  </button>
                );
              })
            ) : (
              <div className="list-empty-state">
                <h3>No matching runs</h3>
                <p>Adjust the filters to see more run records.</p>
              </div>
            )}
          </div>
        </aside>

        <section className="detail-pane">
          {!selected ? (
            <div className="detail-placeholder">
              <div className="placeholder-orb" />
              <h2>Select a run record</h2>
              <p>Choose a run from the left pane to inspect its summary, metadata, and log preview.</p>
            </div>
          ) : (
            <div className="detail-scroll">
              <section className="detail-section">
                <div className="section-heading">
                  <h2>Run Summary</h2>
                  <span className={`result-pill result-${selected.result || "pending"}`}>
                    {selected.result || "pending"}
                  </span>
                </div>
                <div className="detail-grid">
                  {selectedSummaryItems.map((item) => (
                    <div key={item.label} className="detail-card">
                      <p>{item.label}</p>
                      <strong>{item.value}</strong>
                    </div>
                  ))}
                </div>
              </section>

              <section className="detail-section">
                <div className="section-heading">
                  <h2>Service-Specific Details</h2>
                </div>
                {selectedMetadata.length ? (
                  <div className="detail-grid">
                    {selectedMetadata.map(([key, value]) => (
                      <div key={key} className="detail-card">
                        <p>{formatLabel(key)}</p>
                        <strong>{formatValue(value)}</strong>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-detail-card">
                    <p>No service metadata was recorded for this run.</p>
                  </div>
                )}
              </section>

              <section className="detail-section">
                <div className="section-heading">
                  <h2>Derived Log Insights</h2>
                </div>
                <div className="empty-detail-card">
                  <p>Derived insights are not enabled in this pass. This view is currently ledger-backed.</p>
                </div>
              </section>

              <section className="detail-section">
                <div className="log-header-row">
                  <h2>{isFullLogLoaded ? "Run Log (Full)" : "Run Log Preview"}</h2>
                  {isTruncated ? (
                    <button
                      type="button"
                      className="load-full-log-button"
                      onClick={handleLoadFullLog}
                      disabled={isLoadingFullLog}
                    >
                      {isLoadingFullLog ? "Loading full log..." : "Load full log"}
                    </button>
                  ) : null}
                </div>

                {logLoadError ? <p className="inline-error">{logLoadError}</p> : null}
                <pre className="log-output">{logText || "No log preview available."}</pre>
              </section>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
