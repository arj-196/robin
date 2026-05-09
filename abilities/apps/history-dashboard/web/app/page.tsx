"use client";

import { useEffect, useMemo, useState, type ReactElement } from "react";

type RunRecord = {
  event: string;
  run_id: string;
  service: string;
  command: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  result: string | null;
  exit_code: number | null;
  failure_code: string | null;
  message: string | null;
  log_path: string;
  metadata: Record<string, string | number | boolean | null>;
};

type LogTailResponse = {
  tail?: string;
  isTruncated?: boolean;
  error?: string;
};

export default function Home(): ReactElement {
  const [records, setRecords] = useState<RunRecord[]>([]);
  const [selectedServices, setSelectedServices] = useState<string[]>([]);
  const [selectedResults, setSelectedResults] = useState<string[]>([]);
  const [runQuery, setRunQuery] = useState("");
  const [selectedRunId, setSelectedRunId] = useState("");

  const [logText, setLogText] = useState("");
  const [isTruncated, setIsTruncated] = useState(false);
  const [isFullLogLoaded, setIsFullLogLoaded] = useState(false);
  const [isLoadingFullLog, setIsLoadingFullLog] = useState(false);
  const [logLoadError, setLogLoadError] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void fetch("/api/history")
      .then((response) => response.json())
      .then((payload: { records: RunRecord[] }) => {
        setRecords(payload.records || []);
      })
      .catch(() => setError("Failed to load run history."));
  }, []);

  const services = useMemo(
    () => [...new Set(records.map((r) => r.service).filter(Boolean))].sort(),
    [records],
  );
  const results = useMemo(
    () => [...new Set(records.map((r) => r.result || "").filter(Boolean))].sort(),
    [records],
  );

  useEffect(() => {
    setSelectedServices(services);
  }, [services]);

  useEffect(() => {
    setSelectedResults(results);
  }, [results]);

  const filtered = useMemo(() => {
    const query = runQuery.trim().toLowerCase();
    return records.filter((record) => {
      if (selectedServices.length && !selectedServices.includes(record.service)) {
        return false;
      }
      if (selectedResults.length && !selectedResults.includes(record.result || "")) {
        return false;
      }
      if (query && !record.run_id.toLowerCase().includes(query)) {
        return false;
      }
      return true;
    });
  }, [records, runQuery, selectedResults, selectedServices]);

  useEffect(() => {
    if (!filtered.length) {
      setSelectedRunId("");
      return;
    }
    if (!filtered.some((record) => record.run_id === selectedRunId)) {
      setSelectedRunId(filtered[0].run_id);
    }
  }, [filtered, selectedRunId]);

  const selected = filtered.find((record) => record.run_id === selectedRunId) || null;

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
    <main className="container">
      <h1>History Dashboard</h1>
      {error ? <p>{error}</p> : null}
      <p>Showing {filtered.length} of {records.length} runs</p>

      <section className="filters">
        <label>
          Service
          <select
            multiple
            value={selectedServices}
            onChange={(event) => {
              const options = Array.from(event.target.selectedOptions).map((option) => option.value);
              setSelectedServices(options);
            }}
          >
            {services.map((service) => <option key={service}>{service}</option>)}
          </select>
        </label>
        <label>
          Result
          <select
            multiple
            value={selectedResults}
            onChange={(event) => {
              const options = Array.from(event.target.selectedOptions).map((option) => option.value);
              setSelectedResults(options);
            }}
          >
            {results.map((result) => <option key={result}>{result}</option>)}
          </select>
        </label>
        <label>
          Run ID contains
          <input value={runQuery} onChange={(event) => setRunQuery(event.target.value)} />
        </label>
      </section>

      <section>
        <table>
          <thead>
            <tr>
              <th>service</th>
              <th>run_id</th>
              <th>result</th>
              <th>started_at</th>
              <th>finished_at</th>
              <th>duration_ms</th>
              <th>failure_code</th>
              <th>task_id</th>
              <th>project</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((record) => (
              <tr
                key={record.run_id}
                className={record.run_id === selectedRunId ? "selected" : ""}
                onClick={() => setSelectedRunId(record.run_id)}
              >
                <td>{record.service}</td>
                <td>{record.run_id}</td>
                <td>{record.result || ""}</td>
                <td>{record.started_at}</td>
                <td>{record.finished_at || ""}</td>
                <td>{record.duration_ms ?? ""}</td>
                <td>{record.failure_code || ""}</td>
                <td>{String(record.metadata.task_id ?? "")}</td>
                <td>{String(record.metadata.project ?? "")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {!selected ? <p>No runs available for current filters.</p> : null}
      {selected ? (
        <>
          <h2>Run record</h2>
          <pre>{JSON.stringify(selected, null, 2)}</pre>

          <h2>
            {selected.service === "auto-coder"
              ? "Auto-coder details"
              : selected.service === "chores"
                ? "Chores details"
                : "Generic details"}
          </h2>
          <pre>
            {JSON.stringify(
              selected.service === "auto-coder"
                ? {
                    task_id: selected.metadata.task_id,
                    project: selected.metadata.project,
                    failure_code: selected.failure_code,
                    message: selected.message,
                  }
                : {
                    metadata: selected.metadata,
                    failure_code: selected.failure_code,
                    message: selected.message,
                  },
              null,
              2,
            )}
          </pre>

          <div className="log-header-row">
            <h2>{isFullLogLoaded ? "Run log (full)" : "Run log (tail)"}</h2>
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

          {logLoadError ? <p>{logLoadError}</p> : null}
          <pre>{logText}</pre>
        </>
      ) : null}
    </main>
  );
}
