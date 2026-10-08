const http = require("http");
const fs = require("fs");
const path = require("path");

const root = __dirname;
const port = Number(process.env.PORT || 4173);
const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8"
};

function safePath(urlPath) {
  let decodedPath;
  try {
    decodedPath = decodeURIComponent(urlPath.split("?")[0]);
  } catch (_error) {
    return { status: 400, filePath: null };
  }
  const requestedPath = decodedPath === "/" ? "/index.html" : decodedPath;
  const resolved = path.resolve(root, `.${requestedPath}`);
  const relativePath = path.relative(root, resolved);
  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    return { status: 403, filePath: null };
  }
  return { status: 200, filePath: resolved };
}

const server = http.createServer((request, response) => {
  if (!['GET', 'HEAD'].includes(request.method || '')) {
    response.writeHead(405, { "Content-Type": "text/plain; charset=utf-8", "Allow": "GET, HEAD" });
    response.end("Method not allowed");
    return;
  }

  const result = safePath(request.url || "/");
  const filePath = result.filePath;
  if (!filePath) {
    response.writeHead(result.status, { "Content-Type": "text/plain; charset=utf-8" });
    response.end(result.status === 400 ? "Bad request" : "Forbidden");
    return;
  }

  fs.readFile(filePath, (error, contents) => {
    if (error) {
      response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      response.end("Not found");
      return;
    }

    response.writeHead(200, { "Content-Type": types[path.extname(filePath)] || "application/octet-stream" });
    response.end(request.method === "HEAD" ? undefined : contents);
  });
});

server.on("clientError", (_error, socket) => {
  if (socket.writable) {
    socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
  }
});

server.listen(port, () => {
  console.log(`FlowShock Climate ECG dashboard: http://localhost:${port}`);
});
