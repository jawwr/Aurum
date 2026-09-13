import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams, useLocation } from "react-router-dom";
import { storage } from "@/lib/storage";

export function useQueryState<T extends string | number>(
  key: string,
  defaultValue: T,
  parser: (value: string) => T = (v) => {
    if (v === "" || v === "null" || v === "undefined") return defaultValue;
    const n = Number(v);
    return isNaN(n) ? (v as unknown as T) : (n as unknown as T);
  }
) {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  
  const getStorageKey = useCallback(() => {
    const path = location.pathname.split("/").filter(Boolean)[0] || "root";
    return `${path}:${key}`;
  }, [location.pathname, key]);

  const storageKey = getStorageKey();
  const stateRef = useRef<T>();

  const isEmpty = (value: T) => {
    if (value === defaultValue) return true;
    if (typeof value === "string" && value.trim() === "") return true;
    return false;
  };

  const [state, setState] = useState<T>(() => {
    const urlValue = searchParams.get(key);
    const initialValue = urlValue !== null 
      ? parser(urlValue) 
      : storage.get(storageKey, defaultValue);
    
    stateRef.current = initialValue;
    
    if (urlValue !== null && !isEmpty(initialValue)) {
      storage.set(storageKey, initialValue);
    }
    
    return initialValue;
  });

  useEffect(() => {
    const urlValue = searchParams.get(key);
    if (urlValue !== null) {
      const parsed = parser(urlValue);
      
      if (parsed !== stateRef.current) {
        stateRef.current = parsed;
        setState(parsed);
        if (!isEmpty(parsed)) {
          storage.set(storageKey, parsed);
        } else {
          storage.remove(storageKey);
        }
      }
    }
  }, [searchParams, key, storageKey]);

  const updateState = useCallback((newValue: T | ((prev: T) => T)) => {
    setState((prev) => {
      const value = typeof newValue === "function" ? (newValue as Function)(prev) : newValue;
      
      stateRef.current = value;

      if (!isEmpty(value)) {
        storage.set(storageKey, value);
      } else {
        storage.remove(storageKey);
      }
      
      const currentParams = new URLSearchParams(window.location.search);
      if (!isEmpty(value)) {
        currentParams.set(key, String(value));
      } else {
        currentParams.delete(key);
      }
      setSearchParams(currentParams, { replace: true });
      
      return value;
    });
  }, [key, storageKey, setSearchParams]);

  useEffect(() => {
    const urlValue = searchParams.get(key);
    
    // If the value is in state but missing from URL, add it immediately
    // This handles the "initial load from storage" case.
    if (urlValue === null && !isEmpty(state)) {
      const currentParams = new URLSearchParams(window.location.search);
      currentParams.set(key, String(state));
      setSearchParams(currentParams, { replace: true });
    } 
    // If the URL has a value but it's "empty", remove it to keep URL clean.
    else if (urlValue !== null && isEmpty(parser(urlValue))) {
      const currentParams = new URLSearchParams(window.location.search);
      currentParams.delete(key);
      setSearchParams(currentParams, { replace: true });
    }
  }, [key, setSearchParams, parser]); 
  // Note: 'state' is deliberately omitted to avoid the flicker loop.
  // We rely on the initial render to trigger this once.

  // We remove the automatic sync-to-URL effect entirely.
  // The state is already initialized from URL/Storage in useState.
  // Any subsequent changes are handled by updateState.
  // This prevents the "initial load -> effect -> setSearchParams -> re-render" cycle.

  return [state, updateState] as const;
}
