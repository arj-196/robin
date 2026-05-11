/* @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React, { Children, cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "./page";
import type { RunRecord } from "./history-timeline";

vi.mock("recharts", () => {
  const ResponsiveContainer = ({ children }: { children: ReactNode }) => <div>{children}</div>;
  const CartesianGrid = () => null;
  const XAxis = () => null;
  const YAxis = () => null;
  const Tooltip = () => null;
  const Cell = () => null;

  const Bar = ({
    chartData = [],
    onClick,
  }: {
    chartData?: Array<{ runId: string }>;
    onClick?: (data: { payload: { runId: string } }, index: number, event: MouseEvent) => void;
  }) => (
    <div>
      {chartData.map((entry, index) => (
        <button
          key={entry.runId}
          type="button"
          aria-label={`timeline bar ${entry.runId}`}
          onClick={(event) => onClick?.({ payload: entry }, index, event.nativeEvent)}
        >
          {entry.runId}
        </button>
      ))}
    </div>
  );

  const BarChart = ({ children, data = [] }: { children: ReactNode; data?: Array<{ runId: string }> }) => {
    const enhancedChildren = Children.map(children, (child) => {
      if (!isValidElement(child)) {
        return child;
      }

      const element = child as ReactElement<{ chartData?: Array<{ runId: string }> }>;
      if (element.type === Bar) {
        return cloneElement(element, { chartData: data });
      }

      return child;
    });

    return <div data-testid="timeline-chart">{enhancedChildren}</div>;
  };

  return {
    ResponsiveContainer,
    BarChart,
    Bar,
    CartesianGrid,
    Cell,
    Tooltip,
    XAxis,
    YAxis,
  };
});

const RECORDS: RunRecord[] = [
  {
    event: "run_finished",
    run_id: "chores-1",
    service: "chores",
    command: "bin/chores",
    started_at: "2026-05-08T08:00:00.000Z",
    finished_at: "2026-05-08T08:00:05.000Z",
    duration_ms: 5_000,
    result: "ok",
    exit_code: 0,
    failure_code: null,
    message: null,
    log_path: "/tmp/chores-1.log",
    metadata: {},
  },
  {
    event: "run_finished",
    run_id: "chores-2",
    service: "chores",
    command: "bin/chores",
    started_at: "2026-05-09T09:00:00.000Z",
    finished_at: "2026-05-09T09:00:08.000Z",
    duration_ms: 8_000,
    result: "ok",
    exit_code: 0,
    failure_code: null,
    message: null,
    log_path: "/tmp/chores-2.log",
    metadata: {},
  },
  {
    event: "run_finished",
    run_id: "auto-1",
    service: "auto-coder",
    command: "bin/auto-coder",
    started_at: "2026-05-10T10:00:00.000Z",
    finished_at: "2026-05-10T10:00:15.000Z",
    duration_ms: 15_000,
    result: "ok",
    exit_code: 0,
    failure_code: null,
    message: null,
    log_path: "/tmp/auto-1.log",
    metadata: {},
  },
  {
    event: "run_finished",
    run_id: "auto-2",
    service: "auto-coder",
    command: "bin/auto-coder",
    started_at: "2026-05-11T11:00:00.000Z",
    finished_at: "2026-05-11T11:00:12.000Z",
    duration_ms: 12_000,
    result: "ok",
    exit_code: 0,
    failure_code: null,
    message: null,
    log_path: "/tmp/auto-2.log",
    metadata: {},
  },
];

const fetchMock = vi.fn<(input: string) => Promise<{ ok: boolean; json: () => Promise<unknown>; text: () => Promise<string> }>>();

function renderHome(): void {
  render(<Home />);
}

async function waitForHistoryLoad(): Promise<void> {
  await waitFor(() => {
    expect(screen.getByText("4 visible of 4 total run records")).toBeTruthy();
  });
}

function openDateRangePicker(): void {
  fireEvent.click(screen.getByRole("button", { name: "Date range" }));
}

function chooseCalendarDay(label: string): void {
  fireEvent.click(screen.getByRole("button", { name: `Choose ${label}` }));
}

beforeEach(() => {
  fetchMock.mockImplementation(async (input: string) => {
    if (input.startsWith("/api/history")) {
      return {
        ok: true,
        json: async () => ({ records: RECORDS }),
        text: async () => "",
      };
    }

    if (input.startsWith("/api/log-tail")) {
      return {
        ok: true,
        json: async () => ({ tail: "tail output", isTruncated: false }),
        text: async () => "",
      };
    }

    if (input.startsWith("/api/log-full")) {
      return {
        ok: true,
        json: async () => ({}),
        text: async () => "full output",
      };
    }

    throw new Error(`Unhandled fetch: ${input}`);
  });

  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("history dashboard timeline interactions", () => {
  it("keeps single click behavior for selecting a run", async () => {
    renderHome();
    await waitForHistoryLoad();

    fireEvent.click(screen.getByRole("button", { name: "timeline bar chores-1" }));

    await waitFor(() => {
      expect(screen.getByText("Run Summary")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Run record chores-1" })).toBeTruthy();
      expect(screen.getByText("/tmp/chores-1.log")).toBeTruthy();
    });
    expect(screen.getByText("Showing full loaded window")).toBeTruthy();
  });

  it("keeps the full dataset visible until the end date is selected", async () => {
    renderHome();
    await waitForHistoryLoad();

    openDateRangePicker();
    chooseCalendarDay("Sunday, May 10, 2026");

    await waitFor(() => {
      expect(screen.getByText("Date range start selected: May 10, 2026")).toBeTruthy();
      expect(screen.getByText("4 shown")).toBeTruthy();
    });
    expect(screen.getByText("Select the end date.")).toBeTruthy();
  });

  it("applies the range after the second calendar selection", async () => {
    renderHome();
    await waitForHistoryLoad();

    openDateRangePicker();
    chooseCalendarDay("Saturday, May 9, 2026");
    chooseCalendarDay("Sunday, May 10, 2026");

    await waitFor(() => {
      expect(screen.getByText("Filtered dates: May 9, 2026 - May 10, 2026")).toBeTruthy();
      expect(screen.getByText("2 shown")).toBeTruthy();
    });
    expect(screen.getByRole("button", { name: "Run record chores-2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run record auto-1" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Run record chores-1" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Run record auto-2" })).toBeNull();
  });

  it("normalizes reverse selection into an inclusive range", async () => {
    renderHome();
    await waitForHistoryLoad();

    openDateRangePicker();
    chooseCalendarDay("Sunday, May 10, 2026");
    chooseCalendarDay("Saturday, May 9, 2026");

    await waitFor(() => {
      expect(screen.getByText("Filtered dates: May 9, 2026 - May 10, 2026")).toBeTruthy();
      expect(screen.getByText("2 shown")).toBeTruthy();
    });
    expect(screen.getByRole("button", { name: "Run record chores-2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run record auto-1" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Run record chores-1" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Run record auto-2" })).toBeNull();
  });

  it("updates the visible records when other filters combine with the date range", async () => {
    renderHome();
    await waitForHistoryLoad();

    openDateRangePicker();
    chooseCalendarDay("Sunday, May 10, 2026");
    chooseCalendarDay("Monday, May 11, 2026");

    await waitFor(() => {
      expect(screen.getByText("2 shown")).toBeTruthy();
    });

    fireEvent.change(screen.getByLabelText("Service"), { target: { value: "chores" } });

    await waitFor(() => {
      expect(screen.getByText("No matching runs")).toBeTruthy();
    });
  });

  it("shows all records again when the date filter is cleared", async () => {
    renderHome();
    await waitForHistoryLoad();

    openDateRangePicker();
    chooseCalendarDay("Sunday, May 10, 2026");
    chooseCalendarDay("Monday, May 11, 2026");

    await waitFor(() => {
      expect(screen.getByText("2 shown")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await waitFor(() => {
      expect(screen.getByText("Showing full loaded window")).toBeTruthy();
      expect(screen.getByText("4 shown")).toBeTruthy();
    });
  });
});
