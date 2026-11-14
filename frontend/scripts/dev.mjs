#!/usr/bin/env node
/**
 * Starts Vite on the first port that can actually be bound.
 *
 * On Windows, Hyper-V / WSL / Docker (the "winnat" service) permanently reserve
 * blocks of TCP ports. Binding inside one of those blocks fails with
 * `EACCES: permission denied` even though nothing is listening on the port, so
 * a hardcoded dev port such as 5173 can break after a reboot.
 *
 * The chosen port is written to `frontend/.dev-port` so start.bat (and anything
 * else) can discover it, then Vite is launched with `--strictPort` so the port
 * we picked is the port it uses.
 */
import { execFile, spawn } from 'node:child_process'
import { rmSync, writeFileSync } from 'node:fs'
import net from 'node:net'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)
const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const portFile = join(frontendDir, '.dev-port')
const viteBin = join(frontendDir, 'node_modules', 'vite', 'bin', 'vite.js')

const MAX_CANDIDATES = 200
const FIRST_PORT = 1024
const LAST_PORT = 65535

function parsePort(value) {
  const port = Number.parseInt(value ?? '', 10)
  return Number.isInteger(port) && port >= FIRST_PORT && port <= LAST_PORT ? port : null
}

/** Preferred port: --port/-p, then $PORT, then Vite's default (5173). */
function preferredPort(argv) {
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--port' || argv[i] === '-p') {
      const port = parsePort(argv[i + 1])
      if (port) return port
      i += 1
    } else if (argv[i].startsWith('--port=')) {
      const port = parsePort(argv[i].slice('--port='.length))
      if (port) return port
    }
  }
  return parsePort(process.env.PORT) ?? 5173
}

/** Ranges reported by `netsh ... show excludedportrange` (Windows only). */
async function reservedPortRanges() {
  if (process.platform !== 'win32') return []

  const ranges = []
  for (const family of ['ipv4', 'ipv6']) {
    try {
      const { stdout } = await execFileAsync(
        'netsh',
        ['interface', family, 'show', 'excludedportrange', 'protocol=tcp'],
        { windowsHide: true },
      )
      for (const line of stdout.split(/\r?\n/)) {
        const match = line.match(/^\s*(\d+)\s+(\d+)\s*\*?\s*$/)
        if (match) ranges.push([Number(match[1]), Number(match[2])])
      }
    } catch {
      // netsh unavailable/blocked: fall back to probing alone.
    }
  }
  return ranges
}

function inRanges(port, ranges) {
  return ranges.some(([start, end]) => port >= start && port <= end)
}

/**
 * True when the port can be bound on this address. Ports denied by policy
 * (EACCES) or already in use count as unavailable; unsupported address
 * families (EADDRNOTAVAIL, EAFNOSUPPORT) do not block the port.
 */
function canBind(port, host) {
  return new Promise((done) => {
    const server = net.createServer()
    server.unref()
    server.once('error', (error) => done(error.code !== 'EADDRINUSE' && error.code !== 'EACCES'))
    server.listen({ port, host }, () => server.close(() => done(true)))
  })
}

async function isAvailable(port) {
  const [ipv4, ipv6] = await Promise.all([canBind(port, '127.0.0.1'), canBind(port, '::1')])
  return ipv4 && ipv6
}

async function findPort(start) {
  const ranges = await reservedPortRanges()

  for (let offset = 0; offset < MAX_CANDIDATES; offset += 1) {
    const port = start + offset
    if (port > LAST_PORT) break
    // Cheap pre-filter: a reserved port always fails, no need to probe it.
    if (inRanges(port, ranges)) continue
    if (await isAvailable(port)) return { port, start, skippedReserved: offset > 0 }
  }

  throw new Error(
    `Could not find a free port between ${start} and ${Math.min(start + MAX_CANDIDATES - 1, LAST_PORT)}.`,
  )
}

function removePortFile() {
  try {
    rmSync(portFile, { force: true })
  } catch {
    // Nothing to clean up.
  }
}

/** Vite arguments other than the port, forwarded untouched. */
function passthroughArgs(argv) {
  const forwarded = []
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--port' || argv[i] === '-p') {
      i += 1
    } else if (!argv[i].startsWith('--port=')) {
      forwarded.push(argv[i])
    }
  }
  return forwarded
}

const start = preferredPort(process.argv.slice(2))
const { port } = await findPort(start)

writeFileSync(portFile, `${port}\n`, 'utf8')
process.on('exit', removePortFile)

if (port === start) {
  console.log(`\n  QwanEj dev server -> http://localhost:${port}\n`)
} else {
  console.log(
    `\n  QwanEj dev server -> http://localhost:${port}` +
      `\n  (port ${start} is unavailable on this machine, so the next free port was used)\n`,
  )
}

const child = spawn(
  process.execPath,
  [viteBin, '--port', String(port), '--strictPort', ...passthroughArgs(process.argv.slice(2))],
  { cwd: frontendDir, stdio: 'inherit' },
)

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal))
}

child.on('exit', (code) => {
  removePortFile()
  process.exit(code ?? 0)
})

child.on('error', (error) => {
  console.error(`Failed to start Vite: ${error.message}`)
  process.exit(1)
})
