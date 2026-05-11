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
  const Cell = ({ children }: { children?: ReactNode }) => <>{children}</>;

  const Bar = ({
    chartData = [],
    onClick,
    children,
  }: {
    chartData?: Array<{ runId: string }>;
    onClick?: (data: { payload: { runId: string } }, index: number, event: MouseEvent) => void;
    children?: ReactNode;
  }) => (
    <div>
      {chartData.map((entry, index) => {
        const cell = Children.toArray(children)[index];
        const cellProps = isValidElement(cell) ? (cell.props as Record<string, unknown>) : {};
        return (
          <button
            key={entry.runId}
            type="button"
            aria-label={`timeline bar ${entry.runId}`}
            className={typeof cellProps.className === "string" ? cellProps.className : ""}
            data-fill={typeof cellProps.fill === "string" ? cellProps.fill : ""}
            data-fill-opacity={typeof cellProps.fillOpacity === "number" ? String(cellProps.fillOpacity) : ""}
            data-stroke={typeof cellProps.stroke === "string" ? cellProps.stroke : ""}
            onClick={(event) => onClick?.({ payload: entry }, index, event.nativeEvent)}
          >
            {entry.runId}
          </button>
        );
      })}
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
const scrollIntoViewMock = vi.fn();
const scrollToMock = vi.fn();

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
  scrollIntoViewMock.mockReset();
  scrollToMock.mockReset();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: scrollIntoViewMock,
  });
  Object.defineProperty(HTMLElement.prototype, "scrollTo", {
    configurable: true,
    value: scrollToMock,
  });

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
  it("syncs timeline bar styling when selecting a run from the list", async () => {
    renderHome();
    await waitForHistoryLoad();

    fireEvent.click(screen.getByRole("button", { name: "Run record chores-1" }));

    await waitFor(() => {
      const selectedBar = screen.getByRole("button", { name: "timeline bar chores-1" });
      const unselectedBar = screen.getByRole("button", { name: "timeline bar chores-2" });
      expect(selectedBar.className).toContain("selected");
      expect(selectedBar.getAttribute("data-fill")).toBe("#d97706");
      expect(unselectedBar.className).not.toContain("selected");
      expect(unselectedBar.getAttribute("data-fill-opacity")).toBe("0.5");
    });
  });

  it("keeps single click behavior for selecting a run from the timeline and top-aligns it in the run list", async () => {
    renderHome();
    await waitForHistoryLoad();

    fireEvent.click(screen.getByRole("button", { name: "timeline bar chores-1" }));

    await waitFor(() => {
      expect(screen.getByText("Run Summary")).toBeTruthy();
      expect(screen.getByRole("button", { name: "Run record chores-1" })).toBeTruthy();
      expect(screen.getByText("/tmp/chores-1.log")).toBeTruthy();
    });
    expect(scrollToMock).toHaveBeenCalledWith(
      expect.objectContaining({
        top: expect.any(Number),
        behavior: "smooth",
      }),
    );
    expect(screen.getByText("Showing full loaded window")).toBeTruthy();
  });

  it("keeps the run list independently scrollable", async () => {
    renderHome();
    await waitForHistoryLoad();

    const listContainer = document.querySelector(".run-list-scroll");
    expect(listContainer).toBeTruthy();
    expect(listContainer?.className).toContain("run-list-scroll");
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
