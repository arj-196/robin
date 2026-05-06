import http from "node:http";
import { pathToFileURL } from "node:url";

export function getPort(): number {
  const raw = process.env.DASHBOARD_PORT ?? "3000";
  const value = Number.parseInt(raw, 10);
  return Number.isNaN(value) ? 3000 : value;
}

export function buildDashboardPayload(mode: "serve" | "status") {
  return {
    ability: "dashboard",
    mode,
    port: getPort(),
    status: "ready",
  };
}

function printHelp(): void {
  console.log(`dashboard <command>\n\nCommands:\n  serve     Start the dashboard HTTP server\n  status    Print dashboard status\n  help      Show this message`);
}

function startServer(): void {
  const port = getPort();
  const server = http.createServer((_request, response) => {
    response.setHeader("content-type", "application/json");
    response.end(JSON.stringify(buildDashboardPayload("serve"), null, 2));
  });

  server.listen(port, () => {
    console.log(`Robin dashboard listening on http://localhost:${port}`);
  });
}

function printStatus(): void {
  console.log(JSON.stringify(buildDashboardPayload("status"), null, 2));
}

export function runCli(argv: string[] = process.argv.slice(2)): void {
  const mode = argv[0] ?? "help";

  if (mode === "serve") {
    startServer();
  } else if (mode === "status") {
    printStatus();
  } else if (mode === "help" || mode === "--help" || mode === "-h") {
    printHelp();
  } else {
    console.error(`Unsupported mode: ${mode}`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runCli();
}
