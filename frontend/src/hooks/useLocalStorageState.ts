import { useState, useEffect } from "react";

const AURUM_PREFIX_KEY = "aurum:";

export function useLocalStorageState<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const storedValue = localStorage.getItem(AURUM_PREFIX_KEY + key);
      if (storedValue !== null) {
        return JSON.parse(storedValue);
      }
    } catch (error) {
      console.error(`Error reading localStorage key "${key}":`, error);
    }
    return initialValue;
  });

  useEffect(() => {
    try {
      localStorage.setItem(AURUM_PREFIX_KEY + key, JSON.stringify(value));
    } catch (error) {
      console.error(`Error writing localStorage key "${key}":`, error);
    }
  }, [AURUM_PREFIX_KEY + key, value]);

  return [value, setValue] as const;
}

