import { useCallback, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import type { ParamSchema, ParamValues } from "@/lib/pageParams";

const STORAGE_PREFIX = "aurum:page-params:";

function readStored(storageKey: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(storageKey) ?? "null");
    return parsed !== null && typeof parsed === "object" ? (parsed as Record<string, unknown>) : {};
  } catch {
    // storage unavailable or corrupted JSON — behave as if nothing was saved
    return {};
  }
}

function writeStored(storageKey: string, serialized: Record<string, string>) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(serialized));
  } catch {
    // storage unavailable — the URL still carries the state
  }
}

/**
 * The URL is the main source. If it carries at least one of the page's
 * parameters it is treated as a complete snapshot (a deep link like
 * `/transactions?year=2024&month=3` must not inherit a stale page number or
 * filter from a previous visit): missing/invalid parameters fall back to
 * their defaults. Only a URL with none of them falls back to localStorage
 * (and, per parameter, to defaults for anything missing or invalid there).
 */
function resolveValues<S extends ParamSchema>(
  schema: S,
  searchParams: URLSearchParams,
  stored: Record<string, unknown>
): ParamValues<S> {
  const names = Object.keys(schema);
  const urlHasParams = names.some((name) => searchParams.has(name));
  const result: Record<string, unknown> = {};
  for (const name of names) {
    const spec = schema[name];
    let value: unknown;
    if (urlHasParams) {
      const raw = searchParams.get(name);
      value = raw !== null ? spec.parse(raw) : undefined;
    } else {
      const raw = stored[name];
      value = typeof raw === "string" ? spec.parse(raw) : undefined;
    }
    result[name] = value !== undefined ? value : spec.defaultValue();
  }
  return result as ParamValues<S>;
}

function serializeValues<S extends ParamSchema>(schema: S, values: ParamValues<S>): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [name, spec] of Object.entries(schema)) {
    result[name] = spec.serialize((values as Record<string, unknown>)[name]);
  }
  return result;
}

/** Copies `base` (keeping query params this page doesn't own) and applies the page's values on top. */
function buildSearchParams<S extends ParamSchema>(
  base: URLSearchParams,
  schema: S,
  values: ParamValues<S>
): URLSearchParams {
  const next = new URLSearchParams(base);
  for (const [name, serialized] of Object.entries(serializeValues(schema, values))) {
    if (serialized === "") next.delete(name);
    else next.set(name, serialized);
  }
  return next;
}

type Patch<S extends ParamSchema> = Partial<ParamValues<S>> | ((prev: ParamValues<S>) => Partial<ParamValues<S>>);

/**
 * Keeps a page's request parameters in the URL query *and* in localStorage.
 *
 * Priority: the URL; if it has none of the page's parameters, the values saved
 * in localStorage for this page; for anything still missing, the schema's
 * default (e.g. today's date). Every schema should contain at least one
 * parameter that is always serialized (year, range, ...), so that once the
 * URL is filled in it can't be mistaken for "empty". The resolved values are computed during render, so the very first
 * request already uses them; an effect then writes them back to the URL
 * (replacing the history entry, no extra back-button stop) and to
 * localStorage. `setParams` updates both again, so paging/filtering survives
 * leaving the page and coming back.
 *
 * `schema` must be a stable reference — declare it at module level.
 */
export function usePageParams<S extends ParamSchema>(pageKey: string, schema: S) {
  const storageKey = STORAGE_PREFIX + pageKey;
  const [searchParams, setSearchParams] = useSearchParams();

  const values = useMemo(
    () => resolveValues(schema, searchParams, readStored(storageKey)),
    [schema, searchParams, storageKey]
  );

  // Latest state for `setParams`, so several calls in one tick (or a call
  // from a stale closure such as a debounce timer) build on each other
  // instead of on an outdated render.
  const latest = useRef({ values, searchParams });
  latest.current = { values, searchParams };
  const setSearchParamsRef = useRef(setSearchParams);
  setSearchParamsRef.current = setSearchParams;

  useEffect(() => {
    writeStored(storageKey, serializeValues(schema, values));
    const canonical = buildSearchParams(searchParams, schema, values);
    if (canonical.toString() !== searchParams.toString()) {
      setSearchParamsRef.current(canonical, { replace: true });
    }
  }, [schema, storageKey, values, searchParams]);

  const setParams = useCallback(
    (patch: Patch<S>) => {
      const resolved = typeof patch === "function" ? patch(latest.current.values) : patch;
      if (Object.keys(resolved).length === 0) return;
      const nextValues = { ...latest.current.values, ...resolved } as ParamValues<S>;
      const nextSearchParams = buildSearchParams(latest.current.searchParams, schema, nextValues);
      latest.current = { values: nextValues, searchParams: nextSearchParams };
      writeStored(storageKey, serializeValues(schema, nextValues));
      setSearchParamsRef.current(nextSearchParams, { replace: true });
    },
    [schema, storageKey]
  );

  return [values, setParams] as const;
}
