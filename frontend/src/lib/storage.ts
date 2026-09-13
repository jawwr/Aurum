export const AURUM_PREFIX_KEY = "aurum:";

export const storage = {
  get: <T>(key: string, defaultValue: T): T => {
    try {
      const fullKey = AURUM_PREFIX_KEY + key;
      const item = localStorage.getItem(fullKey);
      if (item === null) return defaultValue;
      
      // Try to parse JSON, if it fails, return as string (for simple primitives)
      try {
        return JSON.parse(item) as T;
      } catch {
        return item as unknown as T;
      }
    } catch (error) {
      console.error(`Error reading localStorage key ${key}:`, error);
      return defaultValue;
    }
  },
  set: <T>(key: string, value: T): void => {
    try {
      const fullKey = AURUM_PREFIX_KEY + key;
      const valueToStore = typeof value === "string" ? value : JSON.stringify(value);
      localStorage.setItem(fullKey, valueToStore);
    } catch (error) {
      console.error(`Error writing localStorage key ${key}:`, error);
    }
  },
  remove: (key: string): void => {
    localStorage.removeItem(AURUM_PREFIX_KEY + key);
  }
};
