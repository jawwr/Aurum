import { RANGE_PRESETS, type RangePreset } from "@/lib/dateRange";

/**
 * Describes one query parameter of a page (see hooks/usePageParams.ts): how
 * to read it from a string, how to write it back, and what to use when
 * neither the URL nor localStorage has a valid value.
 *
 * Serializing to "" means "no value" — such a parameter is left out of the
 * URL instead of showing up as `?category=`.
 */
export interface ParamSpec<T> {
  /** Raw string -> value, or `undefined` when the string is not valid. */
  parse(raw: string): T | undefined;
  serialize(value: T): string;
  /** Last resort, e.g. today's year/month. */
  defaultValue(): T;
}

export type ParamSchema = Record<string, ParamSpec<unknown>>;

export type ParamValues<S extends ParamSchema> = { [K in keyof S]: ReturnType<S[K]["defaultValue"]> };

export function intParam(fallback: () => number, min = 1, max = 1_000_000): ParamSpec<number> {
  return {
    parse(raw) {
      const parsed = Number(raw);
      return raw.trim() !== "" && Number.isInteger(parsed) && parsed >= min && parsed <= max ? parsed : undefined;
    },
    serialize: (value) => String(value),
    defaultValue: fallback,
  };
}

/** Positive integer id, or `null` when the filter is off (left out of the URL). */
export function optionalIntParam(): ParamSpec<number | null> {
  return {
    parse(raw) {
      if (raw === "") return null;
      const parsed = Number(raw);
      return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
    },
    serialize: (value) => (value === null ? "" : String(value)),
    defaultValue: () => null,
  };
}

export function boolParam(fallback: boolean): ParamSpec<boolean> {
  return {
    parse: (raw) => (raw === "true" ? true : raw === "false" ? false : undefined),
    serialize: (value) => String(value),
    defaultValue: () => fallback,
  };
}

/** Free text; empty string = off (left out of the URL). */
export function stringParam(): ParamSpec<string> {
  return {
    parse: (raw) => raw,
    serialize: (value) => value,
    defaultValue: () => "",
  };
}

export function enumParam<T extends string>(allowed: readonly T[], fallback: T): ParamSpec<T> {
  return {
    parse: (raw) => (allowed.includes(raw as T) ? (raw as T) : undefined),
    serialize: (value) => value,
    defaultValue: () => fallback,
  };
}

/** Current year unless the URL / localStorage say otherwise. */
export function yearParam(): ParamSpec<number> {
  return intParam(() => new Date().getFullYear(), 1, 9999);
}

/** Current month (1-12) unless the URL / localStorage say otherwise. */
export function monthParam(): ParamSpec<number> {
  return intParam(() => new Date().getMonth() + 1, 1, 12);
}

export function rangePresetParam(fallback: RangePreset): ParamSpec<RangePreset> {
  return enumParam<RangePreset>(RANGE_PRESETS, fallback);
}

/** Page number, 1-based. */
export function pageParam(): ParamSpec<number> {
  return intParam(() => 1, 1, 100_000);
}
