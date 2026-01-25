/**
 * Space-Lua Runner for silverbullet-rag
 *
 * This script executes space-lua code blocks from CONFIG.md
 * and returns the captured configuration values.
 *
 * Usage:
 *   echo '{"luaCode": "config.set(\"key\", \"value\")"}' | deno run space_lua_runner.ts
 *
 * Output:
 *   {"success": true, "config": {"key": "value"}}
 */

import { luaBuildStandardEnv } from "../silverbullet/client/space_lua/stdlib.ts";
import { parse } from "../silverbullet/client/space_lua/parse.ts";
import { evalStatement } from "../silverbullet/client/space_lua/eval.ts";
import {
  LuaBuiltinFunction,
  LuaEnv,
  LuaStackFrame,
  LuaTable,
  luaValueToJS,
} from "../silverbullet/client/space_lua/runtime.ts";

/**
 * Simple config storage that mimics SilverBullet's Config class
 * but without the Ajv JSON schema validation dependency
 */
class SimpleConfig {
  public values: Record<string, unknown> = {};

  get<T>(path: string | string[], defaultValue: T): T {
    if (typeof path === "string") {
      path = path.split(".");
    }
    let current: unknown = this.values;
    for (const part of path) {
      if (current === null || current === undefined || typeof current !== "object") {
        return defaultValue;
      }
      current = (current as Record<string, unknown>)[part];
    }
    return (current ?? defaultValue) as T;
  }

  set<T>(
    keyOrValues: string | string[] | Record<string, unknown>,
    value?: T,
  ): void {
    if (typeof keyOrValues === "string") {
      keyOrValues = keyOrValues.split(".");
    }
    if (Array.isArray(keyOrValues)) {
      const path = keyOrValues as string[];
      let current = this.values;
      for (let i = 0; i < path.length - 1; i++) {
        const part = path[i];
        if (!(part in current) || typeof current[part] !== "object") {
          current[part] = {};
        }
        current = current[part] as Record<string, unknown>;
      }
      current[path[path.length - 1]] = value;
    } else {
      // Handle object form: config.set({ key: value, ... })
      for (const [key, val] of Object.entries(keyOrValues)) {
        this.set(key, val);
      }
    }
  }

  insert<T>(key: string | string[], value: T): void {
    if (typeof key === "string") {
      key = key.split(".");
    }
    const existing = this.get(key, [] as unknown[]);
    if (!Array.isArray(existing)) {
      this.set(key, [value]);
    } else {
      existing.push(value);
      this.set(key, existing);
    }
  }

  has(path: string | string[]): boolean {
    if (typeof path === "string") {
      path = path.split(".");
    }
    let current: unknown = this.values;
    for (const part of path) {
      if (current === null || current === undefined || typeof current !== "object") {
        return false;
      }
      if (!(part in (current as Record<string, unknown>))) {
        return false;
      }
      current = (current as Record<string, unknown>)[part];
    }
    return true;
  }
}

/**
 * Create config syscalls that capture config.set() calls
 */
function createConfigSyscalls(config: SimpleConfig) {
  return {
    "config.get": (_ctx: unknown, path: string, defaultValue: unknown) => {
      return config.get(path, defaultValue);
    },
    "config.set": (
      _ctx: unknown,
      keyOrValues: string | string[] | Record<string, unknown>,
      value?: unknown,
    ) => {
      config.set(keyOrValues, value);
    },
    "config.insert": (_ctx: unknown, key: string | string[], value: unknown) => {
      config.insert(key, value);
    },
    "config.has": (_ctx: unknown, path: string) => {
      return config.has(path);
    },
    "config.define": (_ctx: unknown, _key: string, _schema: unknown) => {
      // Schema validation is skipped in this minimal implementation
    },
    "config.getValues": () => {
      return config.values;
    },
    "config.getSchemas": () => {
      return {};
    },
  };
}

/**
 * Expose syscalls to Lua environment (simplified version of exposeSyscalls)
 */
function exposeSyscalls(
  env: LuaEnv,
  syscalls: Record<string, (...args: unknown[]) => unknown>,
) {
  const nativeFs = new LuaStackFrame(env, null);

  for (const [syscallName, callback] of Object.entries(syscalls)) {
    const [ns, fn] = syscallName.split(".");
    if (!env.has(ns)) {
      env.set(ns, new LuaTable(), nativeFs);
    }
    const luaFn = new LuaBuiltinFunction((_sf, ...args) => {
      // Convert Lua values to JS before calling syscall
      const jsArgs = args.map((arg) => {
        if (arg && typeof arg === "object" && "toJS" in arg) {
          return luaValueToJS(arg, _sf);
        }
        return arg;
      });
      return callback({}, ...jsArgs);
    });
    (env.get(ns, nativeFs) as LuaTable).set(fn, luaFn, nativeFs);
  }
}

/**
 * Execute space-lua code and return captured config
 */
async function executeSpaceLua(luaCode: string): Promise<{ success: boolean; config?: Record<string, unknown>; error?: string }> {
  const config = new SimpleConfig();

  // Build standard Lua environment
  const rootEnv = luaBuildStandardEnv();

  // Expose config syscalls
  const syscalls = createConfigSyscalls(config);
  exposeSyscalls(rootEnv, syscalls);

  try {
    // Parse the Lua code
    const chunk = parse(luaCode, {});
    const sf = LuaStackFrame.createWithGlobalEnv(rootEnv, chunk.ctx);

    // Execute each statement
    const localEnv = new LuaEnv(rootEnv);
    for (const statement of chunk.statements) {
      try {
        await evalStatement(statement, localEnv, sf);
      } catch (e: unknown) {
        // Log but continue (matching boot_config.ts behavior)
        const errorMsg = e instanceof Error ? e.message : String(e);
        console.error(
          `Statement errored during execution, ignoring:`,
          luaCode.slice(statement.ctx.from, statement.ctx.to),
          "Error:",
          errorMsg,
        );
      }
    }

    return { success: true, config: config.values };
  } catch (e: unknown) {
    const errorMsg = e instanceof Error ? e.message : String(e);
    return { success: false, error: errorMsg };
  }
}

/**
 * Read JSON input from stdin
 */
async function readStdin(): Promise<string> {
  const decoder = new TextDecoder();
  const chunks: Uint8Array[] = [];

  for await (const chunk of Deno.stdin.readable) {
    chunks.push(chunk);
  }

  const totalLength = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }

  return decoder.decode(result);
}

// Main entry point
async function main() {
  try {
    const inputJson = await readStdin();
    const input = JSON.parse(inputJson) as { luaCode: string };

    if (!input.luaCode) {
      console.log(JSON.stringify({ success: false, error: "Missing luaCode field" }));
      Deno.exit(1);
    }

    const result = await executeSpaceLua(input.luaCode);
    console.log(JSON.stringify(result));
  } catch (e: unknown) {
    const errorMsg = e instanceof Error ? e.message : String(e);
    console.log(JSON.stringify({ success: false, error: `Failed to parse input: ${errorMsg}` }));
    Deno.exit(1);
  }
}

main();
