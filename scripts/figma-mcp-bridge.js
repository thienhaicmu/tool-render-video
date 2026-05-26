#!/usr/bin/env node
/**
 * stdio ↔ HTTP bridge for figma-developer-mcp.
 * figma-developer-mcp v0.11+ only runs as an HTTP server (port 3333).
 * Claude Code expects stdio protocol, so this bridge:
 *   1. Starts figma-developer-mcp as a child process (HTTP mode, port 3333)
 *   2. Reads JSON-RPC messages from stdin
 *   3. POSTs each to http://127.0.0.1:3333/mcp
 *   4. Writes responses back to stdout
 */

const { spawn } = require("child_process");
const http = require("http");

const PORT = 3333;
const HOST = "127.0.0.1";
const API_KEY = process.env.FIGMA_API_KEY || "";

if (!API_KEY) {
  process.stderr.write("FIGMA_API_KEY env var is required\n");
  process.exit(1);
}

// On Windows, use cmd /c to launch npx (a .cmd file)
const isWin = process.platform === "win32";
const serverArgs = isWin
  ? ["/c", "npx", "-y", "figma-developer-mcp", "--figma-api-key", API_KEY, "--port", String(PORT), "--no-telemetry"]
  : ["-y", "figma-developer-mcp", "--figma-api-key", API_KEY, "--port", String(PORT), "--no-telemetry"];
const serverCmd = isWin ? "cmd" : "npx";

const serverProc = spawn(serverCmd, serverArgs, { stdio: ["ignore", "ignore", "ignore"] });

serverProc.on("error", (e) => {
  process.stderr.write("Failed to start figma-developer-mcp: " + e.message + "\n");
  process.exit(1);
});

function checkServer(attempts, cb) {
  if (attempts <= 0) return cb(new Error("figma-developer-mcp did not start after 10s"));
  const req = http.request(
    { host: HOST, port: PORT, path: "/mcp", method: "POST",
      headers: { "content-type": "application/json", accept: "application/json, text/event-stream" } },
    (res) => { res.resume(); cb(null); }
  );
  req.on("error", () => setTimeout(() => checkServer(attempts - 1, cb), 500));
  req.end("{}");
}

checkServer(20, (err) => {
  if (err) { process.stderr.write(err.message + "\n"); process.exit(1); }
  startBridge();
});

function startBridge() {
  let buf = "";
  let pending = 0;
  let stdinDone = false;

  function maybeExit() {
    if (stdinDone && pending === 0) { serverProc.kill(); process.exit(0); }
  }

  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => {
    buf += chunk;
    let idx;
    while ((idx = buf.indexOf("\n")) !== -1) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (line) { pending++; forward(line, () => { pending--; maybeExit(); }); }
    }
  });
  process.stdin.on("end", () => { stdinDone = true; maybeExit(); });
}

function forward(jsonLine, done) {
  const body = Buffer.from(jsonLine, "utf8");
  const opts = {
    host: HOST,
    port: PORT,
    path: "/mcp",
    method: "POST",
    headers: {
      "content-type": "application/json",
      "content-length": body.length,
      accept: "application/json, text/event-stream",
    },
  };
  const req = http.request(opts, (res) => {
    const chunks = [];
    res.on("data", (d) => chunks.push(d));
    res.on("end", () => {
      const text = Buffer.concat(chunks).toString("utf8");
      for (const line of text.split("\n")) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6).trim();
          if (data && data !== "[DONE]") process.stdout.write(data + "\n");
        } else if (line.trim().startsWith("{")) {
          process.stdout.write(line.trim() + "\n");
        }
      }
      done();
    });
  });
  req.on("error", (e) => {
    process.stdout.write(
      JSON.stringify({ jsonrpc: "2.0", error: { code: -32000, message: e.message }, id: null }) + "\n"
    );
    done();
  });
  req.write(body);
  req.end();
}

process.on("exit", () => { try { serverProc.kill(); } catch (_) {} });
process.on("SIGINT", () => { serverProc.kill(); process.exit(0); });
process.on("SIGTERM", () => { serverProc.kill(); process.exit(0); });
